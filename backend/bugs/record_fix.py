#!/usr/bin/env python3
"""
AI PM Framework - バグ修正記録ヘルパー

バグ修正タスク完了時に、DBのbugsテーブルとPROJECT_INFO.mdの両方に記録する。

Usage:
    python backend/bugs/record_fix.py PROJECT_ID [options]

Options:
    --title         バグタイトル（必須）
    --description   バグの詳細説明（必須）
    --solution      解決策・修正内容（必須）
    --severity      深刻度（Critical/High/Medium/Low、デフォルト: Medium）
    --pattern-type  パターン分類
    --related-files 関連ファイルパス（カンマ区切り）
    --rule          再発防止ルール（指定時はRULE-XXXとしてPROJECT_INFO.mdに追記）
    --task-id       関連タスクID
    --order-id      関連ORDER ID
    --skip-db       DB登録をスキップ（PROJECT_INFO.mdのみ更新）
    --skip-file     PROJECT_INFO.md更新をスキップ（DB登録のみ）
    --json          JSON形式で出力

Example:
    python backend/bugs/record_fix.py ai_pm_manager_v2 \
        --title "相対パスによるLocal/Roaming不整合" \
        --description "to_order.pyが相対パスでLocalにファイル作成" \
        --solution "get_project_paths()経由に修正" \
        --severity High \
        --rule "ファイルパスはget_project_paths()で構築すること" \
        --task-id TASK_016
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List

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
    DatabaseError,
)
from config.db_config import get_project_paths

import logging
logger = logging.getLogger(__name__)


@dataclass
class RecordFixResult:
    """バグ修正記録結果"""
    success: bool
    bug_id: str = ""
    rule_id: str = ""
    bug_history_id: str = ""
    db_registered: bool = False
    file_updated: bool = False
    message: str = ""
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def _get_next_bug_number(conn) -> str:
    """次のBUG番号を取得"""
    row = fetch_one(
        conn,
        "SELECT MAX(CAST(SUBSTR(id, 5) AS INTEGER)) as max_num FROM bugs"
    )
    max_num = row["max_num"] if row and row["max_num"] else 0
    return f"BUG_{max_num + 1:03d}"


def _get_next_rule_number(content: str) -> str:
    """PROJECT_INFO.mdから次のRULE番号を取得"""
    matches = re.findall(r'RULE-(\d+)', content)
    if matches:
        max_num = max(int(m) for m in matches)
        return f"RULE-{max_num + 1:03d}"
    return "RULE-001"


def _get_next_bug_history_id(content: str) -> str:
    """PROJECT_INFO.mdから次のBUG-P番号を取得"""
    matches = re.findall(r'BUG-P(\d+)', content)
    if matches:
        max_num = max(int(m) for m in matches)
        return f"BUG-P{max_num + 1:03d}"
    return "BUG-P001"


def _register_bug_in_db(
    project_id: str,
    title: str,
    description: str,
    solution: str,
    severity: str = "Medium",
    pattern_type: Optional[str] = None,
    related_files: Optional[str] = None,
) -> Optional[str]:
    """DBにバグパターンを登録（重複チェック付き）"""
    try:
        with transaction() as conn:
            # 重複チェック（同一タイトル + 同一プロジェクト）
            existing = fetch_one(
                conn,
                "SELECT id FROM bugs WHERE title = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))",
                (title, project_id, project_id)
            )
            if existing:
                # 既存のバグパターンの occurrence_count をインクリメント
                execute_query(
                    conn,
                    """UPDATE bugs
                    SET occurrence_count = occurrence_count + 1,
                        last_occurred_at = ?,
                        updated_at = ?
                    WHERE id = ?""",
                    (datetime.now().isoformat(), datetime.now().isoformat(), existing["id"])
                )
                return existing["id"]

            # 新規登録
            bug_id = _get_next_bug_number(conn)
            now = datetime.now().isoformat()
            execute_query(
                conn,
                """INSERT INTO bugs (
                    id, project_id, title, description, pattern_type,
                    severity, status, solution, related_files, tags,
                    occurrence_count, last_occurred_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, NULL, 1, ?, ?, ?)""",
                (bug_id, project_id, title, description, pattern_type,
                 severity, solution, related_files, now, now, now)
            )
            return bug_id

    except Exception as e:
        logger.warning(f"DB登録失敗: {e}")
        return None


def _update_project_info(
    project_id: str,
    title: str,
    description: str,
    solution: str,
    rule_text: Optional[str] = None,
    task_id: Optional[str] = None,
) -> dict:
    """PROJECT_INFO.mdにバグ修正履歴と開発ルールを追記"""
    result = {"rule_id": "", "bug_history_id": "", "updated": False}

    try:
        paths = get_project_paths(project_id)
        project_info_path = paths["base"] / "PROJECT_INFO.md"

        if not project_info_path.exists():
            logger.warning(f"PROJECT_INFO.md が見つかりません: {project_info_path}")
            return result

        content = project_info_path.read_text(encoding="utf-8")
        today = datetime.now().strftime("%Y-%m-%d")
        modified = False

        # 1. バグ修正履歴セクションに追記
        bug_history_id = _get_next_bug_history_id(content)
        history_entry = f"| {bug_history_id} | {today} | {title} | {solution} |"

        if "## バグ修正履歴" in content:
            # 既存テーブルの最終行の後に追記
            lines = content.split("\n")
            insert_idx = None
            in_table = False
            for i, line in enumerate(lines):
                if "## バグ修正履歴" in line:
                    in_table = True
                    continue
                if in_table:
                    if line.startswith("|"):
                        insert_idx = i + 1
                    elif line.startswith("#") or (insert_idx and not line.strip()):
                        break

            if insert_idx:
                lines.insert(insert_idx, history_entry)
                content = "\n".join(lines)
                result["bug_history_id"] = bug_history_id
                modified = True
        else:
            # セクションがない場合は末尾に追加
            content += f"\n\n## バグ修正履歴\n\n| ID | 発生日 | 概要 | 対応 |\n|----|--------|------|------|\n{history_entry}\n"
            result["bug_history_id"] = bug_history_id
            modified = True

        # 2. 開発ルール追記（rule_text指定時のみ）
        if rule_text:
            rule_id = _get_next_rule_number(content)
            rule_entry = f"\n### {rule_id}: {rule_text}\n- **理由**: {description}\n- **発生日**: {today}"
            if task_id:
                rule_entry += f" / {task_id}"

            if "## 開発ルール" in content:
                # セクション末尾に追記
                lines = content.split("\n")
                insert_idx = len(lines)
                found_section = False
                for i, line in enumerate(lines):
                    if "## 開発ルール" in line:
                        found_section = True
                        continue
                    if found_section and line.startswith("## ") and "開発ルール" not in line:
                        insert_idx = i
                        break

                lines.insert(insert_idx, rule_entry)
                content = "\n".join(lines)
            else:
                content += f"\n\n## 開発ルール（再発防止）\n{rule_entry}\n"

            result["rule_id"] = rule_id
            modified = True

        if modified:
            project_info_path.write_text(content, encoding="utf-8")
            result["updated"] = True

    except Exception as e:
        logger.warning(f"PROJECT_INFO.md更新失敗: {e}")

    return result


def record_fix(
    project_id: str,
    title: str,
    description: str,
    solution: str,
    *,
    severity: str = "Medium",
    pattern_type: Optional[str] = None,
    related_files: Optional[str] = None,
    rule_text: Optional[str] = None,
    task_id: Optional[str] = None,
    order_id: Optional[str] = None,
    skip_db: bool = False,
    skip_file: bool = False,
) -> RecordFixResult:
    """
    バグ修正を記録（DB + PROJECT_INFO.md）

    Args:
        project_id: プロジェクトID
        title: バグタイトル
        description: バグの詳細説明
        solution: 解決策
        severity: 深刻度
        pattern_type: パターン分類
        related_files: 関連ファイル（カンマ区切り）
        rule_text: 再発防止ルール（指定時はRULE-XXXとして追記）
        task_id: 関連タスクID
        order_id: 関連ORDER ID
        skip_db: DB登録をスキップ
        skip_file: PROJECT_INFO.md更新をスキップ

    Returns:
        RecordFixResult
    """
    result = RecordFixResult(success=False)

    try:
        # 1. DB登録
        if not skip_db:
            bug_id = _register_bug_in_db(
                project_id=project_id,
                title=title,
                description=description,
                solution=solution,
                severity=severity,
                pattern_type=pattern_type,
                related_files=related_files,
            )
            if bug_id:
                result.bug_id = bug_id
                result.db_registered = True
            else:
                result.warnings.append("DB登録に失敗しました")

        # 2. PROJECT_INFO.md更新
        if not skip_file:
            file_result = _update_project_info(
                project_id=project_id,
                title=title,
                description=description,
                solution=solution,
                rule_text=rule_text,
                task_id=task_id,
            )
            if file_result["updated"]:
                result.rule_id = file_result["rule_id"]
                result.bug_history_id = file_result["bug_history_id"]
                result.file_updated = True
            else:
                result.warnings.append("PROJECT_INFO.md更新に失敗しました")

        # 成功判定
        if result.db_registered or result.file_updated:
            result.success = True
            parts = []
            if result.db_registered:
                parts.append(f"DB: {result.bug_id}")
            if result.file_updated:
                file_parts = []
                if result.bug_history_id:
                    file_parts.append(result.bug_history_id)
                if result.rule_id:
                    file_parts.append(result.rule_id)
                parts.append(f"PROJECT_INFO: {', '.join(file_parts)}")
            result.message = f"バグ修正記録完了 - {' | '.join(parts)}"
        else:
            result.error = "DB登録とPROJECT_INFO.md更新の両方に失敗しました"

    except Exception as e:
        result.error = f"予期しないエラー: {e}"

    return result


def main():
    """コマンドライン実行"""
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="バグ修正記録ヘルパー（DB + PROJECT_INFO.md）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("--title", "-t", required=True, help="バグタイトル")
    parser.add_argument("--description", "-d", required=True, help="バグの詳細説明")
    parser.add_argument("--solution", "-s", required=True, help="解決策・修正内容")
    parser.add_argument("--severity", choices=["Critical", "High", "Medium", "Low"], default="Medium", help="深刻度")
    parser.add_argument("--pattern-type", help="パターン分類")
    parser.add_argument("--related-files", help="関連ファイル（カンマ区切り）")
    parser.add_argument("--rule", help="再発防止ルール（RULE-XXXとして追記）")
    parser.add_argument("--task-id", help="関連タスクID")
    parser.add_argument("--order-id", help="関連ORDER ID")
    parser.add_argument("--skip-db", action="store_true", help="DB登録をスキップ")
    parser.add_argument("--skip-file", action="store_true", help="PROJECT_INFO.md更新をスキップ")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    result = record_fix(
        project_id=args.project_id,
        title=args.title,
        description=args.description,
        solution=args.solution,
        severity=args.severity,
        pattern_type=args.pattern_type,
        related_files=args.related_files,
        rule_text=args.rule,
        task_id=args.task_id,
        order_id=args.order_id,
        skip_db=args.skip_db,
        skip_file=args.skip_file,
    )

    if args.json:
        output = {
            "success": result.success,
            "bug_id": result.bug_id,
            "rule_id": result.rule_id,
            "bug_history_id": result.bug_history_id,
            "db_registered": result.db_registered,
            "file_updated": result.file_updated,
            "message": result.message,
            "error": result.error,
            "warnings": result.warnings,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            print(f"[OK] {result.message}")
            if result.bug_id:
                print(f"  BUG ID: {result.bug_id}")
            if result.bug_history_id:
                print(f"  履歴ID: {result.bug_history_id}")
            if result.rule_id:
                print(f"  ルールID: {result.rule_id}")
            for w in result.warnings:
                print(f"  [WARNING] {w}")
        else:
            print(f"[ERROR] {result.error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
