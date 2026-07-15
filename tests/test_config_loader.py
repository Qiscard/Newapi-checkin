import json
import tempfile
import unittest
from pathlib import Path

from config_loader import (
    ConfigSource,
    load_account_config,
    parse_accounts,
    write_accounts_to_env_atomic,
)
from models import AccountConfig


class ConfigLoaderTests(unittest.TestCase):
    def test_parse_json_accounts_into_dataclasses(self):
        raw = json.dumps([{
            'url': 'https://api.example.com/',
            'session': 'session-value',
            'name': '主账号',
            'user_id': 123,
        }])

        accounts = parse_accounts(raw)

        self.assertEqual(len(accounts), 1)
        self.assertIsInstance(accounts[0], AccountConfig)
        self.assertEqual(accounts[0].user_id, '123')

    def test_tracks_env_file_as_the_account_source(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / '.env'
            env_file.write_text(
                'NEWAPI_ACCOUNTS=' + json.dumps([
                    {'url': 'https://api.example.com', 'session': 'from-file'}
                ]) + '\n',
                encoding='utf-8',
            )
            environ = {}

            loaded = load_account_config(env_file=env_file, environ=environ)

            self.assertEqual(loaded.source, ConfigSource.ENV_FILE)
            self.assertEqual(loaded.accounts[0].session, 'from-file')

    def test_external_environment_takes_precedence_over_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / '.env'
            env_file.write_text(
                'NEWAPI_ACCOUNTS=' + json.dumps([
                    {'url': 'https://api.example.com', 'session': 'from-file'}
                ]) + '\n',
                encoding='utf-8',
            )
            environ = {
                'NEWAPI_ACCOUNTS': json.dumps([
                    {'url': 'https://api.example.com', 'session': 'from-environment'}
                ])
            }

            loaded = load_account_config(env_file=env_file, environ=environ)

            self.assertEqual(loaded.source, ConfigSource.ENVIRONMENT)
            self.assertEqual(loaded.accounts[0].session, 'from-environment')

    def test_atomic_write_replaces_only_accounts_line(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / '.env'
            env_file.write_text(
                '# keep this comment\n'
                'NEWAPI_ACCOUNTS=[]\n'
                'SMTP_HOST=smtp.example.com\n',
                encoding='utf-8',
            )
            accounts = [AccountConfig(
                url='https://api.example.com',
                session='renewed-session',
                name='主账号',
            )]

            write_accounts_to_env_atomic(env_file, accounts)

            content = env_file.read_text(encoding='utf-8')
            self.assertIn('# keep this comment', content)
            self.assertIn('SMTP_HOST=smtp.example.com', content)
            self.assertIn('renewed-session', content)
            self.assertEqual(content.count('NEWAPI_ACCOUNTS='), 1)
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])

    def test_atomic_write_preserves_crlf_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / '.env'
            with env_file.open('w', encoding='utf-8', newline='') as handle:
                handle.write('NEWAPI_ACCOUNTS=[]\r\nSMTP_HOST=smtp.example.com\r\n')

            write_accounts_to_env_atomic(
                env_file,
                [AccountConfig(url='https://api.example.com', session='renewed')],
            )

            with env_file.open('r', encoding='utf-8', newline='') as handle:
                content = handle.read()
            self.assertIn('\r\nSMTP_HOST=', content)
            self.assertNotIn('\nSMTP_HOST=', content.replace('\r\n', ''))


if __name__ == '__main__':
    unittest.main()
