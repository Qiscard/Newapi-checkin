import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from checkin_service import run_checkins
from models import AccountConfig, CheckinResult


class FakeClient:
    def __init__(self, *args):
        self.session_cookie = args[1]
        self.session = object()

    def get_user_info(self):
        self.session_cookie = 'renewed-session'
        return {'username': 'tester'}

    def checkin(self):
        return {
            'success': True,
            'message': '签到成功',
            'checkin_date': '2026-07-14',
            'quota_awarded': 1000,
        }

    def get_checkin_history(self):
        return {'stats': {'checkin_count': 3, 'total_quota': 3000}}


class CheckinServiceTests(unittest.TestCase):
    @patch('checkin_service.run_site_extensions', return_value=['抽奖结果'])
    def test_returns_dataclass_results_and_tracks_session_updates(self, _extensions):
        account = AccountConfig(url='https://api.example.com', session='old-session')

        with redirect_stdout(StringIO()):
            summary = run_checkins(
                [account],
                FakeClient,
                lambda value: str(value),
                lambda value: value,
                lambda value: value,
            )

        self.assertTrue(summary.session_updated)
        self.assertEqual(account.session, 'renewed-session')
        self.assertIsInstance(summary.results[0], CheckinResult)
        self.assertEqual(summary.results[0].lottery, ['抽奖结果'])
        self.assertEqual(summary.success_count, 1)


if __name__ == '__main__':
    unittest.main()
