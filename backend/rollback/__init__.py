"""
AI PM Framework - ロールバック機能

直前操作の取り消し（undo）と時点指定での復元（restore）を提供。
change_history テーブルを活用した操作履歴の逆転処理。
"""

from .undo import (
    undo_last_operation,
    get_last_operation,
    UndoError,
)

from .restore import (
    restore_to_point,
    get_operations_after,
    RestoreError,
)

__all__ = [
    # undo
    "undo_last_operation",
    "get_last_operation",
    "UndoError",
    # restore
    "restore_to_point",
    "get_operations_after",
    "RestoreError",
]
