"""
AI PM Framework - 入力検証ユーティリティ

プロジェクト名、ORDER番号、タスクID等の形式チェックと存在確認。
"""

import re
import sqlite3
from typing import Optional, List, Dict, Any

from .db import fetch_one


class ValidationError(Exception):
    """入力検証エラー"""

    def __init__(self, message: str, field: str = "", value: Any = None):
        super().__init__(message)
        self.field = field
        self.value = value


# パターン定義
PATTERNS = {
    "project_name": re.compile(r"^[A-Za-z][A-Za-z0-9_]*$"),
    "order_id": re.compile(r"^ORDER_(\d{3,})$"),
    "task_id": re.compile(r"^TASK_(\d{3,})(?:_INT(?:_(\d{2}))?)?$"),
    "backlog_id": re.compile(r"^BACKLOG_(\d{3,})$"),
    "escalation_id": re.compile(r"^ESC_(\d{3,})$"),
}

# ステータス定義
VALID_STATUSES = {
    "project": [
        "INITIAL", "PLANNING", "IN_PROGRESS", "REVIEW", "REWORK",
        "ESCALATED", "ESCALATION_RESOLVED", "COMPLETED", "ON_HOLD",
        "CANCELLED", "INTERRUPTED"
    ],
    "order": [
        "PLANNING", "IN_PROGRESS", "REVIEW", "COMPLETED",
        "ON_HOLD", "CANCELLED"
    ],
    "task": [
        "QUEUED", "BLOCKED", "IN_PROGRESS", "DONE", "REWORK",
        "COMPLETED", "INTERRUPTED"
    ],
    "backlog": ["TODO", "IN_PROGRESS", "DONE", "CANCELED", "EXTERNAL"],
    "review": ["PENDING", "IN_REVIEW", "APPROVED", "REJECTED"],
    "escalation": ["OPEN", "RESOLVED", "CANCELED"],
}

# 優先度定義
VALID_PRIORITIES = ["P0", "P1", "P2"]

# 推奨モデル定義
VALID_MODELS = ["Haiku", "Sonnet", "Opus"]


def validate_project_name(name: str) -> str:
    """
    プロジェクト名の形式を検証

    Args:
        name: プロジェクト名

    Returns:
        検証済みのプロジェクト名

    Raises:
        ValidationError: 形式が不正な場合

    Note:
        形式: 英字で始まり、英数字とアンダースコアのみ
        例: AI_PM_PJ, MyProject, project_01
    """
    if not name:
        raise ValidationError("プロジェクト名が空です", "project_name", name)

    if not PATTERNS["project_name"].match(name):
        raise ValidationError(
            f"プロジェクト名の形式が不正です: {name}\n"
            "形式: 英字で始まり、英数字とアンダースコアのみ使用可能",
            "project_name",
            name
        )

    return name


def validate_order_id(order_id: str) -> str:
    """
    ORDER IDの形式を検証

    Args:
        order_id: ORDER ID

    Returns:
        検証済みのORDER ID

    Raises:
        ValidationError: 形式が不正な場合

    Note:
        形式: ORDER_XXX（XXXは3桁の数字）
        例: ORDER_001, ORDER_036, ORDER_999
    """
    if not order_id:
        raise ValidationError("ORDER IDが空です", "order_id", order_id)

    if not PATTERNS["order_id"].match(order_id):
        raise ValidationError(
            f"ORDER IDの形式が不正です: {order_id}\n"
            "形式: ORDER_XXX（XXXは3桁の数字）",
            "order_id",
            order_id
        )

    return order_id


def validate_task_id(task_id: str) -> str:
    """
    タスクIDの形式を検証

    Args:
        task_id: タスクID

    Returns:
        検証済みのタスクID

    Raises:
        ValidationError: 形式が不正な場合

    Note:
        形式:
        - 通常: TASK_XXX（XXXは3桁の数字）
        - 割り込み: TASK_XXX_INT または TASK_XXX_INT_YY（YYは2桁連番）
        例: TASK_188, TASK_075_INT, TASK_075_INT_02
    """
    if not task_id:
        raise ValidationError("タスクIDが空です", "task_id", task_id)

    if not PATTERNS["task_id"].match(task_id):
        raise ValidationError(
            f"タスクIDの形式が不正です: {task_id}\n"
            "形式: TASK_XXX または TASK_XXX_INT または TASK_XXX_INT_YY",
            "task_id",
            task_id
        )

    return task_id


def validate_backlog_id(backlog_id: str) -> str:
    """
    BACKLOG IDの形式を検証

    Args:
        backlog_id: BACKLOG ID

    Returns:
        検証済みのBACKLOG ID

    Raises:
        ValidationError: 形式が不正な場合
    """
    if not backlog_id:
        raise ValidationError("BACKLOG IDが空です", "backlog_id", backlog_id)

    if not PATTERNS["backlog_id"].match(backlog_id):
        raise ValidationError(
            f"BACKLOG IDの形式が不正です: {backlog_id}\n"
            "形式: BACKLOG_XXX（XXXは3桁の数字）",
            "backlog_id",
            backlog_id
        )

    return backlog_id


def validate_status(
    status: str,
    entity_type: str = "task",
) -> str:
    """
    ステータスの有効性を検証

    Args:
        status: ステータス値
        entity_type: エンティティ種別（project/order/task/backlog/review/escalation）

    Returns:
        検証済みのステータス

    Raises:
        ValidationError: ステータスが無効な場合
    """
    if entity_type not in VALID_STATUSES:
        raise ValidationError(
            f"不明なエンティティ種別: {entity_type}",
            "entity_type",
            entity_type
        )

    valid = VALID_STATUSES[entity_type]
    if status not in valid:
        raise ValidationError(
            f"無効なステータス: {status}\n"
            f"有効なステータス: {', '.join(valid)}",
            "status",
            status
        )

    return status


def validate_priority(priority: str) -> str:
    """
    優先度の有効性を検証

    Args:
        priority: 優先度値

    Returns:
        検証済みの優先度

    Raises:
        ValidationError: 優先度が無効な場合
    """
    if priority not in VALID_PRIORITIES:
        raise ValidationError(
            f"無効な優先度: {priority}\n"
            f"有効な優先度: {', '.join(VALID_PRIORITIES)}",
            "priority",
            priority
        )

    return priority


def validate_model(model: str) -> str:
    """
    推奨モデルの有効性を検証

    Args:
        model: モデル名

    Returns:
        検証済みのモデル名

    Raises:
        ValidationError: モデルが無効な場合
    """
    if model not in VALID_MODELS:
        raise ValidationError(
            f"無効なモデル: {model}\n"
            f"有効なモデル: {', '.join(VALID_MODELS)}",
            "model",
            model
        )

    return model


# === 存在確認クエリ ===

def project_exists(conn: sqlite3.Connection, project_id: str) -> bool:
    """
    プロジェクトの存在を確認

    Args:
        conn: データベース接続
        project_id: プロジェクトID

    Returns:
        bool: 存在すればTrue
    """
    row = fetch_one(
        conn,
        "SELECT id FROM projects WHERE id = ?",
        (project_id,)
    )
    return row is not None


def order_exists(
    conn: sqlite3.Connection,
    order_id: str,
    project_id: Optional[str] = None,
) -> bool:
    """
    ORDERの存在を確認

    Args:
        conn: データベース接続
        order_id: ORDER ID
        project_id: プロジェクトID（複合キー対応、省略時は単一キー検索）

    Returns:
        bool: 存在すればTrue

    Note:
        複合主キー対応（ORDER_043）により、project_idの指定を推奨。
        project_idが省略された場合は、任意のプロジェクトで存在確認を行う。
    """
    if project_id is not None:
        # 複合キー検索（推奨）
        row = fetch_one(
            conn,
            "SELECT id FROM orders WHERE id = ? AND project_id = ?",
            (order_id, project_id)
        )
    else:
        # 単一キー検索（後方互換性）
        row = fetch_one(
            conn,
            "SELECT id FROM orders WHERE id = ?",
            (order_id,)
        )
    return row is not None


def task_exists(
    conn: sqlite3.Connection,
    task_id: str,
    project_id: Optional[str] = None,
) -> bool:
    """
    タスクの存在を確認

    Args:
        conn: データベース接続
        task_id: タスクID
        project_id: プロジェクトID（複合キー対応、省略時は単一キー検索）

    Returns:
        bool: 存在すればTrue

    Note:
        複合主キー対応（ORDER_043）により、project_idの指定を推奨。
        project_idが省略された場合は、任意のプロジェクトで存在確認を行う。
    """
    if project_id is not None:
        # 複合キー検索（推奨）
        row = fetch_one(
            conn,
            "SELECT id FROM tasks WHERE id = ? AND project_id = ?",
            (task_id, project_id)
        )
    else:
        # 単一キー検索（後方互換性）
        row = fetch_one(
            conn,
            "SELECT id FROM tasks WHERE id = ?",
            (task_id,)
        )
    return row is not None


def backlog_exists(
    conn: sqlite3.Connection,
    backlog_id: str,
    project_id: Optional[str] = None,
) -> bool:
    """
    BACKLOGの存在を確認

    Args:
        conn: データベース接続
        backlog_id: BACKLOG ID
        project_id: プロジェクトID（複合キー対応、省略時は単一キー検索）

    Returns:
        bool: 存在すればTrue

    Note:
        複合主キー対応（ORDER_079）により、project_idの指定を推奨。
        project_idが省略された場合は、任意のプロジェクトで存在確認を行う。
    """
    if project_id is not None:
        # 複合キー検索（推奨）
        row = fetch_one(
            conn,
            "SELECT id FROM backlog_items WHERE id = ? AND project_id = ?",
            (backlog_id, project_id)
        )
    else:
        # 単一キー検索（後方互換性）
        row = fetch_one(
            conn,
            "SELECT id FROM backlog_items WHERE id = ?",
            (backlog_id,)
        )
    return row is not None


def validate_project_exists(
    conn: sqlite3.Connection,
    project_id: str,
) -> str:
    """
    プロジェクトの存在を検証

    Args:
        conn: データベース接続
        project_id: プロジェクトID

    Returns:
        検証済みのプロジェクトID

    Raises:
        ValidationError: プロジェクトが存在しない場合
    """
    project_id = validate_project_name(project_id)

    if not project_exists(conn, project_id):
        raise ValidationError(
            f"プロジェクトが見つかりません: {project_id}",
            "project_id",
            project_id
        )

    return project_id


def validate_order_exists(
    conn: sqlite3.Connection,
    order_id: str,
    project_id: Optional[str] = None,
) -> str:
    """
    ORDERの存在を検証

    Args:
        conn: データベース接続
        order_id: ORDER ID
        project_id: プロジェクトID（複合キー対応、省略時は単一キー検索）

    Returns:
        検証済みのORDER ID

    Raises:
        ValidationError: ORDERが存在しない場合

    Note:
        複合主キー対応（ORDER_043）により、project_idの指定を推奨。
    """
    order_id = validate_order_id(order_id)

    if not order_exists(conn, order_id, project_id):
        if project_id:
            raise ValidationError(
                f"ORDERが見つかりません: {order_id} (project: {project_id})",
                "order_id",
                order_id
            )
        else:
            raise ValidationError(
                f"ORDERが見つかりません: {order_id}",
                "order_id",
                order_id
            )

    return order_id


def validate_task_exists(
    conn: sqlite3.Connection,
    task_id: str,
    project_id: Optional[str] = None,
) -> str:
    """
    タスクの存在を検証

    Args:
        conn: データベース接続
        task_id: タスクID
        project_id: プロジェクトID（複合キー対応、省略時は単一キー検索）

    Returns:
        検証済みのタスクID

    Raises:
        ValidationError: タスクが存在しない場合

    Note:
        複合主キー対応（ORDER_043）により、project_idの指定を推奨。
    """
    task_id = validate_task_id(task_id)

    if not task_exists(conn, task_id, project_id):
        if project_id:
            raise ValidationError(
                f"タスクが見つかりません: {task_id} (project: {project_id})",
                "task_id",
                task_id
            )
        else:
            raise ValidationError(
                f"タスクが見つかりません: {task_id}",
                "task_id",
                task_id
            )

    return task_id


def parse_task_id(task_id: str) -> Dict[str, Optional[str]]:
    """
    タスクIDをパースして構成要素を取得

    Args:
        task_id: タスクID

    Returns:
        Dict with keys:
        - base_number: 基本番号（例: "188"）
        - is_interrupt: 割り込みタスクかどうか
        - interrupt_number: 割り込み連番（あれば）

    Example:
        parse_task_id("TASK_188") -> {"base_number": "188", "is_interrupt": False, "interrupt_number": None}
        parse_task_id("TASK_075_INT") -> {"base_number": "075", "is_interrupt": True, "interrupt_number": None}
        parse_task_id("TASK_075_INT_02") -> {"base_number": "075", "is_interrupt": True, "interrupt_number": "02"}
    """
    validate_task_id(task_id)

    match = PATTERNS["task_id"].match(task_id)
    if not match:
        raise ValidationError(f"タスクIDのパースに失敗: {task_id}", "task_id", task_id)

    base_number = match.group(1)
    interrupt_number = match.group(2)

    return {
        "base_number": base_number,
        "is_interrupt": "_INT" in task_id,
        "interrupt_number": interrupt_number,
    }


def get_next_order_number(conn: sqlite3.Connection, project_id: str) -> str:
    """
    次のORDER番号を取得

    Args:
        conn: データベース接続
        project_id: プロジェクトID

    Returns:
        次のORDER ID（例: ORDER_037）
    """
    row = fetch_one(
        conn,
        """
        SELECT MAX(CAST(SUBSTR(id, 7) AS INTEGER)) as max_num
        FROM orders
        WHERE project_id = ?
        """,
        (project_id,)
    )

    max_num = row["max_num"] if row and row["max_num"] else 0
    next_num = max_num + 1

    return f"ORDER_{next_num:03d}"


def get_next_order_number_with_retry(
    conn: sqlite3.Connection,
    project_id: str,
    max_retries: int = 3,
) -> str:
    """
    次のORDER番号を取得（UNIQUE制約違反時リトライ機構付き）

    同時実行時のRace Conditionに対応するため、UNIQUE制約違反が
    発生した場合は再採番してリトライする。

    Args:
        conn: データベース接続
        project_id: プロジェクトID
        max_retries: 最大リトライ回数（デフォルト3）

    Returns:
        次のORDER ID（例: ORDER_037）

    Note:
        この関数は採番のみを行う。実際のINSERTは呼び出し側で行い、
        UNIQUE制約違反時はこの関数を再度呼び出して再採番する。
    """
    return get_next_order_number(conn, project_id)


def get_next_task_number(conn: sqlite3.Connection, order_id: str) -> str:
    """
    次のタスク番号を取得

    Args:
        conn: データベース接続
        order_id: ORDER ID

    Returns:
        次のタスクID（例: TASK_200）
    """
    # 全タスクから最大番号を取得（割り込みタスクを除く、3桁以上対応）
    row = fetch_one(
        conn,
        """
        SELECT MAX(CAST(SUBSTR(id, 6) AS INTEGER)) as max_num
        FROM tasks
        WHERE id GLOB 'TASK_[0-9]*'
          AND id NOT GLOB 'TASK_*_INT*'
        """,
    )

    max_num = row["max_num"] if row and row["max_num"] else 0
    next_num = max_num + 1

    return f"TASK_{next_num:03d}"


def get_next_task_number_with_retry(
    conn: sqlite3.Connection,
    order_id: str,
    max_retries: int = 3,
) -> str:
    """
    次のタスク番号を取得（UNIQUE制約違反時リトライ機構付き）

    同時実行時のRace Conditionに対応するため、UNIQUE制約違反が
    発生した場合は再採番してリトライする。

    Args:
        conn: データベース接続
        order_id: ORDER ID
        max_retries: 最大リトライ回数（デフォルト3）

    Returns:
        次のタスクID（例: TASK_200）

    Note:
        この関数は採番のみを行う。実際のINSERTは呼び出し側で行い、
        UNIQUE制約違反時はこの関数を再度呼び出して再採番する。
    """
    return get_next_task_number(conn, order_id)


def get_next_interrupt_task_id(conn: sqlite3.Connection, base_task_id: str) -> str:
    """
    次の割り込みタスクIDを取得

    Args:
        conn: データベース接続
        base_task_id: 基本タスクID（例: TASK_075）

    Returns:
        次の割り込みタスクID（例: TASK_075_INT, TASK_075_INT_02）
    """
    # 基本タスクIDから番号を抽出
    parsed = parse_task_id(base_task_id)
    base_number = parsed["base_number"]

    # 既存の割り込みタスクを検索
    rows = fetch_one(
        conn,
        """
        SELECT COUNT(*) as count
        FROM tasks
        WHERE id GLOB ?
        """,
        (f"TASK_{base_number}_INT*",)
    )

    count = rows["count"] if rows else 0

    if count == 0:
        return f"TASK_{base_number}_INT"
    else:
        return f"TASK_{base_number}_INT_{count + 1:02d}"
