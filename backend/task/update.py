#!/usr/bin/env python3
"""
AI PM Framework - タスク更新スクリプト

Usage:
    python backend/task/update.py PROJECT_NAME TASK_ID --status NEW_STATUS [options]

Options:
    --status            ステータス変更（QUEUED/BLOCKED/IN_PROGRESS/DONE/REWORK/COMPLETED/INTERRUPTED）
    --assignee          担当者変更
    --title             タイトル変更
    --description       説明変更
    --priority          優先度変更（P0/P1/P2）
    --markdown-created  Markdownファイル作成状態変更（true/false）
    --role              操作者の役割（PM/Worker、デフォルト: Worker）
    --reason            変更理由
    --render            Markdown生成を実行（デフォルト: True）
    --json              JSON形式で出力

Example:
    python backend/task/update.py AI_PM_PJ TASK_188 --status IN_PROGRESS --role Worker
    python backend/task/update.py AI_PM_PJ TASK_188 --status DONE --role Worker
    python backend/task/update.py AI_PM_PJ TASK_188 --status COMPLETED --role PM
    python backend/task/update.py AI_PM_PJ TASK_188 --markdown-created true
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# aipm-db は Python パッケージ名として使えないためモジュール直接参照
try:
    from aipm_db.utils.db import (
        get_connection, transaction, execute_query, fetch_one, fetch_all,
        row_to_dict, DatabaseError
    )
    from aipm_db.utils.validation import (
        validate_project_name, validate_task_id,
        validate_status, validate_priority,
        task_exists, ValidationError
    )
    from aipm_db.utils.transition import (
        validate_transition, record_transition, TransitionError
    )
    from aipm_db.utils.file_lock import FileLockManager, FileLockError
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from utils.db import (
        get_connection, transaction, execute_query, fetch_one, fetch_all,
        row_to_dict, DatabaseError
    )
    from utils.validation import (
        validate_project_name, validate_task_id,
        validate_status, validate_priority,
        task_exists, ValidationError
    )
    from utils.transition import (
        validate_transition, record_transition, TransitionError
    )
    from utils.file_lock import FileLockManager, FileLockError


def update_task(
    project_id: str,
    task_id: str,
    *,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    markdown_created: Optional[bool] = None,
    role: str = "Worker",
    reason: Optional[str] = None,
    render: bool = True,
) -> Dict[str, Any]:
    """
    タスクを更新

    Args:
        project_id: プロジェクトID
        task_id: タスクID
        status: 新しいステータス
        assignee: 新しい担当者
        title: 新しいタイトル
        description: 新しい説明
        priority: 新しい優先度
        markdown_created: Markdownファイル作成状態（True/False）
        role: 操作者の役割（PM/Worker）
        reason: 変更理由
        render: Markdown生成を実行するか

    Returns:
        更新されたタスク情報

    Raises:
        ValidationError: 入力検証エラー
        TransitionError: 状態遷移エラー
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)
    validate_task_id(task_id)

    if status:
        validate_status(status, "task")

    if priority:
        validate_priority(priority)

    if role not in ("PM", "Worker"):
        raise ValidationError(f"無効な役割: {role}（PM または Worker）", "role", role)

    with transaction() as conn:
        # タスク存在確認（複合キー対応）
        if not task_exists(conn, task_id, project_id):
            raise ValidationError(f"タスクが見つかりません: {task_id} (project: {project_id})", "task_id", task_id)

        # 現在のタスク情報を取得（複合キー対応）
        current = fetch_one(
            conn,
            """
            SELECT t.*, t.project_id
            FROM tasks t
            WHERE t.id = ? AND t.project_id = ?
            """,
            (task_id, project_id)
        )

        if not current:
            raise ValidationError(f"タスクが見つかりません: {task_id} (project: {project_id})", "task_id", task_id)

        current_dict = dict(current)
        updates = []
        params = []
        changes = []

        # ステータス更新
        if status and status != current_dict["status"]:
            # 状態遷移検証
            validate_transition(conn, "task", current_dict["status"], status, role)

            updates.append("status = ?")
            params.append(status)
            changes.append(("status", current_dict["status"], status))

            # ステータスに応じたタイムスタンプ更新
            if status == "IN_PROGRESS" and not current_dict.get("started_at"):
                updates.append("started_at = ?")
                params.append(datetime.now().isoformat())

            # REWORK → IN_PROGRESS 遷移時に reviewed_at をリセット
            if status == "IN_PROGRESS" and current_dict["status"] == "REWORK":
                updates.append("reviewed_at = NULL")
                # NULLは値ではなくリテラルなのでparamsには追加しない

            if status in ("COMPLETED",):
                updates.append("completed_at = ?")
                params.append(datetime.now().isoformat())
        elif status and status == current_dict["status"]:
            # 同一ステータスへの遷移（再実行など）
            # validate_transitionはis_transition_allowedで同一ステータスを許可するため
            # ここでは検証のみ実施（エラーは発生しない）
            validate_transition(conn, "task", current_dict["status"], status, role)
            # DBには更新なし（statusフィールドは変更されない）
            # ただし、assigneeなど他のフィールドは更新される可能性がある

        # 担当者更新
        if assignee is not None and assignee != current_dict.get("assignee"):
            updates.append("assignee = ?")
            params.append(assignee if assignee else None)
            changes.append(("assignee", current_dict.get("assignee"), assignee))

        # タイトル更新
        if title and title != current_dict["title"]:
            updates.append("title = ?")
            params.append(title)
            changes.append(("title", current_dict["title"], title))

        # 説明更新
        if description is not None and description != current_dict.get("description"):
            updates.append("description = ?")
            params.append(description if description else None)
            changes.append(("description", current_dict.get("description"), description))

        # 優先度更新
        if priority and priority != current_dict["priority"]:
            updates.append("priority = ?")
            params.append(priority)
            changes.append(("priority", current_dict["priority"], priority))

        # markdown_created更新
        if markdown_created is not None:
            current_md_created = bool(current_dict.get("markdown_created", 0))
            if markdown_created != current_md_created:
                updates.append("markdown_created = ?")
                params.append(1 if markdown_created else 0)
                changes.append(("markdown_created", current_md_created, markdown_created))

        # 更新がなければ早期リターン
        if not updates:
            return row_to_dict(current)

        # updated_at を追加
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())

        # WHERE句のパラメータ（複合キー対応）
        params.append(task_id)
        params.append(project_id)

        # UPDATE実行（複合キー対応）
        execute_query(
            conn,
            f"UPDATE tasks SET {', '.join(updates)} WHERE id = ? AND project_id = ?",
            tuple(params)
        )

        # 変更履歴を記録
        # 注意: statusはrecord_transitionで記録するため、ここではスキップ（重複防止）
        changed_by = f"{role} ({assignee or current_dict.get('assignee') or 'unknown'})"
        for field, old_val, new_val in changes:
            if field == "status":
                continue  # statusはrecord_transitionで記録
            execute_query(
                conn,
                """
                INSERT INTO change_history (
                    entity_type, entity_id, field_name,
                    old_value, new_value, changed_by, change_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("task", task_id, field, str(old_val) if old_val else None, str(new_val) if new_val else None, changed_by, reason)
            )

        # ステータス変更時は状態遷移履歴も記録
        if status and status != current_dict["status"]:
            record_transition(
                conn,
                "task",
                task_id,
                current_dict["status"],
                status,
                changed_by,
                reason
            )

            # COMPLETED/REJECTED/REWORK遷移時は自動的にファイルロックを解放
            # REWORK: PM差し戻し時に解放（再実行前に取り直す）
            # COMPLETED/REJECTED: 終了状態への遷移時に解放
            if status in ("COMPLETED", "REJECTED", "REWORK"):
                try:
                    _release_task_file_locks_in_transaction(conn, project_id, task_id)
                except Exception as e:
                    # ロック解放失敗はログ記録のみ（遷移自体はブロックしない）
                    print(f"警告: タスク {task_id} のファイルロック解放失敗: {e}", file=sys.stderr)

            # COMPLETED になった場合、依存しているタスクのブロック解除をチェック
            if status == "COMPLETED":
                _check_unblock_dependent_tasks(conn, task_id, project_id)

        # 更新後のタスクを取得（複合キー対応）
        updated = fetch_one(
            conn,
            "SELECT * FROM tasks WHERE id = ? AND project_id = ?",
            (task_id, project_id)
        )

        result = row_to_dict(updated)

    return result


def _check_unblock_dependent_tasks(conn, completed_task_id: str, project_id: str) -> List[str]:
    """
    完了したタスクに依存しているタスクのブロック解除をチェック

    Args:
        conn: データベース接続
        completed_task_id: 完了したタスクID
        project_id: プロジェクトID

    Returns:
        ブロック解除されたタスクIDのリスト
    """
    unblocked = []

    # このタスクに依存しているタスクを取得（複合キー対応）
    dependent_tasks = fetch_all(
        conn,
        """
        SELECT DISTINCT task_id
        FROM task_dependencies
        WHERE depends_on_task_id = ? AND project_id = ?
        """,
        (completed_task_id, project_id)
    )

    for row in dependent_tasks:
        dependent_id = row["task_id"]

        # 依存タスクが BLOCKED かチェック（複合キー対応）
        task = fetch_one(
            conn,
            "SELECT status FROM tasks WHERE id = ? AND project_id = ?",
            (dependent_id, project_id)
        )

        if not task or task["status"] != "BLOCKED":
            continue

        # 全ての依存タスクが COMPLETED かチェック（複合キー対応）
        pending_deps = fetch_one(
            conn,
            """
            SELECT COUNT(*) as count
            FROM task_dependencies td
            JOIN tasks t ON td.depends_on_task_id = t.id AND td.project_id = t.project_id
            WHERE td.task_id = ? AND td.project_id = ?
            AND t.status != 'COMPLETED'
            """,
            (dependent_id, project_id)
        )

        if pending_deps and pending_deps["count"] == 0:
            # 全ての依存が完了 → QUEUED に変更（複合キー対応）
            execute_query(
                conn,
                "UPDATE tasks SET status = 'QUEUED', updated_at = ? WHERE id = ? AND project_id = ?",
                (datetime.now().isoformat(), dependent_id, project_id)
            )

            record_transition(
                conn,
                "task",
                dependent_id,
                "BLOCKED",
                "QUEUED",
                "System",
                f"依存タスク {completed_task_id} 完了によるブロック解除"
            )

            unblocked.append(dependent_id)

    return unblocked


def _release_task_file_locks(project_id: str, task_id: str) -> None:
    """
    タスクが保持するファイルロックを解放（新しい接続を開く）

    Args:
        project_id: プロジェクトID
        task_id: タスクID

    Raises:
        FileLockError: ロック解放失敗時
    """
    try:
        FileLockManager.release_locks(project_id, task_id)
    except FileLockError as e:
        # FileLockErrorを再スロー
        raise
    except Exception as e:
        # その他の予期しないエラー
        raise FileLockError(f"Unexpected error releasing locks for {task_id}: {e}")


def _release_task_file_locks_in_transaction(conn, project_id: str, task_id: str) -> None:
    """
    タスクが保持するファイルロックを解放（既存のトランザクション内で実行）

    Args:
        conn: データベース接続（既存のトランザクション）
        project_id: プロジェクトID
        task_id: タスクID

    Raises:
        FileLockError: ロック解放失敗時
    """
    try:
        execute_query(
            conn,
            "DELETE FROM file_locks WHERE project_id = ? AND task_id = ?",
            (project_id, task_id)
        )
    except DatabaseError as e:
        raise FileLockError(f"Failed to release locks for {task_id}: {e}")


def update_task_status(
    project_id: str,
    task_id: str,
    status: str,
    role: str = "Worker",
    reason: Optional[str] = None,
    render: bool = True,
) -> Dict[str, Any]:
    """
    タスクのステータスのみを更新（ショートカット関数）

    Args:
        project_id: プロジェクトID
        task_id: タスクID
        status: 新しいステータス
        role: 操作者の役割
        reason: 変更理由
        render: Markdown生成を実行するか

    Returns:
        更新されたタスク情報
    """
    return update_task(
        project_id,
        task_id,
        status=status,
        role=role,
        reason=reason,
        render=render,
    )


def replan_task(
    project_id: str,
    task_id: str,
    updated_description: Optional[str] = None,
    reason: Optional[str] = None,
    changed_by: str = "PM",
    completed_task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    後続タスクを再計画（description更新 + markdown再生成 + ログ記録）

    Args:
        project_id: プロジェクトID
        task_id: タスクID
        updated_description: 新しい説明
        reason: 再計画理由
        changed_by: 変更者
        completed_task_id: 完了タスクID（影響分析元）

    Returns:
        更新されたタスク情報

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)
    validate_task_id(task_id)

    with transaction() as conn:
        # タスク存在確認
        if not task_exists(conn, task_id, project_id):
            raise ValidationError(f"タスクが見つかりません: {task_id} (project: {project_id})", "task_id", task_id)

        # 現在のタスク情報を取得
        current = fetch_one(
            conn,
            """
            SELECT t.*, o.title as order_title
            FROM tasks t
            LEFT JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
            WHERE t.id = ? AND t.project_id = ?
            """,
            (task_id, project_id)
        )

        if not current:
            raise ValidationError(f"タスクが見つかりません: {task_id} (project: {project_id})", "task_id", task_id)

        current_dict = dict(current)
        order_id = current_dict.get("order_id")

        # description更新
        if updated_description is not None and updated_description != current_dict.get("description"):
            execute_query(
                conn,
                """
                UPDATE tasks
                SET description = ?, updated_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (updated_description, datetime.now().isoformat(), task_id, project_id)
            )

            # 変更履歴を記録
            execute_query(
                conn,
                """
                INSERT INTO change_history (
                    entity_type, entity_id, field_name,
                    old_value, new_value, changed_by, change_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "task", task_id, "description",
                    current_dict.get("description"), updated_description,
                    changed_by, reason or "再計画による更新"
                )
            )

            # 再計画ログをエスカレーションとして記録
            try:
                _log_replan_escalation(
                    conn, project_id, task_id, order_id,
                    completed_task_id, reason
                )
            except Exception as e:
                # エスカレーションログ失敗は警告のみ
                print(f"警告: 再計画ログ記録失敗: {e}", file=sys.stderr)

        # 更新後のタスク情報を取得
        updated = fetch_one(
            conn,
            """
            SELECT t.*, o.title as order_title
            FROM tasks t
            LEFT JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
            WHERE t.id = ? AND t.project_id = ?
            """,
            (task_id, project_id)
        )

        result = row_to_dict(updated)

    # markdown再生成
    if order_id:
        try:
            _regenerate_task_markdown(project_id, order_id, result)
        except Exception as e:
            # markdown生成失敗はログに記録するが、エラーにはしない
            print(f"警告: TASK markdown再生成失敗: {e}", file=sys.stderr)

    return result


def _log_replan_escalation(
    conn,
    project_id: str,
    task_id: str,
    order_id: Optional[str],
    completed_task_id: Optional[str],
    reason: Optional[str]
) -> None:
    """
    再計画をエスカレーションログとして記録

    Args:
        conn: データベース接続
        project_id: プロジェクトID
        task_id: タスクID
        order_id: ORDER ID
        completed_task_id: 完了タスクID
        reason: 再計画理由
    """
    try:
        # log_escalationをインポート（遅延インポート）
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from escalation.log_escalation import log_escalation

        description = f"タスク再計画: {completed_task_id or '不明'} 完了後の影響分析により自動更新"
        if reason:
            description += f"\n理由: {reason}"

        log_escalation(
            project_id=project_id,
            task_id=task_id,
            escalation_type="task_replan",
            description=description,
            order_id=order_id,
            metadata={
                "completed_task_id": completed_task_id,
                "reason": reason,
            },
            severity="MEDIUM"
        )
    except ImportError:
        # log_escalationが利用できない場合はスキップ
        pass


def _regenerate_task_markdown(project_id: str, order_id: str, task: Dict[str, Any]) -> None:
    """
    TASKファイルのMarkdownを再生成

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        task: タスク情報辞書
    """
    # プロジェクトパスを取得
    project_root = Path(__file__).resolve().parent.parent.parent
    result_dir = project_root / "PROJECTS" / project_id / "RESULT" / order_id
    queue_dir = result_dir / "04_QUEUE"
    queue_dir.mkdir(parents=True, exist_ok=True)

    task_id = task.get("id", "UNKNOWN")
    task_file = queue_dir / f"{task_id}.md"

    # markdown内容を生成
    content = _format_task_markdown(task, order_id)

    # ファイルに書き込み
    task_file.write_text(content, encoding="utf-8")


def _format_task_markdown(task: Dict[str, Any], order_id: str) -> str:
    """
    TASKファイルのMarkdown内容をフォーマット

    Args:
        task: タスク情報辞書
        order_id: ORDER ID

    Returns:
        Markdown形式のタスク内容
    """
    task_id = task.get("id", "UNKNOWN")
    title = task.get("title", "Untitled Task")
    description = task.get("description", "（説明なし）")
    priority = task.get("priority", "P1")
    model = task.get("recommended_model", "Sonnet")

    # 依存タスクの取得
    conn = get_connection()
    try:
        depends_rows = fetch_all(
            conn,
            "SELECT depends_on_task_id FROM task_dependencies WHERE task_id = ? AND project_id = ?",
            (task_id, task.get("project_id"))
        )
        depends_on = [row["depends_on_task_id"] for row in depends_rows] if depends_rows else []
    finally:
        conn.close()

    # 依存タスクの表示
    depends_display = ", ".join(depends_on) if depends_on else "なし"

    lines = [
        f"# {task_id}: {title}",
        "",
        "## 基本情報",
        "",
        "| 項目 | 内容 |",
        "|------|------|",
        f"| タスクID | {task_id} |",
        f"| ORDER | {order_id} |",
        f"| 推奨モデル | {model} |",
        f"| 優先度 | {priority} |",
        f"| 依存 | {depends_display} |",
        "",
        "---",
        "",
        "## 実施内容",
        "",
        description,
        "",
        "---",
        "",
        "## 完了条件",
        "",
        "- [ ] タスクの実施内容がすべて完了していること",
        "- [ ] 成果物が適切に作成・更新されていること",
        "- [ ] エラーや警告が残っていないこと",
        "",
        "---",
        "",
    ]

    # 対象ファイル（target_filesがある場合）
    target_files_json = task.get("target_files")
    if target_files_json:
        try:
            import json
            target_files = json.loads(target_files_json) if isinstance(target_files_json, str) else target_files_json
            if target_files:
                lines.append("## 対象ファイル")
                lines.append("")
                for file in target_files:
                    lines.append(f"- `{file}`")
                lines.append("")
                lines.append("---")
                lines.append("")
        except Exception:
            pass

    lines.append("## 注意事項")
    lines.append("")
    lines.append("**既知バグパターン**: 実装前に必ず既知バグパターン（DBのbugsテーブル）を確認してください")
    lines.append("")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


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
        description="タスクを更新",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("task_id", help="タスクID")
    parser.add_argument("--status", help="ステータス変更")
    parser.add_argument("--assignee", help="担当者変更")
    parser.add_argument("--title", help="タイトル変更")
    parser.add_argument("--description", help="説明変更")
    parser.add_argument("--priority", help="優先度変更（P0/P1/P2）")
    parser.add_argument("--markdown-created", choices=["true", "false"], help="Markdownファイル作成状態（true/false）")
    parser.add_argument("--role", default="Worker", help="操作者の役割（PM/Worker）")
    parser.add_argument("--reason", help="変更理由")
    parser.add_argument("--no-render", action="store_true", help="Markdown生成をスキップ")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    # markdown_created引数のパース
    markdown_created = None
    if args.markdown_created is not None:
        markdown_created = args.markdown_created.lower() == "true"

    # 更新内容がなければエラー
    if not any([args.status, args.assignee, args.title, args.description, args.priority, args.markdown_created]):
        print("エラー: 更新内容を指定してください", file=sys.stderr)
        sys.exit(1)

    try:
        result = update_task(
            args.project_id,
            args.task_id,
            status=args.status,
            assignee=args.assignee,
            title=args.title,
            description=args.description,
            priority=args.priority,
            markdown_created=markdown_created,
            role=args.role,
            reason=args.reason,
            render=not args.no_render,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"タスクを更新しました: {result['id']}")
            print(f"  タイトル: {result['title']}")
            print(f"  ステータス: {result['status']}")
            if result.get('assignee'):
                print(f"  担当者: {result['assignee']}")

    except (ValidationError, TransitionError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
