import json
import threading
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import patch, Mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import api_bridge
from social_policy import Conversations, normalize_message, split_action
from sticker_choices import catalog
from deepseek_web import execute


class SocialTests(unittest.TestCase):
    def test_fresh_start_does_not_open_old_history_or_memory(self):
        bot=api_bridge.Bot.__new__(api_bridge.Bot)
        bot.cfg={'bot':{'fresh_start':True}};bot.history={};bot.group_memory={}
        with patch.object(Path,'read_text',side_effect=AssertionError('old file read')):
            bot._load_history();bot._load_group_memory()
        self.assertEqual(bot.history,{});self.assertEqual(bot.group_memory,{})

    def test_fresh_listener_starts_at_latest_not_saved_watermark(self):
        from wechatauto.db import Listener
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'listener_watermark.json').write_text('{"g":1}',encoding='utf-8')
            bot=api_bridge.Bot.__new__(api_bridge.Bot)
            bot.cfg={'bot':{'fresh_start':True,'poll_interval':1}}
            bot.db=type('DB',(),{'workdir':folder,'get_messages':lambda *a,**k:[{'sort_seq':100}]})()
            listener=bot._new_listener(Listener)
            listener.add_listener('g',lambda *a:None)
            self.assertEqual(listener.watermark,{'g':100})
            self.assertEqual(listener.watermark_file,'')

    def test_other_people_do_not_close_conversation(self):
        c = Conversations(150)
        c.open('g','a',100)
        self.assertFalse(c.follows('g','b','哈哈',now=110))
        self.assertTrue(c.follows('g','a','那你呢',now=120))
        c.open('g','a',120)
        self.assertTrue(c.follows('g','a','继续',now=260))
        self.assertFalse(c.follows('g','a','继续',now=271))

    def test_quote_other_and_mentions_are_not_hijacked(self):
        c = Conversations()
        c.open('g','a',100)
        self.assertFalse(c.follows('g','a','嗯',quote='other',now=110))
        self.assertFalse(c.follows('g','a','@别人 你呢',now=110))
        self.assertTrue(c.follows('g','b','那你呢',quote='self',now=110))

    def test_goodbye_closes_only_this_person(self):
        c = Conversations()
        c.open('g','a',100); c.open('g','b',100)
        self.assertFalse(c.follows('g','a','晚安',now=110))
        self.assertTrue(c.follows('g','b','然后呢',now=110))

    def test_quote_xml(self):
        m={'type':'文件/链接/卡片','content':'wxid_a:\n<msg><appmsg><type>57</type><title>真的吗</title><refermsg><fromusr>wxid_bot</fromusr><content>原话</content></refermsg></appmsg></msg>'}
        text, target=normalize_message(m,'wxid_bot')
        self.assertEqual(target,'self');self.assertIn('真的吗',text)
        self.assertEqual(normalize_message({'type':'图片','content':'anything'},'bot'),('','none'))

    def test_banter_requires_explicit_mention_and_correct_subject(self):
        bot=api_bridge.Bot.__new__(api_bridge.Bot)
        bot.cfg={'bot':{'banter_target_ids':['haoid'],'banter_names':['示例群友','阿甲']}}
        self.assertFalse(bot._banter_allowed('speaker','示例群友','haoid','我来了'))
        self.assertFalse(bot._banter_allowed('name','路人','x','小鲸鱼怎么评价示例群友'))
        self.assertFalse(bot._banter_allowed('followup','示例群友','haoid','继续'))
        self.assertTrue(bot._banter_allowed('mention','改名后','haoid','@小鲸鱼 你好'))
        self.assertTrue(bot._banter_allowed('mention','路人','x','@小鲸鱼 怎么评价示例群友'))
        self.assertFalse(bot._banter_allowed('mention','路人','x','@小鲸鱼 示例群友说这是装备名'))
        self.assertFalse(bot._banter_allowed('mention','路人','x','@小鲸鱼 怎么评价别的人'))

    def test_private_sticker_commands_and_skip(self):
        self.assertEqual(split_action('？ [[sticker:angry]]'),('？','angry'))
        self.assertEqual(split_action('[[sticker:doge]]'),('','doge'))
        self.assertEqual(split_action('<SKIP> [[sticker:doge]]'),('',None))
        self.assertEqual(split_action('不知道'),('不知道',None))
        self.assertEqual(split_action('？ [[sticker:ang'),('？',None))

    def test_catalog_has_real_images(self):
        c=catalog(Path(__file__).resolve().parent,{'dir':'stickers'})
        self.assertGreaterEqual(len(c),12)
        self.assertTrue(all(v['path'].is_file() for v in c.values()))

    def test_delivery_never_leaks_marker_or_path(self):
        bot=api_bridge.Bot.__new__(api_bridge.Bot)
        bot.dry_run=False;bot.sticker_queue=__import__('queue').Queue()
        bot.sticker_catalog={'doge':{'path':Path('verified.png')}}
        bot._send_multi=Mock();g={'_username':'g'}
        bot._deliver_reply(g,'？ [[sticker:doge]]')
        bot._send_multi.assert_called_once_with(g,'？')
        self.assertEqual(bot.sticker_queue.get()[1],'doge')
        bot._send_multi.reset_mock()
        self.assertFalse(bot._deliver_reply(g,'[[sticker:../../secret]]'))
        self.assertFalse(bot._deliver_reply(g,'<SKIP>'))
        bot._send_multi.assert_not_called()

    def test_directed_followup_is_not_lost_to_cooldown(self):
        bot=api_bridge.Bot.__new__(api_bridge.Bot)
        g={'_username':'g','_display':'test','aliases':['bot']}
        bot.allowed_groups={'g'};bot.self_username='wxid_bot';bot.sent_texts=[]
        bot.recent={'g':deque(maxlen=10)};bot.seen={'g':deque(maxlen=10)}
        bot._maybe_enqueue_memory=lambda g:None;bot._sender_name=lambda *a:'a'
        bot.proactive_lock=threading.Lock();bot.last_message_at={};bot.pending_question={}
        bot._speaker_triggered=lambda *a:False;bot._triggered=lambda *a:''
        bot.conversations=Conversations();bot.conversations.open('g','a')
        bot._mentions_banter_target=lambda *a:False;bot.cfg={'bot':{}}
        bot.last_reply={'g':__import__('time').time()};bot._stop=Mock();bot._stop.wait.return_value=False
        bot._ask=Mock(return_value='？');bot._deliver_reply=Mock(return_value=True);bot._mark_active=Mock()
        bot._addressed_to_bot=Mock(return_value=True);bot.last_exchange={};bot.dialogue_counts={}
        bot._on_message(g,{'type':'文本','content':'然后呢','sender_username':'a','local_id':1,'sort_seq':1})
        bot._stop.wait.assert_called_once();bot._ask.assert_called_once()
        self.assertEqual(bot._ask.call_args.args[3],'followup')

    def test_web_rejects_local_and_unknown_tools_without_requests(self):
        s=Mock()
        for name,args in [('web_fetch',{'url':'file:///C:/secret'}),('web_fetch',{'url':'http://127.0.0.1:30001'}),('shell',{})]:
            with self.assertRaises(ValueError):execute(s,'https://api.deepseek.com',name,args)
        s.post.assert_not_called()


class ToolHandler(BaseHTTPRequestHandler):
    seen=[]
    def log_message(self,*a):pass
    def do_POST(self):
        p=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).seen.append(p)
        if not any(m['role']=='tool' for m in p['messages']):
            msg={'role':'assistant','content':None,'tool_calls':[{'id':'s1','type':'function','function':{'name':'web_search','arguments':'{"query":"test"}'}}]}
        else:msg={'role':'assistant','content':'查到了'}
        b=json.dumps({'choices':[{'message':msg}]}).encode()
        self.send_response(200);self.end_headers();self.wfile.write(b)


class ToolTests(unittest.TestCase):
    def test_tool_results_are_fed_back_to_flash(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),ToolHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            cfg={'api':{'base_url':f'http://127.0.0.1:{server.server_port}','model':'deepseek-flash','api_key_env':'TEST_ONLY_KEY','web_enabled':True}}
            with patch.dict('os.environ',{'TEST_ONLY_KEY':'fake'}),patch('deepseek_web.execute',return_value='{"results":[]}') as run:
                api=api_bridge.ApiClient(cfg)
                self.assertEqual(api.chat([{'role':'system','content':'【网页工具边界】'}]),'查到了')
                run.assert_called_once()
                self.assertEqual(ToolHandler.seen[-1]['thinking'],{'type':'disabled'})
                self.assertEqual(ToolHandler.seen[-1]['messages'][-1]['tool_call_id'],'s1')
        finally:server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()
