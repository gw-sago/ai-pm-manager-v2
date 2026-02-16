#!/usr/bin/env python3
"""
AI PM Framework - BACKLOG→ORDER変換スクリプト

BACKLOG項目をORDERに変換し、新規プロジェクトとして開始します。
一連の処理をトランザクションで実行し、エラー時は自動ロールバックします。

Usage:
    python backend/backlog/to_order.py PROJECT_NAME BACKLOG_ID [options]

Options:
    --title         ORDER名（省略時はBACKLOGのタイトルを使用）
    --priority      ORDERの優先度（P0/P1/P2、省略時はBACKLOGの優先度から変換）
    --order-id      ORDER ID指定（省略時は自動採番）
    --no-order-md   ORDER.mdファイルを作成しない（DB登録のみ）
    --no-render     （廃止: 後方互換性のため引数のみ残存）
    --json          JSON形式で出力

Example:
    # 基本的な変換
    python backend/backlog/to_order.py AI_PM_PJ BACKLOG_029

    # ORDER名を指定
    python backend/backlog/to_order.py AI_PM_PJ BACKLOG_029 --title "新機能実装"

    # 緊急ORDER（P0）として変換
    python backend/backlog/to_order.py AI_PM_PJ BACKLOG_029 --priority P0
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# ロギング設定
logger = logging.getLogger(__name__)

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    transaction,
    execute_query,
    fetch_one,
    fetch_all,
    row_to_dict,
    rows_to_dicts,
    DatabaseError,
)
from utils.validation import (
    validate_project_name,
    validate_backlog_id,
    validate_order_id,
    validate_priority,
    project_exists,
    order_exists,
    get_next_order_number,
    ValidationError,
    VALID_STATUSES,
)
from utils.transition import (
    validate_transition,
    record_transition,
    TransitionError,
)


# 優先度変換マッピング（BACKLOG → ORDER）
PRIORITY_MAPPING = {
    "High": "P0",
    "Medium": "P1",
    "Low": "P2",
}


@dataclass
class ToOrderResult:
    """BACKLOG→ORDER変換結果"""
    success: bool
    backlog_id: str = ""
    order_id: str = ""
    backlog_title: str = ""
    order_title: str = ""
    old_status: str = ""
    new_status: str = ""
    order_priority: str = ""
    order_path: str = ""
    message: str = ""
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    order_md_created: bool = False
    result_dirs_created: bool = False


def generate_order_md_content(
    order_id: str,
    project_name: str,
    backlog_id: str,
    title: str,
    description: str,
    priority: str,
    today: str,
) -> str:
    """
    ORDER.mdファイルの内容を生成

    Args:
        order_id: ORDER ID
        project_name: プロジェクト名
        backlog_id: 元のBACKLOG ID
        title: ORDERタイトル
        description: 詳細説明
        priority: 優先度
        today: 今日の日付（YYYY-MM-DD形式）

    Returns:
        str: ORDER.mdの内容
    """
    return f"""# {order_id}.md

## 発注情報
- **発注ID**: {order_id}
- **発注日**: {today}
- **発注者**: User
- **優先度**: {priority}
- **由来**: {backlog_id}

---

## 発注内容

### 概要
{title}

### 詳細
{description or '（説明なし）'}

### 受け入れ条件
（BACKLOGから引き継ぎ）

---

## PM記入欄

### 要件理解チェック
- [ ] 発注内容を理解した
- [ ] GOAL.mdを作成した
- [ ] REQUIREMENTS.mdを作成した
- [ ] STAFFING.mdを作成した
- [ ] タスクを発行した

### 備考
（PM記入）

---

**作成日**: {today}
**作成者**: System（BACKLOG→ORDER変換）
**変換元**: PROJECTS/{project_name}/BACKLOG.md#{backlog_id}
"""


def create_order_md_file(
    project_name: str,
    order_id: str,
    backlog_id: str,
    title: str,
    description: str,
    priority: str,
) -> bool:
    """
    ORDER.mdファイルを作成

    Args:
        project_name: プロジェクト名
        order_id: ORDER ID
        backlog_id: 元のBACKLOG ID
        title: ORDERタイトル
        description: 詳細説明
        priority: 優先度

    Returns:
        bool: 作成成功したかどうか
    """
    today = datetime.now().strftime("%Y-%m-%d")
    content = generate_order_md_content(
        order_id=order_id,
        project_name=project_name,
        backlog_id=backlog_id,
        title=title,
        description=description,
        priority=priority,
        today=today,
    )

    order_path = Path(f"PROJECTS/{project_name}/ORDERS/{order_id}.md")
    order_path.parent.mkdir(parents=True, exist_ok=True)
    order_path.write_text(content, encoding="utf-8")
    logger.info(f"ORDER.mdファイルを作成しました: {order_path}")
    return True


def create_result_directories(project_name: str, order_id: str) -> bool:
    """
    ORDER結果ディレクトリ構造を作成

    Args:
        project_name: プロジェクト名
        order_id: ORDER ID

    Returns:
        bool: 作成成功したかどうか
    """
    base_path = Path(f"PROJECTS/{project_name}/RESULT/{order_id}")
    subdirs = [
        "01_GOAL",
        "02_REQUIREMENTS",
        "03_STAFFING",
        "04_TASK",
        "05_REPORT",
        "06_ARTIFACTS",
        "07_REVIEW",
    ]

    for subdir in subdirs:
        dir_path = base_path / subdir
        dir_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"結果ディレクトリを作成しました: {base_path}")
    return True


def get_backlog(conn, backlog_id: str, project_id: str) -> Optional[Dict[str, Any]]:
    """
    BACKLOG項目を取得

    Args:
        conn: データベース接続
        backlog_id: BACKLOG ID
        project_id: プロジェクトID

    Returns:
        Dict or None: BACKLOG情報
    """
    row = fetch_one(
        conn,
        "SELECT * FROM backlog_items WHERE id = ? AND project_id = ?",
        (backlog_id, project_id)
    )
    return row_to_dict(row)


def convert_backlog_to_order(
    project_name: str,
    backlog_id: str,
    *,
    title: Optional[str] = None,
    priority: Optional[str] = None,
    order_id: Optional[str] = None,
    render: bool = True,
    create_order_md: bool = True,
    db_path: Optional[Path] = None,
) -> ToOrderResult:
    """
    BACKLOG項目をORDERに変換

    一連の処理をトランザクションで実行し、エラー時は自動ロールバック。

    Args:
        project_name: プロジェクト名
        backlog_id: BACKLOG ID
        title: ORDER名（省略時はBACKLOGのタイトルを使用）
        priority: ORDERの優先度（省略時はBACKLOGの優先度から変換）
        order_id: ORDER ID（省略時は自動採番）
        render: （廃止: 後方互換性のため引数のみ残存）
        create_order_md: ORDER.mdファイルを作成するかどうか（デフォルト: True）
        db_path: データベースパス（テスト用）

    Returns:
        ToOrderResult: 変換結果

    Workflow:
        1. BACKLOG項目取得・ステータス検証
        2. ORDER ID採番
        3. ORDER作成（orders テーブル）
        4. BACKLOGステータス更新（TODO → IN_PROGRESS、ORDER紐付け）
        5. 状態遷移履歴記録
        6. ORDER.mdファイル作成（create_order_md=True の場合）
        7. RESULTディレクトリ構造作成（create_order_md=True の場合）
    """
    try:
        # 入力検証
        validate_project_name(project_name)
        validate_backlog_id(backlog_id)

        if priority:
            validate_priority(priority)

        if order_id:
            validate_order_id(order_id)

        with transaction(db_path=db_path) as conn:
            # 1. プロジェクト存在確認
            if not project_exists(conn, project_name):
                return ToOrderResult(
                    success=False,
                    backlog_id=backlog_id,
                    error=f"プロジェクトが見つかりません: {project_name}"
                )

            # 2. BACKLOG項目取得（project_id条件付き）
            backlog = get_backlog(conn, backlog_id, project_name)
            if not backlog:
                return ToOrderResult(
                    success=False,
                    backlog_id=backlog_id,
                    error=f"BACKLOGが見つかりません（プロジェクト {project_name} 内）: {backlog_id}"
                )

            # 3. ステータス検証（TODOのみ変換可能）
            old_status = backlog["status"]
            if old_status != "TODO":
                return ToOrderResult(
                    success=False,
                    backlog_id=backlog_id,
                    old_status=old_status,
                    error=f"ORDER化できるのはステータスが 'TODO' の項目のみです。現在のステータス: {old_status}"
                )

            # 4. ORDER ID決定（指定がなければ自動採番）
            if order_id:
                # 複合キー対応: project_nameを指定してORDER存在確認
                if order_exists(conn, order_id, project_name):
                    return ToOrderResult(
                        success=False,
                        backlog_id=backlog_id,
                        error=f"ORDER IDが既に存在します: {order_id} (project: {project_name})"
                    )
                final_order_id = order_id
            else:
                final_order_id = get_next_order_number(conn, project_name)

            # 5. ORDER名決定（指定がなければBACKLOGのタイトルを使用）
            final_title = title or backlog["title"]

            # 6. 優先度決定
            priority_warnings: List[str] = []
            if priority:
                final_priority = priority
            else:
                backlog_priority = backlog.get("priority", "Medium")
                if backlog_priority not in PRIORITY_MAPPING:
                    # 不明な優先度値の警告
                    warning_msg = f"不明な優先度値 '{backlog_priority}' をデフォルト 'P1' に変換しました"
                    logger.warning(warning_msg)
                    priority_warnings.append(warning_msg)
                final_priority = PRIORITY_MAPPING.get(backlog_priority, "P1")

            # 7. 状態遷移検証
            # ORDER: None → PLANNING
            validate_transition(conn, "order", None, "PLANNING", "PM")
            # BACKLOG: TODO → IN_PROGRESS
            validate_transition(conn, "backlog", "TODO", "IN_PROGRESS", "PM")

            # 8. ORDER作成
            now = datetime.now().isoformat()
            execute_query(
                conn,
                """
                INSERT INTO orders (
                    id, project_id, title, priority, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    final_order_id, project_name, final_title, final_priority,
                    "PLANNING", now, now
                )
            )

            # 9. ORDER状態遷移履歴を記録
            record_transition(
                conn,
                "order",
                final_order_id,
                None,
                "PLANNING",
                "PM",
                f"BACKLOG {backlog_id} から変換"
            )

            # 10. BACKLOG状態更新
            execute_query(
                conn,
                """
                UPDATE backlog_items
                SET status = ?,
                    related_order_id = ?,
                    updated_at = ?
                WHERE id = ? AND project_id = ?
                """,
                ("IN_PROGRESS", final_order_id, now, backlog_id, project_name)
            )

            # 11. BACKLOG状態遷移履歴を記録
            record_transition(
                conn,
                "backlog",
                backlog_id,
                "TODO",
                "IN_PROGRESS",
                "PM",
                f"ORDER {final_order_id} に変換"
            )

            # 成功結果を構築（まずDBトランザクション内で基本情報を設定）
            warnings_list: List[str] = priority_warnings.copy()  # 優先度警告を引き継ぐ
            backlog_description = backlog.get("description", "")

        # トランザクション外でファイル操作を実行
        # （DBコミット後にファイル作成することで、DB登録成功を保証）
        order_md_created = False
        result_dirs_created = False

        if create_order_md:
            try:
                # ORDER.mdファイル作成
                order_md_created = create_order_md_file(
                    project_name=project_name,
                    order_id=final_order_id,
                    backlog_id=backlog_id,
                    title=final_title,
                    description=backlog_description,
                    priority=final_priority,
                )
                # RESULTディレクトリ作成
                result_dirs_created = create_result_directories(
                    project_name=project_name,
                    order_id=final_order_id,
                )
            except Exception as e:
                # ファイル作成失敗は警告として記録（DB登録は成功済み）
                warning_msg = f"ORDER.mdファイル作成に失敗しました: {e}"
                logger.warning(warning_msg)
                warnings_list.append(warning_msg)

        result = ToOrderResult(
            success=True,
            backlog_id=backlog_id,
            order_id=final_order_id,
            backlog_title=backlog["title"],
            order_title=final_title,
            old_status="TODO",
            new_status="IN_PROGRESS",
            order_priority=final_priority,
            order_path=f"PROJECTS/{project_name}/ORDERS/{final_order_id}.md",
            message=f"BACKLOG {backlog_id} を {final_order_id} に変換しました",
            warnings=warnings_list,
            order_md_created=order_md_created,
            result_dirs_created=result_dirs_created,
        )

        return result

    except ValidationError as e:
        return ToOrderResult(
            success=False,
            backlog_id=backlog_id,
            error=f"入力検証エラー: {e}"
        )
    except TransitionError as e:
        return ToOrderResult(
            success=False,
            backlog_id=backlog_id,
            error=f"状態遷移エラー: {e}"
        )
    except DatabaseError as e:
        return ToOrderResult(
            success=False,
            backlog_id=backlog_id,
            error=f"データベースエラー: {e}"
        )
    except Exception as e:
        return ToOrderResult(
            success=False,
            backlog_id=backlog_id,
            error=f"予期しないエラー: {e}"
        )


def main():
    """コマンドライン実行"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="BACKLOG項目をORDERに変換",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 基本的な変換
  python to_order.py AI_PM_PJ BACKLOG_029

  # ORDER名を指定
  python to_order.py AI_PM_PJ BACKLOG_029 --title "新機能実装"

  # 緊急ORDER（P0）として変換
  python to_order.py AI_PM_PJ BACKLOG_029 --priority P0

  # JSON形式で出力
  python to_order.py AI_PM_PJ BACKLOG_029 --json

処理フロー:
  1. BACKLOG項目を取得（ステータスがTODOか検証）
  2. ORDER IDを採番（または指定）
  3. ordersテーブルにORDER作成（status=PLANNING）
  4. backlog_itemsテーブルを更新（status=IN_PROGRESS、ORDER紐付け）
  5. 状態遷移履歴を記録

ステータス遷移:
  ORDER:   None → PLANNING
  BACKLOG: TODO → IN_PROGRESS
"""
    )

    parser.add_argument(
        "project_name",
        help="プロジェクト名 (例: AI_PM_PJ)"
    )
    parser.add_argument(
        "backlog_id",
        help="BACKLOG ID (例: BACKLOG_029)"
    )
    parser.add_argument(
        "--title", "-t",
        help="ORDER名（省略時はBACKLOGのタイトルを使用）"
    )
    parser.add_argument(
        "--priority", "-p",
        choices=["P0", "P1", "P2"],
        help="ORDERの優先度（省略時はBACKLOGの優先度から変換）"
    )
    parser.add_argument(
        "--order-id", "-o",
        help="ORDER ID（省略時は自動採番）"
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="（廃止: 後方互換性のため引数のみ残存）"
    )
    parser.add_argument(
        "--no-order-md",
        action="store_true",
        help="ORDER.mdファイルを作成しない（DB登録のみ実行）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    result = convert_backlog_to_order(
        project_name=args.project_name,
        backlog_id=args.backlog_id,
        title=args.title,
        priority=args.priority,
        order_id=args.order_id,
        render=not args.no_render,
        create_order_md=not args.no_order_md,
    )

    if args.json:
        output = {
            "success": result.success,
            "backlog_id": result.backlog_id,
            "order_id": result.order_id,
            "backlog_title": result.backlog_title,
            "order_title": result.order_title,
            "old_status": result.old_status,
            "new_status": result.new_status,
            "order_priority": result.order_priority,
            "order_path": result.order_path,
            "message": result.message,
            "error": result.error,
            "warnings": result.warnings,
            "order_md_created": result.order_md_created,
            "result_dirs_created": result.result_dirs_created,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            print("【ORDER化完了】")
            print()
            print(f"BACKLOG: {result.backlog_id}")
            print(f"  タイトル: {result.backlog_title}")
            print(f"  ステータス: {result.old_status} → {result.new_status}")
            print()
            print(f"ORDER: {result.order_id}")
            print(f"  タイトル: {result.order_title}")
            print(f"  優先度: {result.order_priority}")
            print(f"  パス: {result.order_path}")
            print(f"  ORDER.md作成: {'完了' if result.order_md_created else 'スキップ'}")
            print(f"  RESULTディレクトリ: {'作成済み' if result.result_dirs_created else 'スキップ'}")
            print()
            if result.warnings:
                print("【警告】")
                for warning in result.warnings:
                    print(f"  - {warning}")
                print()
            print("【次のアクション】")
            print(f"PMとして要件定義とタスク発行を実施してください：")
            print(f"/aipm-pm {args.project_name} {result.order_id.replace('ORDER_', '')}")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
