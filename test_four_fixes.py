import json
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from collections import deque

import api_bridge
from member_memory import MemberMemory
from dialogue_policy import addressed, other_recipient, STOP
from social_policy import Conversations, split_action


class MemoryTests(unittest.TestCase):
    def test_nickname_survives_context_loss_and_restart_but_is_group_scoped(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'members.json'
            m=MemberMemory(file)
            m.observe('g','a','甲','记住，示例成员乙的外号是小乙',{'b':'示例成员乙'})
            m=MemberMemory(file)
            self.assertIn('小乙',m.context('g','小乙是谁','a'))
            self.assertNotIn('小乙',m.context('other','小乙是谁','a'))
            self.assertEqual(m.names('g')['b'],['示例成员乙','小乙'])

    def test_unresolved_reference_and_persona_changes_are_not_names(self):
        with tempfile.TemporaryDirectory() as folder:
            m=MemberMemory(Path(folder)/'m.json')
            m.observe('g','a','甲','他叫小乙',{'b':'乙'})
            m.observe('g','a','甲','以后叫我永远怼人',{})
            self.assertNotIn('小乙',m.context('g','小乙','a'))
            self.assertFalse(m.names('g')['a'][1:])

    def test_reverse_alias_and_same_nickname_ambiguity(self):
        with tempfile.TemporaryDirectory() as folder:
            m=MemberMemory(Path(folder)/'m.json')
            m.observe('g','a','甲','小乙就是乙',{'b':'乙'})
            self.assertIn('小乙',m.names('g')['b'])
            m.observe('g','c','乙','乙的外号是阿茶',{})
            self.assertNotIn('阿茶',m.context('g','阿茶','a'))

    def test_explicit_nickname_correction_replaces_old_alias(self):
        with tempfile.TemporaryDirectory() as folder:
            m=MemberMemory(Path(folder)/'m.json')
            m.observe('g','a','甲','阿茶是乙的外号',{'b':'乙'})
            m.observe('g','a','甲','乙不叫阿茶了，叫小乙',{})
            self.assertEqual(m.names('g')['b'],['乙','小乙'])


def bare_bot():
    b=api_bridge.Bot.__new__(api_bridge.Bot)
    b.allowed_groups={'g'};b.self_username='bot';b.sent_texts=[];b.members={}
    b.recent={'g':deque(maxlen=20)};b.seen={'g':deque(maxlen=20)}
    b.proactive_lock=threading.Lock();b.last_message_at={};b.pending_question={}
    b.conversations=Conversations();b.conversations.open('g','a')
    b._sender_name=lambda *a:'甲';b._maybe_enqueue_memory=Mock()
    b._speaker_triggered=lambda *a:False;b._triggered=lambda *a:''
    b._addressed_to_bot=Mock(return_value=False);b._keyword_reply=lambda *a:''
    b._looks_like_open_question=lambda *a:False;b._schedule_question=Mock()
    b._ask=Mock(return_value='知道了');b._deliver_reply=Mock(return_value=True);b._mark_active=Mock()
    b.last_reply={};b.last_exchange={};b.dialogue_counts={};b.cfg={'bot':{}};b._stop=threading.Event()
    return b


class RoutingTests(unittest.TestCase):
    g={'_username':'g','_display':'test'}
    def message(self,text):return {'type':'文本','content':text,'sender_username':'a','local_id':1,'sort_seq':1}

    def test_previous_mention_does_not_force_reply(self):
        b=bare_bot();b._on_message(self.g,self.message('哼'))
        b._ask.assert_not_called()

    def test_stop_closes_window_without_another_retort(self):
        b=bare_bot();b._on_message(self.g,self.message('我不是和你说话，你不要自作聪明'))
        self.assertNotIn(('g','a'),b.conversations.sessions)
        b._ask.assert_not_called();b._addressed_to_bot.assert_not_called()

    def test_no_previous_mention_can_still_receive_answer(self):
        b=bare_bot();b.conversations.sessions.clear();b._addressed_to_bot.return_value=True
        b._on_message(self.g,self.message('你能搜索最新游戏资料吗'))
        self.assertEqual(b._ask.call_args.args[3],'implicit')

    def test_other_member_vocative_is_not_hijacked(self):
        self.assertTrue(other_recipient('小乙，你怎么回事',{'b':['示例成员乙','小乙']}))
        self.assertTrue(other_recipient('不行啊，小乙，啥都加钱',{'b':['小乙']}))
        self.assertFalse(other_recipient('小乙是谁',{'b':['小乙']}))

    def test_classifier_uses_bounded_no_tools_and_fails_closed(self):
        api=Mock();api.cfg={'model':'deepseek-flash'};api.base_url='https://api.deepseek.com'
        api.session.post.return_value.json.return_value={'choices':[{'message':{'content':'{"to_bot":false,"reason":"在和别人聊"}'}}]}
        self.assertFalse(addressed(api,[],{},'甲','你说呢',True)[0])
        payload=api.session.post.call_args.kwargs
        self.assertNotIn('tools',payload['json']);self.assertEqual(payload['timeout'],(3,7))


class StickerTests(unittest.TestCase):
    def test_search_marker_cannot_leak_into_wechat_or_history_text(self):
        self.assertEqual(split_action('？ [[search_sticker:疑惑]]'),('？',None))
        self.assertEqual(split_action('[[search_sticker:疑惑'),('',None))
        b=bare_bot();b.dry_run=False;b.network_offered_at={};b.sticker_catalog={}
        b.api=Mock();b.api.request_local=threading.local();b._queue_network_sticker=Mock(return_value={'queued':True})
        b._send_multi=Mock();b._deliver_reply=api_bridge.Bot._deliver_reply.__get__(b)
        self.assertTrue(b._deliver_reply(self.g if hasattr(self,'g') else {'_username':'g'},'[[search_sticker:疑惑]]'))
        b._send_multi.assert_not_called();b._queue_network_sticker.assert_called_once_with('疑惑')

    def test_selected_local_reaction_gets_network_opportunity_without_extra_text(self):
        b=bare_bot();b.dry_run=False;b.network_offered_at={};b.dialogue_counts={'g':5}
        b.sticker_catalog={'sad':{'path':Path('sad.png'),'description':'委屈'}}
        b.api=Mock();b.api.request_local=threading.local();b._queue_network_sticker=Mock(return_value={'queued':True})
        b._send_multi=Mock();b._deliver_reply=api_bridge.Bot._deliver_reply.__get__(b)
        self.assertTrue(b._deliver_reply({'_username':'g'},'[[sticker:sad]]'))
        b._queue_network_sticker.assert_called_once_with('委屈')


if __name__=='__main__':unittest.main()
