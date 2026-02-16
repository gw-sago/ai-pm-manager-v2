#!/usr/bin/env python3
"""
AI PM Framework - ログストリーミング読み取りスクリプト

指定されたログファイルをtail -f風にリアルタイム読み取り。
ファイルの追記を監視し、新しい行を逐次出力する。

Usage:
    python backend/utils/log_stream.py LOG_FILE_PATH [options]

Options:
    --lines N       初期表示行数（デフォルト: 10）
    --follow        ファイル終端後も監視を続ける（デフォルト: True）
    --interval SEC  ポーリング間隔秒数（デフォルト: 0.1）

Example:
    python backend/utils/log_stream.py logs/worker_TASK_001.log
    python backend/utils/log_stream.py logs/worker_TASK_001.log --lines 20
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional, TextIO


def tail_initial_lines(file_path: Path, num_lines: int = 10) -> None:
    """
    ファイルの末尾N行を出力

    Args:
        file_path: ログファイルパス
        num_lines: 表示行数
    """
    if not file_path.exists():
        return

    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            # すべての行を読み込んで末尾N行を取得
            lines = f.readlines()
            tail_lines = lines[-num_lines:] if len(lines) > num_lines else lines

            for line in tail_lines:
                print(line, end='')
    except Exception as e:
        print(f"警告: 初期行読み取りエラー: {e}", file=sys.stderr)


def stream_log_file(
    file_path: Path,
    *,
    initial_lines: int = 10,
    follow: bool = True,
    interval: float = 0.1,
) -> None:
    """
    ログファイルをtail -f風にストリーミング表示

    Args:
        file_path: ログファイルパス
        initial_lines: 初期表示行数
        follow: ファイル終端後も監視を続けるか
        interval: ポーリング間隔（秒）

    Note:
        - ファイルが存在しない場合は作成を待つ
        - Ctrl+Cで終了
    """
    file_path = Path(file_path)

    # ファイルが存在しない場合は待機
    if not file_path.exists():
        print(f"ログファイルを待機中: {file_path}", file=sys.stderr)
        while not file_path.exists():
            time.sleep(interval)
        print(f"ログファイル検出: {file_path}", file=sys.stderr)

    # 初期行を表示
    if initial_lines > 0:
        tail_initial_lines(file_path, initial_lines)

    # ストリーミング開始
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            # ファイル終端まで移動
            if initial_lines > 0:
                f.seek(0, 2)  # ファイル終端へ

            while True:
                # 新しい行を読み取り
                line = f.readline()

                if line:
                    # 新しい行があれば出力
                    print(line, end='')
                    sys.stdout.flush()
                else:
                    # 新しい行がない場合
                    if not follow:
                        # followモードでなければ終了
                        break

                    # 少し待機してからリトライ
                    time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\nストリーミング終了", file=sys.stderr)
    except Exception as e:
        print(f"\nエラー: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="ログファイルをリアルタイムストリーミング表示",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "log_file",
        type=Path,
        help="ログファイルパス"
    )
    parser.add_argument(
        "--lines",
        type=int,
        default=10,
        help="初期表示行数（デフォルト: 10）"
    )
    parser.add_argument(
        "--no-follow",
        dest="follow",
        action="store_false",
        default=True,
        help="ファイル終端後に監視を終了"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.1,
        help="ポーリング間隔秒数（デフォルト: 0.1）"
    )

    args = parser.parse_args()

    try:
        stream_log_file(
            args.log_file,
            initial_lines=args.lines,
            follow=args.follow,
            interval=args.interval,
        )
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
