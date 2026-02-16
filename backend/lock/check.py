#!/usr/bin/env python3
"""
AI PM Framework - モジュール競合チェックスクリプト

Usage:
    python backend/lock/check.py PROJECT_ID MODULE1 [MODULE2 ...]

Options:
    --json     JSON形式で出力

Example:
    python backend/lock/check.py AI_PM_PJ backend .claude/commands
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection, fetch_one, fetch_all, row_to_dict, rows_to_dicts, DatabaseError
)
from utils.validation import (
    validate_project_name, ValidationError
)


def check_conflict(
    project_id: str,
    modules: List[str],
) -> Dict[str, Any]:
    """
    モジュールの競合をチェック

    Args:
        project_id: プロジェクトID
        modules: チェック対象のモジュール名リスト

    Returns:
        競合チェック結果

    Raises:
        ValidationError: 入力検証エラー
        DatabaseError: DB操作エラー
    """
    # 入力検証
    validate_project_name(project_id)

    if not modules:
        raise ValidationError("モジュールを1つ以上指定してください", "modules", modules)

    conn = get_connection()
    try:
        conflicts = []
        available = []

        for module in modules:
            row = fetch_one(
                conn,
                """
                SELECT ml.id, ml.project_id, ml.order_id, ml.module_name, ml.locked_at,
                       o.title as order_title, o.status as order_status
                FROM module_locks ml
                LEFT JOIN orders o ON ml.order_id = o.id AND ml.project_id = o.project_id
                WHERE ml.project_id = ? AND ml.module_name = ?
                """,
                (project_id, module)
            )

            if row:
                conflict_info = row_to_dict(row)
                conflict_info['module_name'] = module
                conflicts.append(conflict_info)
            else:
                available.append(module)

        has_conflict = len(conflicts) > 0

        return {
            'project_id': project_id,
            'checked_modules': modules,
            'has_conflict': has_conflict,
            'conflicts': conflicts,
            'available': available,
        }

    finally:
        conn.close()


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="モジュールの競合をチェック",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("modules", nargs="+", help="チェック対象のモジュール名")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        result = check_conflict(
            args.project_id,
            args.modules,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"競合チェック結果: {args.project_id}")
            print("-" * 40)

            if result['has_conflict']:
                print("\n[競合あり]")
                for conflict in result['conflicts']:
                    print(f"  - {conflict['module_name']}")
                    print(f"      ロック保持: {conflict['order_id']}")
                    if conflict.get('order_title'):
                        print(f"      ORDER名: {conflict['order_title']}")
                    if conflict.get('order_status'):
                        print(f"      ステータス: {conflict['order_status']}")
                    print(f"      ロック日時: {conflict['locked_at']}")
            else:
                print("\n[競合なし] 全てのモジュールが利用可能です")

            if result['available']:
                print(f"\n利用可能なモジュール:")
                for module in result['available']:
                    print(f"  - {module}")

            # 終了コード
            sys.exit(1 if result['has_conflict'] else 0)

    except (ValidationError, DatabaseError) as e:
        if args.json:
            print(json.dumps({'error': str(e)}, ensure_ascii=False, indent=2))
        else:
            print(f"エラー: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        if args.json:
            print(json.dumps({'error': str(e)}, ensure_ascii=False, indent=2))
        else:
            print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
