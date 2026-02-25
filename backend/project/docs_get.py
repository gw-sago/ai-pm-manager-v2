#!/usr/bin/env python3
"""
AI PM Framework - docs/配下ファイル内容取得スクリプト

プロジェクトのdocs/ディレクトリ配下にある指定ファイルの内容を取得する。
パストラバーサル防止機能を備え、docs/外のファイルへのアクセスを禁止する。

Usage:
    python backend/project/docs_get.py PROJECT_ID FILENAME [--json]

Arguments:
    PROJECT_ID    プロジェクトID（例: ai_pm_manager_v2）
    FILENAME      取得するファイル名（例: architecture.md, decisions/001_xxx.md）

Options:
    --json        JSON形式で出力（デフォルト）
    --raw         ファイル内容のみ出力（Markdownそのまま）

Output (JSON):
    {
        "success": true,
        "project_id": "...",
        "filename": "architecture.md",
        "relative_path": "architecture.md",
        "title": "アーキテクチャ概要",
        "size_bytes": 1234,
        "content": "# アーキテクチャ概要\\n..."
    }

Example:
    python backend/project/docs_get.py ai_pm_manager_v2 architecture.md
    python backend/project/docs_get.py ai_pm_manager_v2 decisions/001_xxx.md --json
    python backend/project/docs_get.py ai_pm_manager_v2 INDEX.md --raw
"""

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Dict, Any, Optional


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


def _is_safe_path(docs_dir: Path, target_path: Path) -> bool:
    """
    パストラバーサル防止: 対象パスがdocs/ディレクトリ内に収まっているか検証する

    Args:
        docs_dir: docs/ディレクトリの絶対パス
        target_path: 検証対象ファイルの絶対パス

    Returns:
        安全なパスであればTrue
    """
    try:
        # resolveで正規化（シンボリックリンク解決、..除去）
        resolved_docs = docs_dir.resolve()
        resolved_target = target_path.resolve()

        # target_pathがdocs_dir配下にあることを検証
        resolved_target.relative_to(resolved_docs)
        return True
    except ValueError:
        return False


def get_doc_content(project_id: str, filename: str) -> Dict[str, Any]:
    """
    docs/配下の指定ファイルの内容を取得する

    Args:
        project_id: プロジェクトID
        filename: docs/からの相対パス（例: architecture.md, decisions/001_xxx.md）

    Returns:
        ファイル内容を含む辞書
    """
    paths = get_project_paths(project_id)
    docs_path = paths["docs"]

    if not docs_path.exists():
        return {
            "success": False,
            "error": f"docs/ ディレクトリが見つかりません: {docs_path}",
            "project_id": project_id,
        }

    # ファイル名の正規化（バックスラッシュをスラッシュに統一）
    normalized_filename = filename.replace("\\", "/")

    # 拡張子がない場合は .md を自動付与（file.idから呼ばれるケース対応）
    if not Path(normalized_filename).suffix:
        normalized_filename += ".md"

    # パス構築
    target_path = docs_path / normalized_filename

    # パストラバーサル防止チェック
    if not _is_safe_path(docs_path, target_path):
        return {
            "success": False,
            "error": f"アクセス禁止: docs/外のファイルにはアクセスできません: {filename}",
            "project_id": project_id,
        }

    # ファイル存在チェック
    if not target_path.exists():
        return {
            "success": False,
            "error": f"ファイルが見つかりません: {filename}",
            "project_id": project_id,
            "docs_path": str(docs_path),
        }

    if not target_path.is_file():
        return {
            "success": False,
            "error": f"指定されたパスはファイルではありません: {filename}",
            "project_id": project_id,
        }

    # ファイル内容読み込み
    try:
        content = target_path.read_text(encoding="utf-8")
        stat = target_path.stat()
        relative_path = target_path.relative_to(docs_path).as_posix()
        title = _extract_title(target_path)

        # ファイルID（拡張子なしの相対パス）
        file_id = Path(relative_path).with_suffix("").as_posix()

        return {
            "success": True,
            "project_id": project_id,
            "file_id": file_id,
            "filename": target_path.name,
            "relative_path": relative_path,
            "title": title or target_path.stem,
            "size_bytes": stat.st_size,
            "content": content,
        }
    except UnicodeDecodeError as e:
        return {
            "success": False,
            "error": f"ファイルのエンコーディングエラー: {e}",
            "project_id": project_id,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"ファイル読み込みエラー: {e}",
            "project_id": project_id,
        }


def main() -> None:
    """CLIエントリーポイント"""
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="AI PM Framework - docs/配下ファイル内容取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "project_id",
        help="プロジェクトID（例: ai_pm_manager_v2）",
    )
    parser.add_argument(
        "filename",
        help="取得するファイル名（例: architecture.md, decisions/001_xxx.md）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        dest="json_output",
        help="JSON形式で出力（デフォルト）",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="ファイル内容のみ出力（Markdownそのまま）",
    )

    args = parser.parse_args()

    result = get_doc_content(args.project_id, args.filename)

    if args.raw:
        if result.get("success"):
            print(result["content"])
        else:
            print(f"エラー: {result.get('error', '不明なエラー')}", file=sys.stderr)
            sys.exit(1)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("success", False):
            sys.exit(1)


if __name__ == "__main__":
    main()
