"""
AI PM Framework - ログローテーション設定

バックグラウンドログのローテーション（クリーンアップ）に関する設定値を管理する。
既存の db_config.py と同様にデフォルト値を持ちつつ、環境変数で上書き可能。
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class LogRotationConfig:
    """ログローテーション設定を保持するクラス"""

    # 保持日数: この日数より古いログエントリを削除する
    # 環境変数: AIPM_LOG_RETENTION_DAYS
    retention_days: int = 30

    # 最大行数: テーブル内のログ行数がこれを超えたら古い行を削除する
    # 環境変数: AIPM_LOG_MAX_ROWS
    max_rows: int = 10000

    # バッチサイズ: 1回の削除処理で削除する最大行数（DBロック最小化のため）
    # 環境変数: AIPM_LOG_BATCH_SIZE
    batch_size: int = 500

    # バッチ間のスリープ時間（秒）: DBロックの競合を避けるための待機時間
    # 環境変数: AIPM_LOG_BATCH_SLEEP_SEC
    batch_sleep_sec: float = 0.1

    # クリーンアップ対象テーブル名
    # 環境変数: AIPM_LOG_TABLE_NAME
    log_table_name: str = "background_logs"

    # 日付カラム名（削除対象の日付を判定するカラム）
    # 環境変数: AIPM_LOG_TIMESTAMP_COLUMN
    timestamp_column: str = "created_at"

    # ドライラン: Trueの場合、削除件数を計算するが実際には削除しない
    # 環境変数: AIPM_LOG_DRY_RUN
    dry_run: bool = False

    def __post_init__(self):
        """設定値のバリデーション"""
        if self.retention_days < 1:
            raise ValueError("retention_days must be >= 1")

        if self.max_rows < 1:
            raise ValueError("max_rows must be >= 1")

        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")

        if self.batch_sleep_sec < 0:
            raise ValueError("batch_sleep_sec must be >= 0")

        if not self.log_table_name:
            raise ValueError("log_table_name must not be empty")

        if not self.timestamp_column:
            raise ValueError("timestamp_column must not be empty")


# グローバルデフォルト設定インスタンス
_default_config: Optional[LogRotationConfig] = None


def get_log_rotation_config() -> LogRotationConfig:
    """
    ログローテーション設定を取得する

    Returns:
        LogRotationConfig: 設定インスタンス（環境変数が適用済み）
    """
    global _default_config

    if _default_config is None:
        _default_config = load_config_from_env()

    return _default_config


def set_log_rotation_config(config: LogRotationConfig) -> None:
    """
    ログローテーション設定を上書きする（主にテスト用）

    Args:
        config: 設定インスタンス
    """
    global _default_config
    _default_config = config


def load_config_from_env() -> LogRotationConfig:
    """
    環境変数からログローテーション設定を読み込む

    対応環境変数:
        AIPM_LOG_RETENTION_DAYS   : 保持日数（整数）
        AIPM_LOG_MAX_ROWS         : 最大行数（整数）
        AIPM_LOG_BATCH_SIZE       : バッチサイズ（整数）
        AIPM_LOG_BATCH_SLEEP_SEC  : バッチ間スリープ秒数（浮動小数点）
        AIPM_LOG_TABLE_NAME       : 対象テーブル名（文字列）
        AIPM_LOG_TIMESTAMP_COLUMN : タイムスタンプカラム名（文字列）
        AIPM_LOG_DRY_RUN          : ドライランフラグ（"true"/"false"）

    Returns:
        LogRotationConfig: 環境変数を反映した設定インスタンス
    """
    config = LogRotationConfig()

    if os.getenv("AIPM_LOG_RETENTION_DAYS"):
        config.retention_days = int(os.environ["AIPM_LOG_RETENTION_DAYS"])

    if os.getenv("AIPM_LOG_MAX_ROWS"):
        config.max_rows = int(os.environ["AIPM_LOG_MAX_ROWS"])

    if os.getenv("AIPM_LOG_BATCH_SIZE"):
        config.batch_size = int(os.environ["AIPM_LOG_BATCH_SIZE"])

    if os.getenv("AIPM_LOG_BATCH_SLEEP_SEC"):
        config.batch_sleep_sec = float(os.environ["AIPM_LOG_BATCH_SLEEP_SEC"])

    if os.getenv("AIPM_LOG_TABLE_NAME"):
        config.log_table_name = os.environ["AIPM_LOG_TABLE_NAME"]

    if os.getenv("AIPM_LOG_TIMESTAMP_COLUMN"):
        config.timestamp_column = os.environ["AIPM_LOG_TIMESTAMP_COLUMN"]

    if os.getenv("AIPM_LOG_DRY_RUN"):
        config.dry_run = os.environ["AIPM_LOG_DRY_RUN"].lower() == "true"

    return config


def reset_config() -> None:
    """
    グローバル設定をリセットする（主にテスト用）

    次回 get_log_rotation_config() 呼び出し時に環境変数から再読み込みされる。
    """
    global _default_config
    _default_config = None
