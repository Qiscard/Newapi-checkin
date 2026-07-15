#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Email and ServerChan notification transports."""

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Iterable, Optional

import requests

from reporting import (
    build_report_html,
    build_report_markdown,
    build_report_text,
    format_quota,
    result_counts,
)


def send_email_notification(results: Iterable[Any], execution_time: Optional[str] = None) -> bool:
    items = list(results)
    host = os.environ.get('SMTP_HOST', '')
    user = os.environ.get('SMTP_USER', '')
    password = os.environ.get('SMTP_PASS', '')
    to_addr = os.environ.get('SMTP_TO', '')
    from_addr = os.environ.get('SMTP_FROM', user)

    if not all([host, user, password, to_addr]):
        print('[邮件通知] 未完整配置 SMTP_HOST/USER/PASS/TO，跳过通知')
        return False

    try:
        port = int(os.environ.get('SMTP_PORT', '465') or '465')
    except ValueError:
        print('[邮件通知] SMTP_PORT 不是有效端口，跳过通知')
        return False

    execution_time = execution_time or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    success_count, fail_count = result_counts(items)
    subject = _notification_title('NewAPI 签到', success_count, fail_count)

    message = MIMEMultipart('alternative')
    message['Subject'] = subject
    message['From'] = from_addr
    message['To'] = to_addr
    message.attach(MIMEText(build_report_text(items, execution_time), 'plain', 'utf-8'))
    message.attach(MIMEText(build_report_html(items, execution_time), 'html', 'utf-8'))

    server = None
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
        server.login(user, password)
        server.sendmail(from_addr, [to_addr], message.as_string())
        print(f'[邮件通知] 发送成功 -> {to_addr}')
        return True
    except Exception as exc:
        print(f'[邮件通知] 发送失败: {exc}')
        return False
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


def send_serverchan_notification(results: Iterable[Any], execution_time: Optional[str] = None) -> bool:
    items = list(results)
    send_key = os.environ.get('SERVERCHAN_SENDKEY', '')
    if not send_key:
        print('[ServerChan] 未配置 SERVERCHAN_SENDKEY，跳过通知')
        return False

    execution_time = execution_time or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    success_count, fail_count = result_counts(items)
    title = _notification_title('NewAPI 签到', success_count, fail_count)

    try:
        response = requests.post(
            f'https://sctapi.ftqq.com/{send_key}.send',
            data={'title': title, 'desp': build_report_markdown(items, execution_time)},
            timeout=15,
        )
        data = response.json()
        if data.get('code') == 0:
            print('[ServerChan] 推送成功')
            return True
        print(f'[ServerChan] 推送失败: {data.get("message", "未知错误")}')
    except Exception as exc:
        print(f'[ServerChan] 推送异常: {exc}')
    return False


def _notification_title(prefix: str, success_count: int, fail_count: int) -> str:
    if fail_count == 0:
        return f'{prefix}成功 ({success_count}个账号)'
    if success_count == 0:
        return f'{prefix}失败 ({fail_count}个账号)'
    return f'{prefix}完成 (成功{success_count}/失败{fail_count})'
