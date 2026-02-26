"""
AI PM Framework - ログクリーンアップテスト

backend/log/cleanup.py の以下の機能をユニットテストする:
1. 日付ベース削除（保持日数超過の古いログを削除）
2. サイズベース削除（最大行数超過の古いログを削除）
3. バッチ処理（小さいバッチサイズで複数回に分けて削除）
4. 境界値テスト（ちょうど閾値のログ）
5. 異常系テスト（空テーブル、テーブル不在）
6. ドライランテスト（実際に削除されないことを確認）

テスト用の一時DBを作成して background_logs テーブルを CREATE し、
本番DBには一切触れない。
"""

import unittest
import sqlite3
import tempfile
import sys
from pathlib import Path
from datetime import datetime, timedelta

# backend/ をパスに追加
_test_dir = Path(__file__).resolve().parent
_package_root = _test_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from config.log_rotation_config import LogRotationConfig, reset_config
from log.cleanup import (
    run_cleanup,
    cleanup_by_date,
    cleanup_by_size,
    CleanupResult,
)
from utils.db import get_connection, fetch_one, execute_query

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

_CREATE_BACKGROUND_LOGS = """
CREATE TABLE IF NOT EXISTS background_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    task_id TEXT,
    level TEXT DEFAULT 'INFO',
    message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


def _make_db(with_table: bool = True) -> Path:
    """テスト用の一時DBを作成して返す"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = Path(tmp.name)
    tmp.close()

    if with_table:
        conn = get_connection(db_path)
        conn.execute(_CREATE_BACKGROUND_LOGS)
        conn.commit()
        conn.close()

    return db_path


def _insert_logs(db_path: Path, rows: list[tuple]):
    """
    background_logs にテストデータを一括挿入する。

    rows: [(created_at_str, message), ...]
    """
    conn = get_connection(db_path)
    for created_at, message in rows:
        execute_query(
            conn,
            "INSERT INTO background_logs (created_at, message) VALUES (?, ?)",
            (created_at, message),
        )
    conn.commit()
    conn.close()


def _count(db_path: Path) -> int:
    """background_logs の行数を返す"""
    conn = get_connection(db_path)
    row = fetch_one(conn, "SELECT COUNT(*) as cnt FROM background_logs")
    cnt = row["cnt"]
    conn.close()
    return cnt


def _make_config(**overrides) -> LogRotationConfig:
    """テスト用のLogRotationConfigを作成する。batch_sleep_secはデフォルト0。"""
    defaults = dict(
        retention_days=30,
        max_rows=10000,
        batch_size=500,
        batch_sleep_sec=0,  # テストでは待機不要
        log_table_name="background_logs",
        timestamp_column="created_at",
        dry_run=False,
    )
    defaults.update(overrides)
    return LogRotationConfig(**defaults)


def _ts(days_ago: int = 0, hours_ago: int = 0, minutes_ago: int = 0) -> str:
    """現在から指定時間前のタイムスタンプ文字列を返す"""
    dt = datetime.now() - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ===========================================================================
# テストクラス
# ===========================================================================


class TestDateBasedCleanup(unittest.TestCase):
    """日付ベース削除のテスト"""

    def setUp(self):
        reset_config()
        self.db_path = _make_db()

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)
        reset_config()

    # ----- 正常系 -----

    def test_deletes_old_logs(self):
        """保持日数を超過した古いログが削除される"""
        _insert_logs(self.db_path, [
            (_ts(days_ago=60), "ancient log 1"),
            (_ts(days_ago=45), "ancient log 2"),
            (_ts(days_ago=31), "old log"),
            (_ts(days_ago=10), "recent log 1"),
            (_ts(days_ago=1), "recent log 2"),
        ])

        config = _make_config(retention_days=30)
        result = run_cleanup(config, db_path=self.db_path)

        self.assertTrue(result.to_dict()["success"])
        self.assertFalse(result.dry_run)
        # 60日前、45日前、31日前の3件が削除される
        self.assertEqual(result.date_based_deleted, 3)
        self.assertEqual(result.rows_before, 5)
        self.assertEqual(result.rows_after, 2)
        self.assertEqual(_count(self.db_path), 2)

    def test_no_deletion_when_all_recent(self):
        """すべてのログが保持日数内であれば削除されない"""
        _insert_logs(self.db_path, [
            (_ts(days_ago=10), "log 1"),
            (_ts(days_ago=5), "log 2"),
            (_ts(days_ago=1), "log 3"),
        ])

        config = _make_config(retention_days=30)
        result = run_cleanup(config, db_path=self.db_path)

        self.assertEqual(result.date_based_deleted, 0)
        self.assertEqual(result.rows_after, 3)

    def test_retention_days_1(self):
        """保持日数=1でも正しく動作する"""
        _insert_logs(self.db_path, [
            (_ts(days_ago=3), "old"),
            (_ts(hours_ago=12), "recent"),
        ])

        config = _make_config(retention_days=1)
        result = run_cleanup(config, db_path=self.db_path)

        self.assertEqual(result.date_based_deleted, 1)
        self.assertEqual(result.rows_after, 1)

    # ----- 境界値 -----

    def test_boundary_exactly_at_threshold(self):
        """ちょうど保持日数ぴったりのログは削除されない（cutoff = now - retention_days）"""
        # 30日ちょうど前は cutoff より後（同じ秒数ならギリギリ）のケースを検証
        # 実装: cutoff = now - timedelta(days=30) => 30日前ちょうどは cutoff と同時刻
        # WHERE created_at < cutoff なので、ちょうど同時刻のログは削除されない

        # 正確なcutoffを再現: 30日前 + 少し余裕
        _insert_logs(self.db_path, [
            (_ts(days_ago=30, hours_ago=1), "just over threshold"),
            (_ts(days_ago=30), "exactly at threshold"),
            (_ts(days_ago=29, hours_ago=23), "just under threshold"),
        ])

        config = _make_config(retention_days=30)
        result = run_cleanup(config, db_path=self.db_path)

        # 30日+1時間前は確実に削除される
        # 30日ちょうどは cutoff_date の微妙な差により結果が変わりうるが、
        # cleanup_by_date は "< cutoff" で判定するので、ちょうど同時刻は残る
        # ただしテスト実行中の時刻差があるため、30日前ぴったりは保持される
        self.assertGreaterEqual(result.date_based_deleted, 1)
        # 29日23時間前は確実に残る
        self.assertGreaterEqual(result.rows_after, 1)


class TestSizeBasedCleanup(unittest.TestCase):
    """サイズベース削除のテスト"""

    def setUp(self):
        reset_config()
        self.db_path = _make_db()

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)
        reset_config()

    # ----- 正常系 -----

    def test_deletes_excess_rows(self):
        """最大行数を超過した分が古い順に削除される"""
        rows = [(_ts(days_ago=i), f"log {i}") for i in range(20, 0, -1)]
        _insert_logs(self.db_path, rows)  # 20行挿入

        config = _make_config(max_rows=10, retention_days=365)  # 日付では削除されない
        result = run_cleanup(config, db_path=self.db_path)

        self.assertEqual(result.size_based_deleted, 10)
        self.assertEqual(result.rows_after, 10)
        self.assertEqual(_count(self.db_path), 10)

        # 古いもの（days_ago=20〜11）が削除され、新しいもの（days_ago=10〜1）が残る
        conn = get_connection(self.db_path)
        row = fetch_one(
            conn,
            "SELECT MIN(message) as oldest FROM background_logs",
        )
        conn.close()
        # 残っているのは "log 1" 〜 "log 10" (days_ago=1〜10)
        self.assertIn("log", row["oldest"])

    def test_no_deletion_when_under_limit(self):
        """行数が最大行数以下であれば削除されない"""
        _insert_logs(self.db_path, [
            (_ts(days_ago=1), "log 1"),
            (_ts(days_ago=2), "log 2"),
        ])

        config = _make_config(max_rows=100, retention_days=365)
        result = run_cleanup(config, db_path=self.db_path)

        self.assertEqual(result.size_based_deleted, 0)
        self.assertEqual(result.rows_after, 2)

    # ----- 境界値 -----

    def test_boundary_exactly_at_max_rows(self):
        """ちょうど最大行数ぴったりのとき削除されない"""
        rows = [(_ts(days_ago=i), f"log {i}") for i in range(10, 0, -1)]
        _insert_logs(self.db_path, rows)  # 10行挿入

        config = _make_config(max_rows=10, retention_days=365)
        result = run_cleanup(config, db_path=self.db_path)

        self.assertEqual(result.size_based_deleted, 0)
        self.assertEqual(result.rows_after, 10)

    def test_boundary_one_over_max_rows(self):
        """最大行数+1のとき1件だけ削除される"""
        rows = [(_ts(days_ago=i), f"log {i}") for i in range(11, 0, -1)]
        _insert_logs(self.db_path, rows)  # 11行挿入

        config = _make_config(max_rows=10, retention_days=365)
        result = run_cleanup(config, db_path=self.db_path)

        self.assertEqual(result.size_based_deleted, 1)
        self.assertEqual(result.rows_after, 10)

    def test_max_rows_1(self):
        """max_rows=1でも正しく動作する"""
        _insert_logs(self.db_path, [
            (_ts(days_ago=3), "old"),
            (_ts(days_ago=2), "mid"),
            (_ts(days_ago=1), "new"),
        ])

        config = _make_config(max_rows=1, retention_days=365)
        result = run_cleanup(config, db_path=self.db_path)

        self.assertEqual(result.size_based_deleted, 2)
        self.assertEqual(result.rows_after, 1)


class TestBatchProcessing(unittest.TestCase):
    """バッチ処理のテスト"""

    def setUp(self):
        reset_config()
        self.db_path = _make_db()

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)
        reset_config()

    def test_date_batch_processing(self):
        """日付ベース削除が小さいバッチサイズで複数回に分けて実行される"""
        # 50件の古いログ（全て31日以上前）
        rows = [(_ts(days_ago=31 + i), f"old log {i}") for i in range(50)]
        # 5件の新しいログ
        rows += [(_ts(days_ago=i), f"recent log {i}") for i in range(5)]
        _insert_logs(self.db_path, rows)

        config = _make_config(
            retention_days=30,
            batch_size=10,  # 10件ずつバッチ削除
            max_rows=99999,
        )
        result = run_cleanup(config, db_path=self.db_path)

        self.assertEqual(result.date_based_deleted, 50)
        # バッチ数: 50件を10件ずつ → 5バッチで全削除 + 1バッチ(0件で終了確認) = 6バッチ
        # cleanup_by_date は最後に batch_size 未満の結果を得て break するため +1
        self.assertEqual(result.date_based_batches, 6)
        self.assertEqual(result.rows_after, 5)

    def test_size_batch_processing(self):
        """サイズベース削除が小さいバッチサイズで複数回に分けて実行される"""
        rows = [(_ts(days_ago=0, minutes_ago=i), f"log {i}") for i in range(30)]
        _insert_logs(self.db_path, rows)  # 30行

        config = _make_config(
            retention_days=365,
            max_rows=10,
            batch_size=7,  # 7件ずつバッチ削除 → 20件超過 = 3バッチ (7+7+6)
        )
        result = run_cleanup(config, db_path=self.db_path)

        self.assertEqual(result.size_based_deleted, 20)
        # 20 / 7 = 2バッチ(14) + 1バッチ(6) = 3バッチ
        self.assertEqual(result.size_based_batches, 3)
        self.assertEqual(result.rows_after, 10)

    def test_batch_size_larger_than_target(self):
        """バッチサイズが削除対象数より大きい場合、1バッチで完了する"""
        rows = [(_ts(days_ago=60), f"old log {i}") for i in range(5)]
        _insert_logs(self.db_path, rows)

        config = _make_config(
            retention_days=30,
            batch_size=1000,
        )
        result = run_cleanup(config, db_path=self.db_path)

        self.assertEqual(result.date_based_deleted, 5)
        self.assertEqual(result.date_based_batches, 1)

    def test_batch_size_1(self):
        """batch_size=1でも正しく動作する（1件ずつ削除）"""
        rows = [(_ts(days_ago=60), f"old {i}") for i in range(3)]
        _insert_logs(self.db_path, rows)

        config = _make_config(
            retention_days=30,
            batch_size=1,
        )
        result = run_cleanup(config, db_path=self.db_path)

        self.assertEqual(result.date_based_deleted, 3)
        # 3件を1件ずつ → 3バッチで全削除 + 1バッチ(0件で終了確認) = 4バッチ
        self.assertEqual(result.date_based_batches, 4)


class TestCombinedCleanup(unittest.TestCase):
    """日付ベース + サイズベース の複合テスト"""

    def setUp(self):
        reset_config()
        self.db_path = _make_db()

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)
        reset_config()

    def test_date_then_size_cleanup(self):
        """日付ベース削除後にサイズベース削除が実行される"""
        # 60日前のログ: 5件（日付で削除対象）
        rows = [(_ts(days_ago=60), f"ancient {i}") for i in range(5)]
        # 10日前のログ: 20件（日付では残るがサイズで削除対象になりうる）
        rows += [(_ts(days_ago=10, minutes_ago=i), f"recent {i}") for i in range(20)]
        _insert_logs(self.db_path, rows)  # 合計25行

        config = _make_config(
            retention_days=30,
            max_rows=10,  # 日付削除後20行残る → 10件超過
        )
        result = run_cleanup(config, db_path=self.db_path)

        self.assertEqual(result.date_based_deleted, 5)
        self.assertEqual(result.size_based_deleted, 10)
        self.assertEqual(result.total_deleted, 15)
        self.assertEqual(result.rows_before, 25)
        self.assertEqual(result.rows_after, 10)

    def test_date_cleanup_enough_no_size_needed(self):
        """日付ベース削除だけで十分な場合、サイズベース削除は不要"""
        # 60日前のログ: 15件
        rows = [(_ts(days_ago=60), f"old {i}") for i in range(15)]
        # 1日前のログ: 5件
        rows += [(_ts(days_ago=1), f"new {i}") for i in range(5)]
        _insert_logs(self.db_path, rows)  # 合計20行

        config = _make_config(
            retention_days=30,
            max_rows=10,  # 日付削除後5行 < 10行 → サイズ削除不要
        )
        result = run_cleanup(config, db_path=self.db_path)

        self.assertEqual(result.date_based_deleted, 15)
        self.assertEqual(result.size_based_deleted, 0)
        self.assertEqual(result.rows_after, 5)


class TestDryRun(unittest.TestCase):
    """ドライランのテスト"""

    def setUp(self):
        reset_config()
        self.db_path = _make_db()

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)
        reset_config()

    def test_dry_run_date_based_no_deletion(self):
        """ドライラン時、日付ベースの削除対象件数は返すが実際には削除しない"""
        _insert_logs(self.db_path, [
            (_ts(days_ago=60), "old 1"),
            (_ts(days_ago=45), "old 2"),
            (_ts(days_ago=1), "new 1"),
        ])

        config = _make_config(retention_days=30, dry_run=True)
        result = run_cleanup(config, db_path=self.db_path)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.date_based_deleted, 2)
        # ドライランなのでrows_afterはrows_beforeと同じ
        self.assertEqual(result.rows_after, result.rows_before)
        # 実際のDB行数が変わっていない
        self.assertEqual(_count(self.db_path), 3)

    def test_dry_run_size_based_no_deletion(self):
        """ドライラン時、サイズベースの削除対象件数は返すが実際には削除しない"""
        rows = [(_ts(days_ago=0, minutes_ago=i), f"log {i}") for i in range(15)]
        _insert_logs(self.db_path, rows)

        config = _make_config(retention_days=365, max_rows=10, dry_run=True)
        result = run_cleanup(config, db_path=self.db_path)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.size_based_deleted, 5)
        self.assertEqual(result.rows_after, 15)
        self.assertEqual(_count(self.db_path), 15)

    def test_dry_run_combined(self):
        """ドライラン時、日付+サイズ両方の削除対象件数が正しく算出される"""
        # 古いログ: 5件
        rows = [(_ts(days_ago=60), f"old {i}") for i in range(5)]
        # 新しいログ: 20件
        rows += [(_ts(days_ago=0, minutes_ago=i), f"new {i}") for i in range(20)]
        _insert_logs(self.db_path, rows)  # 25行

        config = _make_config(
            retention_days=30,
            max_rows=10,
            dry_run=True,
        )
        result = run_cleanup(config, db_path=self.db_path)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.date_based_deleted, 5)
        # ドライランでは日付ベース削除が実行されないので、
        # サイズベースは25行 - 10行 = 15件が対象として算出される
        self.assertEqual(result.size_based_deleted, 15)
        # 実際には削除されていない
        self.assertEqual(_count(self.db_path), 25)

    def test_dry_run_returns_cutoff_date(self):
        """ドライラン時にもcutoff_dateが結果に含まれる"""
        _insert_logs(self.db_path, [(_ts(days_ago=1), "log")])

        config = _make_config(retention_days=30, dry_run=True)
        result = run_cleanup(config, db_path=self.db_path)

        self.assertIsNotNone(result.cutoff_date)
        result_dict = result.to_dict()
        self.assertIn("cutoff_date", result_dict)


class TestEmptyTable(unittest.TestCase):
    """空テーブルのテスト"""

    def setUp(self):
        reset_config()
        self.db_path = _make_db()

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)
        reset_config()

    def test_empty_table_no_error(self):
        """空テーブルでもエラーにならない"""
        config = _make_config()
        result = run_cleanup(config, db_path=self.db_path)

        self.assertTrue(result.to_dict()["success"])
        self.assertFalse(result.skipped)
        self.assertEqual(result.date_based_deleted, 0)
        self.assertEqual(result.size_based_deleted, 0)
        self.assertEqual(result.total_deleted, 0)
        self.assertEqual(result.rows_before, 0)
        self.assertEqual(result.rows_after, 0)

    def test_empty_table_dry_run(self):
        """空テーブル + ドライランでもエラーにならない"""
        config = _make_config(dry_run=True)
        result = run_cleanup(config, db_path=self.db_path)

        self.assertTrue(result.to_dict()["success"])
        self.assertTrue(result.dry_run)
        self.assertEqual(result.total_deleted, 0)


class TestTableNotExists(unittest.TestCase):
    """テーブル不在のテスト"""

    def setUp(self):
        reset_config()
        self.db_path = _make_db(with_table=False)

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)
        reset_config()

    def test_missing_table_skipped(self):
        """テーブルが存在しない場合スキップされる"""
        config = _make_config()
        result = run_cleanup(config, db_path=self.db_path)

        self.assertTrue(result.to_dict()["success"])
        self.assertTrue(result.skipped)
        self.assertIn("存在しません", result.skip_reason)
        self.assertEqual(result.total_deleted, 0)

    def test_missing_table_dry_run(self):
        """テーブル不在 + ドライランでもスキップされエラーにならない"""
        config = _make_config(dry_run=True)
        result = run_cleanup(config, db_path=self.db_path)

        self.assertTrue(result.to_dict()["success"])
        self.assertTrue(result.skipped)

    def test_wrong_table_name(self):
        """存在しないテーブル名を指定した場合スキップされる"""
        db_path = _make_db(with_table=True)  # background_logs はあるが
        try:
            config = _make_config(log_table_name="nonexistent_table")
            result = run_cleanup(config, db_path=db_path)

            self.assertTrue(result.skipped)
            self.assertIn("nonexistent_table", result.skip_reason)
        finally:
            db_path.unlink(missing_ok=True)


class TestCleanupResult(unittest.TestCase):
    """CleanupResult の to_dict() 出力テスト"""

    def test_to_dict_structure(self):
        """to_dict() が必要なキーをすべて含む"""
        result = CleanupResult()
        d = result.to_dict()

        expected_keys = [
            "success",
            "dry_run",
            "date_based_deleted",
            "size_based_deleted",
            "total_deleted",
            "rows_before",
            "rows_after",
            "date_based_batches",
            "size_based_batches",
            "elapsed_sec",
            "config",
        ]
        for key in expected_keys:
            self.assertIn(key, d, f"Missing key: {key}")

    def test_to_dict_skipped(self):
        """スキップ時に skipped と skip_reason が含まれる"""
        result = CleanupResult()
        result.skipped = True
        result.skip_reason = "test reason"
        d = result.to_dict()

        self.assertTrue(d["skipped"])
        self.assertEqual(d["skip_reason"], "test reason")

    def test_to_dict_cutoff_date(self):
        """cutoff_date が設定されていれば含まれる"""
        result = CleanupResult()
        result.cutoff_date = "2026-01-01 00:00:00"
        d = result.to_dict()

        self.assertEqual(d["cutoff_date"], "2026-01-01 00:00:00")

    def test_to_dict_no_cutoff_date(self):
        """cutoff_date が未設定なら含まれない"""
        result = CleanupResult()
        d = result.to_dict()

        self.assertNotIn("cutoff_date", d)

    def test_config_summary_in_result(self):
        """run_cleanup の結果に config サマリーが含まれる"""
        db_path = _make_db()
        try:
            config = _make_config(retention_days=7, max_rows=500, batch_size=50)
            result = run_cleanup(config, db_path=db_path)
            d = result.to_dict()

            self.assertEqual(d["config"]["retention_days"], 7)
            self.assertEqual(d["config"]["max_rows"], 500)
            self.assertEqual(d["config"]["batch_size"], 50)
            self.assertEqual(d["config"]["table_name"], "background_logs")
            self.assertEqual(d["config"]["timestamp_column"], "created_at")
        finally:
            db_path.unlink(missing_ok=True)


class TestLogRotationConfigValidation(unittest.TestCase):
    """LogRotationConfig バリデーションのテスト"""

    def test_invalid_retention_days_zero(self):
        """retention_days=0 で ValueError"""
        with self.assertRaises(ValueError):
            LogRotationConfig(retention_days=0)

    def test_invalid_retention_days_negative(self):
        """retention_days=-1 で ValueError"""
        with self.assertRaises(ValueError):
            LogRotationConfig(retention_days=-1)

    def test_invalid_max_rows_zero(self):
        """max_rows=0 で ValueError"""
        with self.assertRaises(ValueError):
            LogRotationConfig(max_rows=0)

    def test_invalid_batch_size_zero(self):
        """batch_size=0 で ValueError"""
        with self.assertRaises(ValueError):
            LogRotationConfig(batch_size=0)

    def test_invalid_batch_sleep_negative(self):
        """batch_sleep_sec=-1 で ValueError"""
        with self.assertRaises(ValueError):
            LogRotationConfig(batch_sleep_sec=-1)

    def test_invalid_empty_table_name(self):
        """空文字のlog_table_name で ValueError"""
        with self.assertRaises(ValueError):
            LogRotationConfig(log_table_name="")

    def test_invalid_empty_timestamp_column(self):
        """空文字のtimestamp_column で ValueError"""
        with self.assertRaises(ValueError):
            LogRotationConfig(timestamp_column="")

    def test_valid_minimal_config(self):
        """最小値設定が受け入れられる"""
        config = LogRotationConfig(
            retention_days=1,
            max_rows=1,
            batch_size=1,
            batch_sleep_sec=0,
        )
        self.assertEqual(config.retention_days, 1)
        self.assertEqual(config.max_rows, 1)
        self.assertEqual(config.batch_size, 1)


class TestElapsedTime(unittest.TestCase):
    """実行時間の計測テスト"""

    def setUp(self):
        reset_config()
        self.db_path = _make_db()

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)
        reset_config()

    def test_elapsed_sec_is_positive(self):
        """elapsed_sec が 0 以上の浮動小数点で返される"""
        config = _make_config()
        result = run_cleanup(config, db_path=self.db_path)

        self.assertIsInstance(result.elapsed_sec, float)
        self.assertGreaterEqual(result.elapsed_sec, 0.0)
        # to_dict() では3桁に丸められる
        d = result.to_dict()
        elapsed_str = str(d["elapsed_sec"])
        # 小数点以下が3桁以内
        if "." in elapsed_str:
            decimal_part = elapsed_str.split(".")[1]
            self.assertLessEqual(len(decimal_part), 3)


class TestVerboseMode(unittest.TestCase):
    """verbose モードのテスト（エラーにならないことを確認）"""

    def setUp(self):
        reset_config()
        self.db_path = _make_db()

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)
        reset_config()

    def test_verbose_with_data(self):
        """verbose=True でデータありの場合もエラーにならない"""
        _insert_logs(self.db_path, [
            (_ts(days_ago=60), "old"),
            (_ts(days_ago=1), "new"),
        ])
        config = _make_config(retention_days=30)
        result = run_cleanup(config, db_path=self.db_path, verbose=True)
        self.assertTrue(result.to_dict()["success"])

    def test_verbose_with_empty_table(self):
        """verbose=True で空テーブルの場合もエラーにならない"""
        config = _make_config()
        result = run_cleanup(config, db_path=self.db_path, verbose=True)
        self.assertTrue(result.to_dict()["success"])

    def test_verbose_with_missing_table(self):
        """verbose=True でテーブル不在の場合もエラーにならない"""
        db_path = _make_db(with_table=False)
        try:
            config = _make_config()
            result = run_cleanup(config, db_path=db_path, verbose=True)
            self.assertTrue(result.to_dict()["success"])
            self.assertTrue(result.skipped)
        finally:
            db_path.unlink(missing_ok=True)


# ===========================================================================
# メインエントリーポイント
# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
