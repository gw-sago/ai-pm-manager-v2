#!/usr/bin/env python3
"""
AI PM Framework - Escalation Logging Module

エスカレーション発生時のログをDB/ファイルに記録します。
- モデル昇格（Worker）
- PM差し戻し（Review）
- 判定基準緩和（Review）
- PM再設計依頼（PM）

Usage:
    from escalation.log_escalation import log_escalation

    log_escalation(
        project_id="ai_pm_manager",
        task_id="TASK_123",
        escalation_type="model_upgrade",
        description="REWORK 2回目: Sonnet → Opus自動昇格",
        metadata={"from_model": "sonnet", "to_model": "opus", "rework_count": 2}
    )
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import json

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, execute_query, fetch_one


class EscalationType:
    """エスカレーション種別定数"""
    MODEL_UPGRADE = "model_upgrade"  # モデル昇格
    REVIEW_REJECTION = "review_rejection"  # PM差し戻し
    CRITERIA_RELAXATION = "criteria_relaxation"  # 判定基準緩和
    PM_REDESIGN = "pm_redesign"  # PM再設計依頼
    REWORK_LIMIT_EXCEEDED = "rework_limit_exceeded"  # リワーク回数超過
    TASK_REPLAN = "task_replan"  # タスク再計画
    REVIEW_ESCALATION = "review_escalation"  # レビューESCALATED→PM自動判断
    ESCALATION_TIMEOUT = "escalation_timeout"  # ESCALATEDタイムアウト→REJECTED


def log_escalation(
    project_id: str,
    task_id: str,
    escalation_type: str,
    description: str,
    order_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    severity: str = "MEDIUM",
) -> str:
    """
    エスカレーションをDBとファイルに記録

    Args:
        project_id: プロジェクトID
        task_id: タスクID
        escalation_type: エスカレーション種別（EscalationType定数を使用）
        description: エスカレーション内容の説明
        order_id: ORDER ID（オプション）
        metadata: 追加メタデータ（dict）、JSON化して保存
        severity: 重要度（LOW/MEDIUM/HIGH/CRITICAL）

    Returns:
        escalation_id: 作成されたエスカレーションID
    """
    conn = get_connection()
    try:
        # 既存のエスカレーション数を取得してIDを生成
        count_row = fetch_one(
            conn,
            "SELECT COUNT(*) as count FROM escalations WHERE task_id = ? AND project_id = ?",
            (task_id, project_id)
        )
        escalation_count = count_row["count"] if count_row else 0
        escalation_id = f"{task_id}_ESC_{escalation_count + 1}"

        # メタデータをJSON化
        metadata_json = None
        if metadata:
            metadata_json = json.dumps(metadata, ensure_ascii=False)

        # エスカレーションタイトルを生成
        title = _generate_title(escalation_type, task_id, metadata)

        # escalationsテーブルに記録
        # スキーマ: id, task_id, project_id, title, description, status, resolution, created_at, resolved_at
        execute_query(
            conn,
            """
            INSERT INTO escalations (id, task_id, project_id, title, description, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'OPEN', ?)
            """,
            (escalation_id, task_id, project_id, title, description, datetime.now().isoformat())
        )

        # change_historyテーブルにも記録（監査ログ）
        execute_query(
            conn,
            """
            INSERT INTO change_history (entity_type, entity_id, project_id, field_name,
                                       old_value, new_value, changed_by, change_reason, changed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "escalation",
                escalation_id,
                project_id,
                "escalation_type",
                None,
                escalation_type,
                "System",
                description,
                datetime.now().isoformat()
            )
        )

        # メタデータがあれば追加記録
        if metadata_json:
            execute_query(
                conn,
                """
                INSERT INTO change_history (entity_type, entity_id, project_id, field_name,
                                           old_value, new_value, changed_by, change_reason, changed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "escalation",
                    escalation_id,
                    project_id,
                    "metadata",
                    None,
                    metadata_json,
                    "System",
                    "エスカレーション詳細メタデータ",
                    datetime.now().isoformat()
                )
            )

        conn.commit()

        # ファイルにも記録（ORDER配下）
        if order_id:
            _write_escalation_log_file(
                project_id, order_id, escalation_id, task_id,
                escalation_type, description, metadata
            )

        return escalation_id

    except Exception as e:
        conn.rollback()
        raise Exception(f"エスカレーションログ記録失敗: {e}")
    finally:
        conn.close()


def _generate_title(escalation_type: str, task_id: str, metadata: Optional[Dict]) -> str:
    """エスカレーションタイトルを生成"""
    if escalation_type == EscalationType.MODEL_UPGRADE:
        from_model = metadata.get("from_model", "?") if metadata else "?"
        to_model = metadata.get("to_model", "?") if metadata else "?"
        return f"{task_id}: モデル自動昇格 ({from_model} → {to_model})"

    elif escalation_type == EscalationType.REVIEW_REJECTION:
        rework_count = metadata.get("rework_count", 0) if metadata else 0
        return f"{task_id}: PM差し戻し (REWORK #{rework_count})"

    elif escalation_type == EscalationType.CRITERIA_RELAXATION:
        rework_count = metadata.get("rework_count", 0) if metadata else 0
        criteria_level = metadata.get("criteria_level", "通常") if metadata else "通常"
        return f"{task_id}: 判定基準緩和 (REWORK #{rework_count}, 基準={criteria_level})"

    elif escalation_type == EscalationType.PM_REDESIGN:
        rework_count = metadata.get("rework_count", 0) if metadata else 0
        return f"{task_id}: PM再設計依頼 (REWORK #{rework_count})"

    elif escalation_type == EscalationType.REWORK_LIMIT_EXCEEDED:
        rework_count = metadata.get("rework_count", 0) if metadata else 0
        return f"{task_id}: リワーク回数上限超過 (REWORK #{rework_count})"

    elif escalation_type == EscalationType.TASK_REPLAN:
        completed_task_id = metadata.get("completed_task_id", "?") if metadata else "?"
        return f"{task_id}: タスク再計画 (影響元: {completed_task_id})"

    elif escalation_type == EscalationType.REVIEW_ESCALATION:
        escalation_count = metadata.get("escalation_count", 0) if metadata else 0
        action = metadata.get("action", "?") if metadata else "?"
        return f"{task_id}: レビューESCALATED→PM自動判断 (#{escalation_count}, action={action})"

    elif escalation_type == EscalationType.ESCALATION_TIMEOUT:
        timeout_seconds = metadata.get("timeout_seconds", "?") if metadata else "?"
        return f"{task_id}: ESCALATEDタイムアウト ({timeout_seconds}秒)"

    else:
        return f"{task_id}: エスカレーション ({escalation_type})"


def _write_escalation_log_file(
    project_id: str,
    order_id: str,
    escalation_id: str,
    task_id: str,
    escalation_type: str,
    description: str,
    metadata: Optional[Dict]
) -> None:
    """エスカレーションログをファイルに記録"""
    try:
        # プロジェクトルートを取得
        project_root = Path(__file__).resolve().parent.parent.parent
        project_dir = project_root / "PROJECTS" / project_id

        # 08_ESCALATIONSディレクトリ作成
        escalation_dir = project_dir / "RESULT" / order_id / "08_ESCALATIONS"
        escalation_dir.mkdir(parents=True, exist_ok=True)

        # ファイル名生成（タスクごとに集約）
        log_file = escalation_dir / f"{task_id}_ESCALATIONS.md"

        # ログエントリ作成
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_entry = f"""
## {escalation_id} ({timestamp})

**種別**: {escalation_type}

**説明**:
{description}
"""

        # メタデータがあれば追加
        if metadata:
            log_entry += "\n**詳細メタデータ**:\n```json\n"
            log_entry += json.dumps(metadata, ensure_ascii=False, indent=2)
            log_entry += "\n```\n"

        log_entry += "\n---\n"

        # ファイルに追記（既存の場合は末尾に追加）
        if log_file.exists():
            content = log_file.read_text(encoding="utf-8")
            content += log_entry
        else:
            # 新規作成の場合はヘッダー追加
            content = f"# {task_id} エスカレーション履歴\n\n"
            content += log_entry

        log_file.write_text(content, encoding="utf-8")

    except Exception as e:
        # ファイル記録失敗は警告のみ（DB記録は成功している）
        import logging
        logging.warning(f"エスカレーションログファイル記録失敗: {e}")


def get_escalation_history(
    project_id: str,
    task_id: Optional[str] = None,
    escalation_type: Optional[str] = None,
    limit: int = 100
) -> list:
    """
    エスカレーション履歴を取得

    Args:
        project_id: プロジェクトID
        task_id: タスクID（指定時はそのタスクのみ）
        escalation_type: エスカレーション種別（指定時はその種別のみ）
        limit: 取得件数上限

    Returns:
        エスカレーション履歴のリスト
    """
    conn = get_connection()
    try:
        # クエリ構築
        query = """
            SELECT e.*, ch.new_value as escalation_type, ch.change_reason
            FROM escalations e
            LEFT JOIN change_history ch
                ON e.id = ch.entity_id
                AND ch.entity_type = 'escalation'
                AND ch.field_name = 'escalation_type'
            WHERE e.project_id = ?
        """
        params = [project_id]

        if task_id:
            query += " AND e.task_id = ?"
            params.append(task_id)

        if escalation_type:
            query += " AND ch.new_value = ?"
            params.append(escalation_type)

        query += " ORDER BY e.created_at DESC LIMIT ?"
        params.append(limit)

        # 実行
        from utils.db import fetch_all, rows_to_dicts
        rows = fetch_all(conn, query, tuple(params))
        return rows_to_dicts(rows)

    finally:
        conn.close()


def get_escalation_statistics(project_id: str, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    エスカレーション統計を取得

    Args:
        project_id: プロジェクトID
        task_id: タスクID（指定時はそのタスクのみ）

    Returns:
        統計情報の辞書
    """
    conn = get_connection()
    try:
        from utils.db import fetch_all, rows_to_dicts

        # 基本クエリ
        base_where = "WHERE e.project_id = ?"
        params = [project_id]

        if task_id:
            base_where += " AND e.task_id = ?"
            params.append(task_id)

        # 総数
        total_row = fetch_one(
            conn,
            f"SELECT COUNT(*) as total FROM escalations e {base_where}",
            tuple(params)
        )
        total = total_row["total"] if total_row else 0

        # 種別ごとの集計
        type_rows = fetch_all(
            conn,
            f"""
            SELECT ch.new_value as escalation_type, COUNT(*) as count
            FROM escalations e
            LEFT JOIN change_history ch
                ON e.id = ch.entity_id
                AND ch.entity_type = 'escalation'
                AND ch.field_name = 'escalation_type'
            {base_where}
            GROUP BY ch.new_value
            """,
            tuple(params)
        )
        by_type = {row["escalation_type"]: row["count"] for row in rows_to_dicts(type_rows)}

        # ステータスごとの集計
        status_rows = fetch_all(
            conn,
            f"""
            SELECT status, COUNT(*) as count
            FROM escalations e
            {base_where}
            GROUP BY status
            """,
            tuple(params)
        )
        by_status = {row["status"]: row["count"] for row in rows_to_dicts(status_rows)}

        return {
            "total": total,
            "by_type": by_type,
            "by_status": by_status,
        }

    finally:
        conn.close()
