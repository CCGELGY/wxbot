"""Offline transport contracts; no WeChat access, no real external sends."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hook_sender import HookSender


class Handler(BaseHTTPRequestHandler):
    calls = []
    ret = 0
    after_send = None

    def log_message(self, *args):
        pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).calls.append((self.path, data))
        if self.after_send:
            self.after_send()
        body = json.dumps({'ret': self.ret}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Handler.calls = []
        Handler.ret = 0
        Handler.after_send = None
        self.sender = HookSender({'base_url': 'http://127.0.0.1:' + str(self.server.server_port),
                                  'min_interval': 0, 'verify_timeout': .05}, allowed_targets={'group@chatroom'})

    def tearDown(self):
        self.sender.session.close()

    def test_payload_uses_group_id(self):
        result = self.sender.send_msg('hello', 'group@chatroom')
        self.assertTrue(result.is_success)
        self.assertFalse(result.verified)
        self.assertEqual(Handler.calls, [('/SendTextMsg', {'wxidorgid': 'group@chatroom', 'msg': 'hello'})])

    def test_other_target_never_sent(self):
        self.assertFalse(self.sender.send_msg('hello', 'other').is_success)
        self.assertEqual(Handler.calls, [])

    def test_rejection_is_not_retried(self):
        Handler.ret = 1
        self.assertFalse(self.sender.send_msg('hello', 'group@chatroom').is_success)
        self.assertEqual(len(Handler.calls), 1)

    def test_old_same_message_does_not_confirm(self):
        row = {'local_id': 1, 'sort_seq': 1, 'sender_id': 2, 'content': 'hello'}
        self.sender.db = type('DB', (), {'get_messages': lambda *args, **kw: [row]})()
        self.assertFalse(self.sender.send_msg('hello', 'group@chatroom', verify=True).is_success)
        self.assertEqual(len(Handler.calls), 1)

    def test_new_row_confirms(self):
        rows = []
        self.sender.db = type('DB', (), {'get_messages': lambda *args, **kw: list(rows)})()
        Handler.after_send = staticmethod(lambda: rows.append({'local_id': 2, 'sort_seq': 2,
                                                              'sender_id': 2, 'content': 'hello'}))
        self.assertTrue(self.sender.send_msg('hello', 'group@chatroom', verify=True).verified)

    def test_missing_image_never_sent(self):
        self.assertFalse(self.sender.send_image('Z:/nonexistent-image.png', 'group@chatroom').is_success)
        self.assertEqual(Handler.calls, [])

    def test_remote_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            HookSender({'base_url': 'http://192.0.2.1:30001'})


if __name__ == '__main__':
    unittest.main()
