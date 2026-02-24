#!/usr/bin/env python3
"""
AI PM Framework - docs/配下ファイル一覧取得スクリプト

プロジェクトのdocs/ディレクトリ配下にある全.mdファイルを一覧表示する。
decisions/サブディレクトリも再帰的に探索し、各ファイルのタイトル（最初の#行）、
サイズ、更新日時を返す。

Usage:
    python backend/project/docs_list.py PROJECT_ID [--json]

Arguments:
    PROJECT_ID    プロジェクトID（例: ai_pm_manager_v2）

Options:
    --json        JSON形式で出力（デフォルト）
    --table       テーブル形式で出力

Output (JSON):
    {
        "success": true,
        "project_id": "...",
        "docs_path": "...",
        "files": [
            {
                "filename": "architecture.md",
                "relative_path": "architecture.md",
                "title": "アーキテクチャ概要",
                "size_bytes": 1234,
                "updated_at": "2026-02-24T12:00:00"
            },
            ...
        ],
        "total_count": 7
    }

Example:
    python backend/project/docs_list.py ai_pm_manager_v2
    python backend/project/docs_list.py ai_pm_manager_v2 --json
    python backend/project/docs_list.py ai_pm_manager_v2 --table
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional


# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from config.db_config import setup_utf8_output, get_project_paths


def _extract_title(file_path: Path) -> Optional[str]:
    """
    Markdownファイルの最初の#行からタイトルを抽出する

    Args:
        file_path: Markdownファイルのパス

    Returns:
        タイトル文字列、見つからない場合はNone
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("# "):
                    return line[2:].strip()
        return None
    except Exception:
        return None


def list_docs(project_id: str) -> Dict[str, Any]:
    """
    docs/配下の全.mdファイル一覧を取得する

    Args:
        project_id: プロジェクトID

    Returns:
        ファイル一覧情報を含む辞書
    """
    paths = get_project_paths(project_id)
    docs_path = paths["docs"]

    if not docs_path.exists():
        return {
            "success": False,
            "error": f"docs/ ディレクトリが見つかりません: {docs_path}",
            "project_id": project_id,
        }

    if not docs_path.is_dir():
        return {
            "success": False,
            "error": f"docs/ がディレクトリではありません: {docs_path}",
            "project_id": project_id,
        }

    files: List[Dict[str, Any]] = []

    # docs/配下の全.mdファイルを再帰的に探索
    for md_file in sorted(docs_path.rglob("*.md")):
        if not md_file.is_file():
            continue

        # docs/からの相対パス（Windowsでもスラッシュ区切り）
        relative_path = md_file.relative_to(docs_path).as_posix()

        # ファイル情報取得
        stat = md_file.stat()
        updated_at = datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%S")

        title = _extract_title(md_file)

        files.append({
            "filename": md_file.name,
            "relative_path": relative_path,
            "title": title or md_file.stem,
            "size_bytes": stat.st_size,
            "updated_at": updated_at,
        })

    return {
        "success": True,
        "project_id": project_id,
        "docs_path": str(docs_path),
        "files": files,
        "total_count": len(files),
    }


def format_table(result: Dict[str, Any]) -> str:
    """
    ファイル一覧をテーブル形式でフォーマットする

    Args:
        result: list_docs()の戻り値

    Returns:
        テーブル形式の文字列
    """
    if not result.get("success"):
        return f"エラー: {result.get('error', '不明なエラー')}"

    files = result.get("files", [])
    if not files:
        return "docs/ 配下にファイルが見つかりません。"

    lines = [
        f"プロジェクト: {result['project_id']}",
        f"docs/パス: {result['docs_path']}",
        f"ファイル数: {result['total_count']}",
        "",
        "| ファイル | タイトル | サイズ | 更新日時 |",
        "|---------|---------|--------|----------|",
    ]

    for f in files:
        size_str = _format_size(f["size_bytes"])
        lines.append(
            f"| {f['relative_path']} | {f['title']} | {size_str} | {f['updated_at']} |"
        )

    return "\n".join(lines)


def _format_size(size_bytes: int) -> str:
    """バイトサイズを人間に読みやすい形式に変換"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


def main() -> None:
    """CLIエントリーポイント"""
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="AI PM Framework - docs/配下ファイル一覧取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "project_id",
        help="プロジェクトID（例: ai_pm_manager_v2）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        dest="json_output",
        help="JSON形式で出力（デフォルト）",
    )
    parser.add_argument(
        "--table",
        action="store_true",
        help="テーブル形式で出力",
    )

    args = parser.parse_args()

    result = list_docs(args.project_id)

    if args.table:
        print(format_table(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result.get("success", False):
        sys.exit(1)


if __name__ == "__main__":
    main()
