#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared, escaped report rendering for all notification channels."""

import html
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, List, Tuple


def format_quota(quota: int) -> str:
    value = int(quota or 0)
    if value >= 1_000_000:
        return f'{value / 1_000_000:.2f}M'
    if value >= 1_000:
        return f'{value / 1_000:.2f}K'
    return str(value)


def build_report_text(results: Iterable[Any], execution_time: str) -> str:
    items, success, failed = _partition(results)
    lines = ['NewAPI 签到报告', f'执行时间: {execution_time}', '', '-' * 40, '']

    if success:
        lines.append(f'成功 ({len(success)}个):')
        for item in success:
            lines.append(
                f'  {_plain(item.get("name", "未知账号"))} | '
                f'{_quota_text(item)} | {_detail(item)} | {_lottery_text(item)}'
            )
        lines.append('')

    if failed:
        lines.append(f'失败 ({len(failed)}个):')
        for item in failed:
            message = _plain(item.get('message', '未知错误'))
            if _session_expired(item):
                message = f'[Session失效] {message}'
            lines.append(f'  {_plain(item.get("name", "未知账号"))} | {message}')
        lines.append('')

    lines.extend(['-' * 40, _summary_text(items, success, failed)])
    if any(_session_expired(item) for item in failed):
        lines.extend(['', '注意: 部分账号 Session 已失效，请及时更新 Cookie！'])
    return '\n'.join(lines)


def build_report_markdown(results: Iterable[Any], execution_time: str) -> str:
    items, success, failed = _partition(results)
    lines = ['# NewAPI 签到报告', '', f'**执行时间**: {_md(execution_time)}', '']

    if success:
        lines.extend([
            f'## 成功 ({len(success)}个)', '',
            '| 账号 | 奖励 | 详情 | 抽奖 |',
            '|---|---|---|---|',
        ])
        for item in success:
            lines.append(
                f'| {_md(item.get("name", "未知账号"))} '
                f'| {_md(_quota_text(item))} '
                f'| {_md(_detail(item))} '
                f'| {_md(_lottery_text(item))} |'
            )
        lines.append('')

    if failed:
        lines.extend([f'## 失败 ({len(failed)}个)', '', '| 账号 | 原因 |', '|---|---|'])
        for item in failed:
            message = item.get('message', '未知错误')
            if _session_expired(item):
                message = f'Session失效: {message}'
            lines.append(f'| {_md(item.get("name", "未知账号"))} | {_md(message)} |')
        lines.append('')

    lines.extend(['---', '', f'**{_md(_summary_text(items, success, failed))}**'])
    if any(_session_expired(item) for item in failed):
        lines.extend(['', '> 注意: 部分账号 Session 已失效，请及时更新 Cookie！'])
    return '\n'.join(lines)


def build_report_html(results: Iterable[Any], execution_time: str) -> str:
    items, success, failed = _partition(results)
    rows: List[str] = []

    if success:
        rows.append(f'<tr><th colspan="4">成功 ({len(success)}个)</th></tr>')
        for item in success:
            rows.append(
                '<tr>'
                f'<td>{_html(item.get("name", "未知账号"))}</td>'
                f'<td>{_html(_quota_text(item))}</td>'
                f'<td>{_html(_detail(item))}</td>'
                f'<td>{_html(_lottery_text(item))}</td>'
                '</tr>'
            )

    if failed:
        rows.append(f'<tr><th colspan="4">失败 ({len(failed)}个)</th></tr>')
        for item in failed:
            message = item.get('message', '未知错误')
            if _session_expired(item):
                message = f'Session失效: {message}'
            rows.append(
                '<tr>'
                f'<td>{_html(item.get("name", "未知账号"))}</td>'
                f'<td colspan="3" class="failed">{_html(message)}</td>'
                '</tr>'
            )

    warning = ''
    if any(_session_expired(item) for item in failed):
        warning = '<p class="warning">部分账号 Session 已失效，请及时更新 Cookie！</p>'

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><style>
body{{font-family:Arial,sans-serif;color:#24292f;margin:0;padding:20px}}
.report{{max-width:680px;margin:auto;border:1px solid #d0d7de}}
header{{background:#24292f;color:#fff;padding:16px 20px}}
main{{padding:18px 20px}} table{{width:100%;border-collapse:collapse}}
th,td{{padding:8px 10px;border-bottom:1px solid #d8dee4;text-align:left}}
th{{background:#f6f8fa}} .failed,.warning{{color:#cf222e}}
.meta{{color:#57606a}} .summary{{font-weight:700}}
</style></head>
<body><section class="report"><header><strong>NewAPI 签到报告</strong></header><main>
<p class="meta">执行时间: {_html(execution_time)}</p>
<table><thead><tr><th>账号</th><th>奖励</th><th>详情</th><th>抽奖</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p class="summary">{_html(_summary_text(items, success, failed))}</p>{warning}
</main></section></body></html>'''


def result_counts(results: Iterable[Any]) -> Tuple[int, int]:
    _, success, failed = _partition(results)
    return len(success), len(failed)


def _partition(results: Iterable[Any]):
    items = [_to_dict(item) for item in results]
    success = [item for item in items if item.get('success')]
    failed = [item for item in items if not item.get('success')]
    return items, success, failed


def _to_dict(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    if is_dataclass(item):
        return asdict(item)
    if hasattr(item, 'to_dict'):
        return item.to_dict()
    raise TypeError(f'不支持的签到结果类型: {type(item)!r}')


def _quota_text(item: Dict[str, Any]) -> str:
    quota = int(item.get('quota_awarded') or 0)
    return f'+{format_quota(quota)}' if quota > 0 else '-'


def _detail(item: Dict[str, Any]) -> str:
    count = int(item.get('checkin_count') or 0)
    return f'已签 {count} 天' if count else _plain(item.get('message', '成功'))


def _lottery_text(item: Dict[str, Any]) -> str:
    return ' / '.join(_plain(value) for value in item.get('lottery', [])) or '-'


def _summary_text(items, success, failed) -> str:
    if not failed:
        return f'汇总: 全部成功 ({len(success)}/{len(items)})'
    if not success:
        return f'汇总: 全部失败 ({len(failed)}/{len(items)})'
    return f'汇总: 成功 {len(success)}，失败 {len(failed)}'


def _session_expired(item: Dict[str, Any]) -> bool:
    message = str(item.get('message', ''))
    return bool(item.get('session_expired')) or 'session' in message.lower() or '认证' in message or '过期' in message


def _plain(value: Any) -> str:
    return str(value).replace('\r', ' ').replace('\n', ' ').strip()


def _html(value: Any) -> str:
    return html.escape(_plain(value), quote=True)


def _md(value: Any) -> str:
    return _html(value).replace('\\', '\\\\').replace('|', '\\|')
