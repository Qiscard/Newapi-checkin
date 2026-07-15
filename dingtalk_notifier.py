#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DingTalk robot notification transport."""

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
from datetime import datetime
from typing import Any, Iterable, Optional

import requests

from reporting import build_report_markdown, result_counts


class DingTalkNotifier:
    def __init__(self, webhook_url: str, secret: Optional[str] = None):
        self.webhook_url = webhook_url
        self.secret = secret

    def send_markdown(self, title: str, text: str) -> bool:
        data = {
            'msgtype': 'markdown',
            'markdown': {'title': title, 'text': text},
            'at': {'atMobiles': [], 'isAtAll': False},
        }
        try:
            response = requests.post(
                self._signed_url(),
                headers={'Content-Type': 'application/json'},
                data=json.dumps(data, ensure_ascii=False),
                timeout=10,
            )
            result = response.json()
            if result.get('errcode') == 0:
                print('[钉钉通知] 消息发送成功')
                return True
            print(f'[钉钉通知] 发送失败: {result.get("errmsg", "未知错误")}')
        except Exception as exc:
            print(f'[钉钉通知] 发送异常: {exc}')
        return False

    def _signed_url(self) -> str:
        if not self.secret:
            return self.webhook_url
        timestamp = str(round(time.time() * 1000))
        signature = hmac.new(
            self.secret.encode('utf-8'),
            f'{timestamp}\n{self.secret}'.encode('utf-8'),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(signature))
        separator = '&' if '?' in self.webhook_url else '?'
        return f'{self.webhook_url}{separator}timestamp={timestamp}&sign={sign}'


def build_checkin_report(results: Iterable[Any], execution_time: str) -> str:
    return build_report_markdown(results, execution_time)


def send_checkin_notification(results: Iterable[Any], execution_time: Optional[str] = None) -> bool:
    items = list(results)
    webhook_url = os.environ.get('DINGTALK_WEBHOOK', '')
    if not webhook_url:
        print('[钉钉通知] 未配置 DINGTALK_WEBHOOK，跳过通知')
        return False

    execution_time = execution_time or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    success_count, fail_count = result_counts(items)
    if fail_count == 0:
        title = f'签到成功 ({success_count}个账号)'
    elif success_count == 0:
        title = f'签到失败 ({fail_count}个账号)'
    else:
        title = f'签到完成 (成功{success_count}/失败{fail_count})'

    notifier = DingTalkNotifier(
        webhook_url,
        os.environ.get('DINGTALK_SECRET') or None,
    )
    return notifier.send_markdown(title, build_report_markdown(items, execution_time))
