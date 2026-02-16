#!/usr/bin/env python3
"""
AI PM Framework - Fault Detection Core Module

Detects four types of faults:
1. Stuck tasks (IN_PROGRESS > 10 minutes)
2. Invalid status transitions
3. Subagent crashes/exceptions
4. File write failures

Usage:
    from fault_detection import FaultDetector, detect_all_faults

    # Detect all faults
    faults = detect_all_faults()
    for fault in faults:
        print(f"{fault.fault_type}: {fault.description}")

    # Or use individual detectors
    detector = FaultDetector()
    stuck_tasks = detector.detect_stuck_tasks()
    invalid_transitions = detector.detect_invalid_transitions()
"""

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional

# Path setup
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, fetch_all, row_to_dict, rows_to_dicts

logger = logging.getLogger(__name__)


class FaultType(Enum):
    """障害タイプ"""
    STUCK_TASK = "STUCK_TASK"  # タスクスタック
    INVALID_TRANSITION = "INVALID_TRANSITION"  # 無効な状態遷移
    SUBAGENT_CRASH = "SUBAGENT_CRASH"  # サブエージェントクラッシュ
    FILE_WRITE_FAILURE = "FILE_WRITE_FAILURE"  # ファイル書き込み失敗


@dataclass
class FaultReport:
    """障害レポート"""
    fault_type: FaultType
    severity: str  # HIGH, MEDIUM, LOW
    project_id: Optional[str]
    order_id: Optional[str]
    task_id: Optional[str]
    description: str
    root_cause: Optional[str] = None
    affected_records: Optional[str] = None
    detected_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "fault_type": self.fault_type.value,
            "severity": self.severity,
            "project_id": self.project_id,
            "order_id": self.order_id,
            "task_id": self.task_id,
            "description": self.description,
            "root_cause": self.root_cause,
            "affected_records": self.affected_records,
            "detected_at": self.detected_at.isoformat(),
            "metadata": self.metadata,
        }


class FaultDetector:
    """障害検出器"""

    def __init__(
        self,
        stuck_threshold_minutes: int = 10,
        check_subagent_logs: bool = True,
        check_file_writes: bool = True,
        verbose: bool = False
    ):
        """
        Args:
            stuck_threshold_minutes: スタック判定時間（分）
            check_subagent_logs: サブエージェントログをチェックするか
            check_file_writes: ファイル書き込みをチェックするか
            verbose: 詳細ログ出力
        """
        self.stuck_threshold_minutes = stuck_threshold_minutes
        self.check_subagent_logs = check_subagent_logs
        self.check_file_writes = check_file_writes
        self.verbose = verbose

        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)

    def detect_all(self) -> List[FaultReport]:
        """
        全種類の障害を検出

        Returns:
            検出された障害のリスト
        """
        faults: List[FaultReport] = []

        # 1. スタックタスク検出
        try:
            stuck_faults = self.detect_stuck_tasks()
            faults.extend(stuck_faults)
            logger.debug(f"スタックタスク検出: {len(stuck_faults)}件")
        except Exception as e:
            logger.warning(f"スタックタスク検出エラー: {e}")

        # 2. 無効な状態遷移検出
        try:
            transition_faults = self.detect_invalid_transitions()
            faults.extend(transition_faults)
            logger.debug(f"無効遷移検出: {len(transition_faults)}件")
        except Exception as e:
            logger.warning(f"無効遷移検出エラー: {e}")

        # 3. サブエージェントクラッシュ検出
        if self.check_subagent_logs:
            try:
                crash_faults = self.detect_subagent_crashes()
                faults.extend(crash_faults)
                logger.debug(f"サブエージェントクラッシュ検出: {len(crash_faults)}件")
            except Exception as e:
                logger.warning(f"サブエージェントクラッシュ検出エラー: {e}")

        # 4. ファイル書き込み失敗検出
        if self.check_file_writes:
            try:
                file_faults = self.detect_file_write_failures()
                faults.extend(file_faults)
                logger.debug(f"ファイル書き込み失敗検出: {len(file_faults)}件")
            except Exception as e:
                logger.warning(f"ファイル書き込み失敗検出エラー: {e}")

        logger.info(f"障害検出完了: 合計{len(faults)}件")
        return faults

    def detect_stuck_tasks(self) -> List[FaultReport]:
        """
        スタックタスク検出（IN_PROGRESS > threshold分）

        Returns:
            検出された障害のリスト
        """
        faults: List[FaultReport] = []
        threshold_time = datetime.now() - timedelta(minutes=self.stuck_threshold_minutes)

        conn = get_connection()
        try:
            # IN_PROGRESSで閾値時間を超えているタスクを検索
            stuck_tasks = fetch_all(
                conn,
                """
                SELECT t.id, t.project_id, t.order_id, t.title, t.status,
                       t.started_at, t.assignee
                FROM tasks t
                WHERE t.status = 'IN_PROGRESS'
                  AND t.started_at IS NOT NULL
                  AND t.started_at < ?
                """,
                (threshold_time.isoformat(),)
            )

            for task_row in stuck_tasks:
                task = row_to_dict(task_row)
                started_at = datetime.fromisoformat(task["started_at"])
                elapsed_minutes = (datetime.now() - started_at).total_seconds() / 60

                fault = FaultReport(
                    fault_type=FaultType.STUCK_TASK,
                    severity="HIGH",
                    project_id=task["project_id"],
                    order_id=task["order_id"],
                    task_id=task["id"],
                    description=f"タスクが{elapsed_minutes:.1f}分間IN_PROGRESSのままスタック",
                    root_cause=f"Worker '{task['assignee']}' がタスク実行中にスタックまたはクラッシュした可能性",
                    affected_records=json.dumps({"task_id": task["id"], "status": "IN_PROGRESS"}),
                    metadata={
                        "elapsed_minutes": elapsed_minutes,
                        "started_at": task["started_at"],
                        "assignee": task["assignee"],
                    }
                )
                faults.append(fault)

        finally:
            conn.close()

        return faults

    def detect_invalid_transitions(self) -> List[FaultReport]:
        """
        無効な状態遷移検出（status_transitionsテーブル参照）

        change_historyから最近の遷移を取得し、
        status_transitionsで許可されていない遷移をチェック

        Returns:
            検出された障害のリスト
        """
        faults: List[FaultReport] = []

        conn = get_connection()
        try:
            # 最近24時間の状態遷移を取得
            recent_changes = fetch_all(
                conn,
                """
                SELECT entity_type, entity_id,
                       field_name, old_value, new_value, changed_at, changed_by
                FROM change_history
                WHERE field_name = 'status'
                  AND changed_at > datetime('now', '-24 hours')
                ORDER BY changed_at DESC
                """
            )

            for change_row in recent_changes:
                change = row_to_dict(change_row)
                entity_type = change["entity_type"]
                old_status = change["old_value"]
                new_status = change["new_value"]

                # status_transitionsテーブルで許可されているか確認
                allowed = fetch_all(
                    conn,
                    """
                    SELECT * FROM status_transitions
                    WHERE entity_type = ?
                      AND (from_status = ? OR from_status IS NULL)
                      AND to_status = ?
                      AND is_active = 1
                    """,
                    (entity_type, old_status, new_status)
                )

                if not allowed:
                    # 無効な遷移を検出
                    fault = FaultReport(
                        fault_type=FaultType.INVALID_TRANSITION,
                        severity="MEDIUM",
                        project_id=None,  # change_historyテーブルにproject_idカラムなし
                        order_id=None,
                        task_id=change["entity_id"] if entity_type == "task" else None,
                        description=f"無効な状態遷移: {entity_type} {old_status} → {new_status}",
                        root_cause=f"status_transitionsテーブルで許可されていない遷移が実行された",
                        affected_records=json.dumps({
                            "entity_type": entity_type,
                            "entity_id": change["entity_id"],
                            "from_status": old_status,
                            "to_status": new_status
                        }),
                        metadata={
                            "entity_type": entity_type,
                            "entity_id": change["entity_id"],
                            "from_status": old_status,
                            "to_status": new_status,
                            "changed_by": change["changed_by"],
                            "changed_at": change["changed_at"],
                        }
                    )
                    faults.append(fault)

        finally:
            conn.close()

        return faults

    def detect_subagent_crashes(self) -> List[FaultReport]:
        """
        サブエージェントクラッシュ検出

        ログファイルから例外・クラッシュを検出
        - Python tracebacks
        - Error messages
        - Unexpected terminations

        Returns:
            検出された障害のリスト
        """
        faults: List[FaultReport] = []

        # ログディレクトリ検索
        log_patterns = [
            _project_root / "logs" / "**" / "*.log",
            _project_root / "PROJECTS" / "**" / "RESULT" / "**" / "*.log",
            _project_root / "PROJECTS" / "**" / "RESULT" / "**" / "worker_output.txt",
        ]

        # 検出パターン（正規表現）
        error_patterns = [
            (r"Traceback \(most recent call last\):", "Python traceback detected"),
            (r"Error:|ERROR:|Exception:", "Error message detected"),
            (r"Fatal|FATAL|Crash|CRASH", "Fatal error or crash detected"),
            (r"exit code [1-9]\d*", "Non-zero exit code detected"),
            (r"subprocess.*failed", "Subprocess failure detected"),
        ]

        # 最近24時間以内のログをチェック
        threshold_time = datetime.now() - timedelta(hours=24)

        for pattern in log_patterns:
            for log_file in _project_root.glob(str(pattern.relative_to(_project_root))):
                if not log_file.is_file():
                    continue

                # 最終更新時刻チェック
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < threshold_time:
                    continue

                # ログファイルからプロジェクト・ORDER・タスク情報を抽出
                project_id = None
                order_id = None
                task_id = None

                parts = log_file.parts
                if "PROJECTS" in parts:
                    idx = parts.index("PROJECTS")
                    if idx + 1 < len(parts):
                        project_id = parts[idx + 1]
                    if idx + 3 < len(parts) and parts[idx + 2] == "RESULT":
                        order_id = parts[idx + 3]

                # ログ内容をチェック
                try:
                    content = log_file.read_text(encoding="utf-8", errors="ignore")

                    # タスクIDをログから抽出（TASK_XXX形式）
                    task_match = re.search(r"TASK_\d+", content)
                    if task_match and not task_id:
                        task_id = task_match.group(0)

                    # エラーパターンをチェック
                    for pattern, description in error_patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            # エラー行を抽出（最大5行）
                            error_lines = []
                            for line in content.split("\n"):
                                if re.search(pattern, line, re.IGNORECASE):
                                    error_lines.append(line.strip())
                                    if len(error_lines) >= 5:
                                        break

                            fault = FaultReport(
                                fault_type=FaultType.SUBAGENT_CRASH,
                                severity="HIGH",
                                project_id=project_id,
                                order_id=order_id,
                                task_id=task_id,
                                description=f"サブエージェントクラッシュ検出: {description}",
                                root_cause=f"ログファイル {log_file.name} でエラーパターン検出",
                                affected_records=json.dumps({
                                    "log_file": str(log_file.relative_to(_project_root)),
                                    "error_pattern": pattern
                                }),
                                metadata={
                                    "log_file": str(log_file),
                                    "error_pattern": pattern,
                                    "error_lines": error_lines[:3],  # 最初の3行のみ
                                }
                            )
                            faults.append(fault)
                            break  # 1ファイルにつき1件の障害のみ記録

                except Exception as e:
                    logger.warning(f"ログファイル読み込みエラー {log_file}: {e}")
                    continue

        return faults

    def detect_file_write_failures(self) -> List[FaultReport]:
        """
        ファイル書き込み失敗検出

        RESULTディレクトリ内の不完全なファイルや
        書き込み失敗の痕跡を検出

        Returns:
            検出された障害のリスト
        """
        faults: List[FaultReport] = []

        # 検出パターン
        # 1. 空のREPORTファイル
        # 2. .tmpファイルの残存
        # 3. 不完全なJSONファイル

        projects_dir = _project_root / "PROJECTS"
        if not projects_dir.exists():
            return faults

        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            project_id = project_dir.name
            result_dir = project_dir / "RESULT"

            if not result_dir.exists():
                continue

            for order_dir in result_dir.iterdir():
                if not order_dir.is_dir():
                    continue

                order_id = order_dir.name

                # 1. 空のREPORTファイル検出
                report_files = list(order_dir.glob("**/REPORT_*.md"))
                for report_file in report_files:
                    if report_file.stat().st_size == 0:
                        # タスクIDを抽出
                        task_match = re.search(r"REPORT_(TASK_\d+)", report_file.name)
                        task_id = task_match.group(1) if task_match else None

                        fault = FaultReport(
                            fault_type=FaultType.FILE_WRITE_FAILURE,
                            severity="MEDIUM",
                            project_id=project_id,
                            order_id=order_id,
                            task_id=task_id,
                            description=f"空のREPORTファイル検出: {report_file.name}",
                            root_cause="ファイル書き込み中に処理が中断された可能性",
                            affected_records=json.dumps({
                                "file_path": str(report_file.relative_to(_project_root)),
                                "file_size": 0
                            }),
                            metadata={
                                "file_path": str(report_file),
                                "file_size": 0,
                            }
                        )
                        faults.append(fault)

                # 2. .tmpファイルの残存検出
                tmp_files = list(order_dir.glob("**/*.tmp"))
                for tmp_file in tmp_files:
                    # 最終更新から1時間以上経過している場合のみ
                    mtime = datetime.fromtimestamp(tmp_file.stat().st_mtime)
                    if datetime.now() - mtime > timedelta(hours=1):
                        fault = FaultReport(
                            fault_type=FaultType.FILE_WRITE_FAILURE,
                            severity="LOW",
                            project_id=project_id,
                            order_id=order_id,
                            task_id=None,
                            description=f"一時ファイルの残存検出: {tmp_file.name}",
                            root_cause="ファイル書き込み処理が正常終了しなかった可能性",
                            affected_records=json.dumps({
                                "file_path": str(tmp_file.relative_to(_project_root)),
                            }),
                            metadata={
                                "file_path": str(tmp_file),
                                "mtime": mtime.isoformat(),
                            }
                        )
                        faults.append(fault)

                # 3. 不完全なJSONファイル検出
                json_files = list(order_dir.glob("**/*.json"))
                for json_file in json_files:
                    # TypeScript設定ファイルなどを除外（コメント・trailing comma許可）
                    if json_file.name in ("tsconfig.json", "jsconfig.json", ".eslintrc.json"):
                        continue

                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            json.load(f)
                    except json.JSONDecodeError as e:
                        fault = FaultReport(
                            fault_type=FaultType.FILE_WRITE_FAILURE,
                            severity="MEDIUM",
                            project_id=project_id,
                            order_id=order_id,
                            task_id=None,
                            description=f"不正なJSONファイル検出: {json_file.name}",
                            root_cause=f"JSONパースエラー: {str(e)}",
                            affected_records=json.dumps({
                                "file_path": str(json_file.relative_to(_project_root)),
                                "error": str(e)
                            }),
                            metadata={
                                "file_path": str(json_file),
                                "error": str(e),
                            }
                        )
                        faults.append(fault)

        return faults


# Convenience functions

def detect_all_faults(
    stuck_threshold_minutes: int = 10,
    verbose: bool = False
) -> List[FaultReport]:
    """
    全種類の障害を検出（便利関数）

    Args:
        stuck_threshold_minutes: スタック判定時間（分）
        verbose: 詳細ログ出力

    Returns:
        検出された障害のリスト
    """
    detector = FaultDetector(
        stuck_threshold_minutes=stuck_threshold_minutes,
        verbose=verbose
    )
    return detector.detect_all()


def detect_stuck_tasks(
    stuck_threshold_minutes: int = 10,
    verbose: bool = False
) -> List[FaultReport]:
    """スタックタスク検出（便利関数）"""
    detector = FaultDetector(stuck_threshold_minutes=stuck_threshold_minutes, verbose=verbose)
    return detector.detect_stuck_tasks()


def detect_invalid_transitions(verbose: bool = False) -> List[FaultReport]:
    """無効な状態遷移検出（便利関数）"""
    detector = FaultDetector(verbose=verbose)
    return detector.detect_invalid_transitions()


def detect_subagent_crashes(verbose: bool = False) -> List[FaultReport]:
    """サブエージェントクラッシュ検出（便利関数）"""
    detector = FaultDetector(verbose=verbose)
    return detector.detect_subagent_crashes()


def detect_file_write_failures(verbose: bool = False) -> List[FaultReport]:
    """ファイル書き込み失敗検出（便利関数）"""
    detector = FaultDetector(verbose=verbose)
    return detector.detect_file_write_failures()


def main():
    """CLI エントリーポイント"""
    import argparse

    parser = argparse.ArgumentParser(description="障害検出ツール")
    parser.add_argument("--type", choices=["all", "stuck", "transition", "crash", "file"],
                        default="all", help="検出タイプ")
    parser.add_argument("--threshold", type=int, default=10,
                        help="スタック判定時間（分）")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    # ロギング設定
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 障害検出
    detector = FaultDetector(
        stuck_threshold_minutes=args.threshold,
        verbose=args.verbose
    )

    if args.type == "all":
        faults = detector.detect_all()
    elif args.type == "stuck":
        faults = detector.detect_stuck_tasks()
    elif args.type == "transition":
        faults = detector.detect_invalid_transitions()
    elif args.type == "crash":
        faults = detector.detect_subagent_crashes()
    elif args.type == "file":
        faults = detector.detect_file_write_failures()
    else:
        faults = []

    # 出力
    if args.json:
        output = [fault.to_dict() for fault in faults]
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if not faults:
            print("✓ 障害は検出されませんでした")
        else:
            print(f"⚠ {len(faults)}件の障害を検出しました:\n")
            for i, fault in enumerate(faults, 1):
                print(f"{i}. [{fault.severity}] {fault.fault_type.value}")
                print(f"   {fault.description}")
                if fault.task_id:
                    print(f"   タスク: {fault.task_id}")
                if fault.root_cause:
                    print(f"   原因: {fault.root_cause}")
                print()

    sys.exit(0 if not faults else 1)


if __name__ == "__main__":
    main()
