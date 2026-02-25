"""
AI PM Framework - BACKLOG管理モジュール

[DEPRECATED] このモジュール全体が非推奨です。
バックログ管理機能はORDERシステム（backend/order/）に統合されました。
- 新規追加: order/create.py --status DRAFT
- 一覧取得: order/list.py --draft
- 更新: order/update.py
- ORDER変換: order/update.py --status PLANNING
このモジュールは将来のバージョンで削除されます。

BACKLOGの追加・状態更新・一覧取得・ORDER変換を提供。
"""

import warnings

_DEPRECATION_MSG = (
    "[DEPRECATED] backend/backlog/ モジュール全体が非推奨です。"
    "バックログ管理機能は backend/order/ に統合されました。"
    "このモジュールは将来のバージョンで削除されます。"
)
warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)

from .add import add_backlog, AddBacklogResult
from .update import update_backlog, UpdateBacklogResult
from .list import list_backlogs, ListBacklogResult
from .to_order import convert_backlog_to_order, ToOrderResult
from .suggest import suggest_backlogs

__all__ = [
    "add_backlog",
    "AddBacklogResult",
    "update_backlog",
    "UpdateBacklogResult",
    "list_backlogs",
    "ListBacklogResult",
    "convert_backlog_to_order",
    "ToOrderResult",
    "suggest_backlogs",
]
