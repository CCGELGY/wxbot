import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from knowledge_memory import KnowledgeMemory
from dialogue_policy import candidate
from agency_policy import repair_reason,naming_request
from style_policy import should_repair


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.k=KnowledgeMemory(Path(self.tmp.name)/'m.db',lambda:None)
        self.people={'a':'甲','b':'乙','c':'丙','d':'丁'}
    def tearDown(self):self.k.stop();self.tmp.cleanup()

    def test_repetition_by_one_person_is_not_confirmation(self):
        for _ in range(4):self.k.observe('g','a','甲','乙的外号是小乙',self.people)
        self.assertIsNone(self.k.store.resolve('g','小乙'))
        self.assertEqual(self.k.store.proposals('g')[0]['witnesses'],1)

    def test_three_independent_witnesses_can_confirm(self):
        for uid,name in [('a','甲'),('c','丙'),('d','丁')]:self.k.observe('g',uid,name,'乙的外号是小乙',self.people)
        self.assertEqual(self.k.store.resolve('g','小乙'),'b')

    def test_member_confirmation_has_priority(self):
        self.k.observe('g','a','甲','乙的外号是小乙',self.people)
        self.k.observe('g','b','乙','以后叫我小乙',self.people)
        self.assertEqual(self.k.store.resolve('g','小乙'),'b')
        self.assertNotIn('小乙',[r['value'] for r in __import__('json').loads(self.k.context('g','小乙是谁','a'))['unconfirmed_aliases']])

    def test_member_denial_cannot_be_overridden_by_others(self):
        self.k.observe('g','a','甲','乙的外号是小乙',self.people)
        self.k.observe('g','b','乙','我不叫小乙',self.people)
        for uid,name in [('c','丙'),('d','丁')]:self.k.observe('g',uid,name,'乙的外号是小乙',self.people)
        self.assertIsNone(self.k.store.resolve('g','小乙'))
        self.k.observe('g','b','乙','以后叫我小乙',self.people)
        self.assertEqual(self.k.store.resolve('g','小乙'),'b')

    def test_new_member_who_question_reaches_recipient_judgement(self):
        self.assertTrue(candidate('成员甲是谁',False))
        self.assertTrue(candidate('成员乙又是谁',False))
        self.assertTrue(candidate('成员丁是谁',False))

    def test_agency_guard_without_suppressing_self_introduction(self):
        self.assertTrue(naming_request('记住乙是小乙'))
        self.assertFalse(naming_request('以后叫我阿甲'))
        self.assertFalse(naming_request('你记住哪些人了'))
        self.assertEqual(repair_reason('帮我喊一下乙','@乙 过来一下'),'relay')
        self.assertEqual(repair_reason('帮我喊一下乙','你自己喊'),'')
        self.assertEqual(repair_reason('记住乙是小乙','记住了',True),'naming')

    def test_playful_teasing_and_retort_survive(self):
        self.assertFalse(should_repair('蓝色大肥鱼','？你再说一遍试试'))
        self.assertFalse(should_repair('帮我喊人','你自己没嘴啊'))
        self.assertTrue(should_repair('你好','你就是个废物'))

if __name__=='__main__':unittest.main()
