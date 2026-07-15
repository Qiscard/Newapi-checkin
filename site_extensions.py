#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Host-specific post-check-in extensions."""

import os
from typing import Callable, List
from urllib.parse import urlparse

from lottery import run_for_account, run_gwent_for_account
from models import AccountConfig


def run_site_extensions(account: AccountConfig, client, quota_formatter: Callable[[int], str]) -> List[str]:
    host = (urlparse(account.url).hostname or '').lower()
    if host == 'lanxiu.cc' or host.endswith('.lanxiu.cc'):
        return _run_lanxiu(account, client, quota_formatter)
    if host == 'vsllm.com' or host.endswith('.vsllm.com'):
        return _run_vsllm(account, client, quota_formatter)
    return []


def _run_lanxiu(account: AccountConfig, client, quota_formatter: Callable[[int], str]) -> List[str]:
    if os.environ.get('GITHUB_ACTIONS'):
        return []
    user_info = getattr(client, 'user_info', None) or {}
    display_name = user_info.get('username') or account.login_username
    if not display_name:
        return []

    items = []
    for _ in range(2):
        prize, error = run_for_account(client.session, account.url, display_name)
        if error:
            line = f'⏭️ {error}'
            items.append(line)
            print(f'  抽奖: {line}')
            break
        if prize:
            line = f'🎉 {prize["prize_name"]} +{quota_formatter(prize.get("quota_awarded", 0))}'
            items.append(line)
            print(f'  抽奖: {line}')
            if prize.get('remaining_times', 0) <= 0:
                break
    return items


def _run_vsllm(account: AccountConfig, client, quota_formatter: Callable[[int], str]) -> List[str]:
    items = []
    for index in range(3):
        prize, error = run_gwent_for_account(client.session, account.url)
        if error:
            line = f'⏭️ {error}'
            items.append(line)
            print(f'  翻卡: {line}')
            break
        if prize:
            line = (
                f'🎉 第{index + 1}次 {prize["prize_name"]} '
                f'+{quota_formatter(prize.get("quota_awarded", 0))}'
            )
            items.append(line)
            print(f'  翻卡: {line}')
    return items
