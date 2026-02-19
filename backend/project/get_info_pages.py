#!/usr/bin/env python3
"""
AI PM Framework - INFO_PAGES読み込みスクリプト

プロジェクトのINFO_PAGES/index.jsonと各Markdownファイルを読み込む。
get_project_paths()を使いRoamingパスを解決する。

Usage:
    python backend/project/get_info_pages.py PROJECT_ID [--page PAGE_ID] [--json]

Arguments:
    PROJECT_ID    プロジェクトID（例: ai_pm_manager_v2）

Options:
    --page PAGE_ID   特定ページのコンテンツを取得（省略時はindex.json一覧を返す）
    --json           JSON形式で出力（デフォルト）

Output:
    index.json取得時:
        {"success": true, "data": {"version": "...", "project_id": "...", "pages": [...]}}
    ページコンテンツ取得時:
        {"success": true, "page_id": "...", "content": "..."}
    エラー時:
        {"success": false, "error": "..."}

Example:
    python backend/project/get_info_pages.py ai_pm_manager_v2
    python backend/project/get_info_pages.py ai_pm_manager_v2 --page overview
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any


# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from config.db_config import setup_utf8_output, get_project_paths


def get_info_pages_index(project_id: str) -> Dict[str, Any]:
    """
    INFO_PAGES/index.jsonを読み込む

    Args:
        project_id: プロジェクトID

    Returns:
        index.jsonの内容、存在しない場合はエラー情報
    """
    paths = get_project_paths(project_id)
    base_path = paths["base"]
    index_path = base_path / "INFO_PAGES" / "index.json"

    if not index_path.exists():
        return {
            "success": False,
            "error": f"INFO_PAGES/index.json not found: {index_path}"
        }

    try:
        content = index_path.read_text(encoding="utf-8")
        data = json.loads(content)
        return {
            "success": True,
            "data": data
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Invalid JSON in index.json: {e}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to read index.json: {e}"
        }


def get_info_page_content(project_id: str, page_id: str) -> Dict[str, Any]:
    """
    INFO_PAGESの指定ページのMarkdownコンテンツを取得

    Args:
        project_id: プロジェクトID
        page_id: ページID（index.jsonのidフィールド）

    Returns:
        ページコンテンツ、見つからない場合はエラー情報
    """
    # まずindex.jsonを読み込んでファイル名を取得
    index_result = get_info_pages_index(project_id)
    if not index_result["success"]:
        return index_result

    pages = index_result["data"].get("pages", [])
    page = next((p for p in pages if p.get("id") == page_id), None)

    if page is None:
        return {
            "success": False,
            "error": f"Page '{page_id}' not found in index.json"
        }

    paths = get_project_paths(project_id)
    base_path = paths["base"]
    page_path = base_path / "INFO_PAGES" / page["file"]

    if not page_path.exists():
        return {
            "success": False,
            "error": f"Page file not found: {page_path}"
        }

    try:
        content = page_path.read_text(encoding="utf-8")
        return {
            "success": True,
            "page_id": page_id,
            "title": page.get("title", page_id),
            "file": page["file"],
            "content": content
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to read page file: {e}"
        }


def main() -> None:
    """メインエントリポイント"""
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="AI PM Framework - INFO_PAGES読み込みスクリプト",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("project_id", help="プロジェクトID（例: ai_pm_manager_v2）")
    parser.add_argument(
        "--page",
        metavar="PAGE_ID",
        help="特定ページのコンテンツを取得（省略時はindex.json一覧を返す）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        dest="json_output",
        help="JSON形式で出力（デフォルト）"
    )

    args = parser.parse_args()

    if args.page:
        result = get_info_page_content(args.project_id, args.page)
    else:
        result = get_info_pages_index(args.project_id)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result.get("success", False):
        sys.exit(1)


if __name__ == "__main__":
    main()
