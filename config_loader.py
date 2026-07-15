#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Configuration loading, source tracking, and atomic local persistence."""

import base64
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Mapping, MutableMapping, Optional, Set
from urllib.parse import urlparse

import requests

from models import AccountConfig


class ConfigSource(str, Enum):
    CLOUD = 'cloud'
    ENVIRONMENT = 'environment'
    ENV_FILE = 'env_file'


@dataclass
class LoadedConfig:
    accounts: List[AccountConfig]
    source: ConfigSource
    env_file: Path


def parse_accounts(accounts_str: str) -> List[AccountConfig]:
    """Parse JSON or the legacy URL#SESSION comma-separated format."""
    if not accounts_str:
        return []

    try:
        data = json.loads(accounts_str)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, list):
        accounts = []
        for item in data:
            if isinstance(item, dict) and item.get('url') and item.get('session'):
                accounts.append(AccountConfig.from_dict(item))
        return accounts

    accounts = []
    for part in accounts_str.split(','):
        part = part.strip()
        if '#' not in part:
            continue
        url, session = part.split('#', 1)
        if url.strip() and session.strip():
            accounts.append(AccountConfig(url=url.strip(), session=session.strip()))
    return accounts


def load_env_file(
    env_file: Optional[Path] = None,
    environ: Optional[MutableMapping[str, str]] = None,
) -> Set[str]:
    """Load missing variables from .env and return the keys sourced from it."""
    target = env_file or Path(__file__).resolve().with_name('.env')
    env = environ if environ is not None else os.environ
    loaded_keys: Set[str] = set()

    if not target.is_file():
        return loaded_keys

    with target.open('r', encoding='utf-8') as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip()
            if key and value and key not in env:
                env[key] = value
                loaded_keys.add(key)
    return loaded_keys


def load_config_from_cloud(
    config_url: str,
    config_auth: str = '',
    environ: Optional[MutableMapping[str, str]] = None,
) -> Optional[str]:
    """Download an account list and optional notification settings."""
    env = environ if environ is not None else os.environ
    headers = {}
    if config_auth:
        if config_auth.startswith('token:'):
            headers['Authorization'] = 'Bearer ' + config_auth[6:]
        elif ':' in config_auth:
            credentials = base64.b64encode(config_auth.encode('utf-8')).decode('utf-8')
            headers['Authorization'] = 'Basic ' + credentials

    print(f'[云端] 正在从云端加载配置: {_mask_url(config_url)}')
    try:
        response = requests.get(config_url, headers=headers, timeout=30)
        if response.status_code == 401:
            print('[云端] 认证失败: 请检查 CONFIG_AUTH 配置')
            return None
        if response.status_code == 404:
            print('[云端] 配置文件不存在')
            return None
        if response.status_code != 200:
            print(f'[云端] 加载失败: HTTP {response.status_code}')
            return None

        data = response.json()
        if isinstance(data, list):
            accounts = data
        elif isinstance(data, dict) and isinstance(data.get('accounts'), list):
            accounts = data['accounts']
            _load_notification_settings(data, env)
        else:
            print('[云端] 配置格式错误: 无法解析账号列表')
            return None

        print(f'[云端] 成功加载 {len(accounts)} 个账号配置')
        return json.dumps(accounts, ensure_ascii=False)
    except json.JSONDecodeError:
        print('[云端] 配置文件不是有效的 JSON 格式')
    except requests.exceptions.Timeout:
        print('[云端] 请求超时')
    except requests.exceptions.RequestException as exc:
        print(f'[云端] 网络请求失败: {exc}')
    except Exception as exc:
        print(f'[云端] 加载失败: {exc}')
    return None


def load_account_config(
    env_file: Optional[Path] = None,
    environ: Optional[MutableMapping[str, str]] = None,
) -> LoadedConfig:
    """Load accounts while preserving whether NEWAPI_ACCOUNTS came from .env."""
    target = env_file or Path(__file__).resolve().with_name('.env')
    env = environ if environ is not None else os.environ
    accounts_preexisting = bool(env.get('NEWAPI_ACCOUNTS'))
    loaded_keys = load_env_file(target, env)

    config_url = env.get('CONFIG_URL', '')
    if config_url:
        cloud_value = load_config_from_cloud(config_url, env.get('CONFIG_AUTH', ''), env)
        if cloud_value:
            accounts = parse_accounts(cloud_value)
            if accounts:
                return LoadedConfig(accounts, ConfigSource.CLOUD, target)

    accounts_value = env.get('NEWAPI_ACCOUNTS', '')
    accounts = parse_accounts(accounts_value)
    if not accounts:
        raise ValueError('未配置账号信息或账号配置解析失败')

    source = ConfigSource.ENVIRONMENT
    if not accounts_preexisting and 'NEWAPI_ACCOUNTS' in loaded_keys:
        source = ConfigSource.ENV_FILE
    return LoadedConfig(accounts, source, target)


def write_accounts_to_env_atomic(env_file: Path, accounts: Iterable[AccountConfig]) -> None:
    """Atomically replace the NEWAPI_ACCOUNTS line while preserving the file."""
    target = Path(env_file)
    with target.open('r', encoding='utf-8', newline='') as handle:
        content = handle.read()
    newline = '\r\n' if '\r\n' in content else '\n'
    value = json.dumps([account.to_dict() for account in accounts], ensure_ascii=False)
    replacement = f'NEWAPI_ACCOUNTS={value}'
    pattern = re.compile(r'^NEWAPI_ACCOUNTS=.*?(?=\r?$)', re.MULTILINE)

    if pattern.search(content):
        updated = pattern.sub(lambda _: replacement, content, count=1)
    else:
        separator = '' if not content or content.endswith(('\n', '\r')) else newline
        updated = content + separator + replacement + newline

    mode = stat.S_IMODE(target.stat().st_mode)
    fd, temp_name = tempfile.mkstemp(prefix=f'.{target.name}.', suffix='.tmp', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _load_notification_settings(data: Mapping[str, object], env: MutableMapping[str, str]) -> None:
    mappings = {
        'dingtalk': {
            'webhook': 'DINGTALK_WEBHOOK',
            'secret': 'DINGTALK_SECRET',
        },
        'email': {
            'smtp_host': 'SMTP_HOST',
            'smtp_port': 'SMTP_PORT',
            'user': 'SMTP_USER',
            'pass': 'SMTP_PASS',
            'to': 'SMTP_TO',
            'from_addr': 'SMTP_FROM',
        },
        'serverchan': {'sendkey': 'SERVERCHAN_SENDKEY'},
    }
    for section, fields in mappings.items():
        values = data.get(section)
        if not isinstance(values, Mapping):
            continue
        loaded = False
        for source_key, env_key in fields.items():
            value = values.get(source_key)
            if value and not env.get(env_key):
                env[env_key] = str(value)
                loaded = True
        if loaded:
            print(f'[云端] 已加载 {section} 通知配置')


def _mask_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ''
        parts = host.split('.')
        masked = f'{parts[0]}.***.{parts[-1]}' if len(parts) >= 2 else '***'
        return f'{parsed.scheme}://{masked}'
    except Exception:
        return 'https://***'
