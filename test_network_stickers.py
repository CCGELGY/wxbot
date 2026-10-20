import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from PIL import Image

import network_stickers as net
import api_bridge
from sticker_choices import catalog


def fixture():
    out=io.BytesIO();Image.new('RGB',(128,128),'blue').save(out,format='PNG');return out.getvalue()


class Tests(unittest.TestCase):
    def test_loopback_target_rejected(self):
        with self.assertRaises(ValueError):net.public_target('http://127.0.0.1/image.png','http://127.0.0.1:7897')
        with self.assertRaises(ValueError):net.public_target('file:///C:/secret')

    def test_trusted_cdn_uses_proxy_without_fake_dns(self):
        with patch('socket.getaddrinfo',side_effect=AssertionError('must not resolve local fake IP')):
            p,ip=net.public_target('https://raw.githubusercontent.com/user/repo/image.png','http://127.0.0.1:7897')
        self.assertIsNone(ip)

    def test_download_keeps_api_credentials_out_of_proxy(self):
        response=Mock(status_code=200,headers={});response.iter_content.return_value=[b'image']
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        session=Mock();session.get.return_value=response
        manager=Mock();manager.__enter__=Mock(return_value=session);manager.__exit__=Mock(return_value=False)
        with patch('network_stickers.requests.Session',return_value=manager) as factory:
            data=net.download_public('https://raw.githubusercontent.com/a/b/x.png',proxy_url='http://127.0.0.1:7897')
        self.assertEqual(data,b'image')
        factory.assert_called_once()
        headers=session.get.call_args.kwargs['headers']
        self.assertNotIn('Authorization',headers)
        self.assertTrue(session.get.call_args.args[0].startswith('https://raw.githubusercontent.com/'))
        self.assertFalse(session.trust_env)
        self.assertEqual(session.proxies['https'],'http://127.0.0.1:7897')

    def test_http_images_do_not_receive_https_only_proxy_options(self):
        response=Mock(status=200,headers={});response.read.return_value=b'image'
        pool=Mock();pool.urlopen.return_value=response
        with patch('network_stickers.public_target',return_value=(__import__('urllib.parse',fromlist=['urlsplit']).urlsplit('http://example.com/a.jpg'),'93.184.216.34')),patch('network_stickers.urllib3.ProxyManager',return_value=pool) as factory:
            net.download_public('http://example.com/a.jpg',proxy_url='http://127.0.0.1:7897')
        self.assertNotIn('assert_hostname',factory.call_args.kwargs)
        self.assertNotIn('server_hostname',factory.call_args.kwargs)

    def test_bad_or_oversized_images_rejected(self):
        self.assertEqual(net.validate_image(fixture()),('png','image/png'))
        for data in [b'not an image',b'x'*(net.MAX_BYTES+1)]:
            with self.assertRaises(Exception):net.validate_image(data)

    def test_markdown_images_prefer_stickers_not_badges(self):
        links=net.image_links('![b](badge.svg) ![s](previews/1.webp)','https://raw.githubusercontent.com/a/b/main/README.md')
        self.assertEqual(links,['https://raw.githubusercontent.com/a/b/main/previews/1.webp'])

    def test_search_review_and_collection_contract(self):
        net._attempts.clear()
        session=Mock();session.post.return_value.json.return_value={'results':[{'url':'https://example.com/page','content':'![图](https://raw.githubusercontent.com/a/b/previews/1.png)'}]}
        with tempfile.TemporaryDirectory() as folder,patch('network_stickers.download_public',return_value=fixture()),patch('network_stickers.visual_review',return_value='鲸鱼娘蹭饭卖萌'):
            root=Path(folder)
            r=net.find(session,'https://api.deepseek.com','deepseek-flash',root,{'network_enabled':True},'蹭饭')
            self.assertTrue(r['id'].startswith('net_'))
            self.assertIn(r['id'],catalog(root,{}))
            second=net.find(session,'https://api.deepseek.com','deepseek-flash',root,{'network_enabled':True},'蹭饭')
            self.assertIn('error',second)

    def test_rejected_image_is_not_collected(self):
        net._attempts.clear()
        session=Mock();session.post.return_value.json.return_value={'results':[{'url':'https://example.com/a.png'}]}
        with tempfile.TemporaryDirectory() as folder,patch('network_stickers.download_public',return_value=fixture()),patch('network_stickers.visual_review',side_effect=ValueError('not whale')):
            root=Path(folder);r=net.find(session,'https://api.deepseek.com','deepseek-flash',root,{'network_enabled':True},'笑')
            self.assertIn('error',r)
            self.assertFalse((root/'stickers/network/index.json').exists())

    def test_background_request_queues_without_waiting(self):
        b=api_bridge.Bot.__new__(api_bridge.Bot)
        b.api=Mock();b.api.request_local=threading.local();b.api.request_local.group={'_username':'g'}
        b.sticker_cfg={'network_enabled':True};b.dry_run=False;b.proactive_lock=threading.Lock()
        b.network_pending=set();b.sticker_queue=__import__('queue').Queue()
        self.assertTrue(b._queue_network_sticker('笑')['queued'])
        self.assertEqual(b.sticker_queue.qsize(),1)
        self.assertTrue(b._queue_network_sticker('笑')['queued'])
        self.assertEqual(b.sticker_queue.qsize(),1)


if __name__=='__main__':unittest.main()
