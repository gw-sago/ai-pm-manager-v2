#!/usr/bin/env python3
"""
AI PM Framework - PROJECT_INFO.md 自動更新モジュール

リリース完了時にプロジェクトのORDER履歴・完了タスク等から
PROJECT_INFO.mdを深化・更新する。

主な機能:
- ORDER完了後の学習内容をPROJECT_INFO.mdに追記（バグ修正履歴・技術的制約・実装パターン等）
- 重複チェック付きの安全な追記（同一内容の重複追記防止）
- セクションが存在しない場合は自動生成

Usage:
    from pm.update_project_info import update_project_info_from_order

    result = update_project_info_from_order(
        project_id="ai_pm_manager_v2",
        order_id="ORDER_074",
        learnings={
            "bug_patterns": ["...", "..."],
            "technical_constraints": ["...", "..."],
            "implementation_patterns": ["...", "..."],
            "notes": ["...", "..."],
        }
    )
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

logger = logging.getLogger(__name__)

# カテゴリとPROJECT_INFO.mdセクションのマッピング
CATEGORY_SECTION_MAP = {
    "bug_patterns": "バグ修正履歴・既知パターン",
    "technical_constraints": "技術的制約・注意事項",
    "implementation_patterns": "実装パターン・ベストプラクティス",
    "notes": "運用ノート",
}


def _get_project_info_path(project_id: str) -> Optional[Path]:
    """
    PROJECT_INFO.mdのRoaming絶対パスを取得

    Args:
        project_id: プロジェクトID

    Returns:
        PROJECT_INFO.mdのパス（存在しない場合はNone）
    """
    try:
        from config.db_config import get_project_paths
        paths = get_project_paths(project_id)
        project_info_path = paths["base"] / "PROJECT_INFO.md"
        return project_info_path
    except Exception as e:
        logger.warning(f"project_info_path取得失敗: {e}")
        return None


def _is_duplicate_entry(content: str, entry_text: str) -> bool:
    """
    エントリーが既にPROJECT_INFO.mdに含まれているか確認する（重複チェック）

    タスクID/ORDERIDプレフィックス（[TASK_054]、[ORDER_074]等）を除外した
    先頭80文字での重複判定。タスクID違いの同一内容も検出する。

    Args:
        content: PROJECT_INFO.mdの全文
        entry_text: チェックするエントリーテキスト

    Returns:
        重複している場合True
    """
    import re

    # プレフィックスパターン: [TASK_NNN] or [ORDER_NNN]
    PREFIX_PATTERN = r'^\[(?:TASK|ORDER)_\d+\]\s*'

    # 入力テキストからプレフィックスを除去
    entry_clean = re.sub(PREFIX_PATTERN, '', entry_text.strip())
    # 先頭80文字で比較
    entry_short = entry_clean[:80].lower().strip()

    if not entry_short:
        return False

    # コンテンツの各行を検索
    for line in content.split("\n"):
        # リスト記号とプレフィックスを除去
        line_clean = re.sub(r'^\s*[-*]\s*', '', line.strip())
        line_clean = re.sub(PREFIX_PATTERN, '', line_clean)
        line_short = line_clean[:80].lower().strip()
        if line_short and line_short == entry_short:
            return True

    return False


def _ensure_section_exists(content: str, section_name: str, order_id: str) -> str:
    """
    指定セクションが存在しない場合は末尾に追加する

    Args:
        content: PROJECT_INFO.mdの全文
        section_name: セクション名（## ではじまる見出し）
        order_id: 更新元のORDER ID（コメントに記録）

    Returns:
        更新されたコンテンツ
    """
    if f"## {section_name}" in content:
        return content

    today = datetime.now().strftime("%Y-%m-%d")
    new_section = (
        f"\n\n## {section_name}\n"
        f"<!-- 最終更新: {order_id} ({today}) -->\n"
    )
    return content + new_section


def _append_to_section(
    content: str,
    section_name: str,
    entries: List[str],
    order_id: str,
    task_id: Optional[str] = None,
) -> tuple[str, int]:
    """
    指定セクションにエントリーを追加する

    重複チェックを行い、新しいエントリーのみを追加する。

    Args:
        content: PROJECT_INFO.mdの全文
        section_name: セクション名
        entries: 追加するエントリーリスト
        order_id: 更新元のORDER ID
        task_id: 更新元のタスクID（オプション）

    Returns:
        (更新されたコンテンツ, 追加されたエントリー数)
    """
    prefix = f"[{task_id}]" if task_id else f"[{order_id}]"
    added_count = 0

    lines = content.split("\n")
    section_header = f"## {section_name}"

    # セクションの終端インデックスを見つける
    insert_idx = None
    section_found = False
    section_level = 2  # ## の場合はレベル2

    for i, line in enumerate(lines):
        if section_header in line:
            section_found = True
            insert_idx = i + 1  # セクション直後
            continue

        if section_found:
            # コメント行はスキップ
            if line.strip().startswith("<!--"):
                insert_idx = i + 1
                continue

            # 空行は末尾候補として更新
            if not line.strip():
                # 空行の後にまだセクション内容が来る可能性があるのでinsert_idxを更新
                insert_idx = i + 1
                continue

            # 次のセクション（##以上）が来たら終了
            if line.startswith("##") and not line.startswith("###"):
                break

            # 内容行の後のinsert_idxを更新
            insert_idx = i + 1

    if not section_found or insert_idx is None:
        return content, 0

    # 追加するエントリーを構築
    new_lines = []
    for entry in entries:
        if not entry.strip():
            continue
        formatted_entry = f"- {prefix} {entry.strip()}"
        if not _is_duplicate_entry(content, entry):
            new_lines.append(formatted_entry)
            added_count += 1

    if not new_lines:
        return content, 0

    # セクションコメントを更新
    today = datetime.now().strftime("%Y-%m-%d")
    comment_line = f"<!-- 最終更新: {order_id} ({today}) -->"

    # コメント行の更新（セクション直後のコメントを探す）
    comment_updated = False
    for i in range(insert_idx - 1, min(insert_idx + 5, len(lines))):
        if i < len(lines) and lines[i].strip().startswith("<!-- 最終更新:"):
            lines[i] = comment_line
            comment_updated = True
            break

    # 挿入位置に新しいエントリーを追加
    for j, new_line in enumerate(new_lines):
        lines.insert(insert_idx + j, new_line)

    return "\n".join(lines), added_count


def update_project_info_from_order(
    project_id: str,
    order_id: str,
    learnings: Dict[str, List[str]],
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    ORDER完了時の学習内容をPROJECT_INFO.mdに追記する

    重複チェックを行い、新しい内容のみを追加する。
    セクションが存在しない場合は自動生成する。

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID（例: ORDER_074）
        learnings: カテゴリ別の学習内容
            - bug_patterns: バグパターン・修正内容
            - technical_constraints: 技術的制約・注意事項
            - implementation_patterns: 実装パターン・ベストプラクティス
            - notes: 運用ノート
        task_id: タスクID（オプション、エントリープレフィックスとして使用）

    Returns:
        {
            "success": bool,
            "updated": bool,
            "added_count": int,  # 追加されたエントリー数
            "sections_updated": [...],  # 更新されたセクション名のリスト
            "error": str (エラー時のみ)
        }
    """
    result: Dict[str, Any] = {
        "success": True,
        "updated": False,
        "added_count": 0,
        "sections_updated": [],
    }

    project_info_path = _get_project_info_path(project_id)
    if project_info_path is None:
        result["success"] = False
        result["error"] = "PROJECT_INFO.mdのパス取得に失敗"
        return result

    if not project_info_path.exists():
        logger.warning(f"PROJECT_INFO.md が見つかりません: {project_info_path}")
        result["success"] = False
        result["error"] = f"PROJECT_INFO.md が見つかりません: {project_info_path}"
        return result

    try:
        content = project_info_path.read_text(encoding="utf-8")
    except Exception as e:
        result["success"] = False
        result["error"] = f"PROJECT_INFO.md 読み込み失敗: {e}"
        return result

    total_added = 0
    modified = False

    for category, entries in learnings.items():
        if not entries:
            continue

        section_name = CATEGORY_SECTION_MAP.get(category)
        if not section_name:
            logger.warning(f"未知のカテゴリ: {category}")
            continue

        # セクションが存在しない場合は追加
        content = _ensure_section_exists(content, section_name, order_id)

        # エントリーを追加
        content, added = _append_to_section(
            content, section_name, entries, order_id, task_id
        )

        if added > 0:
            total_added += added
            result["sections_updated"].append(section_name)
            modified = True

    if modified:
        try:
            project_info_path.write_text(content, encoding="utf-8")
            result["updated"] = True
            result["added_count"] = total_added
            logger.info(
                f"PROJECT_INFO.md 更新完了: {total_added}件追記 "
                f"({', '.join(result['sections_updated'])})"
            )
        except Exception as e:
            result["success"] = False
            result["error"] = f"PROJECT_INFO.md 書き込み失敗: {e}"
            return result
    else:
        logger.info("PROJECT_INFO.md: 追加すべき新規エントリーなし（重複スキップ）")

    return result


def extract_learnings_from_reports(
    project_id: str,
    order_id: str,
) -> Dict[str, List[str]]:
    """
    完了タスクのREPORTファイルから学習内容を収集・分類する

    RESULT/ORDER_XXX/05_REPORT/ 配下の全REPORTファイルを読み込み、
    バグパターン・技術的制約・実装パターン・運用ノートに分類して返す。

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID

    Returns:
        カテゴリ別の学習内容辞書
    """
    learnings: Dict[str, List[str]] = {
        "bug_patterns": [],
        "technical_constraints": [],
        "implementation_patterns": [],
        "notes": [],
    }

    try:
        from config.db_config import get_project_paths
        paths = get_project_paths(project_id)
        report_dir = paths["result"] / order_id / "05_REPORT"

        if not report_dir.exists():
            logger.debug(f"REPORTディレクトリが見つかりません: {report_dir}")
            return learnings

        # 全REPORTファイルを読み込む
        report_files = sorted(report_dir.glob("*.md"))
        if not report_files:
            report_files = sorted(report_dir.glob("**/*.md"))

        for report_file in report_files:
            try:
                content = report_file.read_text(encoding="utf-8")
                file_learnings = _parse_report_for_learnings(content, order_id)
                for category, entries in file_learnings.items():
                    learnings[category].extend(entries)
            except Exception as e:
                logger.warning(f"REPORTファイル読み込み失敗 ({report_file.name}): {e}")

    except Exception as e:
        logger.warning(f"学習内容収集失敗: {e}")

    return learnings


def _parse_report_for_learnings(
    report_content: str,
    order_id: str,
) -> Dict[str, List[str]]:
    """
    REPORTファイルの内容から学習内容を抽出・分類する

    REPORTに含まれる「issues」「details」「summary」セクションを解析し、
    バグパターン・技術的制約・実装パターン等に分類する。

    Args:
        report_content: REPORTファイルの内容
        order_id: ORDER ID

    Returns:
        カテゴリ別の学習内容辞書
    """
    import re

    learnings: Dict[str, List[str]] = {
        "bug_patterns": [],
        "technical_constraints": [],
        "implementation_patterns": [],
        "notes": [],
    }

    # バグ・問題に関するキーワード
    BUG_KEYWORDS = [
        "バグ", "bug", "エラー", "error", "失敗", "fail",
        "修正", "fix", "問題", "issue", "不具合", "defect",
    ]

    # 制約・注意に関するキーワード
    CONSTRAINT_KEYWORDS = [
        "制約", "constraint", "注意", "caution", "禁止", "prohibited",
        "必須", "required", "重要", "important", "警告", "warning",
    ]

    # パターン・ベストプラクティスに関するキーワード
    PATTERN_KEYWORDS = [
        "パターン", "pattern", "ベストプラクティス", "best practice",
        "推奨", "recommended", "実装方法", "implementation",
        "方法", "method", "手順", "procedure",
    ]

    lines = report_content.split("\n")
    current_section = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # セクション検出
        if stripped.startswith("#"):
            lower = stripped.lower()
            if any(k in lower for k in ["issue", "問題", "バグ", "エラー"]):
                current_section = "bug_patterns"
            elif any(k in lower for k in ["detail", "詳細", "実施"]):
                current_section = "notes"
            elif any(k in lower for k in ["summary", "サマリ", "まとめ"]):
                current_section = "notes"
            else:
                current_section = None
            continue

        # リスト項目の解析（- で始まる行）
        if stripped.startswith("-") or stripped.startswith("*"):
            item_text = re.sub(r'^[-*]\s*', '', stripped).strip()
            if not item_text or len(item_text) < 10:
                continue

            lower_item = item_text.lower()

            # キーワードで分類
            if any(k in lower_item for k in BUG_KEYWORDS):
                learnings["bug_patterns"].append(item_text)
            elif any(k in lower_item for k in CONSTRAINT_KEYWORDS):
                learnings["technical_constraints"].append(item_text)
            elif any(k in lower_item for k in PATTERN_KEYWORDS):
                learnings["implementation_patterns"].append(item_text)
            elif current_section:
                learnings[current_section].append(item_text)

    return learnings


def collect_and_update_from_db(
    project_id: str,
    order_id: str,
) -> Dict[str, Any]:
    """
    DBからORDER/タスク情報を収集し、PROJECT_INFO.mdを更新する

    完了タスクのREPORTファイルと、DBのchange_history・bugsテーブルから
    学習内容を収集してPROJECT_INFO.mdに追記する。

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID

    Returns:
        更新結果辞書
    """
    result: Dict[str, Any] = {
        "success": True,
        "updated": False,
        "added_count": 0,
        "sections_updated": [],
        "source": "db_and_reports",
    }

    try:
        # REPORTファイルから学習内容を収集
        learnings = extract_learnings_from_reports(project_id, order_id)

        # DBからORDER情報を取得してnotesに追加
        try:
            from utils.db import get_connection, fetch_one, fetch_all
            conn = get_connection()
            try:
                order = fetch_one(
                    conn,
                    "SELECT id, title, completed_at FROM orders WHERE id = ? AND project_id = ?",
                    (order_id, project_id),
                )
                if order:
                    order_title = dict(order).get("title", "")
                    if order_title:
                        learnings["notes"].append(
                            f"{order_id}完了: {order_title}"
                        )

                # 完了タスクの情報を収集
                tasks = fetch_all(
                    conn,
                    """SELECT id, title, description FROM tasks
                       WHERE order_id = ? AND project_id = ?
                       AND status IN ('COMPLETED', 'DONE')""",
                    (order_id, project_id),
                )
                for task in tasks:
                    task_dict = dict(task)
                    task_id = task_dict.get("id", "")
                    task_title = task_dict.get("title", "")
                    if task_title:
                        # タスクタイトルからカテゴリを推定して追加
                        lower_title = task_title.lower()
                        if any(k in lower_title for k in ["バグ", "bug", "修正", "fix"]):
                            learnings["bug_patterns"].append(
                                f"{task_title}を実装・修正 ({task_id})"
                            )
                        elif any(k in lower_title for k in ["制約", "注意", "禁止"]):
                            learnings["technical_constraints"].append(
                                f"{task_title} ({task_id})"
                            )
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"DB情報収集失敗（継続）: {e}")

        # PROJECT_INFO.mdを更新
        if any(learnings.values()):
            update_result = update_project_info_from_order(
                project_id=project_id,
                order_id=order_id,
                learnings=learnings,
            )
            result.update(update_result)
        else:
            logger.info(f"学習内容なし: {order_id}")

    except Exception as e:
        logger.warning(f"PROJECT_INFO.md更新失敗（非致命的）: {e}")
        result["success"] = False
        result["error"] = str(e)

    return result
