#!/usr/bin/env python3
"""
AI PM Framework - リリースノート生成スクリプト

指定ORDERの全タスクREPORTを集約してリリースノートMarkdownを生成し、
RESULT/ORDER_XXX/RELEASE_NOTE.md として保存する。

Usage:
    python backend/release/generate_note.py PROJECT_ID ORDER_ID [OPTIONS]

Options:
    --json          JSON形式で出力
    --dry-run       ファイルに保存せず内容をプレビューのみ
    --verbose       詳細ログ出力

Example:
    python backend/release/generate_note.py ai_pm_manager_v2 ORDER_017
    python backend/release/generate_note.py ai_pm_manager_v2 ORDER_017 --json
    python backend/release/generate_note.py ai_pm_manager_v2 ORDER_017 --dry-run
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# バックエンドルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import setup_utf8_output
from config.db_config import get_project_paths
from utils.db import get_connection, fetch_one, fetch_all

setup_utf8_output()


# ============================================================================
# タスク情報取得
# ============================================================================

def get_order_info(project_id: str, order_id: str) -> Optional[Dict[str, Any]]:
    """
    ORDER情報をDBから取得

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID

    Returns:
        ORDERの辞書、見つからない場合はNone
    """
    conn = get_connection()
    try:
        order = fetch_one(
            conn,
            "SELECT id, project_id, title, priority, status, created_at, completed_at "
            "FROM orders WHERE id = ? AND project_id = ?",
            (order_id, project_id),
        )
        return dict(order) if order else None
    finally:
        conn.close()


def get_tasks_for_order(project_id: str, order_id: str) -> List[Dict[str, Any]]:
    """
    ORDER配下の全タスク一覧をDBから取得

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID

    Returns:
        タスクの辞書リスト
    """
    conn = get_connection()
    try:
        tasks = fetch_all(
            conn,
            """SELECT id, title, description, status, priority, assignee,
                      started_at, completed_at, created_at
               FROM tasks
               WHERE order_id = ? AND project_id = ?
               ORDER BY created_at""",
            (order_id, project_id),
        )
        return [dict(t) for t in tasks]
    finally:
        conn.close()


# ============================================================================
# REPORTファイル読み込み
# ============================================================================

def read_report_files(result_order_dir: Path) -> List[Dict[str, Any]]:
    """
    RESULT/ORDER_XXX/05_REPORT/ 配下のREPORTファイルを読み込む

    Args:
        result_order_dir: RESULT/ORDER_XXX/ のパス

    Returns:
        [{"filename": str, "task_id": str, "content": str}, ...]
    """
    report_dir = result_order_dir / "05_REPORT"
    reports = []

    if not report_dir.exists():
        return reports

    for report_file in sorted(report_dir.glob("REPORT_*.md")):
        try:
            content = report_file.read_text(encoding="utf-8")
            # ファイル名からTASK IDを抽出 (REPORT_042.md → TASK_042)
            stem = report_file.stem  # "REPORT_042"
            task_id = stem.replace("REPORT_", "TASK_")
            reports.append({
                "filename": report_file.name,
                "task_id": task_id,
                "content": content,
            })
        except Exception as e:
            reports.append({
                "filename": report_file.name,
                "task_id": "UNKNOWN",
                "content": f"[REPORTファイル読み込みエラー: {e}]",
            })

    return reports


def parse_report_summary(report_content: str) -> Dict[str, Any]:
    """
    REPORTファイルからJSON結果ブロックを抽出してパース

    Args:
        report_content: REPORTファイルの内容

    Returns:
        {"summary": str, "details": [...], "artifacts": [...], "issues": [...]}
    """
    result = {
        "summary": "",
        "details": [],
        "artifacts": [],
        "issues": [],
    }

    # コードブロック内のJSONを抽出
    import re
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", report_content, re.DOTALL)
    if not json_match:
        # フォールバック: REPORTの内容をそのまま使用
        result["summary"] = report_content[:500] if len(report_content) > 500 else report_content
        return result

    try:
        data = json.loads(json_match.group(1))
        result["summary"] = data.get("summary", "")
        result["details"] = data.get("details", [])
        result["artifacts"] = data.get("artifacts", [])
        result["issues"] = data.get("issues", [])
    except json.JSONDecodeError:
        result["summary"] = "[JSONパースエラー]"

    return result


# ============================================================================
# リリースノートMarkdown生成
# ============================================================================

def generate_release_note_markdown(
    project_id: str,
    order_id: str,
    order_info: Dict[str, Any],
    tasks: List[Dict[str, Any]],
    reports: List[Dict[str, Any]],
) -> str:
    """
    リリースノートMarkdownを生成

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        order_info: ORDERのメタデータ
        tasks: タスクのリスト
        reports: REPORTファイルのリスト

    Returns:
        リリースノートのMarkdown文字列
    """
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    order_title = order_info.get("title", order_id)
    order_status = order_info.get("status", "UNKNOWN")
    order_completed = order_info.get("completed_at", "-")

    # タスク数集計
    total_tasks = len(tasks)
    completed_tasks = [t for t in tasks if t.get("status") in ("COMPLETED", "DONE")]
    completed_count = len(completed_tasks)

    # REPORTをTASK IDでインデックス化
    report_by_task = {r["task_id"]: r for r in reports}

    lines = []

    # ヘッダー
    lines.append(f"# リリースノート - {order_id}")
    lines.append("")
    lines.append(f"**ORDER**: {order_id} - {order_title}")
    lines.append(f"**プロジェクト**: {project_id}")
    lines.append(f"**ステータス**: {order_status}")
    lines.append(f"**完了日時**: {order_completed or '-'}")
    lines.append(f"**生成日時**: {generated_at}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # サマリー
    lines.append("## サマリー")
    lines.append("")
    if order_info.get("description"):
        lines.append(order_info["description"])
        lines.append("")
    if order_info.get("priority"):
        lines.append(f"- **優先度**: {order_info['priority']}")
    lines.append(f"- **タスク数**: {total_tasks}件（完了: {completed_count}件）")
    lines.append(f"- **REPORTファイル数**: {len(reports)}件")
    lines.append("")

    # タスク一覧
    lines.append("## タスク一覧")
    lines.append("")
    lines.append("| タスクID | タイトル | 優先度 | ステータス | 担当 |")
    lines.append("|---------|----------|--------|------------|------|")
    for task in tasks:
        task_id = task.get("id", "-")
        title = task.get("title", "-")
        priority = task.get("priority", "-")
        status = task.get("status", "-")
        assignee = task.get("assignee") or "-"
        lines.append(f"| {task_id} | {title} | {priority} | {status} | {assignee} |")
    lines.append("")

    # 各タスクの実施内容
    lines.append("## 実施内容")
    lines.append("")

    for task in tasks:
        task_id = task.get("id", "UNKNOWN")
        task_title = task.get("title", "-")
        task_status = task.get("status", "-")

        lines.append(f"### {task_id}: {task_title}")
        lines.append("")
        lines.append(f"**ステータス**: {task_status}")
        if task.get("completed_at"):
            lines.append(f"**完了日時**: {task['completed_at']}")
        lines.append("")

        if task_id in report_by_task:
            report = report_by_task[task_id]
            parsed = parse_report_summary(report["content"])

            if parsed["summary"]:
                lines.append(f"**概要**: {parsed['summary']}")
                lines.append("")

            if parsed["details"]:
                lines.append("**詳細**:")
                for detail in parsed["details"]:
                    lines.append(f"- {detail}")
                lines.append("")

            if parsed["artifacts"]:
                lines.append("**成果物**:")
                for artifact in parsed["artifacts"]:
                    lines.append(f"- `{artifact}`")
                lines.append("")

            if parsed["issues"]:
                lines.append("**発生した問題**:")
                for issue in parsed["issues"]:
                    lines.append(f"- {issue}")
                lines.append("")
        else:
            lines.append("*REPORTファイルなし*")
            lines.append("")

    # 変更ファイル集計
    all_artifacts = []
    for report in reports:
        parsed = parse_report_summary(report["content"])
        all_artifacts.extend(parsed["artifacts"])

    if all_artifacts:
        lines.append("## 変更ファイル一覧")
        lines.append("")
        seen = set()
        for artifact in all_artifacts:
            if artifact not in seen:
                seen.add(artifact)
                lines.append(f"- `{artifact}`")
        lines.append("")

    # フッター
    lines.append("---")
    lines.append("")
    lines.append(f"*このリリースノートは AI PM Framework によって自動生成されました（{generated_at}）*")

    return "\n".join(lines)


# ============================================================================
# メイン処理
# ============================================================================

def generate_release_note(
    project_id: str,
    order_id: str,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    リリースノートを生成してRELEASE_NOTE.mdに保存

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        dry_run: Trueの場合はファイルに保存しない
        verbose: 詳細ログ出力

    Returns:
        {
            "success": bool,
            "note_path": str,       # 保存先パス（dry_run時はNone）
            "note_content": str,    # 生成されたMarkdown
            "task_count": int,
            "report_count": int,
            "error": str,           # エラー時のみ
        }
    """
    result: Dict[str, Any] = {
        "success": False,
        "note_path": None,
        "note_content": "",
        "task_count": 0,
        "report_count": 0,
    }

    # ORDER情報取得
    if verbose:
        print(f"[INFO] ORDER情報を取得中: {order_id}")
    order_info = get_order_info(project_id, order_id)
    if not order_info:
        result["error"] = f"ORDER {order_id} が見つかりません（project: {project_id}）"
        return result

    # タスク一覧取得
    if verbose:
        print(f"[INFO] タスク一覧を取得中")
    tasks = get_tasks_for_order(project_id, order_id)
    result["task_count"] = len(tasks)

    if verbose:
        print(f"[INFO] {len(tasks)}件のタスクを取得")

    # Roamingパスを取得
    paths = get_project_paths(project_id)
    result_order_dir = paths["result"] / order_id

    if verbose:
        print(f"[INFO] RESULTディレクトリ: {result_order_dir}")

    # REPORTファイル読み込み
    reports = read_report_files(result_order_dir)
    result["report_count"] = len(reports)

    if verbose:
        print(f"[INFO] {len(reports)}件のREPORTファイルを読み込み")
        for r in reports:
            print(f"  - {r['filename']}")

    # Markdown生成
    markdown_content = generate_release_note_markdown(
        project_id=project_id,
        order_id=order_id,
        order_info=order_info,
        tasks=tasks,
        reports=reports,
    )
    result["note_content"] = markdown_content

    # ファイル保存
    note_path = result_order_dir / "RELEASE_NOTE.md"
    result["note_path"] = str(note_path)

    if not dry_run:
        # ディレクトリが存在しない場合は作成
        result_order_dir.mkdir(parents=True, exist_ok=True)

        if verbose:
            print(f"[INFO] RELEASE_NOTE.md を保存中: {note_path}")

        note_path.write_text(markdown_content, encoding="utf-8")

        if verbose:
            print(f"[INFO] 保存完了: {note_path}")
    else:
        if verbose:
            print(f"[INFO] DRY RUN: ファイルへの保存はスキップ")

    result["success"] = True
    return result


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="AI PM Framework - リリースノート生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("order_id", help="ORDER ID（例: ORDER_017）")
    parser.add_argument("--dry-run", action="store_true",
                        help="ファイルに保存せずプレビューのみ")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="詳細ログ出力")

    args = parser.parse_args()

    try:
        result = generate_release_note(
            project_id=args.project_id,
            order_id=args.order_id,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

        if args.json:
            # JSON出力時はnote_contentを除外（大きすぎるため）
            output = {k: v for k, v in result.items() if k != "note_content"}
            if args.dry_run:
                output["note_content"] = result.get("note_content", "")
            print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
        else:
            if result.get("success"):
                if args.dry_run:
                    print("=== リリースノートプレビュー ===")
                    print(result.get("note_content", ""))
                    print("=== プレビュー終了 ===")
                else:
                    print(f"リリースノートを生成しました: {result.get('note_path')}")
                    print(f"タスク数: {result.get('task_count')}, REPORTファイル数: {result.get('report_count')}")
            else:
                print(f"エラー: {result.get('error', '不明なエラー')}", file=sys.stderr)

        sys.exit(0 if result.get("success") else 1)

    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)},
                             ensure_ascii=False))
        else:
            print(f"エラー: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
