#!/usr/bin/env python3
"""
AI PM Framework - Interactionポーリングスクリプト

定期的にDBをポーリングしてstatus=PENDINGのinteractionsを監視し、
新規レコードを検知した場合にイベントを発火する

Usage:
    # 継続監視モード（デフォルト）
    python backend/interaction/poll.py [PROJECT_ID]

    # ワンショット実行
    python backend/interaction/poll.py --once

    # カスタムポーリング間隔（秒）
    python backend/interaction/poll.py --interval 10

    # コールバックコマンド実行
    python backend/interaction/poll.py --callback "python notify.py {id}"

Options:
    --interval N        ポーリング間隔（秒、デフォルト: 5）
    --once              一度だけ実行して終了
    --callback CMD      新規検知時に実行するコマンド（プレースホルダー対応）
    --json              JSON形式で出力
    --quiet             通常ログを抑制（検知時のみ出力）
    --project-id ID     プロジェクトIDでフィルタ

Callback placeholders:
    {id}            - Interaction ID
    {project_id}    - プロジェクトID
    {task_id}       - タスクID
    {session_id}    - セッションID
    {question_type} - 質問タイプ
"""

import argparse
import json
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Set, List, Dict, Any, Callable

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    fetch_all,
    row_to_dict,
    DatabaseError,
)


# グローバル終了フラグ
_should_exit = False


def signal_handler(signum, frame):
    """シグナルハンドラー（Ctrl+C対応）"""
    global _should_exit
    _should_exit = True


def get_pending_interactions(
    project_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    PENDINGステータスのInteractionを取得

    Args:
        project_id: プロジェクトID（省略時は全プロジェクト）
        db_path: データベースパス（テスト用）

    Returns:
        PENDING状態のInteraction一覧
    """
    try:
        conn = get_connection(db_path=db_path)

        query = """
            SELECT
                i.id,
                i.project_id,
                i.task_id,
                i.session_id,
                i.question_type,
                i.question_text,
                i.options_json as options,
                i.status,
                i.created_at,
                i.timeout_at,
                t.title as task_title,
                t.status as task_status,
                o.title as order_title
            FROM interactions i
            LEFT JOIN tasks t ON i.task_id = t.id AND i.project_id = t.project_id
            LEFT JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
            WHERE i.status = 'PENDING'
        """
        params = []

        if project_id:
            query += " AND i.project_id = ?"
            params.append(project_id)

        query += " ORDER BY i.created_at ASC"

        rows = fetch_all(conn, query, tuple(params) if params else None)
        conn.close()

        return [row_to_dict(row) for row in rows]

    except DatabaseError as e:
        print(f"[ERROR] データベースエラー: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"[ERROR] 予期しないエラー: {e}", file=sys.stderr)
        return []


def format_interaction_event(interaction: Dict[str, Any], json_format: bool = False) -> str:
    """
    Interactionイベントをフォーマット

    Args:
        interaction: Interaction情報
        json_format: JSON形式で出力

    Returns:
        フォーマットされた文字列
    """
    if json_format:
        return json.dumps({
            "event": "new_interaction",
            "timestamp": datetime.now().isoformat(),
            "interaction": interaction,
        }, ensure_ascii=False)

    # テキスト形式
    lines = []
    lines.append("=" * 60)
    lines.append("[NEW INTERACTION DETECTED]")
    lines.append("-" * 60)
    lines.append(f"  ID:           {interaction.get('id', 'N/A')}")
    lines.append(f"  Project:      {interaction.get('project_id', 'N/A')}")
    lines.append(f"  Task:         {interaction.get('task_id', 'N/A')} ({interaction.get('task_title', '')})")
    lines.append(f"  Order:        {interaction.get('order_title', 'N/A')}")
    lines.append(f"  Type:         {interaction.get('question_type', 'N/A')}")
    lines.append(f"  Created:      {interaction.get('created_at', 'N/A')}")

    timeout = interaction.get('timeout_at')
    if timeout:
        lines.append(f"  Timeout:      {timeout}")

    lines.append("-" * 60)
    lines.append("  Question:")
    question = interaction.get('question_text', '')
    for line in question.split('\n'):
        lines.append(f"    {line}")

    options = interaction.get('options')
    if options:
        lines.append("")
        lines.append("  Options:")
        try:
            opts = json.loads(options) if isinstance(options, str) else options
            for i, opt in enumerate(opts, 1):
                if isinstance(opt, dict):
                    lines.append(f"    {i}. {opt.get('label', opt)}")
                    if opt.get('description'):
                        lines.append(f"       {opt.get('description')}")
                else:
                    lines.append(f"    {i}. {opt}")
        except:
            lines.append(f"    {options}")

    lines.append("=" * 60)
    return "\n".join(lines)


def execute_callback(
    callback_cmd: str,
    interaction: Dict[str, Any],
) -> bool:
    """
    コールバックコマンドを実行

    Args:
        callback_cmd: コールバックコマンドテンプレート
        interaction: Interaction情報

    Returns:
        成功した場合True
    """
    try:
        # プレースホルダー置換
        cmd = callback_cmd
        cmd = cmd.replace("{id}", str(interaction.get("id", "")))
        cmd = cmd.replace("{project_id}", str(interaction.get("project_id", "")))
        cmd = cmd.replace("{task_id}", str(interaction.get("task_id", "")))
        cmd = cmd.replace("{session_id}", str(interaction.get("session_id", "")))
        cmd = cmd.replace("{question_type}", str(interaction.get("question_type", "")))

        # コマンド実行
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            print(f"[WARN] コールバック失敗 (code={result.returncode}): {result.stderr}", file=sys.stderr)
            return False

        return True

    except subprocess.TimeoutExpired:
        print(f"[WARN] コールバックタイムアウト: {callback_cmd}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] コールバック実行エラー: {e}", file=sys.stderr)
        return False


def poll_interactions(
    project_id: Optional[str] = None,
    interval: float = 5.0,
    once: bool = False,
    callback: Optional[str] = None,
    json_format: bool = False,
    quiet: bool = False,
    on_new_interaction: Optional[Callable[[Dict[str, Any]], None]] = None,
    db_path: Optional[Path] = None,
) -> None:
    """
    Interactionをポーリング監視

    Args:
        project_id: プロジェクトIDフィルタ
        interval: ポーリング間隔（秒）
        once: 一度だけ実行
        callback: コールバックコマンド
        json_format: JSON形式で出力
        quiet: 通常ログを抑制
        on_new_interaction: 新規検知時のコールバック関数
        db_path: データベースパス（テスト用）
    """
    global _should_exit

    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 既知のInteraction IDを管理
    known_ids: Set[int] = set()
    first_run = True

    if not quiet:
        print(f"[INFO] ポーリング開始 (間隔: {interval}秒)", file=sys.stderr)
        if project_id:
            print(f"[INFO] プロジェクトフィルタ: {project_id}", file=sys.stderr)

    while not _should_exit:
        try:
            # PENDINGのInteractionを取得
            pending = get_pending_interactions(project_id=project_id, db_path=db_path)
            current_ids = {i["id"] for i in pending}

            # 新規Interactionを検出（初回は既存を新規扱いしない）
            if first_run:
                known_ids = current_ids
                first_run = False
                if not quiet:
                    print(f"[INFO] 初期状態: PENDING {len(pending)}件", file=sys.stderr)
            else:
                new_ids = current_ids - known_ids

                for interaction in pending:
                    if interaction["id"] in new_ids:
                        # 新規Interaction検出
                        output = format_interaction_event(interaction, json_format)
                        print(output)
                        sys.stdout.flush()

                        # コールバック実行
                        if callback:
                            execute_callback(callback, interaction)

                        # カスタムハンドラー呼び出し
                        if on_new_interaction:
                            on_new_interaction(interaction)

                # 解決済みIDを削除（メモリリーク防止）
                resolved_ids = known_ids - current_ids
                known_ids = current_ids

                if resolved_ids and not quiet:
                    print(f"[INFO] 解決済み: {len(resolved_ids)}件", file=sys.stderr)

            # ワンショットモード
            if once:
                if not quiet:
                    print(f"[INFO] ワンショット完了 (PENDING: {len(pending)}件)", file=sys.stderr)
                break

            # 次のポーリングまで待機
            time.sleep(interval)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[ERROR] ポーリングエラー: {e}", file=sys.stderr)
            if once:
                break
            time.sleep(interval)

    if not quiet:
        print("\n[INFO] ポーリング終了", file=sys.stderr)


def main():
    """コマンドライン実行"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="Interactionをポーリング監視",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 継続監視（デフォルト5秒間隔）
  python poll.py

  # プロジェクト指定
  python poll.py AI_PM_PJ

  # ワンショット実行
  python poll.py --once

  # ポーリング間隔変更
  python poll.py --interval 10

  # コールバック実行
  python poll.py --callback "python notify.py {id}"

  # JSON形式出力
  python poll.py --json

コールバックプレースホルダー:
  {id}            - Interaction ID
  {project_id}    - プロジェクトID
  {task_id}       - タスクID
  {session_id}    - セッションID
  {question_type} - 質問タイプ
"""
    )

    parser.add_argument(
        "project_id",
        nargs="?",
        help="プロジェクトID (例: AI_PM_PJ)"
    )
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=5.0,
        help="ポーリング間隔（秒、デフォルト: 5）"
    )
    parser.add_argument(
        "--once", "-1",
        action="store_true",
        help="一度だけ実行して終了"
    )
    parser.add_argument(
        "--callback", "-c",
        help="新規検知時に実行するコマンド"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="通常ログを抑制"
    )

    args = parser.parse_args()

    poll_interactions(
        project_id=args.project_id,
        interval=args.interval,
        once=args.once,
        callback=args.callback,
        json_format=args.json,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    main()
