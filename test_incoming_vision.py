import base64
import copy
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image

from incoming_vision import IncomingVision, encode_image, quoted_image
from conversation_flow import Inbox
import api_bridge
from hook_sender import open_hook_database


def reference(local_id=1, shard='message_0.db'):
    return {'local_id':local_id, 'sort_seq':local_id, 'shard':shard}


class VisionTests(unittest.TestCase):
    def test_group_sender_isolation_ttl_and_comparison_limit(self):
        v=IncomingVision()
        for i in range(4):v.remember('g','a',reference(i),now=1+i)
        self.assertEqual(len(v.select('g','a','对比这几张图',now=5)),2)
        self.assertEqual(len(v.select('g','a','这是什么图',now=5)),1)
        self.assertEqual(v.select('other','a','看看图',now=5),[])
        self.assertEqual(v.select('g','b','看看图',now=5),[])
        self.assertEqual(v.select('g','a','看看图',now=200),[])
        self.assertEqual(v.select('g','a','今天天气好吗',now=5),[])

    def test_cache_is_bounded_and_duplicates_do_not_spam(self):
        v=IncomingVision()
        for i in range(140):v.remember('g',str(i),reference(i),now=1)
        self.assertEqual(len(v.images),128)
        v.remember('g','139',reference(139),now=2)
        self.assertEqual(len(v.images['g','139']),1)

    def test_awaiting_image_is_sender_scoped_cancelable_and_expires(self):
        v=IncomingVision();v.expect('g','a','@bot 看图',now=1)
        self.assertTrue(v.pending('g','a',now=2))
        self.assertFalse(v.pending('g','b',now=2))
        self.assertFalse(v.pending('g','a',now=200))
        v.cancel('g','a');self.assertFalse(v.pending('g','a',now=2))

    def test_quote_parser_only_accepts_real_image_quotes(self):
        xml='<msg><appmsg><type>57</type><title>@bot 看图</title><refermsg><type>3</type><svrid>12345</svrid></refermsg></appmsg></msg>'
        self.assertEqual(quoted_image({'content':xml})['server_id'],12345)
        self.assertIsNone(quoted_image({'content':xml.replace('<type>3</type>','<type>1</type>')}))
        self.assertIsNone(quoted_image({'content':'<!DOCTYPE x>'+xml}))

    def test_png_is_resized_reencoded_and_contains_real_pixels(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'source.png';Image.new('RGB',(2000,1000),'red').save(p)
            block=encode_image(p);url=block['image_url']['url']
            self.assertTrue(url.startswith('data:image/jpeg;base64,'))
            decoded=Image.open(io.BytesIO(base64.b64decode(url.split(',',1)[1])))
            self.assertEqual(decoded.size,(1600,800))
            self.assertGreater(decoded.getpixel((100,100))[0],200)
            self.assertNotIn(str(p),json.dumps(block))

    def test_invalid_and_oversize_images_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'fake.png';p.write_bytes(b'not an image')
            with self.assertRaises(Exception):encode_image(p)
            Image.new('RGB',(100,100)).save(p)
            with self.assertRaises(ValueError):encode_image(p,{'max_pixels':100})

    def test_media_read_is_shard_scoped_uses_no_gui_and_cleans_up(self):
        paths=[]
        def download(group,local_id,**kwargs):
            self.assertEqual((group,local_id),('g',1))
            self.assertEqual(kwargs['shard'],'message_0.db')
            self.assertEqual(kwargs['tier'],'best')
            p=Path(kwargs['save_dir'])/'decoded.png';Image.new('RGB',(80,80),'blue').save(p)
            paths.append(p);return str(p)
        downloader=Mock();downloader.download_image.side_effect=download
        with patch('wechatauto.MediaDownloader',return_value=downloader):
            blocks=IncomingVision().blocks(Mock(),'g',[reference()])
        self.assertEqual(len(blocks),1)
        self.assertFalse(paths[0].exists())
        downloader.download_image_original.assert_not_called()

    def test_ambiguous_quote_and_missing_shard_are_not_guessed(self):
        db=Mock();db.get_image_rows.return_value=[{'server_id':1},{'server_id':1}]
        with patch('wechatauto.MediaDownloader') as media:
            self.assertEqual(IncomingVision().blocks(db,'g',[{'_quoted_image':True,'server_id':1}, {'local_id':2}]),[])
            media.return_value.download_image.assert_not_called()

    def test_inbox_preserves_all_images_when_text_follows(self):
        cb=Mock();i=Inbox(cb)
        g={'_username':'g'}
        i.submit(g,{'sender_username':'a','content':'[图片]','_image_only':True,'_image_refs':[reference()]},now=1)
        i.submit(g,{'sender_username':'a','content':'@bot 这是什么','_image_only':False},now=1.05)
        key,row=i.take_due(3)[0];i._deliver(key,row)
        message=cb.call_args.args[1]
        self.assertEqual(message['_image_refs'],[reference()]);self.assertFalse(message['_image_only'])
        i.stop()

    def test_image_request_waits_briefly_for_following_picture(self):
        i=Inbox(Mock())
        i.submit({'_username':'g'},{'sender_username':'a','content':'@bot 看图','_await_image':True},now=1)
        self.assertEqual(i.take_due(1.5),[])
        self.assertEqual(len(i.take_due(3)),1);i.stop()

    def test_callback_keeps_picture_reference_and_ignores_self(self):
        b=api_bridge.Bot.__new__(api_bridge.Bot);b.allowed_groups={'g'};b.self_username='bot'
        b.incoming_vision=IncomingVision();b.proactive_lock=threading.Lock()
        b.last_message_at={};b.pending_question={};b.inbox=Mock()
        callback=b._make_callback({'_username':'g'})
        callback(dict(reference(),type='图片',sender_username='a',content='binary placeholder'),None)
        self.assertEqual(b.inbox.submit.call_args.args[1]['_image_refs'],[reference()])
        self.assertEqual(b.inbox.submit.call_args.args[1]['content'],'[图片]')
        callback(dict(reference(),type='图片',sender_username='bot'),None)
        self.assertEqual(b.inbox.submit.call_count,1)

    def test_request_uses_multimodal_content_but_history_never_stores_base64(self):
        b=api_bridge.Bot.__new__(api_bridge.Bot);b.cfg={'bot':{}}
        b.system_prompt='小鲸鱼';b.db=Mock();b.incoming_vision=Mock()
        block={'type':'image_url','image_url':{'url':'data:image/jpeg;base64,TEST'}}
        b.incoming_vision.blocks.return_value=[block]
        b._build_messages=Mock(return_value=[{'role':'user','content':'@bot 看图'}])
        b._chat_for_group=Mock(return_value='红色方块');b._append_history=Mock()
        result=b._ask({'_username':'g'},'甲','@bot 看图','mention','a',image_refs=[reference()])
        self.assertEqual(result,'红色方块')
        content=b._chat_for_group.call_args.args[1][-1]['content']
        self.assertEqual(content[-1],block)
        self.assertNotIn('base64',str(b._append_history.call_args))

    def test_image_failure_returns_honest_reply_without_calling_model(self):
        b=api_bridge.Bot.__new__(api_bridge.Bot);b.db=Mock();b.incoming_vision=Mock()
        b.incoming_vision.blocks.return_value=[]
        b._build_messages=Mock(return_value=[{'role':'user','content':'看图'}])
        b._chat_for_group=Mock()
        self.assertIn('没加载',b._ask({'_username':'g'},'甲','看图',image_refs=[reference()]))
        b._chat_for_group.assert_not_called()

    def test_disabled_images_do_not_produce_model_content(self):
        v=IncomingVision({'enabled':False});v.remember('g','a',reference())
        self.assertEqual(v.select('g','a','看图',[reference()]),[])
        self.assertEqual(len(v.images),0)

    def test_picture_without_a_request_never_calls_model(self):
        b=api_bridge.Bot.__new__(api_bridge.Bot)
        b.allowed_groups={'g'};b.self_username='bot';b.sent_texts=[]
        b.incoming_vision=IncomingVision();b._ask=Mock()
        b._on_message({'_username':'g'},{'type':'文本','content':'[图片]',
                          'sender_username':'a','_image_only':True,'_image_refs':[reference()]})
        b._ask.assert_not_called()


class AccountTests(unittest.TestCase):
    def test_database_is_selected_from_hook_identity_not_file_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ['wxid_example_a_ab12','wxid_example_b_cd34']:
                (Path(tmp)/name/'db_storage').mkdir(parents=True)
            hook=Mock();hook.base_url='http://[::1]:30001';hook.session.post.return_value.json.return_value={'wxid':'wxid_example_a'}
            db=Mock();db.get_self_info.return_value={'username':'wxid_example_a'}
            with patch('hook_sender.HookSender',return_value=hook), \
                 patch('wechatauto.db.auto_detect_db_dir',return_value=tmp), \
                 patch('wechatauto.WeChatDB',return_value=db) as create:
                self.assertIs(open_hook_database({}),db)
                self.assertEqual(create.call_args.kwargs['account'],'wxid_example_a_ab12')
            hook.session.close.assert_called_once()

    def test_missing_account_never_falls_back_to_another_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            hook=Mock();hook.base_url='http://[::1]:30001';hook.session.post.return_value.json.return_value={'wxid':'wxid_example_a'}
            with patch('hook_sender.HookSender',return_value=hook), \
                 patch('wechatauto.db.auto_detect_db_dir',return_value=tmp), \
                 patch('wechatauto.WeChatDB') as create:
                with self.assertRaises(RuntimeError):open_hook_database({})
                create.assert_not_called()

    def test_empty_hook_identity_stops_before_database_access(self):
        hook=Mock();hook.base_url='http://[::1]:30001';hook.session.post.return_value.json.return_value={'wxid':''}
        with patch('hook_sender.HookSender',return_value=hook),patch('wechatauto.WeChatDB') as create:
            with self.assertRaises(RuntimeError):open_hook_database({})
            create.assert_not_called()


if __name__=='__main__':unittest.main()
