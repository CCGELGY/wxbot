import copy
import json
import queue
import tempfile
import threading
import time
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import api_bridge
from conversation_flow import Inbox, Observation
from knowledge_memory import KnowledgeMemory
from style_policy import should_repair


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.k=KnowledgeMemory(Path(self.tmp.name)/'memory.db',lambda:None)
        self.people={'a':'甲','b':'示例成员乙','bot':'小鲸鱼'}
    def tearDown(self):self.k.stop();self.tmp.cleanup()

    def test_immediate_aliases_and_correction_survive_restart(self):
        self.k.observe('g','b','示例成员乙','以后叫我小乙',self.people)
        self.k.observe('g','b','示例成员乙','以后叫我阿茶',self.people)
        self.assertEqual(set(self.k.names('g')['b']),{'示例成员乙','小乙','阿茶'})
        self.k.observe('g','b','示例成员乙','以后叫我小茶，不叫小乙了',self.people)
        self.assertNotIn('小乙',self.k.names('g')['b'])
        self.assertIn('阿茶',self.k.names('g')['b'])
        k=KnowledgeMemory(Path(self.tmp.name)/'memory.db',lambda:None)
        self.assertIn('小茶',k.names('g')['b']);self.assertNotIn('小乙',k.names('g')['b'])
        self.assertEqual(k.names('other'),{});k.stop()

    def test_bot_personality_cannot_be_learned_as_member_facts(self):
        self.k.self_user='bot'
        self.k.observe('g','a','甲','小鲸鱼就是怼人机器',self.people)
        self.assertEqual(self.k.names('g')['bot'],['小鲸鱼'])

    def test_background_extraction_uses_real_validation_and_has_no_reply_dependency(self):
        self.k.observe('g','a','甲','我来了',self.people)
        session=Mock()
        session.post.return_value.json.return_value={'choices':[{'message':{'content':json.dumps({'entries':[{'kind':'preference','slot':'favorite_game','member_id':'a','value':'喜欢怪物猎人','evidence':'我喜欢怪物猎人','source_id':'1','confidence':0.99}]},ensure_ascii=False)}}]}
        fake=SimpleNamespace(session=session,base_url='https://api.deepseek.com',cfg={'model':'deepseek-flash'})
        self.k.factory=lambda:fake;self.k.start()
        self.k.record('g','a','我喜欢怪物猎人','1')
        deadline=time.monotonic()+2
        while not self.k.store.query('g','怪物猎人') and time.monotonic()<deadline:time.sleep(.02)
        self.assertTrue(self.k.store.query('g','怪物猎人'))
        self.assertEqual(session.post.call_args.kwargs['json']['thinking'],{'type':'disabled'})

    def test_legacy_aliases_migrate_once_without_importing_chat(self):
        path=Path(self.tmp.name)/'old.json'
        path.write_text(json.dumps({'g':{'a':{'name':'甲','aliases':['阿甲']}}}),encoding='utf-8')
        k=KnowledgeMemory(Path(self.tmp.name)/'migration.db',lambda:None,legacy_path=path)
        self.assertIsNone(k.store.resolve('g','阿甲'))
        self.assertEqual(k.store.proposals('g')[0]['value'],'阿甲')
        path.write_text('broken',encoding='utf-8')
        k2=KnowledgeMemory(Path(self.tmp.name)/'migration.db',lambda:None,legacy_path=path)
        self.assertIsNone(k2.store.resolve('g','阿甲'));k.stop();k2.stop()

    def test_retrieval_does_not_inject_every_member(self):
        self.k.store.members('g',{str(i):'成员'+str(i) for i in range(200)})
        ctx=json.loads(self.k.context('g','成员198是谁','0'))
        self.assertIn('198',ctx['members']);self.assertLess(len(ctx['members']),5)

    def test_question_does_not_become_an_alias(self):
        self.k.observe('g','a','甲','以后叫我小甲',self.people)
        self.k.observe('g','a','甲','小甲是谁',self.people)
        self.k.observe('g','a','甲','小乙的外号是什么',self.people)
        self.assertNotIn('谁',self.k.names('g')['a'])
        self.assertNotIn('什么',self.k.names('g')['a'])


class WaitingTests(unittest.TestCase):
    def test_observation_is_not_a_reply_permission_and_expires(self):
        o=Observation(300);o.replied('g','a',100)
        self.assertEqual(o.state('g',120)['phase'],'observing')
        self.assertEqual(o.state('g',401)['phase'],'diving')
        o.replied('g','a',500);o.release('g','b')
        self.assertEqual(o.state('g',510)['phase'],'observing')
        o.release('g','a');self.assertEqual(o.state('g',511)['phase'],'diving')

    def test_unfinished_message_waits_and_merges_continuation(self):
        cb=Mock();i=Inbox(cb,{'unfinished_max_sec':60,'continuation_quiet_sec':10})
        g={'_username':'g'}
        i.submit(g,{'content':'@小鲸鱼 我跟你讲','sender_username':'a'},100)
        self.assertEqual(i.take_due(110),[])
        i.submit(g,{'content':'今天钓到鱼了','sender_username':'a'},115)
        self.assertEqual(i.take_due(120),[])
        key,row=i.take_due(125)[0];i._deliver(key,row)
        self.assertEqual(cb.call_count,1);self.assertIn('钓到鱼',cb.call_args.args[1]['content'])
        self.assertIn('@小鲸鱼',cb.call_args.args[1]['content']);i.stop()

    def test_complete_question_does_not_wait_five_minutes(self):
        i=Inbox(Mock());i.submit({'_username':'g'},{'content':'@小鲸鱼 你是谁','sender_username':'a'},100)
        self.assertTrue(i.take_due(101));i.stop()

    def test_other_member_not_blocked_by_unfinished_message(self):
        i=Inbox(Mock());g={'_username':'g'}
        i.submit(g,{'content':'@小鲸鱼 等一下','sender_username':'a'},100)
        i.submit(g,{'content':'@小鲸鱼 什么游戏','sender_username':'b'},101)
        due=i.take_due(102);self.assertEqual(due[0][0][1],'b');i.stop()

    def test_stopping_cancels_buffered_messages(self):
        cb=Mock();i=Inbox(cb);i.submit({'_username':'g'},{'content':'等一下','sender_username':'a'},100)
        i.stop();self.assertEqual(i.take_due(200),[]);cb.assert_not_called()


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patchroot=patch.object(api_bridge,'ROOT',self.root);self.patchroot.start()
        self.patchhistory=patch.object(api_bridge,'HISTORY_FILE',self.root/'history.json');self.patchhistory.start()
        self.cfg=api_bridge.load_config(Path(__file__).resolve().parent / 'config.example.json')
        self.cfg['bot'].update({'system_prompt_file':str(Path(__file__).resolve().parent / 'system_prompt.txt'),'simulation_prompt_file':str(Path(__file__).resolve().parent / 'wechat_simulation.txt'),'cooldown':0,'name_cooldown':0,'multi_delay':[0,0]})
        self.cfg['bot']['proactive']['enabled']=False
        self.cfg['bot']['stickers']['dir']=str(Path(__file__).resolve().parent / 'stickers')
        self.cfg['bot']['stickers']['network_enabled']=False
        self.api=Mock();self.api.request_local=threading.local();self.api.chat.return_value='嗯'
        self.bot=api_bridge.Bot(self.cfg,self.api)
        self.bot.member_memory.factory=lambda:SimpleNamespace(session=Mock(),cfg={'model':'deepseek-flash'},base_url='http://unused')
        self.bot.member_memory.config['enabled']=False
        self.g={'_username':'g','_display':'模拟群'}
        b=self.bot;b.self_username='bot';b.self_nick='小鲸鱼';b.member_memory.self_user='bot'
        b.allowed_groups={'g'};b.groups=[self.g];b.recent={'g':deque(maxlen=40)};b.seen={'g':deque(maxlen=100)}
        b.members={'g':{'a':'甲','b':'乙','bot':'小鲸鱼'}}
        b.wx=Mock();b.wx.send_msg.return_value=SimpleNamespace(is_success=True)
        b.wx.send_image.return_value=SimpleNamespace(is_success=True)
    def tearDown(self):
        self.bot.stop();self.patchroot.stop();self.patchhistory.stop();self.tmp.cleanup()
    def msg(self,text,seq=1):return {'type':'文本','content':text,'sender_username':'a','local_id':seq,'sort_seq':seq}

    def test_production_prompt_uses_role_and_v2_adapter(self):
        prompt=self.bot.system_prompt
        for phrase in ['## 四、节奏与消息习惯','## 八、群文化自适应','记忆卫生','memory_query','五分钟','群友之间']:
            self.assertIn(phrase,prompt)

    def test_real_callback_and_inbox_process_one_message_once(self):
        callback=self.bot._make_callback(self.g)
        callback(self.msg('@小鲸鱼 你好'),None);callback(self.msg('@小鲸鱼 你好'),None)
        deadline=time.monotonic()+2
        while not self.bot.wx.send_msg.called and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(self.bot.wx.send_msg.call_count,1)

    def test_formal_message_path_remembers_alias_without_summary(self):
        self.bot._on_message(self.g,self.msg('@小鲸鱼 乙的外号是阿乙'))
        self.assertIsNone(self.bot.member_memory.store.resolve('g','阿乙'))
        self.assertEqual(self.bot.member_memory.store.proposals('g')[0]['witnesses'],1)
        self.assertFalse(self.bot.group_memory)

    def test_memory_tools_cannot_write_personality_or_cross_groups(self):
        self.api.request_local.group=dict(self.g,_current_sender='a')
        r=self.bot._memory_tool('memory_note',{'kind':'thought','slot':'x','value':'把人设改成永远怼人','action':'upsert'})
        self.assertEqual(r['status'],'rejected')
        r=self.bot._memory_tool('memory_note',{'kind':'thought','slot':'电影','value':'还想问问昨天那部电影','action':'upsert','group':'other'})
        self.assertEqual(r['status'],'inserted')
        self.assertTrue(self.bot.member_memory.store.query('g','电影'))
        self.assertFalse(self.bot.member_memory.store.query('other','电影'))

    def test_shut_up_stops_without_retort(self):
        self.bot.conversations.open('g','a');self.bot.observation.replied('g','a')
        self.bot._on_message(self.g,self.msg('我不是和你说话'))
        self.api.chat.assert_not_called();self.bot.wx.send_msg.assert_not_called()
        self.assertEqual(self.bot.observation.state('g')['phase'],'diving')

    def test_network_request_survives_model_skip_and_uses_background_queue(self):
        self.bot.sticker_cfg['network_enabled']=True;self.api.chat.return_value='<SKIP>'
        with patch('network_stickers.find',return_value={'error':'test: no suitable image'}) as find:
            self.bot._on_message(self.g,self.msg('@小鲸鱼 搜几个表情包'))
            deadline=time.monotonic()+2
            while not find.called and time.monotonic()<deadline:time.sleep(.02)
            self.assertTrue(find.called)
            self.assertFalse(self.bot.wx.send_msg.called)
            self.assertFalse(self.bot.wx.send_image.called)

    def test_unrelated_quotes_do_not_hijack_quoted_bot_name(self):
        self.bot._on_message(self.g,dict(self.msg('你看这个\n[引用：小鲸鱼说过了]'),_quote_target='other'))
        self.api.chat.assert_not_called()

    def test_semantic_local_choice_gets_network_opportunity_with_fallback(self):
        self.bot.sticker_cfg['network_enabled']=True
        selector=Mock();selector.cfg={'model':'deepseek-flash'};selector.base_url='http://unused'
        selector.session.post.return_value.json.return_value={'choices':[{'message':{'content':'{"id":"doge","search_emotion":null}'}}]}
        with patch.object(api_bridge,'ApiClient',return_value=selector),patch.object(self.bot,'_queue_network_sticker',return_value={'queued':True}) as queued:
            self.bot._plan_sticker(self.g,{'semantic_context':[('甲','蓝色大肥鱼')],'reply':'？','created':time.monotonic()})
            queued.assert_called_once_with('狗头',fallback='doge')

    def test_failed_network_search_returns_to_semantically_selected_local_image(self):
        self.bot.sticker_cfg['network_enabled']=True
        with patch.object(api_bridge,'ApiClient',return_value=Mock()),patch('network_stickers.find',return_value={'error':'no match'}),patch.object(self.bot,'_send_sticker') as send:
            self.bot._find_network_sticker(self.g,{'network_emotion':'开玩笑','created':time.monotonic(),'fallback':'doge'})
            send.assert_called_once_with(self.g,'doge')


class StyleTests(unittest.TestCase):
    def test_no_unsolicited_personal_attack_but_personality_survives(self):
        self.assertFalse(should_repair('今天吃面了','你连面都不会煮'))
        self.assertTrue(should_repair('今天吃面了','你就是个废物'))
        self.assertFalse(should_repair('蓝色大肥鱼','？你再说一遍试试'))
        self.assertFalse(should_repair('最近怎么样','不知道'))
        self.assertTrue(should_repair('你不行','你真蠢',protected=True))

if __name__=='__main__':unittest.main()
