#!/usr/bin/env python3
"""
AI PM Framework - Periodic Fault Checker

Provides periodic background fault detection that can be integrated into process_order.py

Usage:
    from fault_detection.periodic_checker import PeriodicFaultChecker

    # Create and start checker
    checker = PeriodicFaultChecker(
        check_interval_seconds=60,
        stuck_threshold_minutes=10,
        auto_recovery=True
    )
    checker.start()

    # ... do other work ...

    # Stop checker when done
    checker.stop()
"""

import logging
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Callable, List

# Path setup
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
sys.path.insert(0, str(_package_root))

from fault_detection import detect_all_faults, FaultReport, FaultType

logger = logging.getLogger(__name__)


class PeriodicFaultChecker:
    """定期的な障害チェッカー"""

    def __init__(
        self,
        check_interval_seconds: int = 60,
        stuck_threshold_minutes: int = 10,
        auto_recovery: bool = True,
        on_fault_detected: Optional[Callable[[FaultReport], None]] = None,
        verbose: bool = False
    ):
        """
        Args:
            check_interval_seconds: チェック間隔（秒）
            stuck_threshold_minutes: スタック判定時間（分）
            auto_recovery: 自動リカバリを実行するか
            on_fault_detected: 障害検出時のコールバック関数
            verbose: 詳細ログ出力
        """
        self.check_interval_seconds = check_interval_seconds
        self.stuck_threshold_minutes = stuck_threshold_minutes
        self.auto_recovery = auto_recovery
        self.on_fault_detected = on_fault_detected
        self.verbose = verbose

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._detected_faults: List[FaultReport] = []

        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)

    def start(self) -> None:
        """バックグラウンドチェックを開始"""
        if self._running:
            logger.warning("Periodic fault checker is already running")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._check_loop,
            daemon=True,
            name="FaultCheckerThread"
        )
        self._thread.start()
        logger.info(f"Periodic fault checker started (interval={self.check_interval_seconds}s)")

    def stop(self) -> None:
        """バックグラウンドチェックを停止"""
        if not self._running:
            return

        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Periodic fault checker stopped")

    def is_running(self) -> bool:
        """実行中かどうか"""
        return self._running

    def get_detected_faults(self) -> List[FaultReport]:
        """検出された障害のリストを取得"""
        return self._detected_faults.copy()

    def _check_loop(self) -> None:
        """チェックループ（バックグラウンドスレッド）"""
        logger.debug("Fault checker thread started")

        while self._running:
            try:
                self._perform_check()
            except Exception as e:
                logger.error(f"Fault check error: {e}")
                if self.verbose:
                    logger.exception("Detailed error")

            # 次のチェックまで待機
            time.sleep(self.check_interval_seconds)

        logger.debug("Fault checker thread stopped")

    def _perform_check(self) -> None:
        """障害チェックを実行"""
        logger.debug("Performing periodic fault check...")

        # 全種類の障害を検出
        faults = detect_all_faults(
            stuck_threshold_minutes=self.stuck_threshold_minutes,
            verbose=self.verbose
        )

        if not faults:
            logger.debug("No faults detected")
            return

        logger.warning(f"Detected {len(faults)} faults")

        for fault in faults:
            # 既に検出済みの障害は無視（重複回避）
            if self._is_duplicate_fault(fault):
                logger.debug(f"Skipping duplicate fault: {fault.task_id} - {fault.fault_type.value}")
                continue

            # 障害リストに追加
            self._detected_faults.append(fault)

            # ログ出力
            logger.warning(
                f"Fault detected: {fault.fault_type.value} "
                f"[{fault.severity}] - {fault.description}"
            )

            # INCIDENTSテーブルに記録
            self._log_to_incidents(fault)

            # コールバック実行
            if self.on_fault_detected:
                try:
                    self.on_fault_detected(fault)
                except Exception as e:
                    logger.error(f"Fault callback error: {e}")

            # 自動リカバリ
            if self.auto_recovery and fault.severity == "HIGH":
                self._trigger_auto_recovery(fault)

    def _is_duplicate_fault(self, fault: FaultReport) -> bool:
        """重複障害かどうか判定"""
        # 同じタスク・同じ障害タイプの組み合わせが既に存在するか
        for existing in self._detected_faults:
            if (existing.task_id == fault.task_id and
                existing.fault_type == fault.fault_type):
                return True
        return False

    def _log_to_incidents(self, fault: FaultReport) -> None:
        """INCIDENTSテーブルに記録"""
        try:
            from utils.incident_logger import log_incident

            # FaultType → INCIDENTS.category マッピング
            category_map = {
                FaultType.STUCK_TASK: "WORKER_FAILURE",
                FaultType.INVALID_TRANSITION: "DATA_INTEGRITY",
                FaultType.SUBAGENT_CRASH: "WORKER_FAILURE",
                FaultType.FILE_WRITE_FAILURE: "SYSTEM_ERROR",
            }

            category = category_map.get(fault.fault_type, "OTHER")

            log_incident(
                category=category,
                description=fault.description,
                severity=fault.severity,
                project_id=fault.project_id,
                order_id=fault.order_id,
                task_id=fault.task_id,
                root_cause=fault.root_cause,
                affected_records=fault.affected_records
            )

            logger.info(f"Logged fault to INCIDENTS table: {fault.task_id}")

        except Exception as e:
            logger.warning(f"Failed to log incident: {e}")

    def _trigger_auto_recovery(self, fault: FaultReport) -> None:
        """
        自動リカバリをトリガー

        HIGH severity の障害（特に STUCK_TASK）に対して:
        1. チェックポイントからロールバック
        2. INCIDENTSテーブルにロールバック記録
        3. リトライ可否を判定
        4. タスクステータスを更新（REWORK or REJECTED）
        """
        logger.info(
            f"Triggering auto recovery for fault: "
            f"{fault.task_id} - {fault.fault_type.value}"
        )

        if not fault.task_id or not fault.project_id:
            logger.warning("Auto recovery skipped: missing task_id or project_id")
            return

        try:
            from rollback.auto_rollback import rollback_to_checkpoint, RollbackError
            from incidents.create import create_incident
            from retry.retry_handler import RetryHandler

            # Step 1: Rollback to latest checkpoint
            rollback_result = None
            try:
                rollback_result = rollback_to_checkpoint(
                    project_id=fault.project_id,
                    task_id=fault.task_id,
                    verbose=self.verbose
                )
                if rollback_result.success:
                    logger.info(
                        f"Rollback successful for {fault.task_id}: "
                        f"checkpoint={rollback_result.checkpoint_id}"
                    )
                else:
                    logger.warning(
                        f"Rollback returned failure for {fault.task_id}: "
                        f"{rollback_result.error_message}"
                    )
            except RollbackError as e:
                logger.warning(f"Rollback skipped for {fault.task_id}: {e}")
            except Exception as e:
                logger.warning(f"Rollback error for {fault.task_id}: {e}")

            # Step 2: Record rollback in INCIDENTS table
            rollback_desc = (
                f"Auto-rollback executed for {fault.fault_type.value}: "
                f"{fault.description}"
            )
            if rollback_result and rollback_result.success:
                rollback_desc += (
                    f" (checkpoint={rollback_result.checkpoint_id}, "
                    f"db_restored={rollback_result.db_restored})"
                )

            try:
                create_incident(
                    project_id=fault.project_id,
                    task_id=fault.task_id,
                    category="ROLLBACK",
                    description=rollback_desc,
                    root_cause=fault.root_cause,
                    severity=fault.severity,
                    order_id=fault.order_id,
                )
            except Exception as e:
                logger.warning(f"Failed to record rollback incident: {e}")

            # Step 3: Check retry eligibility
            handler = RetryHandler(
                fault.project_id,
                fault.task_id,
                max_retries=2,
                verbose=self.verbose
            )
            retry_result = handler.prepare_retry()

            # Step 4: Update task status based on retry eligibility
            try:
                from task.update import update_task

                if retry_result.should_retry:
                    # Set task to REWORK for retry
                    update_task(
                        fault.project_id,
                        fault.task_id,
                        status="REWORK",
                        role="PM",
                        reason=(
                            f"Auto-recovery: {fault.fault_type.value} detected, "
                            f"retry {retry_result.retry_count + 1}/"
                            f"{retry_result.max_retries}"
                        ),
                    )
                    logger.info(
                        f"Task {fault.task_id} set to REWORK for retry "
                        f"(attempt {retry_result.retry_count + 1}/"
                        f"{retry_result.max_retries})"
                    )

                    # Record retry incident
                    try:
                        create_incident(
                            project_id=fault.project_id,
                            task_id=fault.task_id,
                            category="RETRY",
                            description=(
                                f"Task set to REWORK for retry "
                                f"(attempt {retry_result.retry_count + 1}/"
                                f"{retry_result.max_retries})"
                            ),
                            severity="MEDIUM",
                            order_id=fault.order_id,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record retry incident: {e}")

                else:
                    # Retry limit exceeded - mark as REJECTED
                    update_task(
                        fault.project_id,
                        fault.task_id,
                        status="REJECTED",
                        role="PM",
                        reason=(
                            f"Auto-recovery: retry limit exceeded "
                            f"({retry_result.retry_count}/"
                            f"{retry_result.max_retries}), "
                            f"fault: {fault.fault_type.value}"
                        ),
                    )
                    logger.warning(
                        f"Task {fault.task_id} set to REJECTED "
                        f"(retry limit exceeded: {retry_result.retry_count}/"
                        f"{retry_result.max_retries})"
                    )

                    # Record rejection incident
                    try:
                        create_incident(
                            project_id=fault.project_id,
                            task_id=fault.task_id,
                            category="SYSTEM_ERROR",
                            description=(
                                f"Task REJECTED: retry limit exceeded "
                                f"({retry_result.retry_count}/"
                                f"{retry_result.max_retries}). "
                                f"Original fault: {fault.description}"
                            ),
                            severity="HIGH",
                            order_id=fault.order_id,
                            root_cause=fault.root_cause,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to record rejection incident: {e}"
                        )

            except Exception as e:
                logger.error(
                    f"Failed to update task status for {fault.task_id}: {e}"
                )

            logger.info(f"Auto recovery completed for {fault.task_id}")

        except ImportError as e:
            logger.error(f"Auto recovery module import failed: {e}")
        except Exception as e:
            logger.error(f"Auto recovery failed for {fault.task_id}: {e}")
            if self.verbose:
                logger.exception("Auto recovery detailed error")


def main():
    """CLI エントリーポイント - デモンストレーション"""
    import argparse

    parser = argparse.ArgumentParser(description="Periodic fault checker")
    parser.add_argument("--interval", type=int, default=60,
                        help="Check interval in seconds")
    parser.add_argument("--threshold", type=int, default=10,
                        help="Stuck task threshold in minutes")
    parser.add_argument("--duration", type=int, default=300,
                        help="Run duration in seconds (0 = infinite)")
    parser.add_argument("--no-auto-recovery", action="store_true",
                        help="Disable auto recovery")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")

    args = parser.parse_args()

    # ロギング設定
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # チェッカー起動
    checker = PeriodicFaultChecker(
        check_interval_seconds=args.interval,
        stuck_threshold_minutes=args.threshold,
        auto_recovery=not args.no_auto_recovery,
        verbose=args.verbose
    )

    checker.start()

    try:
        if args.duration > 0:
            logger.info(f"Running for {args.duration} seconds...")
            time.sleep(args.duration)
        else:
            logger.info("Running indefinitely (press Ctrl+C to stop)...")
            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")

    finally:
        checker.stop()

        # 検出された障害をサマリー表示
        faults = checker.get_detected_faults()
        if faults:
            logger.info(f"\n=== Detected Faults Summary ===")
            logger.info(f"Total: {len(faults)} faults")
            for i, fault in enumerate(faults, 1):
                logger.info(f"{i}. [{fault.severity}] {fault.fault_type.value}")
                logger.info(f"   {fault.description}")
                if fault.task_id:
                    logger.info(f"   Task: {fault.task_id}")
        else:
            logger.info("No faults detected during run")


if __name__ == "__main__":
    main()
