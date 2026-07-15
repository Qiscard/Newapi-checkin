import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from application import run_application
from checkin_service import CheckinSummary
from config_loader import ConfigSource, LoadedConfig
from models import AccountConfig, CheckinResult


class ApplicationTests(unittest.TestCase):
    @patch('application.send_serverchan_notification')
    @patch('application.send_email_notification')
    @patch('application.send_checkin_notification')
    @patch('application.run_checkins')
    @patch('application.load_account_config')
    def test_failed_run_still_dispatches_all_configured_notifications(
        self,
        load_config,
        run_checkins_mock,
        send_dingtalk,
        send_email,
        send_serverchan,
    ):
        account = AccountConfig(url='https://api.example.com', session='session')
        result = CheckinResult(name='账号1', success=False, message='认证失败')
        load_config.return_value = LoadedConfig(
            accounts=[account],
            source=ConfigSource.ENVIRONMENT,
            env_file=Path('.env'),
        )
        run_checkins_mock.return_value = CheckinSummary(results=[result])

        with patch.dict('application.os.environ', {'SMTP_HOST': 'smtp.example.com'}, clear=True):
            with redirect_stdout(StringIO()):
                exit_code = run_application(object, str, str)

        self.assertEqual(exit_code, 1)
        send_dingtalk.assert_called_once()
        send_email.assert_called_once()
        send_serverchan.assert_called_once()


if __name__ == '__main__':
    unittest.main()
