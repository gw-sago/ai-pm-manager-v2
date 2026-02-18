"""
AI PM Framework - 状態遷移ユーティリティ

status_transitions テーブルを使用した状態遷移ルールの検証・管理。
"""

import sqlite3
from typing import List, Optional, Dict, Any

from .db import fetch_one, fetch_all


class TransitionError(Exception):
    """
    状態遷移エラー

    不正な状態遷移が試行された場合に発生します。
    エラーメッセージには以下が含まれます:
    - 現在のステータス
    - 遷移先ステータス
    - 許可された遷移先の一覧

    Attributes:
        entity_type: エンティティ種別（project/order/task/backlog/review）
        from_status: 現在のステータス
        to_status: 試行された遷移先ステータス
        role: 操作者の役割
        allowed_transitions: 許可された遷移先のリスト（オプション）
    """

    def __init__(
        self,
        message: str,
        entity_type: str = "",
        from_status: Optional[str] = None,
        to_status: str = "",
        role: str = "",
        allowed_transitions: Optional[List[str]] = None,
    ):
        super().__init__(message)
        self.entity_type = entity_type
        self.from_status = from_status
        self.to_status = to_status
        self.role = role
        self.allowed_transitions = allowed_transitions or []

    def get_error_details(self) -> Dict[str, Any]:
        """エラー詳細を辞書として取得"""
        return {
            "entity_type": self.entity_type,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "role": self.role,
            "allowed_transitions": self.allowed_transitions,
            "message": str(self),
        }


def is_transition_allowed(
    conn: sqlite3.Connection,
    entity_type: str,
    from_status: Optional[str],
    to_status: str,
    role: str = "ANY",
) -> bool:
    """
    状態遷移が許可されているかを確認

    Args:
        conn: データベース接続
        entity_type: エンティティ種別（project/order/task/backlog/review）
        from_status: 現在のステータス（Noneは初期状態）
        to_status: 遷移先ステータス
        role: 操作者の役割（PM/Worker/System/ANY）

    Returns:
        bool: 遷移が許可されていればTrue

    Note:
        - from_status が None の場合は初期状態からの遷移
        - allowed_role が "ANY" の遷移は誰でも実行可能
        - allowed_role が指定されている場合はその役割のみ実行可能
        - 同一ステータスへの遷移（from_status == to_status）は常に許可される
          これは冪等性を保証し、再実行や復帰処理を安全にするため
        - role が "ANY" の場合は全ロールの遷移ルールを許可（ロール制限なし）
    """
    # 同一ステータスへの遷移は常に許可（変更なし）
    # これにより、IN_PROGRESS → IN_PROGRESS などの再実行が可能になる
    # 呼び出し側で適切な処理（assignee更新のみ、ログ記録など）を行う責任がある
    if from_status == to_status:
        return True

    # role='ANY' の場合はロール制限なしで遷移ルールを検索
    # （呼び出し側が任意のロールを許可する場合）
    if role == "ANY":
        if from_status is None:
            query = """
            SELECT id FROM status_transitions
            WHERE entity_type = ?
            AND from_status IS NULL
            AND to_status = ?
            AND is_active = 1
            """
            params = (entity_type, to_status)
        else:
            query = """
            SELECT id FROM status_transitions
            WHERE entity_type = ?
            AND from_status = ?
            AND to_status = ?
            AND is_active = 1
            """
            params = (entity_type, from_status, to_status)
        row = fetch_one(conn, query, params)
        return row is not None

    # 遷移ルールを検索（特定ロール or DBのANYロールルール）
    if from_status is None:
        # 初期状態からの遷移
        query = """
        SELECT id FROM status_transitions
        WHERE entity_type = ?
        AND from_status IS NULL
        AND to_status = ?
        AND is_active = 1
        AND (allowed_role = 'ANY' OR allowed_role = ?)
        """
        params = (entity_type, to_status, role)
    else:
        query = """
        SELECT id FROM status_transitions
        WHERE entity_type = ?
        AND from_status = ?
        AND to_status = ?
        AND is_active = 1
        AND (allowed_role = 'ANY' OR allowed_role = ?)
        """
        params = (entity_type, from_status, to_status, role)

    row = fetch_one(conn, query, params)
    return row is not None


def validate_transition(
    conn: sqlite3.Connection,
    entity_type: str,
    from_status: Optional[str],
    to_status: str,
    role: str = "ANY",
) -> None:
    """
    状態遷移を検証し、許可されていなければエラー

    Args:
        conn: データベース接続
        entity_type: エンティティ種別
        from_status: 現在のステータス
        to_status: 遷移先ステータス
        role: 操作者の役割

    Raises:
        TransitionError: 遷移が許可されていない場合
            エラーメッセージには以下が含まれます:
            - 現在のステータス
            - 遷移先ステータス
            - 許可された遷移先の一覧
    """
    if not is_transition_allowed(conn, entity_type, from_status, to_status, role):
        from_str = from_status or "(初期状態)"

        # 許可された遷移先を取得
        allowed = get_allowed_transitions(conn, entity_type, from_status, role)
        allowed_statuses = [t["to_status"] for t in allowed]

        # 許可遷移先がない場合のメッセージ
        if allowed_statuses:
            allowed_str = ", ".join(allowed_statuses)
        else:
            allowed_str = "(なし - 終端状態)"

        # 明確なエラーメッセージを構築
        error_message = (
            f"TransitionError: Invalid status transition\n"
            f"  Entity: {entity_type}\n"
            f"  Current: {from_str}\n"
            f"  Target: {to_status}\n"
            f"  Role: {role}\n"
            f"  Allowed transitions from {from_str}: {allowed_str}"
        )

        raise TransitionError(
            error_message,
            entity_type=entity_type,
            from_status=from_status,
            to_status=to_status,
            role=role,
            allowed_transitions=allowed_statuses,
        )


def get_allowed_transitions(
    conn: sqlite3.Connection,
    entity_type: str,
    from_status: Optional[str] = None,
    role: str = "ANY",
) -> List[Dict[str, Any]]:
    """
    許可されている遷移先を取得

    Args:
        conn: データベース接続
        entity_type: エンティティ種別
        from_status: 現在のステータス（Noneの場合は全遷移）
        role: 操作者の役割

    Returns:
        List[Dict]: 遷移ルールのリスト
        各要素: {
            "to_status": str,
            "allowed_role": str,
            "description": str
        }
    """
    if from_status is None:
        # 初期状態からの遷移
        query = """
        SELECT to_status, allowed_role, description
        FROM status_transitions
        WHERE entity_type = ?
        AND from_status IS NULL
        AND is_active = 1
        AND (allowed_role = 'ANY' OR allowed_role = ?)
        ORDER BY to_status
        """
        params = (entity_type, role)
    else:
        query = """
        SELECT to_status, allowed_role, description
        FROM status_transitions
        WHERE entity_type = ?
        AND from_status = ?
        AND is_active = 1
        AND (allowed_role = 'ANY' OR allowed_role = ?)
        ORDER BY to_status
        """
        params = (entity_type, from_status, role)

    rows = fetch_all(conn, query, params)

    return [
        {
            "to_status": row["to_status"],
            "allowed_role": row["allowed_role"],
            "description": row["description"],
        }
        for row in rows
    ]


def get_all_transitions(
    conn: sqlite3.Connection,
    entity_type: str,
) -> List[Dict[str, Any]]:
    """
    エンティティ種別の全遷移ルールを取得

    Args:
        conn: データベース接続
        entity_type: エンティティ種別

    Returns:
        List[Dict]: 全遷移ルールのリスト
    """
    query = """
    SELECT from_status, to_status, allowed_role, description, is_active
    FROM status_transitions
    WHERE entity_type = ?
    ORDER BY from_status, to_status
    """

    rows = fetch_all(conn, query, (entity_type,))

    return [
        {
            "from_status": row["from_status"],
            "to_status": row["to_status"],
            "allowed_role": row["allowed_role"],
            "description": row["description"],
            "is_active": bool(row["is_active"]),
        }
        for row in rows
    ]


def can_worker_execute(
    conn: sqlite3.Connection,
    entity_type: str,
    from_status: Optional[str],
    to_status: str,
) -> bool:
    """
    Workerがこの遷移を実行できるかを確認

    Args:
        conn: データベース接続
        entity_type: エンティティ種別
        from_status: 現在のステータス
        to_status: 遷移先ステータス

    Returns:
        bool: Workerが実行可能ならTrue
    """
    return is_transition_allowed(conn, entity_type, from_status, to_status, "Worker")


def can_pm_execute(
    conn: sqlite3.Connection,
    entity_type: str,
    from_status: Optional[str],
    to_status: str,
) -> bool:
    """
    PMがこの遷移を実行できるかを確認

    Args:
        conn: データベース接続
        entity_type: エンティティ種別
        from_status: 現在のステータス
        to_status: 遷移先ステータス

    Returns:
        bool: PMが実行可能ならTrue
    """
    return is_transition_allowed(conn, entity_type, from_status, to_status, "PM")


# === タスク固有のヘルパー関数 ===

def can_start_task(conn: sqlite3.Connection, current_status: str) -> bool:
    """
    タスクを開始できるか確認

    Args:
        conn: データベース接続
        current_status: 現在のタスクステータス

    Returns:
        bool: 開始可能ならTrue（QUEUED から IN_PROGRESS へ遷移可能）
    """
    return is_transition_allowed(
        conn, "task", current_status, "IN_PROGRESS", "Worker"
    )


def can_complete_task(conn: sqlite3.Connection, current_status: str) -> bool:
    """
    タスクを完了できるか確認

    Args:
        conn: データベース接続
        current_status: 現在のタスクステータス

    Returns:
        bool: 完了可能ならTrue（IN_PROGRESS から DONE へ遷移可能）
    """
    return is_transition_allowed(
        conn, "task", current_status, "DONE", "Worker"
    )


def can_approve_task(conn: sqlite3.Connection, current_status: str) -> bool:
    """
    タスクを承認できるか確認

    Args:
        conn: データベース接続
        current_status: 現在のタスクステータス

    Returns:
        bool: 承認可能ならTrue（DONE から COMPLETED へ遷移可能）
    """
    return is_transition_allowed(
        conn, "task", current_status, "COMPLETED", "PM"
    )


def can_reject_task(conn: sqlite3.Connection, current_status: str) -> bool:
    """
    タスクを差し戻しできるか確認

    Args:
        conn: データベース接続
        current_status: 現在のタスクステータス

    Returns:
        bool: 差し戻し可能ならTrue（DONE または IN_PROGRESS から REWORK へ遷移可能）
    """
    return is_transition_allowed(
        conn, "task", current_status, "REWORK", "PM"
    )


# === ORDER固有のヘルパー関数 ===

def can_start_order(conn: sqlite3.Connection, current_status: str) -> bool:
    """
    ORDERを開始できるか確認

    Args:
        conn: データベース接続
        current_status: 現在のORDERステータス

    Returns:
        bool: 開始可能ならTrue
    """
    return is_transition_allowed(
        conn, "order", current_status, "IN_PROGRESS", "PM"
    )


def can_complete_order(conn: sqlite3.Connection, current_status: str) -> bool:
    """
    ORDERを完了できるか確認

    Args:
        conn: データベース接続
        current_status: 現在のORDERステータス

    Returns:
        bool: 完了可能ならTrue
    """
    return is_transition_allowed(
        conn, "order", current_status, "COMPLETED", "PM"
    )


# === 遷移履歴記録 ===

def record_transition(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    from_status: Optional[str],
    to_status: str,
    changed_by: str,
    reason: Optional[str] = None,
) -> int:
    """
    状態遷移を履歴に記録

    Args:
        conn: データベース接続
        entity_type: エンティティ種別
        entity_id: エンティティID
        from_status: 元のステータス
        to_status: 新しいステータス
        changed_by: 変更者
        reason: 変更理由（オプション）

    Returns:
        int: 挿入された履歴のID
    """
    from .db import execute_query

    cursor = execute_query(
        conn,
        """
        INSERT INTO change_history (
            entity_type, entity_id, field_name,
            old_value, new_value, changed_by, change_reason
        ) VALUES (?, ?, 'status', ?, ?, ?, ?)
        """,
        (entity_type, entity_id, from_status, to_status, changed_by, reason)
    )

    return cursor.lastrowid
