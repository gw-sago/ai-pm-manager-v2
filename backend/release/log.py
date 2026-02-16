#!/usr/bin/env python3
"""
AI PM Framework - リリース履歴記録スクリプト

リリース実行履歴をRELEASE_LOG.mdに記録する。

使用例:
    # リリース記録（ファイルリストをJSON形式で渡す）
    python log.py AI_PM_PJ --order ORDER_060 --files '[{"target": ".claude/commands/xxx.md", "change_type": "NEW"}]'

    # 履歴一覧取得
    python log.py AI_PM_PJ --list

    # 履歴一覧（JSON形式）
    python log.py AI_PM_PJ --list --json
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# 親パッケージからインポート
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_project_paths, setup_utf8_output

# UTF-8出力設定
setup_utf8_output()


def get_next_release_id(log_path: Path, date_str: str) -> str:
    """
    次のリリースIDを生成

    Args:
        log_path: RELEASE_LOG.mdのパス
        date_str: 日付文字列（YYYY-MM-DD形式）

    Returns:
        リリースID（RELEASE_YYYY-MM-DD_NNN形式）
    """
    prefix = f"RELEASE_{date_str}_"

    if not log_path.exists():
        return f"{prefix}001"

    content = log_path.read_text(encoding="utf-8")

    # 同日のリリースIDを検索
    pattern = rf"{re.escape(prefix)}(\d{{3}})"
    matches = re.findall(pattern, content)

    if not matches:
        return f"{prefix}001"

    max_num = max(int(m) for m in matches)
    return f"{prefix}{max_num + 1:03d}"


def record_release(
    project_id: str,
    order_id: str,
    files: List[Dict[str, Any]],
    executor: str = "Auto",
    notes: Optional[str] = None,
    backlog_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    リリース履歴を記録

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        files: リリースファイルリスト
        executor: 実行者（Auto/Manual）
        notes: 備考
        backlog_ids: 関連BACKLOG IDリスト（オプション）

    Returns:
        記録結果
    """
    paths = get_project_paths(project_id)
    log_path = paths["release_log"]

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    release_id = get_next_release_id(log_path, date_str)

    # リリースエントリを生成
    entry_lines = [
        f"## {release_id}",
        "",
        f"- **日時**: {now.isoformat()}",
        f"- **ORDER**: {order_id}",
    ]

    if backlog_ids:
        entry_lines.append(f"- **BACKLOG**: {', '.join(backlog_ids)}")

    entry_lines.extend([
        f"- **実行者**: {executor}",
        f"- **ファイル数**: {len(files)}件",
    ])

    if notes:
        entry_lines.append(f"- **備考**: {notes}")

    entry_lines.extend([
        "",
        "### リリースファイル",
        "",
        "| # | 種別 | ファイル |",
        "|---|------|----------|",
    ])

    for i, file_info in enumerate(files, 1):
        change_type = file_info.get("change_type", "MOD")
        target = file_info.get("target", file_info.get("path", "unknown"))
        entry_lines.append(f"| {i} | {change_type} | {target} |")

    entry_lines.extend(["", "---", ""])

    entry_content = "\n".join(entry_lines)

    # RELEASE_LOG.mdに追記（または新規作成）
    if log_path.exists():
        existing_content = log_path.read_text(encoding="utf-8")

        # ヘッダーと本体を分離
        header_end = existing_content.find("\n---\n")
        if header_end != -1:
            header = existing_content[:header_end + 5]
            body = existing_content[header_end + 5:]
        else:
            header = ""
            body = existing_content

        # 新しいエントリを先頭に追加
        new_content = header + "\n" + entry_content + body
    else:
        # 新規作成
        header = f"""# RELEASE_LOG.md

## リリース履歴

> **このファイルはリリース履歴を記録します。自動生成されます。**

---

"""
        new_content = header + entry_content

    log_path.write_text(new_content, encoding="utf-8")

    return {
        "success": True,
        "release_id": release_id,
        "order_id": order_id,
        "file_count": len(files),
        "log_path": str(log_path),
        "recorded_at": now.isoformat(),
    }


def list_releases(
    project_id: str,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    リリース履歴一覧を取得

    Args:
        project_id: プロジェクトID
        limit: 取得件数上限

    Returns:
        履歴一覧
    """
    paths = get_project_paths(project_id)
    log_path = paths["release_log"]

    if not log_path.exists():
        return {
            "success": True,
            "releases": [],
            "count": 0,
            "message": "リリース履歴がありません",
        }

    content = log_path.read_text(encoding="utf-8")

    # リリースエントリをパース（BACKLOGフィールドはオプション）
    releases = []
    pattern = r"## (RELEASE_\d{4}-\d{2}-\d{2}_\d{3})\n\n- \*\*日時\*\*: ([^\n]+)\n- \*\*ORDER\*\*: ([^\n]+)\n(?:- \*\*BACKLOG\*\*: ([^\n]+)\n)?- \*\*実行者\*\*: ([^\n]+)\n- \*\*ファイル数\*\*: (\d+)件"

    for match in re.finditer(pattern, content):
        entry = {
            "release_id": match.group(1),
            "datetime": match.group(2),
            "order_id": match.group(3),
            "executor": match.group(5),
            "file_count": int(match.group(6)),
        }
        if match.group(4):
            entry["backlog_ids"] = match.group(4)
        releases.append(entry)

    # 最新順でソート（IDの降順）
    releases.sort(key=lambda x: x["release_id"], reverse=True)

    return {
        "success": True,
        "releases": releases[:limit],
        "count": len(releases),
        "total": len(releases),
    }


def format_output(result: Dict[str, Any], json_output: bool = False) -> str:
    """
    結果をフォーマット

    Args:
        result: 結果データ
        json_output: JSON形式で出力するか

    Returns:
        フォーマット済み文字列
    """
    if json_output:
        return json.dumps(result, indent=2, ensure_ascii=False)

    if not result.get("success"):
        return f"エラー: {result.get('error', '不明なエラー')}"

    # 記録結果の場合
    if "release_id" in result:
        return f"""リリース履歴を記録しました。

- リリースID: {result['release_id']}
- ORDER: {result['order_id']}
- ファイル数: {result['file_count']}件
- 記録先: {result['log_path']}"""

    # 一覧の場合
    releases = result.get("releases", [])
    if not releases:
        return "リリース履歴がありません。"

    lines = [
        f"リリース履歴（{len(releases)}/{result.get('total', len(releases))}件）",
        "",
        "| リリースID | 日時 | ORDER | 実行者 | ファイル数 |",
        "|------------|------|-------|--------|-----------|",
    ]

    for r in releases:
        dt = r["datetime"][:19] if len(r["datetime"]) > 19 else r["datetime"]
        lines.append(f"| {r['release_id']} | {dt} | {r['order_id']} | {r['executor']} | {r['file_count']}件 |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="リリース履歴を記録・取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
    # リリース記録
    python log.py AI_PM_PJ --order ORDER_060 --files '[{"target": "xxx.md", "change_type": "NEW"}]'

    # 履歴一覧
    python log.py AI_PM_PJ --list

    # JSON形式で取得
    python log.py AI_PM_PJ --list --json
        """
    )

    parser.add_argument(
        "project_id",
        help="プロジェクトID（例: AI_PM_PJ）"
    )
    parser.add_argument(
        "--order", "-o",
        dest="order_id",
        help="ORDER ID（記録時必須）"
    )
    parser.add_argument(
        "--files", "-f",
        help="リリースファイルリスト（JSON形式）"
    )
    parser.add_argument(
        "--executor", "-e",
        default="Auto",
        help="実行者（デフォルト: Auto）"
    )
    parser.add_argument(
        "--notes", "-n",
        help="備考"
    )
    parser.add_argument(
        "--backlog", "-b",
        nargs="*",
        help="関連BACKLOG IDリスト（スペース区切り）"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="履歴一覧を取得"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="一覧取得件数（デフォルト: 10）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    try:
        if args.list:
            result = list_releases(
                project_id=args.project_id,
                limit=args.limit,
            )
        else:
            if not args.order_id:
                print("エラー: --order オプションが必要です", file=sys.stderr)
                sys.exit(1)

            if not args.files:
                print("エラー: --files オプションが必要です", file=sys.stderr)
                sys.exit(1)

            try:
                files = json.loads(args.files)
            except json.JSONDecodeError as e:
                print(f"エラー: ファイルリストのJSON解析に失敗: {e}", file=sys.stderr)
                sys.exit(1)

            result = record_release(
                project_id=args.project_id,
                order_id=args.order_id,
                files=files,
                executor=args.executor,
                notes=args.notes,
                backlog_ids=args.backlog if args.backlog else None,
            )

        output = format_output(result, json_output=args.json)
        print(output)

        sys.exit(0 if result.get("success") else 1)

    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        else:
            print(f"エラー: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
