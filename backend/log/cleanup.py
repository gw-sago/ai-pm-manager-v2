#!/usr/bin/env python3
"""
AI PM Framework - ログクリーンアップスクリプト

バックグラウンドログテーブルに対して以下のクリーンアップ処理を実行する:
1. 日付ベース削除: 保持日数を超過した古いログエントリを削除
2. サイズベース削除: 最大行数を超過した古いログエントリを削除

大量削除時はバッチ処理で実行し、DBロックを最小限にする。
実行結果（削除件数、実行時間等）を標準出力にJSON形式で返す。

Usage:
    python backend/log/cleanup.py [options]

Options:
    --dry-run       削除件数を計算するが実際には削除しない
    --json          JSON形式で出力（デフォルト）
    --verbose       詳細ログを標準エラー出力に表示
    --db-path PATH  データベースファイルパス（テスト用）

Environment:
    AIPM_LOG_RETENTION_DAYS   保持日数（デフォルト: 30）
    AIPM_LOG_MAX_ROWS         最大行数（デフォルト: 10000）
    AIPM_LOG_BATCH_SIZE       バッチサイズ（デフォルト: 500）
    AIPM_LOG_BATCH_SLEEP_SEC  バッチ間スリープ秒数（デフォルト: 0.1）
    AIPM_LOG_TABLE_NAME       対象テーブル名（デフォルト: background_logs）
    AIPM_LOG_TIMESTAMP_COLUMN タイムスタンプカラム名（デフォルト: created_at）
    AIPM_LOG_DRY_RUN          ドライランフラグ（"true"/"false"）

Example:
    python backend/log/cleanup.py
    python backend/log/cleanup.py --dry-run --verbose
    AIPM_LOG_RETENTION_DAYS=7 python backend/log/cleanup.py
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from config.log_rotation_config import get_log_rotation_config, LogRotationConfig
from utils.db import (
    get_connection,
    execute_query,
    fetch_one,
    table_exists,
    DatabaseError,
)


class CleanupResult:
    """クリーンアップ処理結果"""

    def __init__(self):
        self.date_based_deleted: int = 0
        self.size_based_deleted: int = 0
        self.total_deleted: int = 0
        self.rows_before: int = 0
        self.rows_after: int = 0
        self.date_based_batches: int = 0
        self.size_based_batches: int = 0
        self.elapsed_sec: float = 0.0
        self.dry_run: bool = False
        self.skipped: bool = False
        self.skip_reason: Optional[str] = None
        self.cutoff_date: Optional[str] = None
        self.config_summary: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "success": True,
            "dry_run": self.dry_run,
            "date_based_deleted": self.date_based_deleted,
            "size_based_deleted": self.size_based_deleted,
            "total_deleted": self.total_deleted,
            "rows_before": self.rows_before,
            "rows_after": self.rows_after,
            "date_based_batches": self.date_based_batches,
            "size_based_batches": self.size_based_batches,
            "elapsed_sec": round(self.elapsed_sec, 3),
            "config": self.config_summary,
        }
        if self.cutoff_date:
            result["cutoff_date"] = self.cutoff_date
        if self.skipped:
            result["skipped"] = True
            result["skip_reason"] = self.skip_reason
        return result


def _count_table_rows(conn, table_name: str) -> int:
    """テーブルの総行数を取得"""
    row = fetch_one(conn, f"SELECT COUNT(*) as cnt FROM [{table_name}]")
    return row["cnt"] if row else 0


def _log_verbose(message: str, verbose: bool) -> None:
    """詳細ログを標準エラー出力に出力"""
    if verbose:
        print(f"[cleanup] {message}", file=sys.stderr)


def cleanup_by_date(
    conn,
    config: LogRotationConfig,
    *,
    verbose: bool = False,
) -> tuple:
    """
    日付ベースのクリーンアップ: 保持日数を超過したログを削除

    Args:
        conn: DB接続
        config: ログローテーション設定
        verbose: 詳細ログ出力

    Returns:
        (deleted_count, batch_count, cutoff_date_str)
    """
    cutoff_date = datetime.now() - timedelta(days=config.retention_days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")

    _log_verbose(
        f"日付ベース削除: {config.timestamp_column} < '{cutoff_str}' "
        f"(保持日数: {config.retention_days})",
        verbose,
    )

    total_deleted = 0
    batch_count = 0

    while True:
        if config.dry_run:
            # ドライラン: 対象件数のみカウント
            row = fetch_one(
                conn,
                f"SELECT COUNT(*) as cnt FROM [{config.log_table_name}] "
                f"WHERE [{config.timestamp_column}] < ?",
                (cutoff_str,),
            )
            count = row["cnt"] if row else 0
            _log_verbose(f"  ドライラン: 削除対象 {count} 件", verbose)
            return count, 1 if count > 0 else 0, cutoff_str

        # バッチ削除: rowid を使って効率的に削除
        cursor = execute_query(
            conn,
            f"DELETE FROM [{config.log_table_name}] "
            f"WHERE rowid IN ("
            f"  SELECT rowid FROM [{config.log_table_name}] "
            f"  WHERE [{config.timestamp_column}] < ? "
            f"  LIMIT ?"
            f")",
            (cutoff_str, config.batch_size),
        )
        conn.commit()
        deleted_in_batch = cursor.rowcount

        total_deleted += deleted_in_batch
        batch_count += 1

        _log_verbose(
            f"  バッチ {batch_count}: {deleted_in_batch} 件削除 (累計: {total_deleted})",
            verbose,
        )

        if deleted_in_batch < config.batch_size:
            break

        if config.batch_sleep_sec > 0:
            time.sleep(config.batch_sleep_sec)

    return total_deleted, batch_count, cutoff_str


def cleanup_by_size(
    conn,
    config: LogRotationConfig,
    *,
    verbose: bool = False,
) -> tuple:
    """
    サイズベースのクリーンアップ: 最大行数を超過した古いログを削除

    Args:
        conn: DB接続
        config: ログローテーション設定
        verbose: 詳細ログ出力

    Returns:
        (deleted_count, batch_count)
    """
    current_count = _count_table_rows(conn, config.log_table_name)
    excess = current_count - config.max_rows

    if excess <= 0:
        _log_verbose(
            f"サイズベース削除: 不要 (現在 {current_count} 行 / 上限 {config.max_rows} 行)",
            verbose,
        )
        return 0, 0

    _log_verbose(
        f"サイズベース削除: {excess} 件超過 (現在 {current_count} 行 / 上限 {config.max_rows} 行)",
        verbose,
    )

    if config.dry_run:
        _log_verbose(f"  ドライラン: 削除対象 {excess} 件", verbose)
        return excess, 1 if excess > 0 else 0

    total_deleted = 0
    batch_count = 0
    remaining_to_delete = excess

    while remaining_to_delete > 0:
        batch_limit = min(config.batch_size, remaining_to_delete)

        # 古い順に削除（timestamp_column でソートして古い行を特定）
        cursor = execute_query(
            conn,
            f"DELETE FROM [{config.log_table_name}] "
            f"WHERE rowid IN ("
            f"  SELECT rowid FROM [{config.log_table_name}] "
            f"  ORDER BY [{config.timestamp_column}] ASC "
            f"  LIMIT ?"
            f")",
            (batch_limit,),
        )
        conn.commit()
        deleted_in_batch = cursor.rowcount

        total_deleted += deleted_in_batch
        remaining_to_delete -= deleted_in_batch
        batch_count += 1

        _log_verbose(
            f"  バッチ {batch_count}: {deleted_in_batch} 件削除 (累計: {total_deleted})",
            verbose,
        )

        if deleted_in_batch == 0:
            break

        if remaining_to_delete > 0 and config.batch_sleep_sec > 0:
            time.sleep(config.batch_sleep_sec)

    return total_deleted, batch_count


def run_cleanup(
    config: Optional[LogRotationConfig] = None,
    *,
    db_path: Optional[Path] = None,
    verbose: bool = False,
) -> CleanupResult:
    """
    ログクリーンアップ処理のメインエントリーポイント

    Args:
        config: ログローテーション設定（Noneの場合は環境変数から読み込み）
        db_path: DBパス（Noneの場合はデフォルト）
        verbose: 詳細ログ出力

    Returns:
        CleanupResult: 処理結果
    """
    start_time = time.time()
    result = CleanupResult()

    if config is None:
        config = get_log_rotation_config()

    result.dry_run = config.dry_run
    result.config_summary = {
        "retention_days": config.retention_days,
        "max_rows": config.max_rows,
        "batch_size": config.batch_size,
        "table_name": config.log_table_name,
        "timestamp_column": config.timestamp_column,
    }

    _log_verbose(
        f"クリーンアップ開始 (テーブル: {config.log_table_name}, "
        f"ドライラン: {config.dry_run})",
        verbose,
    )

    conn = get_connection(db_path)
    try:
        # テーブル存在チェック
        if not table_exists(conn, config.log_table_name):
            _log_verbose(
                f"テーブル '{config.log_table_name}' が存在しません。スキップします。",
                verbose,
            )
            result.skipped = True
            result.skip_reason = f"テーブル '{config.log_table_name}' が存在しません"
            result.elapsed_sec = time.time() - start_time
            return result

        # 削除前の行数を記録
        result.rows_before = _count_table_rows(conn, config.log_table_name)
        _log_verbose(f"削除前行数: {result.rows_before}", verbose)

        # 1. 日付ベース削除
        date_deleted, date_batches, cutoff_str = cleanup_by_date(
            conn, config, verbose=verbose
        )
        result.date_based_deleted = date_deleted
        result.date_based_batches = date_batches
        result.cutoff_date = cutoff_str

        # 2. サイズベース削除（日付ベース削除後の行数で判定）
        size_deleted, size_batches = cleanup_by_size(
            conn, config, verbose=verbose
        )
        result.size_based_deleted = size_deleted
        result.size_based_batches = size_batches

        # 集計
        result.total_deleted = result.date_based_deleted + result.size_based_deleted

        if config.dry_run:
            result.rows_after = result.rows_before
        else:
            result.rows_after = _count_table_rows(conn, config.log_table_name)

        result.elapsed_sec = time.time() - start_time

        _log_verbose(
            f"クリーンアップ完了: 合計 {result.total_deleted} 件削除 "
            f"({result.rows_before} → {result.rows_after} 行), "
            f"所要時間: {result.elapsed_sec:.3f}秒",
            verbose,
        )

        return result

    finally:
        conn.close()


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        from config.db_config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="バックグラウンドログのクリーンアップ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="削除件数を計算するが実際には削除しない",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="詳細ログを標準エラー出力に表示",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="データベースファイルパス（テスト用）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="JSON形式で出力（デフォルト）",
    )

    args = parser.parse_args()

    try:
        config = get_log_rotation_config()

        # CLI引数でドライランを上書き
        if args.dry_run:
            config.dry_run = True

        db_path = Path(args.db_path) if args.db_path else None

        result = run_cleanup(
            config=config,
            db_path=db_path,
            verbose=args.verbose,
        )

        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))

    except (DatabaseError, ValueError) as e:
        error_output = {"success": False, "error": str(e)}
        print(json.dumps(error_output, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error_output = {"success": False, "error": f"予期しないエラー: {e}"}
        print(json.dumps(error_output, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
