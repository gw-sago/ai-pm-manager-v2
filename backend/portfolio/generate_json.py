#!/usr/bin/env python3
"""
AI PM Framework - ポートフォリオビュー用JSON生成

ポートフォリオビューHTMLから参照されるJSONファイルを生成します。

Usage:
    python backend/portfolio/generate_json.py [--output-dir DIR]

Example:
    python backend/portfolio/generate_json.py
    python backend/portfolio/generate_json.py --output-dir ./portfolio
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any


# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from portfolio.get_all_orders import get_all_orders
from portfolio.get_all_backlogs import get_all_backlogs
from portfolio.get_order_tasks import get_order_tasks


def generate_portfolio_json(output_dir: Path) -> Dict[str, Any]:
    """
    ポートフォリオビュー用のJSONファイルを生成

    Args:
        output_dir: 出力先ディレクトリ

    Returns:
        生成結果のサマリ
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "generated_files": [],
        "errors": [],
    }

    # 全ORDER一覧を生成
    try:
        orders = get_all_orders()
        orders_file = output_dir / "get_all_orders.json"
        with open(orders_file, "w", encoding="utf-8") as f:
            json.dump({"success": True, "count": len(orders), "orders": orders}, f, ensure_ascii=False, indent=2, default=str)
        results["generated_files"].append(str(orders_file))
    except Exception as e:
        results["errors"].append(f"ORDER一覧生成エラー: {e}")

    # 全バックログ一覧を生成
    try:
        backlogs = get_all_backlogs()
        backlogs_file = output_dir / "get_all_backlog.json"
        with open(backlogs_file, "w", encoding="utf-8") as f:
            json.dump({"success": True, "count": len(backlogs), "backlogs": backlogs}, f, ensure_ascii=False, indent=2, default=str)
        results["generated_files"].append(str(backlogs_file))
    except Exception as e:
        results["errors"].append(f"バックログ一覧生成エラー: {e}")

    # ORDER別タスク一覧を生成（アクティブORDERのみ）
    try:
        active_orders = get_all_orders(active_only=True)
        for order in active_orders:
            project_id = order["projectId"]
            order_id = order["id"]
            tasks = get_order_tasks(project_id, order_id)

            # プロジェクト別ディレクトリ
            project_dir = output_dir / project_id
            project_dir.mkdir(parents=True, exist_ok=True)

            tasks_file = project_dir / f"{order_id}_tasks.json"
            with open(tasks_file, "w", encoding="utf-8") as f:
                json.dump({
                    "success": True,
                    "projectId": project_id,
                    "orderId": order_id,
                    "count": len(tasks),
                    "tasks": tasks
                }, f, ensure_ascii=False, indent=2, default=str)
            results["generated_files"].append(str(tasks_file))

    except Exception as e:
        results["errors"].append(f"タスク一覧生成エラー: {e}")

    return results


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="ポートフォリオビュー用JSONファイルを生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "portfolio",
        help="出力先ディレクトリ（デフォルト: backend/portfolio/portfolio/）"
    )

    args = parser.parse_args()

    try:
        results = generate_portfolio_json(args.output_dir)

        print(f"JSON生成完了")
        print(f"  出力先: {args.output_dir}")
        print(f"  生成ファイル数: {len(results['generated_files'])}")

        if results["errors"]:
            print(f"  エラー: {len(results['errors'])}件")
            for err in results["errors"]:
                print(f"    - {err}")

        for f in results["generated_files"]:
            print(f"    - {f}")

    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
