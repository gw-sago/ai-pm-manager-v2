#!/usr/bin/env python3
"""
AI PM Framework - DB整合性検証スクリプト

backend/配下のPythonスクリプト編集後に実行して、
DB状態の整合性を検証する。

Usage:
    python backend/utils/verify_db_consistency.py [options]

Options:
    --verbose       詳細なチェック結果を表示
    --json          JSON形式で出力
    --fix           検出した問題を自動修正（実装予定）
    --project ID    特定プロジェクトのみチェック
    --task TASK_ID  特定タスクのみチェック（--projectと併用）

Example:
    # 全プロジェクトをチェック
    python backend/utils/verify_db_consistency.py

    # 特定プロジェクトをチェック
    python backend/utils/verify_db_consistency.py --project ai_pm_manager

    # 特定タスクをチェック（タスク完了時の検証に使用）
    python backend/utils/verify_db_consistency.py --project ai_pm_manager --task TASK_913

    # 詳細表示
    python backend/utils/verify_db_consistency.py --verbose

    # JSON出力（プログラムから利用）
    python backend/utils/verify_db_consistency.py --project ai_pm_manager --json

検証項目:
1. 外部キー整合性
   - 存在しないプロジェクトIDを参照しているORDER/TASK/BACKLOGがないか
   - 存在しないORDER IDを参照しているTASKがないか
   - 存在しない依存タスクIDを参照しているタスクがないか

2. 状態遷移整合性
   - 不正な状態遷移履歴がないか（status_transitionsテーブルと照合）
   - 現在のステータスが有効な値か（validation.py VALID_STATUSESと照合）

3. 複合キー整合性
   - (id, project_id) の組み合わせが一意か
   - 複合外部キー参照が正しいか

4. タスク依存関係整合性
   - BLOCKEDタスクが実際に未完了の依存を持つか
   - 依存タスクが全て完了しているのにBLOCKEDなタスクがないか

5. レビューキュー整合性
   - review_queue に対応するタスクが存在するか
   - review_queue のステータスとタスクステータスが整合しているか

6. バックログ整合性
   - related_order_id が存在するORDERを参照しているか
   - BACKLOG→ORDER→TASKの連鎖が整合しているか

7. アーティファクトファイル整合性
   - 完了済みタスク(DONE/COMPLETED)の06_ARTIFACTSディレクトリが存在するか
   - 完了済みタスクのREPORTファイル(05_REPORT/REPORT_{task_number}.md)が存在するか
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection, fetch_one, fetch_all,
    row_to_dict, rows_to_dicts, DatabaseError
)
from utils.validation import VALID_STATUSES


class ConsistencyIssue:
    """整合性の問題を表すクラス"""

    def __init__(
        self,
        category: str,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        self.category = category  # 'FK', 'STATUS', 'DEPENDENCY', 'REVIEW', 'BACKLOG', 'ARTIFACT'
        self.severity = severity  # 'ERROR', 'WARNING', 'INFO'
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class DBConsistencyChecker:
    """DB整合性チェッカー"""

    def __init__(self, project_id: Optional[str] = None, verbose: bool = False):
        self.project_id = project_id
        self.verbose = verbose
        self.issues: List[ConsistencyIssue] = []
        self.stats = {
            "total_checks": 0,
            "errors": 0,
            "warnings": 0,
            "info": 0,
        }

    def add_issue(self, issue: ConsistencyIssue) -> None:
        """問題を記録"""
        self.issues.append(issue)
        if issue.severity == "ERROR":
            self.stats["errors"] += 1
        elif issue.severity == "WARNING":
            self.stats["warnings"] += 1
        elif issue.severity == "INFO":
            self.stats["info"] += 1

    def check_all(self) -> Dict[str, Any]:
        """全チェックを実行"""
        conn = get_connection()
        try:
            self._check_foreign_keys(conn)
            self._check_status_validity(conn)
            self._check_status_transitions(conn)
            self._check_composite_keys(conn)
            self._check_task_dependencies(conn)
            self._check_review_queue(conn)
            self._check_backlog(conn)
            self._check_artifact_files(conn)

            return self._build_result()
        finally:
            conn.close()

    def _check_foreign_keys(self, conn) -> None:
        """外部キー整合性チェック"""
        self.stats["total_checks"] += 1

        # ORDERの project_id 参照チェック
        orphan_orders = fetch_all(
            conn,
            """
            SELECT o.id, o.project_id
            FROM orders o
            LEFT JOIN projects p ON o.project_id = p.id
            WHERE p.id IS NULL
            """
        )

        for row in orphan_orders:
            self.add_issue(ConsistencyIssue(
                category="FK",
                severity="ERROR",
                message=f"ORDER {row['id']} が存在しないプロジェクト {row['project_id']} を参照",
                details={"order_id": row['id'], "project_id": row['project_id']}
            ))

        # TASKの project_id / order_id 参照チェック
        orphan_tasks_project = fetch_all(
            conn,
            """
            SELECT t.id, t.project_id
            FROM tasks t
            LEFT JOIN projects p ON t.project_id = p.id
            WHERE p.id IS NULL
            """
        )

        for row in orphan_tasks_project:
            self.add_issue(ConsistencyIssue(
                category="FK",
                severity="ERROR",
                message=f"TASK {row['id']} が存在しないプロジェクト {row['project_id']} を参照",
                details={"task_id": row['id'], "project_id": row['project_id']}
            ))

        orphan_tasks_order = fetch_all(
            conn,
            """
            SELECT t.id, t.order_id, t.project_id
            FROM tasks t
            LEFT JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
            WHERE o.id IS NULL
            """
        )

        for row in orphan_tasks_order:
            self.add_issue(ConsistencyIssue(
                category="FK",
                severity="ERROR",
                message=f"TASK {row['id']} が存在しないORDER {row['order_id']} を参照",
                details={
                    "task_id": row['id'],
                    "order_id": row['order_id'],
                    "project_id": row['project_id']
                }
            ))

        # タスク依存関係の参照チェック
        orphan_deps = fetch_all(
            conn,
            """
            SELECT td.task_id, td.depends_on_task_id, td.project_id
            FROM task_dependencies td
            LEFT JOIN tasks t ON td.depends_on_task_id = t.id AND td.project_id = t.project_id
            WHERE t.id IS NULL
            """
        )

        for row in orphan_deps:
            self.add_issue(ConsistencyIssue(
                category="FK",
                severity="ERROR",
                message=f"TASK {row['task_id']} が存在しない依存タスク {row['depends_on_task_id']} を参照",
                details={
                    "task_id": row['task_id'],
                    "depends_on": row['depends_on_task_id'],
                    "project_id": row['project_id']
                }
            ))

        # BACKLOGの project_id 参照チェック
        orphan_backlogs = fetch_all(
            conn,
            """
            SELECT b.id, b.project_id
            FROM backlog_items b
            LEFT JOIN projects p ON b.project_id = p.id
            WHERE p.id IS NULL
            """
        )

        for row in orphan_backlogs:
            self.add_issue(ConsistencyIssue(
                category="FK",
                severity="ERROR",
                message=f"BACKLOG {row['id']} が存在しないプロジェクト {row['project_id']} を参照",
                details={"backlog_id": row['id'], "project_id": row['project_id']}
            ))

    def _check_status_validity(self, conn) -> None:
        """ステータス値の有効性チェック"""
        self.stats["total_checks"] += 1

        # ORDERステータスチェック
        invalid_order_statuses = fetch_all(
            conn,
            f"""
            SELECT id, project_id, status
            FROM orders
            WHERE status NOT IN ({','.join(['?' for _ in VALID_STATUSES['order']])})
            """,
            tuple(VALID_STATUSES['order'])
        )

        for row in invalid_order_statuses:
            self.add_issue(ConsistencyIssue(
                category="STATUS",
                severity="ERROR",
                message=f"ORDER {row['id']} が無効なステータス '{row['status']}' を持つ",
                details={
                    "order_id": row['id'],
                    "project_id": row['project_id'],
                    "status": row['status'],
                    "valid_statuses": VALID_STATUSES['order']
                }
            ))

        # TASKステータスチェック
        invalid_task_statuses = fetch_all(
            conn,
            f"""
            SELECT id, project_id, status
            FROM tasks
            WHERE status NOT IN ({','.join(['?' for _ in VALID_STATUSES['task']])})
            """,
            tuple(VALID_STATUSES['task'])
        )

        for row in invalid_task_statuses:
            self.add_issue(ConsistencyIssue(
                category="STATUS",
                severity="ERROR",
                message=f"TASK {row['id']} が無効なステータス '{row['status']}' を持つ",
                details={
                    "task_id": row['id'],
                    "project_id": row['project_id'],
                    "status": row['status'],
                    "valid_statuses": VALID_STATUSES['task']
                }
            ))

        # BACKLOGステータスチェック
        invalid_backlog_statuses = fetch_all(
            conn,
            f"""
            SELECT id, project_id, status
            FROM backlog_items
            WHERE status NOT IN ({','.join(['?' for _ in VALID_STATUSES['backlog']])})
            """,
            tuple(VALID_STATUSES['backlog'])
        )

        for row in invalid_backlog_statuses:
            self.add_issue(ConsistencyIssue(
                category="STATUS",
                severity="ERROR",
                message=f"BACKLOG {row['id']} が無効なステータス '{row['status']}' を持つ",
                details={
                    "backlog_id": row['id'],
                    "project_id": row['project_id'],
                    "status": row['status'],
                    "valid_statuses": VALID_STATUSES['backlog']
                }
            ))

    def _check_status_transitions(self, conn) -> None:
        """状態遷移履歴の整合性チェック"""
        self.stats["total_checks"] += 1

        # change_history から status 変更履歴を取得
        status_changes = fetch_all(
            conn,
            """
            SELECT entity_type, entity_id, old_value, new_value, changed_at
            FROM change_history
            WHERE field_name = 'status'
            ORDER BY entity_type, entity_id, changed_at
            """
        )

        # 遷移ルールを事前に取得
        transitions = fetch_all(
            conn,
            """
            SELECT entity_type, from_status, to_status, is_active
            FROM status_transitions
            WHERE is_active = 1
            """
        )

        # 遷移ルールをマップ化
        transition_map = {}
        for t in transitions:
            key = (t['entity_type'], t['from_status'], t['to_status'])
            transition_map[key] = True

        # 各遷移が有効かチェック
        for change in status_changes:
            entity_type = change['entity_type']
            from_status = change['old_value']
            to_status = change['new_value']

            # 初期状態からの遷移は from_status = None
            if from_status == 'None' or from_status is None:
                from_status = None

            key = (entity_type, from_status, to_status)

            if key not in transition_map:
                self.add_issue(ConsistencyIssue(
                    category="STATUS",
                    severity="WARNING",
                    message=f"{entity_type} {change['entity_id']} に不正な状態遷移履歴: {from_status} → {to_status}",
                    details={
                        "entity_type": entity_type,
                        "entity_id": change['entity_id'],
                        "from_status": from_status,
                        "to_status": to_status,
                        "changed_at": change['changed_at']
                    }
                ))

    def _check_composite_keys(self, conn) -> None:
        """複合キー整合性チェック"""
        self.stats["total_checks"] += 1

        # ORDERの複合キー重複チェック
        duplicate_orders = fetch_all(
            conn,
            """
            SELECT id, project_id, COUNT(*) as count
            FROM orders
            GROUP BY id, project_id
            HAVING count > 1
            """
        )

        for row in duplicate_orders:
            self.add_issue(ConsistencyIssue(
                category="FK",
                severity="ERROR",
                message=f"ORDER複合キー (id={row['id']}, project_id={row['project_id']}) が重複",
                details={"order_id": row['id'], "project_id": row['project_id'], "count": row['count']}
            ))

        # TASKの複合キー重複チェック
        duplicate_tasks = fetch_all(
            conn,
            """
            SELECT id, project_id, COUNT(*) as count
            FROM tasks
            GROUP BY id, project_id
            HAVING count > 1
            """
        )

        for row in duplicate_tasks:
            self.add_issue(ConsistencyIssue(
                category="FK",
                severity="ERROR",
                message=f"TASK複合キー (id={row['id']}, project_id={row['project_id']}) が重複",
                details={"task_id": row['id'], "project_id": row['project_id'], "count": row['count']}
            ))

        # BACKLOGの複合キー重複チェック
        duplicate_backlogs = fetch_all(
            conn,
            """
            SELECT id, project_id, COUNT(*) as count
            FROM backlog_items
            GROUP BY id, project_id
            HAVING count > 1
            """
        )

        for row in duplicate_backlogs:
            self.add_issue(ConsistencyIssue(
                category="FK",
                severity="ERROR",
                message=f"BACKLOG複合キー (id={row['id']}, project_id={row['project_id']}) が重複",
                details={"backlog_id": row['id'], "project_id": row['project_id'], "count": row['count']}
            ))

    def _check_task_dependencies(self, conn) -> None:
        """タスク依存関係の整合性チェック"""
        self.stats["total_checks"] += 1

        # BLOCKEDだが依存が全て完了しているタスク
        incorrectly_blocked = fetch_all(
            conn,
            """
            SELECT t.id, t.project_id, t.status
            FROM tasks t
            WHERE t.status = 'BLOCKED'
            AND NOT EXISTS (
                SELECT 1 FROM task_dependencies td
                JOIN tasks dep ON td.depends_on_task_id = dep.id AND td.project_id = dep.project_id
                WHERE td.task_id = t.id AND td.project_id = t.project_id
                AND dep.status NOT IN ('COMPLETED', 'DONE')
            )
            """
        )

        for row in incorrectly_blocked:
            self.add_issue(ConsistencyIssue(
                category="DEPENDENCY",
                severity="WARNING",
                message=f"TASK {row['id']} がBLOCKEDだが依存タスクは全て完了済み",
                details={"task_id": row['id'], "project_id": row['project_id'], "status": row['status']}
            ))

        # BLOCKED以外だが未完了の依存がある（QUEUEDはOK、他は警告）
        should_be_blocked = fetch_all(
            conn,
            """
            SELECT DISTINCT t.id, t.project_id, t.status
            FROM tasks t
            JOIN task_dependencies td ON t.id = td.task_id AND t.project_id = td.project_id
            JOIN tasks dep ON td.depends_on_task_id = dep.id AND td.project_id = dep.project_id
            WHERE t.status NOT IN ('BLOCKED', 'QUEUED', 'COMPLETED', 'DONE')
            AND dep.status NOT IN ('COMPLETED', 'DONE')
            """
        )

        for row in should_be_blocked:
            self.add_issue(ConsistencyIssue(
                category="DEPENDENCY",
                severity="INFO",
                message=f"TASK {row['id']} (status={row['status']}) に未完了の依存があるがBLOCKEDでない",
                details={"task_id": row['id'], "project_id": row['project_id'], "status": row['status']}
            ))

    def _check_review_queue(self, conn) -> None:
        """レビューキューの整合性チェック"""
        self.stats["total_checks"] += 1

        # レビューキューにあるが対応タスクが存在しない
        orphan_reviews = fetch_all(
            conn,
            """
            SELECT rq.task_id, rq.project_id, rq.status
            FROM review_queue rq
            LEFT JOIN tasks t ON rq.task_id = t.id AND rq.project_id = t.project_id
            WHERE t.id IS NULL
            """
        )

        for row in orphan_reviews:
            self.add_issue(ConsistencyIssue(
                category="REVIEW",
                severity="ERROR",
                message=f"review_queue が存在しないタスク {row['task_id']} を参照",
                details={"task_id": row['task_id'], "project_id": row['project_id'], "status": row['status']}
            ))

        # タスクがDONEだがレビューキューにない
        missing_reviews = fetch_all(
            conn,
            """
            SELECT t.id, t.project_id, t.status
            FROM tasks t
            LEFT JOIN review_queue rq ON t.id = rq.task_id AND t.project_id = rq.project_id
            WHERE t.status = 'DONE'
            AND rq.task_id IS NULL
            """
        )

        for row in missing_reviews:
            self.add_issue(ConsistencyIssue(
                category="REVIEW",
                severity="INFO",
                message=f"TASK {row['id']} がDONEだがreview_queueにエントリがない",
                details={"task_id": row['id'], "project_id": row['project_id'], "status": row['status']}
            ))

    def _check_backlog(self, conn) -> None:
        """バックログの整合性チェック"""
        self.stats["total_checks"] += 1

        # related_order_id が存在しないORDERを参照
        orphan_backlog_orders = fetch_all(
            conn,
            """
            SELECT b.id, b.project_id, b.related_order_id
            FROM backlog_items b
            LEFT JOIN orders o ON b.related_order_id = o.id AND b.project_id = o.project_id
            WHERE b.related_order_id IS NOT NULL
            AND o.id IS NULL
            """
        )

        for row in orphan_backlog_orders:
            self.add_issue(ConsistencyIssue(
                category="BACKLOG",
                severity="ERROR",
                message=f"BACKLOG {row['id']} が存在しないORDER {row['related_order_id']} を参照",
                details={
                    "backlog_id": row['id'],
                    "project_id": row['project_id'],
                    "related_order_id": row['related_order_id']
                }
            ))

        # ORDERが完了しているのにBACKLOGがDONEでない
        inconsistent_backlog_status = fetch_all(
            conn,
            """
            SELECT b.id, b.project_id, b.status, b.related_order_id, o.status as order_status
            FROM backlog_items b
            JOIN orders o ON b.related_order_id = o.id AND b.project_id = o.project_id
            WHERE o.status = 'COMPLETED'
            AND b.status != 'DONE'
            """
        )

        for row in inconsistent_backlog_status:
            self.add_issue(ConsistencyIssue(
                category="BACKLOG",
                severity="WARNING",
                message=f"BACKLOG {row['id']} に関連するORDER {row['related_order_id']} が完了しているがBACKLOGはDONEでない",
                details={
                    "backlog_id": row['id'],
                    "project_id": row['project_id'],
                    "backlog_status": row['status'],
                    "related_order_id": row['related_order_id'],
                    "order_status": row['order_status']
                }
            ))

    def _check_artifact_files(self, conn) -> None:
        """アーティファクトファイルの存在チェック"""
        self.stats["total_checks"] += 1

        # 完了済みタスクのアーティファクトディレクトリを検証
        completed_tasks = fetch_all(
            conn,
            """
            SELECT t.id, t.project_id, t.order_id, t.status, p.path as project_path
            FROM tasks t
            JOIN projects p ON t.project_id = p.id
            WHERE t.status IN ('DONE', 'COMPLETED')
            """
        )

        for row in completed_tasks:
            project_path = Path(row['project_path'])
            order_id = row['order_id']
            task_id = row['id']

            # アーティファクトディレクトリのパスを構築
            artifacts_dir = project_path / "RESULT" / order_id / "06_ARTIFACTS"

            # アーティファクトディレクトリが存在しない場合は警告
            if not artifacts_dir.exists():
                self.add_issue(ConsistencyIssue(
                    category="ARTIFACT",
                    severity="WARNING",
                    message=f"TASK {task_id} (status={row['status']}) のアーティファクトディレクトリが存在しません",
                    details={
                        "task_id": task_id,
                        "project_id": row['project_id'],
                        "order_id": order_id,
                        "status": row['status'],
                        "expected_path": str(artifacts_dir)
                    }
                ))
                continue

            # アーティファクトディレクトリが空の場合は情報として記録
            artifact_files = list(artifacts_dir.glob("*"))
            if not artifact_files:
                self.add_issue(ConsistencyIssue(
                    category="ARTIFACT",
                    severity="INFO",
                    message=f"TASK {task_id} (status={row['status']}) のアーティファクトディレクトリが空です",
                    details={
                        "task_id": task_id,
                        "project_id": row['project_id'],
                        "order_id": order_id,
                        "status": row['status'],
                        "path": str(artifacts_dir)
                    }
                ))

        # REPORTファイルの存在チェック
        done_tasks = fetch_all(
            conn,
            """
            SELECT t.id, t.project_id, t.order_id, t.status, p.path as project_path
            FROM tasks t
            JOIN projects p ON t.project_id = p.id
            WHERE t.status IN ('DONE', 'COMPLETED')
            """
        )

        for row in done_tasks:
            project_path = Path(row['project_path'])
            order_id = row['order_id']
            task_id = row['id']

            # REPORTファイルのパスを構築（REPORT_{task_number}.md形式）
            task_number = task_id.split('_')[1] if '_' in task_id else task_id
            report_dir = project_path / "RESULT" / order_id / "05_REPORT"
            report_file = report_dir / f"REPORT_{task_number}.md"

            # REPORTディレクトリが存在しない場合は警告
            if not report_dir.exists():
                self.add_issue(ConsistencyIssue(
                    category="ARTIFACT",
                    severity="WARNING",
                    message=f"TASK {task_id} のREPORTディレクトリが存在しません",
                    details={
                        "task_id": task_id,
                        "project_id": row['project_id'],
                        "order_id": order_id,
                        "status": row['status'],
                        "expected_path": str(report_dir)
                    }
                ))
                continue

            # REPORTファイルが存在しない場合は警告
            if not report_file.exists():
                self.add_issue(ConsistencyIssue(
                    category="ARTIFACT",
                    severity="WARNING",
                    message=f"TASK {task_id} のREPORTファイルが存在しません",
                    details={
                        "task_id": task_id,
                        "project_id": row['project_id'],
                        "order_id": order_id,
                        "status": row['status'],
                        "expected_file": str(report_file)
                    }
                ))

    def _build_result(self) -> Dict[str, Any]:
        """チェック結果を構築"""
        return {
            "success": self.stats["errors"] == 0,
            "timestamp": datetime.now().isoformat(),
            "project_id": self.project_id or "ALL",
            "stats": self.stats,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def verify_task_completion(
    project_id: str,
    task_id: str,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    特定タスクのDB整合性とアーティファクトを検証

    Args:
        project_id: プロジェクトID
        task_id: タスクID
        verbose: 詳細情報を含めるか

    Returns:
        検証結果（success, issues, stats）
    """
    conn = get_connection()
    try:
        # タスク情報を取得
        task = fetch_one(
            conn,
            """
            SELECT t.*, p.path as project_path
            FROM tasks t
            JOIN projects p ON t.project_id = p.id
            WHERE t.id = ? AND t.project_id = ?
            """,
            (task_id, project_id)
        )

        if not task:
            return {
                "success": False,
                "error": f"タスクが見つかりません: {task_id} (project: {project_id})",
                "issues": [],
                "stats": {}
            }

        checker = DBConsistencyChecker(project_id=project_id, verbose=verbose)
        issues = []

        # タスクステータスチェック
        if task['status'] not in ['QUEUED', 'BLOCKED', 'IN_PROGRESS', 'DONE', 'REWORK', 'COMPLETED', 'INTERRUPTED']:
            issues.append({
                "category": "STATUS",
                "severity": "ERROR",
                "message": f"無効なステータス: {task['status']}",
                "details": {"task_id": task_id, "status": task['status']}
            })

        # アーティファクトファイルチェック（DONE/COMPLETED時のみ）
        if task['status'] in ['DONE', 'COMPLETED']:
            project_path = Path(task['project_path'])
            order_id = task['order_id']

            # 06_ARTIFACTSディレクトリ
            artifacts_dir = project_path / "RESULT" / order_id / "06_ARTIFACTS"
            if not artifacts_dir.exists():
                issues.append({
                    "category": "ARTIFACT",
                    "severity": "WARNING",
                    "message": f"アーティファクトディレクトリが存在しません: {artifacts_dir}",
                    "details": {"task_id": task_id, "path": str(artifacts_dir)}
                })
            elif not list(artifacts_dir.glob("*")):
                issues.append({
                    "category": "ARTIFACT",
                    "severity": "INFO",
                    "message": f"アーティファクトディレクトリが空です: {artifacts_dir}",
                    "details": {"task_id": task_id, "path": str(artifacts_dir)}
                })

            # REPORTファイル
            task_number = task_id.split('_')[1] if '_' in task_id else task_id
            report_file = project_path / "RESULT" / order_id / "05_REPORT" / f"REPORT_{task_number}.md"
            if not report_file.exists():
                issues.append({
                    "category": "ARTIFACT",
                    "severity": "WARNING",
                    "message": f"REPORTファイルが存在しません: {report_file}",
                    "details": {"task_id": task_id, "file": str(report_file)}
                })

        return {
            "success": len([i for i in issues if i['severity'] == 'ERROR']) == 0,
            "task_id": task_id,
            "task_status": task['status'],
            "issues": issues,
            "stats": {
                "errors": len([i for i in issues if i['severity'] == 'ERROR']),
                "warnings": len([i for i in issues if i['severity'] == 'WARNING']),
                "info": len([i for i in issues if i['severity'] == 'INFO'])
            }
        }
    finally:
        conn.close()


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="DB整合性を検証",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="詳細なチェック結果を表示")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--project", help="特定プロジェクトのみチェック")
    parser.add_argument("--task", help="特定タスクのみチェック（--projectと併用）")
    parser.add_argument("--fix", action="store_true", help="検出した問題を自動修正（未実装）")

    args = parser.parse_args()

    if args.fix:
        print("エラー: --fix オプションは未実装です", file=sys.stderr)
        sys.exit(1)

    try:
        # 特定タスクのチェック
        if args.task:
            if not args.project:
                print("エラー: --task オプションには --project が必要です", file=sys.stderr)
                sys.exit(1)

            result = verify_task_completion(args.project, args.task, verbose=args.verbose)

            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print("=" * 60)
                print(f"タスク整合性検証結果: {result['task_id']}")
                print("=" * 60)
                print(f"タスクステータス: {result['task_status']}")
                print(f"エラー: {result['stats']['errors']}")
                print(f"警告: {result['stats']['warnings']}")
                print(f"情報: {result['stats']['info']}")
                print()

                if result['success'] and len(result['issues']) == 0:
                    print("✅ 問題は検出されませんでした")
                else:
                    for issue in result['issues']:
                        severity_icon = {
                            "ERROR": "❌",
                            "WARNING": "⚠️",
                            "INFO": "ℹ️"
                        }.get(issue['severity'], "")
                        print(f"{severity_icon} [{issue['category']}] {issue['message']}")

                sys.exit(0 if result['success'] else 1)

        # 全体チェック
        checker = DBConsistencyChecker(project_id=args.project, verbose=args.verbose)
        result = checker.check_all()

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            # 人間可読形式で出力
            print("=" * 60)
            print("DB整合性検証結果")
            print("=" * 60)
            print(f"プロジェクト: {result['project_id']}")
            print(f"チェック日時: {result['timestamp']}")
            print(f"総チェック数: {result['stats']['total_checks']}")
            print()

            # 統計サマリ
            print(f"エラー: {result['stats']['errors']}")
            print(f"警告: {result['stats']['warnings']}")
            print(f"情報: {result['stats']['info']}")
            print()

            # 問題がない場合
            if result['success'] and len(result['issues']) == 0:
                print("✅ 問題は検出されませんでした")
                sys.exit(0)

            # 問題がある場合
            if not result['success']:
                print("❌ エラーが検出されました")
            elif result['stats']['warnings'] > 0:
                print("⚠️  警告があります")
            else:
                print("ℹ️  情報メッセージがあります")

            print()

            # 問題の詳細表示
            if args.verbose or result['stats']['errors'] > 0:
                for issue in result['issues']:
                    severity_icon = {
                        "ERROR": "❌",
                        "WARNING": "⚠️",
                        "INFO": "ℹ️"
                    }.get(issue['severity'], "")

                    print(f"{severity_icon} [{issue['category']}] {issue['message']}")

                    if args.verbose and issue['details']:
                        for key, value in issue['details'].items():
                            print(f"    {key}: {value}")
                    print()

            # 終了コード
            sys.exit(0 if result['success'] else 1)

    except DatabaseError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
