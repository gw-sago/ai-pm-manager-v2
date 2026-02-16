#!/usr/bin/env python3
"""
AI PM Framework - リリース対象検出スクリプト

ORDER完了時にDEV配下のリリース対象ファイルを自動検出する。
差分情報のデフォルト表示機能付き。

検出対象ディレクトリ:
- DEV/.claude/commands/ → .claude/commands/
- DEV/scripts/ → scripts/
- DEV/TEMPLATE/ → TEMPLATE/

使用例:
    python detect.py AI_PM_PJ --order ORDER_060
    python detect.py AI_PM_PJ --order ORDER_060 --json
    python detect.py AI_PM_PJ --all-dev --json
    python detect.py AI_PM_PJ --no-diff  # 差分表示を省略
"""

import argparse
import difflib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# 親パッケージからインポート
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, fetch_all, row_to_dict
from config import get_project_paths


# リリース対象ディレクトリのマッピング（DEV相対パス → 本番相対パス）
RELEASE_DIRS = {
    ".claude/commands": ".claude/commands",
    "scripts": "scripts",
    "TEMPLATE": "TEMPLATE",
}

# 差分表示をスキップするファイル拡張子（バイナリ等）
BINARY_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', '.zip', '.tar', '.gz', '.exe', '.dll', '.so', '.dylib'}

# 差分プレビューの最大行数
DIFF_PREVIEW_LINES = 10


def calculate_diff(source_path: Path, target_path: Path) -> Dict[str, Any]:
    """
    2つのファイル間の差分を計算

    Args:
        source_path: DEV側ファイルパス
        target_path: 本番側ファイルパス

    Returns:
        差分情報の辞書
    """
    diff_info = {
        "has_diff": False,
        "added_lines": 0,
        "deleted_lines": 0,
        "preview": [],
        "is_binary": False,
    }

    # バイナリファイルチェック
    if source_path.suffix.lower() in BINARY_EXTENSIONS:
        diff_info["is_binary"] = True
        diff_info["has_diff"] = True
        return diff_info

    try:
        # ファイル内容を読み込み
        source_content = source_path.read_text(encoding='utf-8', errors='replace')
        source_lines = source_content.splitlines(keepends=True)

        if target_path.exists():
            target_content = target_path.read_text(encoding='utf-8', errors='replace')
            target_lines = target_content.splitlines(keepends=True)
        else:
            target_lines = []

        # 差分を計算
        diff = list(difflib.unified_diff(
            target_lines, source_lines,
            fromfile=str(target_path.name),
            tofile=str(source_path.name),
            lineterm=''
        ))

        if diff:
            diff_info["has_diff"] = True

            # 追加/削除行数をカウント
            for line in diff:
                if line.startswith('+') and not line.startswith('+++'):
                    diff_info["added_lines"] += 1
                elif line.startswith('-') and not line.startswith('---'):
                    diff_info["deleted_lines"] += 1

            # プレビュー（最初のN行）
            preview_lines = []
            for line in diff[2:]:  # ヘッダーをスキップ
                if len(preview_lines) >= DIFF_PREVIEW_LINES:
                    preview_lines.append("...")
                    break
                preview_lines.append(line.rstrip('\n'))
            diff_info["preview"] = preview_lines

    except UnicodeDecodeError:
        # バイナリファイルとして扱う
        diff_info["is_binary"] = True
        diff_info["has_diff"] = True
    except Exception as e:
        diff_info["error"] = str(e)

    return diff_info


def get_dev_files(dev_path: Path) -> List[Dict[str, Any]]:
    """
    DEV配下のリリース対象ファイルを全て取得

    Args:
        dev_path: DEVディレクトリパス

    Returns:
        ファイル情報のリスト
    """
    files = []

    for dev_dir, prod_dir in RELEASE_DIRS.items():
        source_path = dev_path / dev_dir
        if not source_path.exists():
            continue

        for file_path in source_path.rglob("*"):
            if file_path.is_file():
                rel_to_dev_dir = file_path.relative_to(source_path)
                prod_rel_path = Path(prod_dir) / rel_to_dev_dir

                files.append({
                    "source": str(file_path.relative_to(dev_path)),
                    "target": str(prod_rel_path),
                    "source_abs": str(file_path),
                    "mtime": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                    "size": file_path.stat().st_size,
                })

    return files


def detect_release_targets(
    project_id: str,
    order_id: Optional[str] = None,
    all_dev: bool = False,
    include_diff: bool = True,
) -> Dict[str, Any]:
    """
    リリース対象ファイルを検出

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID（指定時は成果物パスから検出）
        all_dev: DEV配下全てを検出
        include_diff: 差分情報を含めるか（デフォルト: True）

    Returns:
        検出結果の辞書
    """
    paths = get_project_paths(project_id)
    dev_path = paths["dev"]
    base_path = paths["base"]

    if not dev_path.exists():
        return {
            "success": False,
            "error": f"DEVディレクトリが存在しません: {dev_path}",
            "targets": [],
            "count": 0,
        }

    # DEV配下のファイルを取得
    dev_files = get_dev_files(dev_path)

    if not dev_files:
        return {
            "success": True,
            "targets": [],
            "count": 0,
            "message": "リリース対象ファイルがありません",
        }

    # 本番環境との比較で変更種別を判定
    targets = []
    for file_info in dev_files:
        prod_file = base_path / file_info["target"]
        source_file = dev_path / file_info["source"]

        if not prod_file.exists():
            change_type = "NEW"
        else:
            # ファイル内容を比較
            try:
                source_content = source_file.read_bytes()
                prod_content = prod_file.read_bytes()
                if source_content == prod_content:
                    continue  # 変更なし - スキップ
                change_type = "MODIFIED"
            except Exception:
                change_type = "MODIFIED"  # 比較エラー時は変更扱い

        target_info = {
            "source": file_info["source"],
            "target": file_info["target"],
            "source_abs": file_info["source_abs"],
            "target_abs": str(prod_file),
            "change_type": change_type,
            "mtime": file_info["mtime"],
            "size": file_info["size"],
        }

        # 差分情報を追加
        if include_diff:
            diff_info = calculate_diff(source_file, prod_file)
            target_info["diff"] = diff_info

        targets.append(target_info)

    # ORDER指定時は成果物パスでフィルタリング
    if order_id and not all_dev:
        # ORDER成果物からリリース対象を絞り込む（将来実装）
        # 現在は全DEVファイルを対象とする
        pass

    return {
        "success": True,
        "project_id": project_id,
        "order_id": order_id,
        "targets": targets,
        "count": len(targets),
        "detected_at": datetime.now().isoformat(),
        "summary": {
            "new": len([t for t in targets if t["change_type"] == "NEW"]),
            "modified": len([t for t in targets if t["change_type"] == "MODIFIED"]),
        }
    }


def format_output(result: Dict[str, Any], json_output: bool = False, show_diff: bool = True) -> str:
    """
    検出結果をフォーマット

    Args:
        result: 検出結果
        json_output: JSON形式で出力するか
        show_diff: 差分情報を表示するか

    Returns:
        フォーマット済み文字列
    """
    if json_output:
        return json.dumps(result, indent=2, ensure_ascii=False)

    if not result.get("success"):
        return f"エラー: {result.get('error', '不明なエラー')}"

    targets = result.get("targets", [])
    if not targets:
        return "リリース対象ファイルがありません。"

    lines = [
        f"【リリース対象】{result.get('project_id', '')}",
        "",
        f"■ 検出ファイル（{len(targets)}件）",
        "| # | 種別 | ソース | リリース先 | 追加 | 削除 |",
        "|---|------|--------|-----------|------|------|",
    ]

    for i, target in enumerate(targets, 1):
        change_mark = "NEW" if target["change_type"] == "NEW" else "MOD"
        diff = target.get("diff", {})

        if diff.get("is_binary"):
            added = "-"
            deleted = "-"
        else:
            added = f"+{diff.get('added_lines', 0)}"
            deleted = f"-{diff.get('deleted_lines', 0)}"

        lines.append(f"| {i} | {change_mark} | DEV/{target['source']} | {target['target']} | {added} | {deleted} |")

    lines.extend([
        "",
        f"■ サマリ",
        f"- 新規: {result['summary']['new']}件",
        f"- 更新: {result['summary']['modified']}件",
    ])

    # 差分詳細を表示
    if show_diff:
        total_added = sum(t.get("diff", {}).get("added_lines", 0) for t in targets)
        total_deleted = sum(t.get("diff", {}).get("deleted_lines", 0) for t in targets)
        lines.extend([
            f"- 総追加行数: +{total_added}",
            f"- 総削除行数: -{total_deleted}",
        ])

        # 各ファイルの差分プレビュー
        lines.append("")
        lines.append("■ 差分プレビュー")

        for i, target in enumerate(targets, 1):
            diff = target.get("diff", {})
            if not diff:
                continue

            lines.append(f"")
            lines.append(f"--- [{i}] {target['target']} ---")

            if diff.get("is_binary"):
                lines.append("  (バイナリファイル)")
            elif diff.get("preview"):
                for preview_line in diff["preview"]:
                    lines.append(f"  {preview_line}")
            elif target["change_type"] == "NEW":
                lines.append("  (新規ファイル)")
            else:
                lines.append("  (差分なし)")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="リリース対象ファイルを検出",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
    python detect.py AI_PM_PJ --order ORDER_060
    python detect.py AI_PM_PJ --all-dev
    python detect.py AI_PM_PJ --json
    python detect.py AI_PM_PJ --no-diff  # 差分表示を省略
        """
    )

    parser.add_argument(
        "project_id",
        help="プロジェクトID（例: AI_PM_PJ）"
    )
    parser.add_argument(
        "--order", "-o",
        dest="order_id",
        help="ORDER ID（例: ORDER_060）"
    )
    parser.add_argument(
        "--all-dev",
        action="store_true",
        help="DEV配下全てを検出対象とする"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )
    parser.add_argument(
        "--no-diff",
        action="store_true",
        help="差分表示を省略（デフォルトは差分表示あり）"
    )

    args = parser.parse_args()

    try:
        include_diff = not args.no_diff

        result = detect_release_targets(
            project_id=args.project_id,
            order_id=args.order_id,
            all_dev=args.all_dev,
            include_diff=include_diff,
        )

        output = format_output(result, json_output=args.json, show_diff=include_diff)
        print(output)

        sys.exit(0 if result.get("success") else 1)

    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        else:
            print(f"エラー: {e}", file=sys.stderr, flush=True)
        sys.exit(2)


# Windows環境でのUTF-8出力設定
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


if __name__ == "__main__":
    main()
