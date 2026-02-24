#!/usr/bin/env python3
"""
AI PM Framework - タスク内容に基づくドキュメント選択的参照ロジック

タスクのタイトル・説明文からキーワードマッチングで必要なdocs/配下ドキュメントを
選択し、Workerプロンプトに注入するためのドキュメント一覧と内容を返す。

Usage:
    python backend/project/docs_selector.py PROJECT_ID --title "タスク名" --description "説明" [--json]

Arguments:
    PROJECT_ID    プロジェクトID（例: ai_pm_manager_v2）

Options:
    --title       タスクのタイトル
    --description タスクの説明文
    --json        JSON形式で出力（デフォルト）
    --table       テーブル形式で出力

Example:
    python backend/project/docs_selector.py ai_pm_manager_v2 --title "DB スキーマ変更" --description "テーブル追加"
    python backend/project/docs_selector.py ai_pm_manager_v2 --title "API実装" --description "IPC追加" --json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from config.db_config import setup_utf8_output, get_project_paths


# === カテゴリ定義（docs_migrate.py の CATEGORY_DEFINITIONS と同一） ===
# キーワードは実装指示に基づき、docs_migrate.py のものを拡張

CATEGORY_KEYWORDS = {
    "architecture": {
        "filename": "architecture.md",
        "description": "アーキテクチャ概要",
        "keywords": [
            "アーキテクチャ", "構成", "ディレクトリ", "技術スタック",
            "構造", "コンポーネント", "モジュール",
        ],
    },
    "db_schema": {
        "filename": "db_schema.md",
        "description": "DBスキーマ定義",
        "keywords": [
            "DB", "データベース", "スキーマ", "テーブル",
            "マイグレーション", "SQL",
        ],
    },
    "api_spec": {
        "filename": "api_spec.md",
        "description": "API仕様",
        "keywords": [
            "API", "IPC", "エンドポイント", "インターフェース",
            "preload", "main.ts",
        ],
    },
    "dev_rules": {
        "filename": "dev_rules.md",
        "description": "開発ルール・制約",
        "keywords": [
            "ルール", "制約", "規約", "開発", "環境",
            "ビルド", "デプロイ", "パス",
        ],
    },
    "bug_history": {
        "filename": "bug_history.md",
        "description": "バグ・既知の問題",
        "keywords": [
            "バグ", "BUG", "既知", "問題", "障害", "エラー",
        ],
    },
}


def _match_keywords(text: str, keywords: List[str]) -> List[str]:
    """
    テキスト中にマッチするキーワードを返す。

    大文字小文字を区別せずにマッチする。

    Args:
        text: 検索対象テキスト
        keywords: マッチ対象キーワードリスト

    Returns:
        マッチしたキーワードのリスト
    """
    text_lower = text.lower()
    matched = []
    for keyword in keywords:
        if keyword.lower() in text_lower:
            matched.append(keyword)
    return matched


def select_docs(
    project_id: str,
    task_title: str,
    task_description: str,
) -> List[Dict[str, Any]]:
    """
    タスク内容に基づいて参照すべきdocs/ファイルを選択する。

    ロジック:
    1. docs/配下のファイル一覧を取得
    2. 各ドキュメントのカテゴリキーワードとタスクのタイトル・説明をマッチング
    3. マッチしたドキュメントのパスと内容を返す
    4. INDEX.mdは常に含める（ドキュメント概要として）
    5. マッチするドキュメントがない場合はINDEX.mdのみ返す

    Args:
        project_id: プロジェクトID
        task_title: タスクのタイトル
        task_description: タスクの説明文

    Returns:
        [{"filename": "architecture.md", "content": "...", "reason": "..."}, ...]
    """
    paths = get_project_paths(project_id)
    docs_path = paths["docs"]

    # docs/ディレクトリが存在しない場合は空リストを返す
    if not docs_path.exists() or not docs_path.is_dir():
        return []

    # 検索対象テキスト（タイトル + 説明を結合）
    search_text = f"{task_title} {task_description}"

    selected: List[Dict[str, Any]] = []
    selected_filenames: set = set()

    # 1. INDEX.md は常に含める
    index_path = docs_path / "INDEX.md"
    if index_path.exists() and index_path.is_file():
        try:
            content = index_path.read_text(encoding="utf-8")
            selected.append({
                "filename": "INDEX.md",
                "content": content,
                "reason": "ドキュメント概要（常に含む）",
            })
            selected_filenames.add("INDEX.md")
        except Exception:
            pass  # 読み取り失敗時はスキップ

    # 2. カテゴリキーワードマッチング
    for category, defn in CATEGORY_KEYWORDS.items():
        filename = defn["filename"]
        keywords = defn["keywords"]

        # 既に選択済みならスキップ
        if filename in selected_filenames:
            continue

        # キーワードマッチ
        matched_keywords = _match_keywords(search_text, keywords)
        if not matched_keywords:
            continue

        # ファイル存在確認＆読み取り
        file_path = docs_path / filename
        if not file_path.exists() or not file_path.is_file():
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
            reason = f"キーワードマッチ: {', '.join(matched_keywords)}"
            selected.append({
                "filename": filename,
                "content": content,
                "reason": reason,
            })
            selected_filenames.add(filename)
        except Exception:
            pass  # 読み取り失敗時はスキップ

    return selected


def select_docs_result(
    project_id: str,
    task_title: str,
    task_description: str,
) -> Dict[str, Any]:
    """
    select_docs()のラッパー。CLIやJSON出力用に結果を辞書形式で返す。

    Args:
        project_id: プロジェクトID
        task_title: タスクのタイトル
        task_description: タスクの説明文

    Returns:
        結果辞書（success, project_id, docs, total_count 等）
    """
    paths = get_project_paths(project_id)
    docs_path = paths["docs"]

    if not docs_path.exists():
        return {
            "success": False,
            "error": f"docs/ ディレクトリが見つかりません: {docs_path}",
            "project_id": project_id,
        }

    docs = select_docs(project_id, task_title, task_description)

    # 内容のサイズ情報を追加（JSONレスポンス用、contentは含めない）
    docs_summary = []
    for doc in docs:
        docs_summary.append({
            "filename": doc["filename"],
            "reason": doc["reason"],
            "size_bytes": len(doc["content"].encode("utf-8")),
        })

    return {
        "success": True,
        "project_id": project_id,
        "task_title": task_title,
        "task_description": task_description,
        "docs_path": str(docs_path),
        "selected_docs": docs_summary,
        "total_count": len(docs),
    }


def format_table(result: Dict[str, Any]) -> str:
    """
    選択結果をテーブル形式でフォーマットする。

    Args:
        result: select_docs_result()の戻り値

    Returns:
        テーブル形式の文字列
    """
    if not result.get("success"):
        return f"エラー: {result.get('error', '不明なエラー')}"

    docs = result.get("selected_docs", [])
    lines = [
        f"プロジェクト: {result['project_id']}",
        f"タスク: {result.get('task_title', '')}",
        f"説明: {result.get('task_description', '')}",
        f"docs/パス: {result['docs_path']}",
        f"選択ドキュメント数: {result['total_count']}",
        "",
    ]

    if not docs:
        lines.append("（マッチするドキュメントなし）")
        return "\n".join(lines)

    lines.append("| ファイル | 理由 | サイズ |")
    lines.append("|---------|------|--------|")

    for doc in docs:
        size_str = _format_size(doc["size_bytes"])
        lines.append(f"| {doc['filename']} | {doc['reason']} | {size_str} |")

    return "\n".join(lines)


def _format_size(size_bytes: int) -> str:
    """バイトサイズを人間に読みやすい形式に変換"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


# === CLI エントリーポイント ===

def main() -> None:
    """CLIエントリーポイント"""
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="AI PM Framework - タスク内容に基づくドキュメント選択的参照",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "project_id",
        help="プロジェクトID（例: ai_pm_manager_v2）",
    )
    parser.add_argument(
        "--title",
        required=True,
        help="タスクのタイトル",
    )
    parser.add_argument(
        "--description",
        default="",
        help="タスクの説明文",
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

    result = select_docs_result(
        project_id=args.project_id,
        task_title=args.title,
        task_description=args.description,
    )

    if args.table:
        print(format_table(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result.get("success", False):
        sys.exit(1)


if __name__ == "__main__":
    main()
