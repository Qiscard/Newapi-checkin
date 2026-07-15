#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch check-in orchestration independent from configuration loading."""

from dataclasses import dataclass
from typing import Callable, List

from models import AccountConfig, CheckinResult
from site_extensions import run_site_extensions


@dataclass
class CheckinSummary:
    results: List[CheckinResult]
    session_updated: bool = False

    @property
    def success_count(self) -> int:
        return sum(result.success for result in self.results)

    @property
    def fail_count(self) -> int:
        return len(self.results) - self.success_count


def run_checkins(
    accounts: List[AccountConfig],
    client_factory: Callable[..., object],
    quota_formatter: Callable[[int], str],
    url_masker: Callable[[str], str],
    user_id_masker: Callable[[str], str],
) -> CheckinSummary:
    results: List[CheckinResult] = []
    session_updated = False

    for index, account in enumerate(accounts, 1):
        name = account.display_name(index)
        print(f'[{index}/{len(accounts)}] {name}')
        print(f'  站点: {url_masker(account.url)}')
        if account.user_id:
            print(f'  用户ID: {user_id_masker(account.user_id)}')

        original_session = account.session
        client = client_factory(
            account.url,
            account.session,
            account.user_id,
            account.cf_clearance,
            account.login_username,
            account.login_password,
        )

        user_info = client.get_user_info()
        client.user_info = user_info
        if client.session_cookie != original_session:
            account.session = client.session_cookie
            session_updated = True

        if user_info:
            username = user_info.get('username', '未知')
            masked_username = username[:3] + '***' if len(username) > 3 else '***'
            print(f'  用户: {masked_username}')
        else:
            print('  用户: 获取失败（可能 session 已过期）')

        attempt = client.checkin()
        if client.session_cookie != original_session:
            account.session = client.session_cookie
            session_updated = True

        if not attempt['success']:
            message = attempt.get('message', '')
            print(f'  结果: ❌ {message}')
            results.append(CheckinResult(
                name=name,
                success=False,
                message=message,
                session_expired='session' in message.lower() or '认证' in message or '过期' in message,
            ))
            print()
            continue

        print(f'  结果: ✅ {attempt["message"]}')
        if attempt.get('checkin_date'):
            print(f'  日期: {attempt["checkin_date"]}')
        quota = attempt.get('quota_awarded')
        if quota:
            print(f'  奖励: +{quota_formatter(quota)} 额度 ({quota:,} tokens)')

        checkin_count = 0
        history = client.get_checkin_history()
        if history and history.get('stats'):
            stats = history['stats']
            checkin_count = stats.get('checkin_count', 0)
            total_quota = stats.get('total_quota', 0)
            print(f'  统计: 本月已签 {checkin_count} 天，累计 {quota_formatter(total_quota)} 额度')

        lottery_items = run_site_extensions(account, client, quota_formatter)
        results.append(CheckinResult(
            name=name,
            success=True,
            message=attempt['message'],
            quota_awarded=quota,
            checkin_count=checkin_count,
            lottery=lottery_items,
        ))
        print()

    return CheckinSummary(results=results, session_updated=session_updated)
