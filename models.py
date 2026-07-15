#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared data models for account configuration and check-in reports."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AccountConfig:
    """Configuration required to process one NewAPI account."""

    url: str
    session: str
    name: str = ''
    user_id: Optional[str] = None
    cf_clearance: Optional[str] = None
    login_username: Optional[str] = None
    login_password: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AccountConfig':
        return cls(
            url=str(data['url']).strip(),
            session=str(data['session']).strip(),
            name=str(data.get('name') or '').strip(),
            user_id=_optional_string(data.get('user_id')),
            cf_clearance=_optional_string(data.get('cf_clearance')),
            login_username=_optional_string(data.get('login_username')),
            login_password=_optional_string(data.get('login_password')),
        )

    def display_name(self, index: int) -> str:
        return self.name or f'账号{index}'

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value not in (None, '')}


@dataclass
class CheckinResult:
    """Final result for one account, shared by all notification channels."""

    name: str
    success: bool
    message: str
    quota_awarded: Optional[int] = None
    checkin_count: int = 0
    lottery: List[str] = field(default_factory=list)
    session_expired: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
