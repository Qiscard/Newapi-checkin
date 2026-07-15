#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Application entry orchestration for scheduled and local runs."""

import os
from datetime import datetime

import pytz

from checkin_service import run_checkins
from config_loader import ConfigSource, load_account_config, write_accounts_to_env_atomic
from dingtalk_notifier import send_checkin_notification
from notifier import format_quota, send_email_notification, send_serverchan_notification


def run_application(client_factory, url_masker, user_id_masker) -> int:
    beijing_tz = pytz.timezone('Asia/Shanghai')
    execution_time = datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')

    print('=' * 50)
    print('NewAPI 自动签到')
    print(f'执行时间: {execution_time}')
    print('=' * 50)

    try:
        loaded = load_account_config()
    except ValueError as exc:
        print(f'[错误] {exc}')
        print('请设置 CONFIG_URL（云端配置）或 NEWAPI_ACCOUNTS（本地配置）环境变量')
        return 1

    print(f'配置来源: {loaded.source.value}')
    print(f'共 {len(loaded.accounts)} 个账号待签到\n')

    summary = run_checkins(
        loaded.accounts,
        client_factory,
        format_quota,
        url_masker,
        user_id_masker,
    )

    print('=' * 50)
    print(f'签到完成: 成功 {summary.success_count}, 失败 {summary.fail_count}')
    print('=' * 50)

    # Notifications are dispatched before deciding the process exit status so
    # failed runs still produce a complete report in every configured channel.
    print('正在发送签到结果通知...')
    send_checkin_notification(summary.results, execution_time)
    if os.environ.get('SMTP_HOST'):
        send_email_notification(summary.results, execution_time)
    send_serverchan_notification(summary.results, execution_time)

    if (
        loaded.source == ConfigSource.ENV_FILE
        and summary.session_updated
        and not os.environ.get('GITHUB_ACTIONS')
    ):
        print('\n[Session] 检测到 session 已更新，正在原子回写 .env...')
        try:
            write_accounts_to_env_atomic(loaded.env_file, loaded.accounts)
            print('[Session] .env 已更新')
        except OSError as exc:
            print(f'[Session] .env 更新失败: {exc}')

    return 1 if summary.fail_count == len(loaded.accounts) else 0
