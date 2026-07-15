#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewAPI 自动签到脚本
支持多账号签到，通过 GitHub Actions 定时执行
"""

import sys
import json
import requests
from datetime import datetime
from typing import Optional

try:
    from cf_bypass import detect_cloudflare_block, CloudflareBypasser
    CF_BYPASS_AVAILABLE = True
except ImportError:
    CF_BYPASS_AVAILABLE = False
    detect_cloudflare_block = None
    CloudflareBypasser = None

class NewAPICheckin:
    """NewAPI 签到类"""

    @staticmethod
    def _mask_url(url: str) -> str:
        """
        脱敏 URL，隐藏域名细节
        例如: https://api.example.com -> https://api.***.**
        """
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain_parts = parsed.netloc.split('.')
            if len(domain_parts) >= 2:
                # 保留第一部分和最后一部分，中间用 *** 代替
                masked_domain = f"{domain_parts[0]}.***." + '.'.join(domain_parts[-1:])
            else:
                masked_domain = '***'
            return f"{parsed.scheme}://{masked_domain}"
        except Exception:
            return 'https://***'

    @staticmethod
    def _mask_user_id(user_id: str) -> str:
        """
        脱敏用户ID
        例如: 1429 -> ****
        """
        return '****'

    def __init__(self, base_url: str, session_cookie: str, user_id: str = None, cf_clearance: str = None,
                 login_username: str = None, login_password: str = None):
        self.base_url = base_url.rstrip('/')
        self.session_cookie = session_cookie
        self.login_username = login_username
        self.login_password = login_password
        self.session = requests.Session()
        self.session.cookies.set('session', session_cookie)

        if cf_clearance:
            self.session.cookies.set('cf_clearance', cf_clearance)

        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'no-store',
            'Pragma': 'no-cache',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })

        self.user_id = user_id
        if user_id:
            self.session.headers.update({'new-api-user': str(user_id)})

    def _try_login(self) -> bool:
        """
        尝试使用配置的账号密码重新登录，获取新的 session

        登录接口：POST /api/user/login
        请求体：{"username": x, "password": x}
        成功时 cookie 中包含新的 session_id

        Returns:
            True 如果登录成功，False 否则
        """
        if not self.login_username or not self.login_password:
            return False

        print(f'  [登录] 尝试重新登录...')
        try:
            resp = self.session.post(
                f'{self.base_url}/api/user/login',
                json={'username': self.login_username, 'password': self.login_password},
                timeout=30
            )

            if resp.status_code == 429:
                print(f'  [登录] 请求过多 (429)，跳过登录')
                return False

            try:
                data = resp.json()
            except json.JSONDecodeError:
                content_preview = resp.text[:100] if resp.text else '(空响应)'
                print(f'  [登录] 响应格式错误 (HTTP {resp.status_code}): {content_preview}')
                return False

            if resp.status_code == 200 and data.get('success'):
                # 从响应 cookie 中获取新的 session_id
                new_session = None
                for cookie in resp.cookies:
                    if cookie.name == 'session' or cookie.name == 'session_id':
                        new_session = cookie.value
                        break

                if new_session:
                    self.session_cookie = new_session
                    self.session.cookies.set('session', new_session)
                    print(f'  [登录] 登录成功，已更新 session')
                    return True
                else:
                    # 可能 session cookie 在 set-cookie 头中
                    set_cookie = resp.headers.get('Set-Cookie', '')
                    import re
                    match = re.search(r'(?:session|session_id)=([^;]+)', set_cookie)
                    if match:
                        new_session = match.group(1)
                        self.session_cookie = new_session
                        self.session.cookies.set('session', new_session)
                        print(f'  [登录] 登录成功，已更新 session')
                        return True

                    print(f'  [登录] 登录成功但未获取到新的 session cookie')
                    return False
            else:
                msg = data.get('message', '未知错误')
                print(f'  [登录] 登录失败: {msg}')
                return False

        except Exception as e:
            print(f'  [登录] 登录请求异常: {e}')
            return False

    def get_user_info(self, verbose: bool = False) -> Optional[dict]:
        """
        获取用户信息

        自动设置 new-api-user 请求头

        Args:
            verbose: 是否显示详细调试信息
        """
        try:
            resp = self.session.get(f'{self.base_url}/api/user/self', timeout=30)

            if verbose:
                print(f'  [调试] HTTP 状态码: {resp.status_code}')
                print(f'  [调试] 响应内容预览: {resp.text[:200]}...')

            # 检查认证失败
            if resp.status_code == 401:
                print(f'[错误] 认证失败 (401): Session 可能已过期')
                if verbose:
                    print(f'  [调试] 完整响应: {resp.text[:500]}')

                # 尝试自动登录
                if self._try_login():
                    print(f'  [登录] 重试获取用户信息...')
                    resp = self.session.get(f'{self.base_url}/api/user/self', timeout=30)
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            if data.get('success'):
                                user_data = data.get('data')
                                if user_data and 'id' in user_data:
                                    self.user_id = user_data['id']
                                    self.session.headers.update({
                                        'new-api-user': str(self.user_id)
                                    })
                                return user_data
                        except Exception:
                            pass
                    print(f'  [登录] 重试后仍无法获取用户信息')
                    return None
                else:
                    if self.login_username and self.login_password:
                        print('  [登录] 尝试登录不成功')
                    else:
                        print('  [登录] 未配置账号密码，无法自动重新登录')
                    return None

            # 尝试解析 JSON
            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                # 检测是否是 Cloudflare 拦截
                if detect_cloudflare_block:
                    is_blocked, reason = detect_cloudflare_block(resp.status_code, resp.text)
                    if is_blocked:
                        print(f'[CF] 获取用户信息时检测到 Cloudflare 拦截: {reason}')
                        print(f'[CF] 该站点需要 CF 绕过才能访问')
                        return None
                print(f'[错误] 响应格式错误 (HTTP {resp.status_code}): 无法解析 JSON')
                if verbose:
                    print(f'  [调试] 原始响应: {resp.text[:500]}')
                return None

            if verbose:
                print(f'  [调试] success 字段: {data.get("success")}')
                print(f'  [调试] message 字段: {data.get("message")}')

            if resp.status_code == 200:
                if data.get('success'):
                    user_data = data.get('data')
                    # 保存用户ID并设置到请求头
                    if user_data and 'id' in user_data:
                        self.user_id = user_data['id']
                        self.session.headers.update({
                            'new-api-user': str(self.user_id)
                        })
                    return user_data
                else:
                    if verbose:
                        print(f'  [调试] API 返回失败: {data.get("message", "未知错误")}')
            else:
                print(f'[错误] HTTP {resp.status_code}: {data.get("message", "未知错误")}')

            return None

        except requests.exceptions.Timeout:
            print(f'[错误] 请求超时')
            return None
        except requests.exceptions.RequestException as e:
            print(f'[错误] 网络请求失败: {e}')
            return None
        except Exception as e:
            print(f'[错误] 未知错误: {e}')
            if verbose:
                import traceback
                traceback.print_exc()
            return None

    def checkin(self) -> dict:
        """
        执行签到

        流程（借鉴 Chrome 扩展 background.js:115-248）：
        1. requests 直连签到（快速模式）
        2. CF 拦截检测 → Playwright 获取 cookie 后重新签到
        3. 仍然失败 → Playwright 浏览器内直接签到（终极回退）

        Returns:
            签到结果字典
        """
        result = {
            'success': False,
            'message': '',
            'checkin_date': None,
            'quota_awarded': None
        }

        try:
            resp = self.session.post(f'{self.base_url}/api/user/checkin', timeout=30)

            if resp.status_code == 401:
                result['message'] = '认证失败: Session 可能已过期，请重新获取'
                # 尝试自动登录
                if self._try_login():
                    print(f'  [登录] 重试签到...')
                    resp = self.session.post(f'{self.base_url}/api/user/checkin', timeout=30)
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            if data.get('success'):
                                result['success'] = True
                                result['message'] = data.get('message', '签到成功')
                                checkin_data = data.get('data', {})
                                result['checkin_date'] = checkin_data.get('checkin_date')
                                result['quota_awarded'] = checkin_data.get('quota_awarded')
                                return result
                        except Exception:
                            pass
                    result['message'] = '重新登录后签到失败'
                    return result
                else:
                    if self.login_username and self.login_password:
                        result['message'] = '尝试登录不成功'
                    return result

            try:
                data = resp.json()
            except json.JSONDecodeError:
                if detect_cloudflare_block:
                    is_blocked, reason = detect_cloudflare_block(resp.status_code, resp.text)
                    if is_blocked:
                        print(f'[CF] 检测到 Cloudflare 拦截: {reason}')
                        return self._cf_bypass_checkin()
                content_preview = resp.text[:200] if resp.text else '(空响应)'
                result['message'] = f'响应格式错误 (HTTP {resp.status_code}): {content_preview}'
                return result

            if detect_cloudflare_block and resp.status_code in (403, 503):
                is_blocked, reason = detect_cloudflare_block(resp.status_code, json.dumps(data))
                if is_blocked:
                    print(f'[CF] 检测到 Cloudflare 拦截: {reason}')
                    return self._cf_bypass_checkin()

            if resp.status_code == 200:
                if data.get('success'):
                    result['success'] = True
                    result['message'] = data.get('message', '签到成功')

                    checkin_data = data.get('data', {})
                    result['checkin_date'] = checkin_data.get('checkin_date')
                    result['quota_awarded'] = checkin_data.get('quota_awarded')
                else:
                    message = data.get('message', '签到失败')
                    already_keywords = ['已签到', '已经签到', 'already', '重复签到']
                    already_checked_in = any(k in message for k in already_keywords)
                    if already_checked_in:
                        result['success'] = True
                        result['message'] = message
                    else:
                        result['message'] = message
            else:
                result['message'] = f'HTTP {resp.status_code}: {data.get("message", "未知错误")}'

        except requests.exceptions.Timeout:
            result['message'] = '请求超时'
        except requests.exceptions.RequestException as e:
            result['message'] = f'网络请求失败: {e}'
        except Exception as e:
            result['message'] = f'未知错误: {e}'

        return result

    def _cf_bypass_checkin(self) -> dict:
        """
        CF 绕过签到流程

        在同一个 Playwright 会话中完成 CF 绕过 + 签到，
        不拆分 cookie 提取和 requests 重试（因为 cf_clearance 绑定浏览器指纹）
        """
        result = {
            'success': False,
            'message': '',
            'checkin_date': None,
            'quota_awarded': None
        }

        if not CF_BYPASS_AVAILABLE or not CloudflareBypasser:
            result['message'] = 'Cloudflare 拦截: 需安装 Playwright 才能自动绕过 (pip install playwright && playwright install chromium)'
            return result

        bypasser = CloudflareBypasser(self.base_url, self.session_cookie, self.user_id)

        if not bypasser.is_available():
            result['message'] = 'Cloudflare 拦截: Playwright 未正确安装'
            return result

        print('[CF] 开始 Playwright 绕过流程...')
        browser_result = bypasser.bypass_and_checkin()

        if not browser_result:
            result['message'] = 'Cloudflare 绕过失败: 无法通过 CF 验证'
            return result

        if browser_result.get('error'):
            result['message'] = f'CF 绕过后签到失败: {browser_result["error"]}'
            return result

        if browser_result.get('alreadyCheckedIn'):
            result['success'] = True
            result['message'] = browser_result.get('message', '今日已签到 (CF绕过)')
        elif browser_result.get('success'):
            result['success'] = True
            result['message'] = browser_result.get('message', '签到成功 (CF绕过)')
            data = browser_result.get('data', {})
            if isinstance(data, dict):
                checkin_data = data.get('data', data)
                result['checkin_date'] = checkin_data.get('checkin_date')
                result['quota_awarded'] = checkin_data.get('quota_awarded')
        else:
            result['message'] = browser_result.get('message', 'CF 绕过后签到失败')

        return result

    def get_checkin_history(self, month: str = None) -> Optional[dict]:
        """
        获取签到历史

        Args:
            month: 月份，格式 YYYY-MM，默认当前月
        """
        if month is None:
            month = datetime.now().strftime('%Y-%m')

        try:
            resp = self.session.get(
                f'{self.base_url}/api/user/checkin',
                params={'month': month},
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data')
            return None
        except Exception as e:
            print(f'[错误] 获取签到历史失败: {e}')
            return None


if __name__ == '__main__':
    from application import run_application

    sys.exit(run_application(
        NewAPICheckin,
        NewAPICheckin._mask_url,
        NewAPICheckin._mask_user_id,
    ))
