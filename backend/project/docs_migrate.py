#!/usr/bin/env python3
"""
AI PM Framework - PROJECT_INFO.mdからdocs/配下への自動分割移行スクリプト

既存PROJECT_INFO.mdの内容をMarkdown見出し構造に基づいてルールベースで
自動分割し、docs/配下の各ドキュメントファイルとINDEX.mdを生成する。

Usage:
    python backend/project/docs_migrate.py PROJECT_ID [--dry-run] [--force] [--json]

Arguments:
    PROJECT_ID    プロジェクトID（例: ai_pm_manager_v2）

Options:
    --dry-run     プレビューモード（ファイル書き込みなし）
    --force       既存ファイルを上書き（デフォルトはスキップ）
    --json        JSON形式で出力

Section Mapping:
    見出しテキストに含まれるキーワードでマッピング：
    - architecture.md: アーキテクチャ, 構成, ディレクトリ, 技術スタック, 構造
    - db_schema.md:    DB, データベース, スキーマ, テーブル
    - api_spec.md:     API, IPC, エンドポイント, インターフェース
    - dev_rules.md:    ルール, 制約, 規約, 開発, 環境, ビルド
    - bug_history.md:  バグ, BUG, 既知, 問題, 障害
    - misc.md:         上記に該当しないセクション

Example:
    python backend/project/docs_migrate.py ai_pm_manager_v2 --dry-run
    python backend/project/docs_migrate.py ai_pm_manager_v2 --force --json
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from config.db_config import setup_utf8_output, get_project_paths


# === セクションマッピング定義 ===

# カテゴリ名 → (出力ファイル名, 説明, マッチキーワードリスト)
CATEGORY_DEFINITIONS = {
    "architecture": {
        "filename": "architecture.md",
        "description": "アーキテクチャ概要",
        "keywords": ["アーキテクチャ", "構成", "ディレクトリ", "技術スタック", "構造"],
    },
    "db_schema": {
        "filename": "db_schema.md",
        "description": "DBスキーマ定義",
        "keywords": ["DB", "データベース", "スキーマ", "テーブル"],
    },
    "api_spec": {
        "filename": "api_spec.md",
        "description": "API仕様",
        "keywords": ["API", "IPC", "エンドポイント", "インターフェース"],
    },
    "dev_rules": {
        "filename": "dev_rules.md",
        "description": "開発ルール・制約",
        "keywords": ["ルール", "制約", "規約", "開発", "環境", "ビルド"],
    },
    "bug_history": {
        "filename": "bug_history.md",
        "description": "バグ・既知の問題",
        "keywords": ["バグ", "BUG", "既知", "問題", "障害"],
    },
}

# デフォルトカテゴリ（マッピング不可のセクション用）
MISC_CATEGORY = {
    "filename": "misc.md",
    "description": "その他",
}


# === セクション解析 ===

def parse_sections(content: str) -> List[Dict[str, Any]]:
    """
    Markdownの見出し構造（## レベル）を解析し、セクションリストを返す。

    ##レベルの見出しをセクション区切りとして扱い、
    各セクションに見出しテキストと本文を格納する。
    # レベル（タイトル）の後、最初の ## までの内容は「概要」セクションとして扱う。

    Args:
        content: PROJECT_INFO.mdの全テキスト

    Returns:
        セクション辞書のリスト。各辞書は以下のキーを持つ:
        - heading: 見出しテキスト（##を除いた文字列）
        - level: 見出しレベル（1 or 2）
        - body: セクション本文
        - line_number: 見出しの行番号
    """
    lines = content.split("\n")
    sections: List[Dict[str, Any]] = []
    current_section: Optional[Dict[str, Any]] = None
    body_lines: List[str] = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # ## レベルの見出しを検出
        match = re.match(r"^(#{1,2})\s+(.+)$", stripped)
        if match:
            level = len(match.group(1))
            heading_text = match.group(2).strip()

            # 前のセクションを保存
            if current_section is not None:
                current_section["body"] = "\n".join(body_lines).strip()
                sections.append(current_section)
                body_lines = []

            current_section = {
                "heading": heading_text,
                "level": level,
                "body": "",
                "line_number": i + 1,
            }
        else:
            body_lines.append(line)

    # 最後のセクションを保存
    if current_section is not None:
        current_section["body"] = "\n".join(body_lines).strip()
        sections.append(current_section)

    return sections


def classify_section(heading: str) -> str:
    """
    見出しテキストからカテゴリ名を判定する。

    キーワードマッチングによるルールベース分類。
    複数カテゴリに該当する場合は、最初にマッチしたカテゴリを採用。
    どのカテゴリにも該当しない場合は "misc" を返す。

    Args:
        heading: 見出しテキスト

    Returns:
        カテゴリ名（"architecture", "db_schema", "api_spec",
                   "dev_rules", "bug_history", "misc"）
    """
    # 見出しテキストを正規化（番号プレフィクスを除去）
    # 例: "3. ディレクトリ構成" → "ディレクトリ構成"
    normalized = re.sub(r"^\d+\.\s*", "", heading)

    for category, defn in CATEGORY_DEFINITIONS.items():
        for keyword in defn["keywords"]:
            # 大文字小文字を区別せずにマッチ（BUG/bug等に対応）
            if keyword.lower() in normalized.lower():
                return category

    return "misc"


def group_sections_by_category(
    sections: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    セクションリストをカテゴリごとにグルーピングする。

    Args:
        sections: parse_sections()の戻り値

    Returns:
        カテゴリ名 → セクションリストの辞書
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}

    for section in sections:
        # # レベル（タイトル）は全カテゴリの前提情報としてスキップ
        # ただし本文がある場合は misc に入れる
        if section["level"] == 1:
            if section["body"]:
                category = "misc"
                section_with_category = {**section, "category": category}
                groups.setdefault(category, []).append(section_with_category)
            continue

        category = classify_section(section["heading"])
        section_with_category = {**section, "category": category}
        groups.setdefault(category, []).append(section_with_category)

    return groups


# === ドキュメント生成 ===

def generate_doc_content(
    category: str, sections: List[Dict[str, Any]], project_id: str
) -> str:
    """
    カテゴリのセクション群からMarkdownドキュメントを生成する。

    Args:
        category: カテゴリ名
        sections: そのカテゴリに属するセクションリスト
        project_id: プロジェクトID

    Returns:
        生成されたMarkdown文字列
    """
    # カテゴリ情報取得
    if category in CATEGORY_DEFINITIONS:
        cat_info = CATEGORY_DEFINITIONS[category]
    else:
        cat_info = MISC_CATEGORY

    lines = [
        f"# {cat_info['description']}",
        "",
        f"> このドキュメントは `PROJECT_INFO.md` から自動生成されました。",
        f"> プロジェクト: {project_id}",
        "",
    ]

    for section in sections:
        # 元の見出しレベルを維持（## → ##）
        heading_prefix = "#" * section["level"]
        lines.append(f"{heading_prefix} {section['heading']}")
        lines.append("")
        if section["body"]:
            lines.append(section["body"])
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def generate_index_md(
    project_id: str,
    generated_files: List[Dict[str, Any]],
    migration_date: str,
) -> str:
    """
    INDEX.mdを生成する。

    Args:
        project_id: プロジェクトID
        generated_files: 生成ファイル情報のリスト
        migration_date: 移行日（YYYY-MM-DD形式）

    Returns:
        INDEX.mdのMarkdown文字列
    """
    lines = [
        f"# {project_id} ドキュメント",
        "",
        "## 概要",
        "このプロジェクトのドキュメント一覧です。",
        "",
        "## ドキュメント一覧",
        "",
        "| ドキュメント | 説明 | 更新日 |",
        "|------------|------|--------|",
    ]

    for finfo in generated_files:
        filename = finfo["filename"]
        description = finfo["description"]
        lines.append(
            f"| [{filename}]({filename}) | {description} | {migration_date} |"
        )

    lines.extend([
        "",
        "## 生成情報",
        f"- 移行元: PROJECT_INFO.md",
        f"- 移行日: {migration_date}",
        "",
    ])

    return "\n".join(lines)


# === メイン処理 ===

def migrate_docs(
    project_id: str,
    dry_run: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """
    PROJECT_INFO.mdからdocs/配下へ自動分割移行を実行する。

    Args:
        project_id: プロジェクトID
        dry_run: Trueの場合はプレビューのみ（ファイル書き込みなし）
        force: Trueの場合は既存ファイルを上書き

    Returns:
        移行結果の辞書
    """
    paths = get_project_paths(project_id)
    base_path = paths["base"]
    docs_path = paths["docs"]
    project_info_path = base_path / "PROJECT_INFO.md"

    # PROJECT_INFO.md の存在確認
    if not project_info_path.exists():
        return {
            "success": False,
            "error": f"PROJECT_INFO.md が見つかりません: {project_info_path}",
            "project_id": project_id,
        }

    # PROJECT_INFO.md を読み込み
    try:
        content = project_info_path.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "success": False,
            "error": f"PROJECT_INFO.md の読み込みに失敗: {e}",
            "project_id": project_id,
        }

    if not content.strip():
        return {
            "success": False,
            "error": "PROJECT_INFO.md が空です",
            "project_id": project_id,
        }

    # セクション解析
    sections = parse_sections(content)
    if not sections:
        return {
            "success": False,
            "error": "PROJECT_INFO.md にセクション（見出し）が見つかりません",
            "project_id": project_id,
        }

    # カテゴリ別にグルーピング
    groups = group_sections_by_category(sections)

    # 移行日
    migration_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    # 各カテゴリのドキュメントを生成
    generated_files: List[Dict[str, Any]] = []
    skipped_files: List[str] = []
    total_sections = sum(
        1 for s in sections if s["level"] >= 2
    )
    mapped_sections = 0
    unmapped_sections = 0

    # docs/ ディレクトリの作成（dry-runでない場合）
    if not dry_run:
        docs_path.mkdir(parents=True, exist_ok=True)

    # 全カテゴリ定義を走査（内容がないカテゴリはスキップ）
    all_categories = list(CATEGORY_DEFINITIONS.keys()) + ["misc"]

    for category in all_categories:
        cat_sections = groups.get(category, [])
        if not cat_sections:
            continue

        if category in CATEGORY_DEFINITIONS:
            cat_info = CATEGORY_DEFINITIONS[category]
        else:
            cat_info = MISC_CATEGORY

        filename = cat_info["filename"]
        description = cat_info["description"]
        target_path = docs_path / filename

        # セクション数カウント
        section_count = len(cat_sections)
        if category == "misc":
            unmapped_sections += section_count
        else:
            mapped_sections += section_count

        # ドキュメント内容生成
        doc_content = generate_doc_content(category, cat_sections, project_id)
        size_bytes = len(doc_content.encode("utf-8"))

        # 既存ファイルチェック
        file_exists = target_path.exists()
        if file_exists and not force:
            skipped_files.append(filename)
            generated_files.append({
                "filename": filename,
                "description": description,
                "sections": section_count,
                "size_bytes": size_bytes,
                "status": "skipped (already exists)",
            })
            continue

        # ファイル書き込み
        if not dry_run:
            target_path.write_text(doc_content, encoding="utf-8")

        generated_files.append({
            "filename": filename,
            "description": description,
            "sections": section_count,
            "size_bytes": size_bytes,
            "status": "overwritten" if file_exists else "created",
        })

    # INDEX.md 生成
    index_content = generate_index_md(project_id, generated_files, migration_date)
    index_path = docs_path / "INDEX.md"
    index_exists = index_path.exists()

    index_generated = True
    if index_exists and not force:
        index_generated = False
        skipped_files.append("INDEX.md")
    elif not dry_run:
        index_path.write_text(index_content, encoding="utf-8")

    # 結果構築
    result = {
        "success": True,
        "project_id": project_id,
        "source": "PROJECT_INFO.md",
        "source_path": str(project_info_path),
        "docs_path": str(docs_path),
        "dry_run": dry_run,
        "force": force,
        "generated_files": generated_files,
        "index_generated": index_generated,
        "total_sections": total_sections,
        "mapped_sections": mapped_sections,
        "unmapped_sections": unmapped_sections,
    }

    if skipped_files:
        result["skipped_files"] = skipped_files

    return result


def format_human_readable(result: Dict[str, Any]) -> str:
    """
    移行結果を人間に読みやすい形式でフォーマットする。

    Args:
        result: migrate_docs()の戻り値

    Returns:
        フォーマット済み文字列
    """
    if not result.get("success"):
        return f"エラー: {result.get('error', '不明なエラー')}"

    lines = []

    mode = ""
    if result.get("dry_run"):
        mode = " [DRY-RUN]"
    lines.append(f"=== PROJECT_INFO.md → docs/ 移行{mode} ===")
    lines.append("")
    lines.append(f"プロジェクト: {result['project_id']}")
    lines.append(f"移行元: {result['source_path']}")
    lines.append(f"移行先: {result['docs_path']}")
    lines.append("")

    # セクション統計
    lines.append(f"セクション総数: {result['total_sections']}")
    lines.append(f"  マッピング済み: {result['mapped_sections']}")
    lines.append(f"  未マッピング(misc): {result['unmapped_sections']}")
    lines.append("")

    # 生成ファイル一覧
    lines.append("生成ファイル:")
    lines.append(
        "| ファイル名 | 説明 | セクション数 | サイズ | ステータス |"
    )
    lines.append(
        "|-----------|------|------------|--------|----------|"
    )
    for finfo in result.get("generated_files", []):
        size_str = _format_size(finfo["size_bytes"])
        lines.append(
            f"| {finfo['filename']} | {finfo['description']} "
            f"| {finfo['sections']} | {size_str} | {finfo['status']} |"
        )
    lines.append("")

    # INDEX.md
    if result.get("index_generated"):
        lines.append("INDEX.md: 生成済み")
    else:
        lines.append("INDEX.md: スキップ（既存）")

    if result.get("skipped_files"):
        lines.append("")
        lines.append(
            f"スキップされたファイル: {', '.join(result['skipped_files'])}"
        )
        lines.append("（上書きするには --force を指定してください）")

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
        description="AI PM Framework - PROJECT_INFO.mdからdocs/配下への自動分割移行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "project_id",
        help="プロジェクトID（例: ai_pm_manager_v2）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="プレビューモード（ファイル書き込みなし）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存ファイルを上書き",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="JSON形式で出力",
    )

    args = parser.parse_args()

    result = migrate_docs(
        project_id=args.project_id,
        dry_run=args.dry_run,
        force=args.force,
    )

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_human_readable(result))

    if not result.get("success", False):
        sys.exit(1)


if __name__ == "__main__":
    main()
