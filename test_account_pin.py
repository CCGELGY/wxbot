import unittest
from unittest.mock import Mock
from hook_sender import HookSender


class AccountPinTests(unittest.TestCase):
    def setUp(self):
        self.sender=HookSender({'account_username':'wxid_example_owner','min_interval':0},
                               db=Mock(),allowed_targets={'g'})
        self.sender.session=Mock()

    def test_wrong_account_cannot_send_or_read_baseline(self):
        self.sender.session.post.return_value.json.return_value={'wxid':'wxid_example_other'}
        result=self.sender.send_msg('test','g',verify=True)
        self.assertFalse(result.is_success)
        self.sender.db.get_messages.assert_not_called()
        self.assertEqual(self.sender.session.post.call_count,1)
        self.assertTrue(self.sender.session.post.call_args.args[0].endswith('/GetSelfProfile'))

    def test_matching_account_can_send(self):
        identity=Mock();identity.json.return_value={'wxid':'wxid_example_owner'}
        accepted=Mock();accepted.json.return_value={'ret':0}
        self.sender.session.post.side_effect=[identity,accepted]
        self.assertTrue(self.sender.send_msg('test','g').is_success)
        self.assertEqual(self.sender.session.post.call_count,2)

    def test_health_rejects_another_account(self):
        self.sender.session.get.return_value.json.return_value={'hWeixin':1}
        self.sender.session.post.return_value.json.return_value={'wxid':'wxid_example_other'}
        with self.assertRaises(RuntimeError):self.sender.health()


if __name__=='__main__':unittest.main()
