"""
AI PM Framework - Pre-flight チェックモジュール

full-auto実行前にDB整合性チェックを自動実行し、
パイプライン中盤での破綻を事前に防止する。

チェック項目:
1. DB接続確認（data/aipm.dbアクセス可能・ロックなし）
2. アクティブORDER競合検出（IN_PROGRESS/REVIEW状態のORDERがないか）
3. BLOCKEDタスクの依存解決状況確認（依存先がCOMPLETEDか検証）
4. 参照ファイル存在確認（アーティファクトファイルがディスク上に存在するか）
"""

import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional
import json


@dataclass
class PreflightCheckResult:
    """Pre-flightチェック結果"""
    passed: bool = True
    db_accessible: bool = True
    db_locked: bool = False
    active_orders: List[Dict[str, Any]] = field(default_factory=list)
    blocked_tasks_unresolved: List[Dict[str, Any]] = field(default_factory=list)
    missing_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def has_issues(self) -> bool:
        """問題があるかどうか"""
        return not self.passed or len(self.errors) > 0 or len(self.warnings) > 0

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "passed": self.passed,
            "db_accessible": self.db_accessible,
            "db_locked": self.db_locked,
            "active_orders": self.active_orders,
            "blocked_tasks_unresolved": self.blocked_tasks_unresolved,
            "missing_artifacts": self.missing_artifacts,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def get_ai_pm_root() -> Path:
    """AI_PM_ROOTパスを取得"""
    current_file = Path(__file__).resolve()
    # backend/utils/preflight_check.py から AI_PM_ROOT へ
    # utils -> backend -> ai-pm-manager-v2
    return current_file.parent.parent.parent


def get_db_path() -> Path:
    """データベースファイルパスを取得"""
    return get_ai_pm_root() / "data" / "aipm.db"


def check_db_connection() -> tuple[bool, bool, Optional[str]]:
    """
    DB接続確認

    Returns:
        tuple[accessible, locked, error_message]
    """
    db_path = get_db_path()

    if not db_path.exists():
        return False, False, f"データベースファイルが存在しません: {db_path}"

    try:
        conn = sqlite3.connect(str(db_path), timeout=1.0)
        # 簡単なクエリでアクセス確認
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        return True, False, None
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return True, True, f"データベースがロックされています: {e}"
        return False, False, f"データベース接続エラー: {e}"
    except Exception as e:
        return False, False, f"予期しないエラー: {e}"


def check_active_orders(project_name: str) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """
    アクティブORDER競合検出

    IN_PROGRESS/REVIEW状態のORDERを検出

    Returns:
        tuple[active_orders, error_message]
    """
    db_path = get_db_path()

    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id as order_id, status, title, updated_at
            FROM orders
            WHERE project_id = ?
              AND status IN ('IN_PROGRESS', 'REVIEW')
            ORDER BY updated_at DESC
        """, (project_name,))

        rows = cursor.fetchall()
        conn.close()

        active_orders = [dict(row) for row in rows]
        return active_orders, None

    except Exception as e:
        return [], f"アクティブORDER検出エラー: {e}"


def check_blocked_tasks(project_name: str) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """
    BLOCKEDタスクの依存解決状況確認

    BLOCKEDタスクの依存先がCOMPLETEDか検証

    Returns:
        tuple[unresolved_blocked_tasks, error_message]
    """
    db_path = get_db_path()

    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # BLOCKEDステータスのタスクを取得
        cursor.execute("""
            SELECT id as task_id, order_id, title
            FROM tasks
            WHERE project_id = ?
              AND status = 'BLOCKED'
        """, (project_name,))

        blocked_tasks = cursor.fetchall()
        unresolved = []

        # 依存関係テーブルから依存先を取得
        for task in blocked_tasks:
            task_id = task["task_id"]

            # 依存関係を取得
            cursor.execute("""
                SELECT depends_on_task_id as dependency
                FROM task_dependencies
                WHERE task_id = ?
            """, (task_id,))

            deps = cursor.fetchall()

            if not deps:
                # 依存なしでBLOCKEDは異常
                unresolved.append({
                    "task_id": task_id,
                    "order_id": task["order_id"],
                    "title": task["title"],
                    "reason": "依存先が未設定",
                    "dependency": None,
                })
                continue

            for dep_row in deps:
                dependency = dep_row["dependency"]

                # 依存先の状態を確認
                cursor.execute("""
                    SELECT status
                    FROM tasks
                    WHERE id = ?
                """, (dependency,))

                dep_row = cursor.fetchone()

                if not dep_row:
                    # 依存先タスクが存在しない
                    unresolved.append({
                        "task_id": task_id,
                        "order_id": task["order_id"],
                        "title": task["title"],
                        "reason": "依存先タスクが存在しません",
                        "dependency": dependency,
                    })
                elif dep_row["status"] != "COMPLETED":
                    # 依存先が未完了
                    unresolved.append({
                        "task_id": task_id,
                        "order_id": task["order_id"],
                        "title": task["title"],
                        "reason": f"依存先タスクが未完了 (status: {dep_row['status']})",
                        "dependency": dependency,
                    })

        conn.close()
        return unresolved, None

    except Exception as e:
        return [], f"BLOCKEDタスク確認エラー: {e}"


def check_artifact_files(project_name: str) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """
    アーティファクトファイル存在確認

    タスクやORDERが参照するアーティファクトファイルがディスク上に存在するか確認

    Returns:
        tuple[missing_artifacts, error_message]
    """
    db_path = get_db_path()
    ai_pm_root = get_ai_pm_root()

    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # ORDER定義ファイルの存在確認
        cursor.execute("""
            SELECT id as order_id
            FROM orders
            WHERE project_id = ?
              AND status NOT IN ('COMPLETED', 'CANCELLED')
        """, (project_name,))

        orders = cursor.fetchall()
        missing = []

        for order in orders:
            order_id = order["order_id"]
            order_file = ai_pm_root / "PROJECTS" / project_name / "ORDERS" / f"{order_id}.md"

            if not order_file.exists():
                missing.append({
                    "type": "order_file",
                    "order_id": order_id,
                    "expected_path": str(order_file),
                    "reason": "ORDERファイルが存在しません",
                })

        # タスクのアーティファクトディレクトリ確認（COMPLETED以外）
        cursor.execute("""
            SELECT id as task_id, order_id, status
            FROM tasks
            WHERE project_id = ?
              AND status IN ('IN_PROGRESS', 'REVIEW')
        """, (project_name,))

        tasks = cursor.fetchall()

        for task in tasks:
            task_id = task["task_id"]
            order_id = task["order_id"]
            artifact_dir = ai_pm_root / "PROJECTS" / project_name / "RESULT" / order_id / "06_ARTIFACTS"

            # アーティファクトディレクトリが期待される場合のみチェック
            # （IN_PROGRESS/REVIEWなら作業成果物があるはず）
            if task["status"] in ("REVIEW",) and not artifact_dir.exists():
                missing.append({
                    "type": "artifact_dir",
                    "task_id": task_id,
                    "order_id": order_id,
                    "expected_path": str(artifact_dir),
                    "reason": f"アーティファクトディレクトリが存在しません (status: {task['status']})",
                })

        conn.close()
        return missing, None

    except Exception as e:
        return [], f"アーティファクトファイル確認エラー: {e}"


def run_preflight_check(project_name: str) -> PreflightCheckResult:
    """
    Pre-flightチェックを実行

    Args:
        project_name: プロジェクト名

    Returns:
        PreflightCheckResult: チェック結果
    """
    result = PreflightCheckResult()

    # 1. DB接続確認
    db_accessible, db_locked, db_error = check_db_connection()
    result.db_accessible = db_accessible
    result.db_locked = db_locked

    if not db_accessible:
        result.passed = False
        result.errors.append(db_error or "データベースにアクセスできません")
        return result

    if db_locked:
        result.passed = False
        result.errors.append(db_error or "データベースがロックされています")
        return result

    # 2. アクティブORDER競合検出
    active_orders, active_error = check_active_orders(project_name)
    if active_error:
        result.warnings.append(active_error)
    elif active_orders:
        result.active_orders = active_orders
        result.warnings.append(
            f"{len(active_orders)}件のアクティブORDERが存在します: "
            + ", ".join([o["order_id"] for o in active_orders])
        )

    # 3. BLOCKEDタスク確認
    blocked_unresolved, blocked_error = check_blocked_tasks(project_name)
    if blocked_error:
        result.warnings.append(blocked_error)
    elif blocked_unresolved:
        result.blocked_tasks_unresolved = blocked_unresolved
        result.warnings.append(
            f"{len(blocked_unresolved)}件の解決不能なBLOCKEDタスクが存在します"
        )

    # 4. アーティファクトファイル確認
    missing_artifacts, artifact_error = check_artifact_files(project_name)
    if artifact_error:
        result.warnings.append(artifact_error)
    elif missing_artifacts:
        result.missing_artifacts = missing_artifacts
        result.warnings.append(
            f"{len(missing_artifacts)}件のアーティファクトファイルが見つかりません"
        )

    # 総合判定
    if result.errors:
        result.passed = False

    return result


def generate_report_markdown(result: PreflightCheckResult) -> str:
    """
    チェック結果をMarkdown形式のレポートに変換

    Args:
        result: チェック結果

    Returns:
        str: Markdownレポート
    """
    lines = []
    lines.append("# Pre-flight チェック結果")
    lines.append("")

    # ステータス
    if result.passed and not result.has_issues():
        lines.append("✅ **全チェック PASSED**")
    elif result.passed:
        lines.append("⚠️ **警告あり（実行可能）**")
    else:
        lines.append("❌ **FAILED - 実行前に修正が必要です**")
    lines.append("")

    # エラー
    if result.errors:
        lines.append("## ❌ エラー")
        lines.append("")
        for error in result.errors:
            lines.append(f"- {error}")
        lines.append("")

    # 警告
    if result.warnings:
        lines.append("## ⚠️ 警告")
        lines.append("")
        for warning in result.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    # 詳細
    lines.append("## チェック詳細")
    lines.append("")

    # DB接続
    lines.append("### 1. DB接続確認")
    if result.db_accessible and not result.db_locked:
        lines.append("✅ OK")
    elif result.db_locked:
        lines.append("❌ データベースがロックされています")
    else:
        lines.append("❌ データベースにアクセスできません")
    lines.append("")

    # アクティブORDER
    lines.append("### 2. アクティブORDER競合検出")
    if not result.active_orders:
        lines.append("✅ 競合なし")
    else:
        lines.append(f"⚠️ {len(result.active_orders)}件のアクティブORDERが存在します")
        lines.append("")
        for order in result.active_orders:
            lines.append(f"- **{order['order_id']}**: {order['title']} (status: {order['status']})")
    lines.append("")

    # BLOCKEDタスク
    lines.append("### 3. BLOCKEDタスク依存解決確認")
    if not result.blocked_tasks_unresolved:
        lines.append("✅ 解決不能なBLOCKEDタスクなし")
    else:
        lines.append(f"⚠️ {len(result.blocked_tasks_unresolved)}件の解決不能なBLOCKEDタスクが存在します")
        lines.append("")
        for task in result.blocked_tasks_unresolved:
            lines.append(
                f"- **TASK_{task['task_id']}** ({task['order_id']}): {task['title']}"
            )
            lines.append(f"  - 理由: {task['reason']}")
            if task.get("dependency"):
                lines.append(f"  - 依存先: TASK_{task['dependency']}")
    lines.append("")

    # アーティファクトファイル
    lines.append("### 4. アーティファクトファイル存在確認")
    if not result.missing_artifacts:
        lines.append("✅ 全ファイル存在確認")
    else:
        lines.append(f"⚠️ {len(result.missing_artifacts)}件のファイルが見つかりません")
        lines.append("")
        for artifact in result.missing_artifacts:
            if artifact["type"] == "order_file":
                lines.append(f"- **{artifact['order_id']}**: ORDERファイルが存在しません")
                lines.append(f"  - 期待パス: `{artifact['expected_path']}`")
            elif artifact["type"] == "artifact_dir":
                lines.append(
                    f"- **TASK_{artifact['task_id']}** ({artifact['order_id']}): "
                    f"アーティファクトディレクトリが存在しません"
                )
                lines.append(f"  - 期待パス: `{artifact['expected_path']}`")
    lines.append("")

    return "\n".join(lines)


def main():
    """CLI エントリーポイント"""
    if len(sys.argv) < 2:
        print("Usage: python preflight_check.py <project_name> [--json]")
        sys.exit(1)

    project_name = sys.argv[1]
    output_json = "--json" in sys.argv

    result = run_preflight_check(project_name)

    if output_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        report = generate_report_markdown(result)
        print(report)

    # 終了コード
    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
