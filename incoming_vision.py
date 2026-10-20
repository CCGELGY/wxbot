"""Bounded, sender/group-scoped image context. No GUI or unsolicited image uploads."""
from collections import OrderedDict, deque
from pathlib import Path
import base64
import io
import re
import tempfile
import threading
import time
import warnings
import xml.etree.ElementTree as ET

IMAGE_REQUEST = re.compile(r'图|照片|截图|画面|识别|看[看下]|这[是啥]|写的|读一下|翻译|几只|什么颜色')
COMPARE = re.compile(r'对比|比较|两张|这几张|这两|分别|区别')


def image_reference(msg):
    return {k: msg[k] for k in ('local_id', 'sort_seq', 'shard', 'server_id') if msg.get(k) is not None}


def quoted_image(msg):
    """Only a real quote of an image, resolved by server ID in the current group."""
    content = msg.get('content')
    if not isinstance(content, str) or len(content) > 50000 or '<!DOCTYPE' in content.upper():
        return None
    if '<refermsg' not in content:
        return None
    try:
        start = content.find('<msg')
        if start < 0:
            start = content.find('<appmsg')
        tree = ET.fromstring(content[start:])
        app = tree if tree.tag == 'appmsg' else tree.find('.//appmsg')
        if app is None or app.findtext('type') != '57':
            return None
        ref = app.find('refermsg')
        if ref is None or ref.findtext('type') != '3':
            return None
        server = ref.findtext('svrid', '')
        if not server.isdigit() or int(server) <= 0:
            return None
        return {'server_id': int(server), '_quoted_image': True}
    except (ET.ParseError, ValueError):
        return None


def encode_image(path, config=None):
    """Validate, strip metadata, bound dimensions and send real pixels, never a local path."""
    from PIL import Image, ImageOps
    config = config or {}
    path = Path(path)
    if path.stat().st_size > int(config.get('max_source_bytes', 32 * 1024 * 1024)):
        raise ValueError('image file too large')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(path) as source:
            if source.format not in ('JPEG', 'PNG', 'GIF', 'WEBP'):
                raise ValueError('unsupported image format')
            if source.width * source.height > int(config.get('max_pixels', 24000000)):
                raise ValueError('image pixel limit exceeded')
            source.seek(0)
            frame = ImageOps.exif_transpose(source).convert('RGBA')
            frame.thumbnail((1600, 1600))
            canvas = Image.new('RGB', frame.size, 'white')
            canvas.paste(frame, mask=frame.getchannel('A'))
            out = io.BytesIO()
            canvas.save(out, format='JPEG', quality=85)
    data = out.getvalue()
    if len(data) > 2 * 1024 * 1024:
        raise ValueError('encoded image exceeds limit')
    return {'type': 'image_url', 'image_url': {
        'url': 'data:image/jpeg;base64,' + base64.b64encode(data).decode('ascii')}}


class IncomingVision:
    def __init__(self, config=None):
        self.config = config or {}
        self.enabled = bool(self.config.get('enabled', True))
        self.ttl = min(600, max(10, float(self.config.get('context_sec', 120))))
        self.limit = min(2, max(1, int(self.config.get('max_images', 2))))
        self.images = OrderedDict()
        self.requests = OrderedDict()
        self.lock = threading.RLock()
        self.media_lock = threading.Lock()

    def remember(self, group, sender, msg, now=None):
        if not self.enabled or not sender or msg.get('local_id') is None:
            return
        now = time.monotonic() if now is None else now
        with self.lock:
            key = (group, sender)
            rows = self.images.setdefault(key, deque(maxlen=8))
            ref = image_reference(msg)
            identity = (ref.get('shard'), ref.get('local_id'), ref.get('sort_seq'))
            if any((r[1].get('shard'), r[1].get('local_id'), r[1].get('sort_seq')) == identity for r in rows):
                return
            rows.append((now, ref))
            self.images.move_to_end(key)
            while len(self.images) > 128:
                self.images.popitem(last=False)

    def expect(self, group, sender, text, now=None):
        if not self.enabled or not IMAGE_REQUEST.search(text):
            return
        now = time.monotonic() if now is None else now
        with self.lock:
            key = (group, sender)
            self.requests[key] = (now, text)
            self.requests.move_to_end(key)
            while len(self.requests) > 128:
                self.requests.popitem(last=False)

    def pending(self, group, sender, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            row = self.requests.get((group, sender))
            return row[1] if row and 0 <= now - row[0] <= self.ttl else ''

    def cancel(self, group, sender):
        with self.lock:
            self.requests.pop((group, sender), None)

    def select(self, group, sender, text, attached=(), now=None):
        if not self.enabled:
            return []
        now = time.monotonic() if now is None else now
        limit = self.limit if COMPARE.search(text) else 1
        explicit = list(attached or [])
        with self.lock:
            if not explicit and IMAGE_REQUEST.search(text):
                explicit = [r for stamp, r in self.images.get((group, sender), ())
                            if 0 <= now - stamp <= self.ttl]
        # Explicit incoming/quoted images always beat unrelated recent images.
        unique = OrderedDict()
        for ref in explicit:
            key = (ref.get('shard'), ref.get('local_id'), ref.get('sort_seq'), ref.get('server_id'))
            unique[key] = dict(ref)
        return list(unique.values())[-limit:]

    def blocks(self, db, group, references):
        """Read only local WeChat cache. Preserve shard identity; no download-original GUI."""
        from wechatauto import MediaDownloader
        results = []
        with self.media_lock, tempfile.TemporaryDirectory(prefix='wxbot-vision-') as folder:
            media = MediaDownloader(db, save_dir=folder)
            for ref in references[:self.limit]:
                if ref.get('_quoted_image'):
                    candidates = [r for r in db.get_image_rows(group, limit=100)
                                  if str(r.get('server_id')) == str(ref.get('server_id'))]
                    if len(candidates) != 1:
                        continue
                    ref = candidates[0]
                if ref.get('local_id') is None or not ref.get('shard'):
                    continue  # Same local_id can exist in more than one shard.
                path = None
                for attempt in range(3):
                    path = media.download_image(group, int(ref['local_id']),
                        save_dir=folder, tier='best', shard=ref['shard'])
                    if path:
                        break
                    if attempt < 2:
                        time.sleep(.35)
                if path:
                    path = Path(path).resolve()
                    if not path.is_relative_to(Path(folder).resolve()):
                        raise ValueError('unexpected media output path')
                    results.append(encode_image(path, self.config))
        return results
