#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地自检：不依赖微信、不依赖真实 API key。

覆盖：
* ApiClient 的请求/响应/401/5xx 重试；
* 群消息前缀剥离、@ 触发、回复清理、分段；
* 配置合并。

运行：
    python selftest_local.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import api_bridge  # noqa: E402


class MockHandler(BaseHTTPRequestHandler):
    calls = 0
    fail_first = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        MockHandler.calls += 1
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {}

        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer good-key"):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"bad key"}')
            return

        if MockHandler.calls <= MockHandler.fail_first:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":"boom"}')
            return

        content = "OK"
        messages = payload.get("messages") or []
        if messages and "ECHO" in str(messages[-1].get("content", "")):
            content = "echo:" + str(messages[-1]["content"])

        body = json.dumps({
            "choices": [{"message": {"content": content}}],
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_api(base_url: str, key: str = "good-key", retries: int = 1) -> api_bridge.ApiClient:
    os.environ["DEEPSEEK_API_KEY"] = key
    cfg = {
        "api": {
            "base_url": base_url,
            "model": "mock",
            "api_key_env": "DEEPSEEK_API_KEY",
            "timeout": 10,
            "max_tokens": 100,
            "temperature": 0.0,
            "retries": retries,
        }
    }
    return api_bridge.ApiClient(cfg)


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"[PASS] {name}")
    except Exception as exc:
        print(f"[FAIL] {name}: {exc!r}")
        raise


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    print(f"mock API: {base}")

    try:
        check("API 正常回复", lambda: (
            None if make_api(base).chat([{"role": "user", "content": "hi"}]) == "OK"
            else (_ for _ in ()).throw(AssertionError("reply != OK"))
        ))

        def bad_key():
            try:
                make_api(base, key="bad-key").chat([{"role": "user", "content": "hi"}])
            except api_bridge.BridgeError as exc:
                if "401" not in str(exc):
                    raise AssertionError(f"unexpected: {exc}")
                return
            raise AssertionError("should fail with 401")

        check("API 401 报错", bad_key)

        MockHandler.calls = 0
        MockHandler.fail_first = 1

        def retry():
            reply = make_api(base, retries=1).chat([{"role": "user", "content": "hi"}])
            if reply != "OK":
                raise AssertionError(reply)
            if MockHandler.calls < 2:
                raise AssertionError(f"expected retry, calls={MockHandler.calls}")

        check("API 500 重试", retry)
        MockHandler.fail_first = 0

        check("群前缀剥离", lambda: (
            None if api_bridge.strip_group_prefix("wxid_abc123:\n你好") == ("wxid_abc123", "你好")
            else (_ for _ in ()).throw(AssertionError("prefix"))
        ))

        cfg = api_bridge.load_config(api_bridge.ROOT / "config.example.json")
        cfg["bot"]["roast_exclude"] = ["示例保护成员"]
        cfg["bot"]["roast_exclude_ids"] = ["wxid_example_member_b"]
        bot = api_bridge.Bot(cfg, api=None)
        bot.self_nick = "小助手"
        bot.cfg["bot"]["bot_aliases"] = ["小助手"]
        g = {"_username": "1@chatroom", "_display": "测试群", "aliases": ["小助手"]}

        def trigger():
            assert bot._triggered(g, "@小助手 你好") == "mention"
            assert bot._triggered(g, "示例同名成员 在吗") == ""
            assert bot._triggered(g, "你好") == ""
            assert bot._speaker_triggered("", "示例成员甲") is False
            assert bot._speaker_triggered("wxid_example_member_a", "改了的昵称") is False
            assert bot._mentions_banter_target("阿甲今天真菜") is True
            assert bot._mentions_banter_target("示例同名成员在吗") is False
            assert bot._keyword_reply("轮了") == ""

        check("@ / 名字 / 轮了 / 阿甲触发", trigger)

        def roast():
            bot.recent[g["_username"]] = []
            normal = bot._build_messages(g, "示例成员甲", "在吗")[-1]["content"]
            excluded = bot._build_messages(g, "示例保护成员", "在吗")[-1]["content"]
            ahao = bot._build_messages(g, "路人", "阿甲今天真菜", "ahao")[-1]["content"]
            by_id = bot._build_messages(
                g, "改了的昵称", "在吗", "speaker", "wxid_example_member_a")[-1]["content"]
            excluded_id = bot._build_messages(
                g, "改了的昵称", "在吗", "mention", "wxid_example_member_b")[-1]["content"]
            assert "本轮不针对示例群友" in normal, normal
            assert "不要怼他" in excluded, excluded
            assert "本轮不针对示例群友" in ahao, ahao
            assert "本轮不针对示例群友" in by_id, by_id
            assert "不要怼他" in excluded_id, excluded_id

        check("怼人白名单/例外/阿甲", roast)

        def clean():
            text = bot._clean_reply("**你好**\n```python\nprint(1)\n```")
            assert "**" not in text and "```" not in text, text

        check("回复清理", clean)

        def split():
            parts = bot._split_reply("a" * 25, 10)
            assert len(parts) == 3 and all(len(p) <= 10 for p in parts), parts

        check("长回复分段", split)

        print("\n全部本地自检通过。")
        return 0
    finally:
        server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
