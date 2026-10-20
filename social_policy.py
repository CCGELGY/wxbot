"""Conversation routing and private sticker commands; no network or desktop actions."""
import re
import time
import xml.etree.ElementTree as ET

STICKER = re.compile(r'\[\[sticker:([^\]\r\n]{1,100})\]\]', re.I)


def split_action(reply):
    if '<SKIP>' in (reply or '').upper():
        return '', None
    matches = STICKER.findall(reply or '')
    text = STICKER.sub('', reply or '').strip().strip('|').strip()
    text = re.sub(r'\[\[search_sticker:[^\]\r\n]*\]\]', '', text, flags=re.I).strip()
    text = re.sub(r'\[\[search_sticker:[^\r\n]*$', '', text, flags=re.I).strip()
    text = re.sub(r'\[\[sticker:[^\r\n]*$', '', text, flags=re.I).strip().strip('|').strip()
    return text, matches[0].strip() if matches else None


def normalize_message(msg, self_username):
    """Return chat text, quote destination (self/other/none). No arbitrary XML cards."""
    content = str(msg.get('content') or '')
    if msg.get('type') in ('文本', 'text'):
        return content, 'none'
    if '<appmsg' not in content or '<refermsg' not in content or '<!DOCTYPE' in content.upper():
        return '', 'none'
    try:
        # Group messages can prepend wxid:\n before XML.
        start = content.find('<msg')
        if start < 0:
            start = content.find('<appmsg')
        tree = ET.fromstring(content[start:])
        app = tree if tree.tag == 'appmsg' else tree.find('.//appmsg')
        if app is None or app.findtext('type') != '57':
            return '', 'none'
        ref = app.find('refermsg')
        source = ref.findtext('fromusr', '') if ref is not None else ''
        title = app.findtext('title', '')
        quoted = ref.findtext('content', '') if ref is not None else ''
        prefix = content[:start] if content[:start].strip().startswith('wxid_') else ''
        return prefix + title + '\n[引用：' + quoted[:200] + ']', ('self' if source and source == self_username else 'other')
    except (ET.ParseError, ValueError):
        return '', 'none'


class Conversations:
    def __init__(self, seconds=150):
        self.seconds = seconds
        self.sessions = {}

    def open(self, group, user, now=None):
        if not user:
            return
        now = time.time() if now is None else now
        self.sessions = {k:v for k,v in self.sessions.items() if v > now}
        self.sessions[(group, user)] = now + self.seconds

    def follows(self, group, user, text, quote='none', now=None):
        now = time.time() if now is None else now
        if quote == 'self':
            return True
        if quote == 'other' or re.search(r'@[^\s]+', text):
            return False
        if re.fullmatch(r'\s*(不聊了|先不聊了|晚安|拜拜|下了|先走了)[！!。~～\s]*', text):
            self.sessions.pop((group, user), None)
            return False
        return bool(user) and self.sessions.get((group, user), 0) > now
