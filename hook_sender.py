"""Loopback-only WeChat-Hook transport. Never drives the desktop or retries sends."""
from __future__ import annotations

import ipaddress
import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import requests

log = logging.getLogger("api-bridge")


def open_hook_database(config):
    """Pin database reads to the Hook account, not an inactive account's file mtime."""
    from wechatauto import WeChatDB
    from wechatauto.db import auto_detect_db_dir
    hook = HookSender(config)
    try:
        hook.health()
        response = hook.session.post(hook.base_url + '/GetSelfProfile', json={}, timeout=(2, 4))
        response.raise_for_status()
        username = str(response.json().get('wxid') or '')
    finally:
        hook.session.close()
    if not re.fullmatch(r'wxid_[A-Za-z0-9_]+', username):
        raise RuntimeError('Hook account identity unavailable; log in to WeChat first')
    base = auto_detect_db_dir()
    if not base:
        raise RuntimeError('WeChat database directory unavailable')
    candidates = [p for p in Path(base).iterdir() if p.is_dir()
                  and (p / 'db_storage').is_dir()
                  and re.sub(r'_\w{4}$', '', p.name) == username]
    if len(candidates) != 1:
        raise RuntimeError('Hook account does not uniquely match a local database')
    db = WeChatDB(db_dir=str(base), account=candidates[0].name)
    if db.get_self_info().get('username') != username:
        raise RuntimeError('Hook/database account mismatch; stopped before listening')
    return db


@dataclass
class SendResult:
    is_success: bool
    message: str
    elapsed_ms: float = 0
    verified: bool = False


class HookSender:
    def __init__(self, config, db=None, allowed_targets=None):
        self.config = config
        self.db = db
        self.allowed_targets = set(allowed_targets or [])
        self.base_url = str(config.get("base_url", "http://[::1]:30001")).rstrip("/")
        url = urlsplit(self.base_url)
        if url.scheme != "http" or not url.hostname or not ipaddress.ip_address(url.hostname).is_loopback:
            raise ValueError("Hook endpoint must be a numeric loopback HTTP address")
        if url.username or url.password or url.path or url.query or url.fragment:
            raise ValueError("Invalid Hook endpoint")
        self.timeout = float(config.get("timeout", 12))
        self.verify_timeout = float(config.get("verify_timeout", 8))
        self.min_interval = float(config.get("min_interval", 0.4))
        self.session = requests.Session()
        self.session.trust_env = False
        self.lock = threading.Lock()
        self.last_send = 0.0

    def health(self):
        response = self.session.get(self.base_url + "/QueryDB/status", timeout=(2, 4))
        response.raise_for_status()
        data = response.json()
        # Upstream main never updates g_IsLogin; use the loaded-module status.
        # The bridge independently requires a readable, logged-in account DB.
        if not int(data.get("hWeixin", 0)):
            raise RuntimeError("Hook has not initialized Weixin.dll")
        self._require_account()
        return data

    def _require_account(self):
        expected = str(self.config.get('account_username') or '')
        if not expected:
            return
        response = self.session.post(self.base_url + '/GetSelfProfile', json={}, timeout=(2, 4))
        response.raise_for_status()
        if response.json().get('wxid') != expected:
            raise RuntimeError('Hook account differs from the configured account; sending refused')

    @staticmethod
    def _identity(row):
        return (str(row.get("shard", "")), int(row.get("local_id") or 0), int(row.get("sort_seq") or 0))

    def _baseline(self, who):
        if self.db is None:
            raise RuntimeError("Database is required for verified sends")
        return {self._identity(row) for row in self.db.get_messages(who, limit=30)}

    def _verify(self, who, before, text=None):
        deadline = time.monotonic() + self.verify_timeout
        while time.monotonic() < deadline:
            for row in self.db.get_messages(who, limit=30):
                if self._identity(row) in before or row.get("sender_id") != 2:
                    continue
                if text is not None and row.get("content") == text:
                    return True
                if text is None and row.get("type") == "图片":
                    return True
            time.sleep(0.2)
        return False

    def _send(self, route, payload, who, verify, text=None):
        if not who or (self.allowed_targets and who not in self.allowed_targets):
            return SendResult(False, "Target is not in the configured allowlist")
        # Entire baseline/send/verification is serialized to correlate image rows.
        with self.lock:
            started = time.monotonic()
            try:
                self._require_account()
                before = self._baseline(who) if verify else None
                remaining = self.min_interval - (time.monotonic() - self.last_send)
                if remaining > 0:
                    time.sleep(remaining)
                self.last_send = time.monotonic()
                response = self.session.post(self.base_url + route, json=payload,
                                             timeout=(2, self.timeout))
                response.raise_for_status()
                body = response.json()
                if body.get("ret") != 0:
                    return SendResult(False, "Hook rejected send: " + str(body.get("retmsg", body.get("msg", body.get("ret")))))
                verified = self._verify(who, before, text) if verify else False
                elapsed = (time.monotonic() - started) * 1000
                if verify and not verified:
                    return SendResult(False, "Hook accepted, database confirmation timed out; NOT retried", elapsed)
                log.info("Hook %s %.0fms, %s", route, elapsed,
                         "database-confirmed" if verified else "accepted (delivery unconfirmed)")
                return SendResult(True, "database-confirmed" if verified else "accepted (delivery unconfirmed)", elapsed, verified)
            except Exception as exc:
                return SendResult(False, "Hook send uncertain/failed; NOT retried: " + str(exc),
                                  (time.monotonic() - started) * 1000)

    def send_msg(self, text, who=None, verify=False):
        if not isinstance(text, str) or not text.strip():
            return SendResult(False, "Empty text")
        return self._send("/SendTextMsg", {"wxidorgid": who, "msg": text}, who, verify, text)

    def send_image(self, path, who=None, verify=False):
        file = Path(path).resolve()
        if not file.is_file():
            return SendResult(False, "Image file does not exist")
        return self._send("/SendImgMsg", {"wxidorgid": who, "path": str(file)}, who, verify)
