#!/usr/bin/env python3
"""
AI PM Framework - ORDER作成スクリプト

Usage:
    python backend/order/create.py PROJECT_NAME --title "ORDER名" [options]

Options:
    --title         ORDER名（必須）
    --priority      優先度（P0/P1/P2、デフォルト: P1）
    --order-id      ORDER ID指定（省略時は自動採番）
    --check-dup     重複チェックを実行（デフォルト: False）
    --backlog-id    関連BACKLOG ID（重複チェック用）
    --force         重複警告を無視して強制作成
    --json          JSON形式で出力

Example:
    python backend/order/create.py AI_PM_PJ --title "新機能実装"
    python backend/order/create.py AI_PM_PJ --title "緊急バグ修正" --priority P0
    python backend/order/create.py AI_PM_PJ --title "機能X" --check-dup --backlog-id BACKLOG_058
"""

import argparse
import json
import logging
import sqlite3
import sys
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
    get_connection, transaction, execute_query, fetch_one, fetch_all,
    row_to_dict, rows_to_dicts, DatabaseError
)
from utils.validation import (
    validate_project_name, validate_order_id, validate_priority,
    project_exists, order_exists, get_next_order_number, ValidationError
)
from utils.transition import (
    validate_transition, record_transition, TransitionError
)


class DuplicateOrderError(Exception):
    """重複ORDER検出エラー"""
    def __init__(self, message: str, duplicates: List[Dict[str, Any]]):
        super().__init__(message)
        self.duplicates = duplicates


def check_duplicate_orders(
    project_id: str,
    title: str,
    backlog_id: Optional[str] = None,
    similarity_threshold: float = 0.9,
) -> Dict[str, Any]:
    """
    重複ORDERをチェック

    Args:
        project_id: プロジェクトID
        title: チェック対象のORDERタイトル
        backlog_id: 関連BACKLOG ID（あれば）
        similarity_threshold: タイトル類似度の閾値（0.0-1.0）

    Returns:
        {
            "has_duplicate": bool,
            "has_similar": bool,
            "exact_matches": [...],  # 完全一致
            "similar_matches": [...],  # 類似一致
            "backlog_matches": [...],  # BACKLOG ID一致
        }
    """
    validate_project_name(project_id)

    conn = get_connection()
    try:
        # アクティブORDER取得（PLANNING/IN_PROGRESS/REVIEW）
        active_orders = fetch_all(
            conn,
            """
            SELECT id, title, status, priority, started_at, created_at
            FROM orders
            WHERE project_id = ?
              AND status IN ('PLANNING', 'IN_PROGRESS', 'REVIEW')
            ORDER BY created_at DESC
            """,
            (project_id,)
        )
        active_orders = rows_to_dicts(active_orders)

        exact_matches = []
        similar_matches = []
        backlog_matches = []

        for order in active_orders:
            order_title = order.get("title", "")

            # 完全一致チェック
            if order_title == title:
                exact_matches.append(order)
                continue

            # タイトル類似度チェック（簡易実装）
            similarity = _calculate_similarity(title, order_title)
            if similarity >= similarity_threshold:
                order["similarity"] = round(similarity * 100, 1)
                similar_matches.append(order)

            # BACKLOG IDチェック（タイトルにBACKLOG_XXXが含まれている場合）
            if backlog_id:
                if backlog_id in order_title:
                    backlog_matches.append(order)

        return {
            "has_duplicate": len(exact_matches) > 0 or len(backlog_matches) > 0,
            "has_similar": len(similar_matches) > 0,
            "exact_matches": exact_matches,
            "similar_matches": similar_matches,
            "backlog_matches": backlog_matches,
        }
    finally:
        conn.close()


def _calculate_similarity(s1: str, s2: str) -> float:
    """
    2つの文字列の類似度を計算（Jaccard係数ベース）

    Returns:
        0.0-1.0の類似度
    """
    if not s1 or not s2:
        return 0.0

    # 単語単位で分割（日本語対応のため文字単位も含む）
    def tokenize(s: str) -> set:
        tokens = set()
        # 空白区切り
        tokens.update(s.split())
        # 2-gramも追加（日本語対応）
        for i in range(len(s) - 1):
            tokens.add(s[i:i+2])
        return tokens

    tokens1 = tokenize(s1.lower())
    tokens2 = tokenize(s2.lower())

    if not tokens1 or not tokens2:
        return 0.0

    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)

    return intersection / union if union > 0 else 0.0


def create_order(
    project_id: str,
    title: str,
    *,
    order_id: Optional[str] = None,
    priority: str = "P1",
    check_duplicate: bool = False,
    backlog_id: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    ORDERを作成

    Args:
        project_id: プロジェクトID
        title: ORDER名
        order_id: ORDER ID（省略時は自動採番）
        priority: 優先度（P0/P1/P2）
        check_duplicate: 重複チェックを実行するか
        backlog_id: 関連BACKLOG ID（重複チェック用）
        force: 重複警告を無視して強制作成

    Returns:
        作成されたORDER情報

    Raises:
        ValidationError: 入力検証エラー
        TransitionError: 状態遷移エラー
        DatabaseError: DB操作エラー
        DuplicateOrderError: 重複ORDER検出（check_duplicate=Trueの場合）
    """
    # 入力検証
    validate_project_name(project_id)
    validate_priority(priority)

    # 重複チェック（オプション）
    if check_duplicate and not force:
        dup_result = check_duplicate_orders(project_id, title, backlog_id)
        if dup_result["has_duplicate"]:
            duplicates = dup_result["exact_matches"] + dup_result["backlog_matches"]
            raise DuplicateOrderError(
                f"重複ORDERが検出されました（{len(duplicates)}件）。--force で強制作成可能です。",
                duplicates
            )

    # リトライ設定（Race Condition対策）
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            with transaction() as conn:
                # プロジェクト存在確認
                if not project_exists(conn, project_id):
                    raise ValidationError(f"プロジェクトが見つかりません: {project_id}", "project_id", project_id)

                # ORDER ID決定（指定がなければ自動採番）
                if order_id:
                    validate_order_id(order_id)
                    # 複合キー対応: project_idを指定してORDER存在確認
                    if order_exists(conn, order_id, project_id):
                        raise ValidationError(f"ORDER IDが既に存在します: {order_id} (project: {project_id})", "order_id", order_id)
                    final_order_id = order_id
                else:
                    final_order_id = get_next_order_number(conn, project_id)

                # 初期ステータス
                initial_status = "PLANNING"

                # 状態遷移検証
                validate_transition(conn, "order", None, initial_status, "PM")

                # ORDER作成
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
                        final_order_id, project_id, title, priority, initial_status,
                        now, now
                    )
                )

                # 状態遷移履歴を記録
                record_transition(
                    conn,
                    "order",
                    final_order_id,
                    None,
                    initial_status,
                    "PM",
                    f"ORDER作成: {title}"
                )

                # 作成されたORDERを取得（複合キー対応）
                created_order = fetch_one(
                    conn,
                    "SELECT * FROM orders WHERE id = ? AND project_id = ?",
                    (final_order_id, project_id)
                )

                result = row_to_dict(created_order)
                break  # 成功時はループを抜ける

        except sqlite3.IntegrityError as e:
            # UNIQUE制約違反の場合、リトライ（自動採番時のみ）
            if order_id is not None:
                # 明示的にIDを指定している場合はリトライしない
                raise ValidationError(
                    f"ORDER IDが既に存在します: {order_id} (project: {project_id})",
                    "order_id", order_id
                ) from e

            retry_count += 1
            if retry_count >= max_retries:
                logger.error(f"ORDER採番リトライ上限到達: {max_retries}回")
                raise DatabaseError(
                    f"ORDER採番に失敗しました（{max_retries}回リトライ）: {e}"
                ) from e

            logger.warning(f"ORDER採番競合検出、リトライ {retry_count}/{max_retries}")
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
        description="ORDERを作成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("--title", required=True, help="ORDER名")
    parser.add_argument("--order-id", help="ORDER ID（省略時は自動採番）")
    parser.add_argument("--priority", default="P1", help="優先度（P0/P1/P2）")
    parser.add_argument("--check-dup", action="store_true", help="重複チェックを実行")
    parser.add_argument("--backlog-id", help="関連BACKLOG ID（重複チェック用）")
    parser.add_argument("--force", action="store_true", help="重複警告を無視して強制作成")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        result = create_order(
            args.project_id,
            args.title,
            order_id=args.order_id,
            priority=args.priority,
            check_duplicate=args.check_dup,
            backlog_id=args.backlog_id,
            force=args.force,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"ORDERを作成しました: {result['id']}")
            print(f"  タイトル: {result['title']}")
            print(f"  優先度: {result['priority']}")
            print(f"  ステータス: {result['status']}")

    except DuplicateOrderError as e:
        print(f"【重複検出】{e}", file=sys.stderr)
        print("\n重複ORDER一覧:", file=sys.stderr)
        for dup in e.duplicates:
            print(f"  - {dup['id']}: {dup['title']} ({dup['status']})", file=sys.stderr)
        print("\n継続実行するには:", file=sys.stderr)
        print(f"  /aipm-full-auto {args.project_id} {{ORDER_ID}}", file=sys.stderr)
        print("\n強制作成するには:", file=sys.stderr)
        print(f"  python backend/order/create.py {args.project_id} --title \"{args.title}\" --force", file=sys.stderr)
        sys.exit(2)  # 重複検出は exit code 2
    except (ValidationError, TransitionError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
