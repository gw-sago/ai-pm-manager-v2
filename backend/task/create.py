#!/usr/bin/env python3
"""
AI PM Framework - タスク作成スクリプト

Usage:
    python backend/task/create.py PROJECT_NAME ORDER_ID --title "タスク名" [options]

Options:
    --title         タスク名（必須）
    --description   タスク説明
    --assignee      担当者（Worker A等）
    --priority      優先度（P0/P1/P2、デフォルト: P1）
    --model         推奨モデル（Haiku/Sonnet/Opus、手動指定）
    --auto-model    モデル自動選択（タスク情報から複雑度を計算）
    --depends       依存タスクID（カンマ区切り）
    --task-id       タスクID指定（省略時は自動採番）
    --render        Markdown生成を実行（デフォルト: True）
    --json          JSON形式で出力

Example:
    python backend/task/create.py AI_PM_PJ ORDER_036 --title "DBスキーマ設計"
    python backend/task/create.py AI_PM_PJ ORDER_036 --title "実装タスク" --depends "TASK_188,TASK_189" --model Opus
    python backend/task/create.py AI_PM_PJ ORDER_036 --title "認証リファクタ" --description "OAuth再構築" --auto-model
"""

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# ロギング設定
logger = logging.getLogger(__name__)


# aipm-db は Python パッケージ名として使えないためモジュール直接参照
try:
    # パッケージとしてインストールされている場合
    from aipm_db.utils.db import (
        get_connection, transaction, execute_query, fetch_one,
        row_to_dict, DatabaseError
    )
    from aipm_db.utils.validation import (
        validate_project_name, validate_order_id, validate_task_id,
        validate_status, validate_priority, validate_model,
        project_exists, order_exists, task_exists,
        get_next_task_number, ValidationError
    )
    from aipm_db.utils.transition import (
        validate_transition, record_transition, TransitionError
    )
    from aipm_db.cost.model_selector import auto_select_model
except ImportError:
    # 直接実行の場合
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from utils.db import (
        get_connection, transaction, execute_query, fetch_one,
        row_to_dict, DatabaseError
    )
    from utils.validation import (
        validate_project_name, validate_order_id, validate_task_id,
        validate_status, validate_priority, validate_model,
        project_exists, order_exists, task_exists,
        get_next_task_number, ValidationError
    )
    from utils.transition import (
        validate_transition, record_transition, TransitionError
    )
    from cost.model_selector import auto_select_model


# GUIキーワード検出用定数
GUI_KEYWORDS = [
    "アプリ起動", "アプリケーション起動", "画面操作", "画面確認",
    "スクリーンショット", "スクショ", "目視確認", "目視チェック",
    "ブラウザ起動", "ブラウザ操作", "手動確認", "手動テスト",
    "GUIテスト", "E2Eテスト", "画面遷移確認", "UI確認",
    "動作確認（画面）", "実機確認", "ウィンドウ操作",
]

GUI_ALTERNATIVE_NOTE = (
    "\n\n【Worker環境制約による注記】"
    "このタスクにはGUI操作を示唆するキーワードが含まれています。"
    "Workerはターミナル操作のみ可能です。"
    "品質確認は npm run build / tsc --noEmit / npm test で代替してください。"
)


def detect_gui_keywords(title: str, description: str = "") -> list[str]:
    """タスクタイトル・説明からGUI操作キーワードを検出する"""
    text = (title + " " + (description or "")).lower()
    found = [kw for kw in GUI_KEYWORDS if kw.lower() in text]
    return found


def create_task(
    project_id: str,
    order_id: str,
    title: str,
    *,
    task_id: Optional[str] = None,
    description: Optional[str] = None,
    assignee: Optional[str] = None,
    priority: str = "P1",
    recommended_model: Optional[str] = None,
    auto_model: bool = False,
    depends_on: Optional[List[str]] = None,
    target_files: Optional[str] = None,
    is_destructive_db_change: bool = False,
    render: bool = True,
) -> Dict[str, Any]:
    """
    タスクを作成

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        title: タスク名
        task_id: タスクID（省略時は自動採番）
        description: タスク説明
        assignee: 担当者
        priority: 優先度（P0/P1/P2）
        recommended_model: 推奨モデル（Haiku/Sonnet/Opus）、手動指定
        auto_model: モデル自動選択フラグ（タスク情報から複雑度を計算）
        depends_on: 依存タスクIDのリスト
        target_files: 対象ファイルリスト（JSON文字列）
        is_destructive_db_change: 破壊的DB変更フラグ（DROP TABLE等を含む場合True）
        render: Markdown生成を実行するか

    Returns:
        作成されたタスク情報

    Raises:
        ValidationError: 入力検証エラー
        TransitionError: 状態遷移エラー
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)
    validate_order_id(order_id)
    validate_priority(priority)

    # モデル選択ロジック
    complexity_score = None
    if auto_model and not recommended_model:
        # 自動選択: タスク情報から複雑度を計算してモデルを選択
        dependency_count = len(depends_on) if depends_on else 0
        # target_filesはJSON文字列の場合があるため、ファイル数をカウント
        target_file_count = 0
        if target_files:
            try:
                files_list = json.loads(target_files) if isinstance(target_files, str) else target_files
                target_file_count = len(files_list) if isinstance(files_list, list) else 0
            except (json.JSONDecodeError, TypeError):
                target_file_count = 0

        selection_result = auto_select_model(
            title=title,
            description=description or "",
            dependency_count=dependency_count,
            target_file_count=target_file_count
        )
        recommended_model = selection_result["recommended_model"]
        complexity_score = selection_result["complexity_score"]
        logger.info(f"Auto-selected model: {recommended_model} (complexity: {complexity_score})")
    elif recommended_model:
        # 手動指定: モデルを検証
        validate_model(recommended_model)
        # 複雑度スコアも計算して保存（将来的な分析用）
        dependency_count = len(depends_on) if depends_on else 0
        target_file_count = 0
        if target_files:
            try:
                files_list = json.loads(target_files) if isinstance(target_files, str) else target_files
                target_file_count = len(files_list) if isinstance(files_list, list) else 0
            except (json.JSONDecodeError, TypeError):
                target_file_count = 0

        try:
            from aipm_db.cost.task_complexity import calculate_complexity
        except ImportError:
            from cost.task_complexity import calculate_complexity
        complexity_score = calculate_complexity(
            title=title,
            description=description or "",
            dependency_count=dependency_count,
            target_file_count=target_file_count
        )
    else:
        # Neither auto_model nor recommended_model specified
        # → Keep current behavior (default to Opus)
        if recommended_model is None:
            recommended_model = "Opus"

    if depends_on:
        for dep_id in depends_on:
            validate_task_id(dep_id)

    # リトライ設定（Race Condition対策）
    max_retries = 3
    retry_count = 0
    result = None

    while retry_count < max_retries:
        try:
            with transaction() as conn:
                # プロジェクト・ORDER存在確認
                if not project_exists(conn, project_id):
                    raise ValidationError(f"プロジェクトが見つかりません: {project_id}", "project_id", project_id)

                # 複合キー対応: project_idを指定してORDER存在確認
                if not order_exists(conn, order_id, project_id):
                    raise ValidationError(f"ORDERが見つかりません: {order_id} (project: {project_id})", "order_id", order_id)

                # タスクID決定（指定がなければ自動採番）
                if task_id:
                    validate_task_id(task_id)
                    # 複合キー対応: project_idを指定してタスク存在確認
                    if task_exists(conn, task_id, project_id):
                        raise ValidationError(f"タスクIDが既に存在します: {task_id} (project: {project_id})", "task_id", task_id)
                    final_task_id = task_id
                else:
                    final_task_id = get_next_task_number(conn, order_id, project_id)

                # 依存タスクの存在確認
                if depends_on:
                    for dep_id in depends_on:
                        # 複合キー対応: project_idを指定して依存タスク存在確認
                        if not task_exists(conn, dep_id, project_id):
                            raise ValidationError(f"依存タスクが見つかりません: {dep_id} (project: {project_id})", "depends_on", dep_id)

                # 初期ステータス決定（依存あり=BLOCKED、なし=QUEUED）
                initial_status = "BLOCKED" if depends_on else "QUEUED"

                # 状態遷移検証
                validate_transition(conn, "task", None, initial_status, "PM")

                # GUIキーワード検出・警告
                gui_hits = detect_gui_keywords(title, description)
                if gui_hits:
                    logger.warning(
                        f"Task {final_task_id}: GUI操作キーワード検出 → {gui_hits}  "
                        "Workerはターミナル操作のみ可能です。"
                    )
                    # descriptionに代替手段の注記を追記
                    if description:
                        description = description + GUI_ALTERNATIVE_NOTE
                    else:
                        description = GUI_ALTERNATIVE_NOTE.lstrip()

                # タスク作成（複合キー対応: project_idを追加）
                now = datetime.now().isoformat()
                execute_query(
                    conn,
                    """
                    INSERT INTO tasks (
                        id, project_id, order_id, title, description, status,
                        assignee, priority, recommended_model, complexity_score, target_files,
                        is_destructive_db_change,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        final_task_id, project_id, order_id, title, description, initial_status,
                        assignee, priority, recommended_model, complexity_score, target_files,
                        1 if is_destructive_db_change else 0,
                        now, now
                    )
                )

                # 依存関係を登録（複合キー対応: project_idを追加）
                if depends_on:
                    for dep_id in depends_on:
                        execute_query(
                            conn,
                            """
                            INSERT INTO task_dependencies (task_id, depends_on_task_id, project_id)
                            VALUES (?, ?, ?)
                            """,
                            (final_task_id, dep_id, project_id)
                        )

                # 状態遷移履歴を記録
                record_transition(
                    conn,
                    "task",
                    final_task_id,
                    None,
                    initial_status,
                    "PM",
                    f"タスク作成: {title}"
                )

                # 作成されたタスクを取得（複合キー対応）
                created_task = fetch_one(
                    conn,
                    "SELECT * FROM tasks WHERE id = ? AND project_id = ?",
                    (final_task_id, project_id)
                )

                result = row_to_dict(created_task)

                # 依存関係も追加
                if depends_on:
                    result["depends_on"] = depends_on
                else:
                    result["depends_on"] = []

                break  # 成功時はループを抜ける

        except sqlite3.IntegrityError as e:
            # UNIQUE制約違反の場合、リトライ（自動採番時のみ）
            if task_id is not None:
                # 明示的にIDを指定している場合はリトライしない
                raise ValidationError(
                    f"タスクIDが既に存在します: {task_id} (project: {project_id})",
                    "task_id", task_id
                ) from e

            retry_count += 1
            if retry_count >= max_retries:
                logger.error(f"タスク採番リトライ上限到達: {max_retries}回")
                raise DatabaseError(
                    f"タスク採番に失敗しました（{max_retries}回リトライ）: {e}"
                ) from e

            logger.warning(f"タスク採番競合検出、リトライ {retry_count}/{max_retries}")
            continue

    return result


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
        description="タスクを作成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("order_id", help="ORDER ID")
    parser.add_argument("--title", required=True, help="タスク名")
    parser.add_argument("--task-id", help="タスクID（省略時は自動採番）")
    parser.add_argument("--description", help="タスク説明")
    parser.add_argument("--assignee", help="担当者（Worker A等）")
    parser.add_argument("--priority", default="P1", help="優先度（P0/P1/P2）")
    parser.add_argument("--model", help="推奨モデル（Haiku/Sonnet/Opus）、手動指定")
    parser.add_argument("--auto-model", action="store_true", help="モデル自動選択（タスク情報から複雑度を計算）")
    parser.add_argument("--depends", help="依存タスクID（カンマ区切り）")
    parser.add_argument("--no-render", action="store_true", help="Markdown生成をスキップ")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    # 依存タスクのパース
    depends_on = None
    if args.depends:
        depends_on = [d.strip() for d in args.depends.split(",") if d.strip()]

    try:
        result = create_task(
            args.project_id,
            args.order_id,
            args.title,
            task_id=args.task_id,
            description=args.description,
            assignee=args.assignee,
            priority=args.priority,
            recommended_model=args.model,
            auto_model=args.auto_model,
            depends_on=depends_on,
            render=not args.no_render,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"タスクを作成しました: {result['id']}")
            print(f"  タイトル: {result['title']}")
            print(f"  ステータス: {result['status']}")
            if result.get('recommended_model'):
                print(f"  推奨モデル: {result['recommended_model']}")
            if result.get('complexity_score') is not None:
                print(f"  複雑度スコア: {result['complexity_score']}")
            if result.get('depends_on'):
                print(f"  依存: {', '.join(result['depends_on'])}")

    except (ValidationError, TransitionError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
