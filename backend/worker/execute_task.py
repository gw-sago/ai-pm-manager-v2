#!/usr/bin/env python3
"""
AI PM Framework - Worker処理親スクリプト

タスク読み込み → claude -p でタスク実行 → REPORT作成 → DB更新 → レビューキュー追加
を1コマンドで完結させる。

Usage:
    python backend/worker/execute_task.py PROJECT_NAME TASK_ID [options]

Options:
    --dry-run       実行計画のみ表示（AI呼び出し・DB更新なし）
    --skip-ai       AI処理をスキップ（ステータス更新のみ）
    --verbose       詳細ログ出力
    --json          JSON形式で出力
    --timeout SEC   claude -p タイムアウト秒数（デフォルト: 600）
    --model MODEL   AIモデル（haiku/sonnet/opus、タスク推奨モデルがあればそちらを優先）
    --auto-review   Worker完了後にレビュー処理を自動実行（デフォルト: 有効）
    --no-review     自動レビューを無効化（手動レビューする場合）
    --review-model MODEL  レビュー用AIモデル（デフォルト: sonnet）
    --loop          タスク完了後に次のQUEUEDタスクを自動起動（連続実行モード）
    --max-tasks N   連続実行時の最大タスク数（デフォルト: 100）

Example:
    python backend/worker/execute_task.py AI_PM_PJ TASK_602
    python backend/worker/execute_task.py AI_PM_PJ TASK_602 --dry-run
    python backend/worker/execute_task.py AI_PM_PJ TASK_602 --model opus
    python backend/worker/execute_task.py AI_PM_PJ TASK_602 --auto-review
    python backend/worker/execute_task.py AI_PM_PJ TASK_602 --loop  # 連続実行

内部処理:
1. タスク情報取得（DB + TASKファイル）
2. Worker割当・ステータス更新（IN_PROGRESS）
3. claude -p でタスク実行
4. REPORT作成
5. レビューキュー追加
6. ステータス更新（DONE）
7. レビュー自動実行 → タスクCOMPLETED（--no-reviewで無効化可）
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 内部モジュールインポート
try:
    from utils.db import (
        get_connection, transaction, execute_query, fetch_one, fetch_all,
        row_to_dict, rows_to_dicts, DatabaseError
    )
    from utils.validation import (
        validate_project_name, validate_task_id,
        project_exists, task_exists, ValidationError
    )
    from utils.transition import (
        validate_transition, record_transition, TransitionError
    )
    from utils.path_validation import (
        safe_path_join, validate_path_components, PathValidationError
    )
except ImportError as e:
    logger.error(f"内部モジュールのインポートに失敗: {e}")
    sys.exit(1)

# claude_runner インポート（オプション）
try:
    from claude_runner import create_runner, ClaudeRunner, ClaudeResult
    CLAUDE_RUNNER_AVAILABLE = True
except ImportError:
    CLAUDE_RUNNER_AVAILABLE = False
    logger.warning("claude_runner が利用できません。--skip-ai オプションのみ利用可能です。")

# Auto Recovery Engine (ORDER_109)
try:
    from worker.auto_recovery import AutoRecoveryEngine
    HAS_AUTO_RECOVERY = True
except ImportError:
    HAS_AUTO_RECOVERY = False

# 権限プロファイル自動判定（ORDER_121）
try:
    from worker.permission_resolver import PermissionResolver
    PERMISSION_RESOLVER_AVAILABLE = True
except ImportError:
    PERMISSION_RESOLVER_AVAILABLE = False


class WorkerExecutionError(Exception):
    """Worker実行エラー"""
    pass


# Worker実行時のデフォルト許可ツール
# claude -p の --allowedTools に渡される
DEFAULT_WORKER_ALLOWED_TOOLS = [
    "Read", "Write", "Edit", "Glob", "Grep",
    "Bash", "WebSearch", "WebFetch",
    "TodoWrite", "Task", "NotebookEdit",
]


class WorkerExecutor:
    """Worker処理を実行するクラス"""

    def __init__(
        self,
        project_id: str,
        task_id: str,
        *,
        dry_run: bool = False,
        skip_ai: bool = False,
        verbose: bool = False,
        timeout: int = 1800,
        model: Optional[str] = None,
        auto_review: bool = True,
        review_model: str = "sonnet",
        loop: bool = False,
        max_tasks: int = 100,
        is_rework: bool = False,
        rework_comment: Optional[str] = None,
        allowed_tools: Optional[list] = None,
    ):
        self.project_id = project_id
        # TASK_XXX 形式に正規化
        self.task_id = f"TASK_{task_id}" if not task_id.startswith("TASK_") else task_id
        self.dry_run = dry_run
        self.skip_ai = skip_ai
        self.verbose = verbose
        self.timeout = timeout
        self.model = model
        self.auto_review = auto_review
        self.review_model = review_model
        self.loop = loop
        self.max_tasks = max_tasks
        self.is_rework = is_rework
        self.rework_comment = rework_comment
        # 権限プロファイル自動判定フラグ: allowed_toolsが未指定の場合、
        # _step_get_task_info()完了後にタスク情報からプロファイルを自動判定する
        self._needs_profile_resolution = (allowed_tools is None) and PERMISSION_RESOLVER_AVAILABLE
        self.allowed_tools = allowed_tools if allowed_tools is not None else DEFAULT_WORKER_ALLOWED_TOOLS.copy()
        self._resolved_profile: Optional[str] = None

        # プロジェクトパス
        self.project_dir = _project_root / "PROJECTS" / project_id

        # 処理結果
        self.results: Dict[str, Any] = {
            "task_id": self.task_id,
            "project_id": project_id,
            "steps": [],
            "success": False,
            "error": None,
            "is_rework": is_rework,
        }

        # タスク情報（後で設定）
        self.task_info: Optional[Dict] = None
        self.order_id: Optional[str] = None
        self.worker_id: Optional[str] = None

        # claude_runner インスタンス（後で設定）
        self.runner: Optional[ClaudeRunner] = None

        # チェックポイントID（後で設定）
        self.checkpoint_id: Optional[str] = None

        # ファイルスナップショットID (ORDER_109)
        self.snapshot_id: Optional[str] = None

    def _log_step(self, step: str, status: str, detail: str = "") -> None:
        """ステップログを記録"""
        entry = {
            "step": step,
            "status": status,
            "detail": detail,
            "timestamp": datetime.now().isoformat(),
        }
        self.results["steps"].append(entry)
        if self.verbose:
            logger.info(f"[{step}] {status}: {detail}")

    def execute(self) -> Dict[str, Any]:
        """
        Worker処理を実行

        Returns:
            処理結果の辞書
        """
        try:
            # Step 1: タスク情報取得
            self._step_get_task_info()

            # Step 2: Worker割当・ステータス更新
            self._step_assign_worker()

            if self.dry_run:
                self._log_step("dry_run", "info", "ドライランモード - 以降の処理をスキップ")
                self.results["success"] = True
                return self.results

            # Step 3: タスク実行（AI）
            if not self.skip_ai:
                self._step_execute_task()

            # Step 3.5: 自己検証＋自己修正ループ
            if not self.skip_ai:
                self._step_self_verification()

            # Step 4: REPORT作成
            self._step_create_report()

            # Step 4.5: 静的解析（成果物に対して自動実行）
            if not self.skip_ai:
                self._step_static_analysis()

            # Step 4.6: 破壊的SQL検出（成果物に対して自動実行）
            if not self.skip_ai:
                self._step_destructive_sql_check()

            # Step 5: ステータス更新（DONE）
            self._step_update_status_done()

            # Step 7: 自動レビュー（--auto-review 指定時）
            # NOTE: ORDER_132で無効化 - レビューはreview_workerで別プロセス実行
            # if self.auto_review:
            #     review_result = self._step_auto_review()
            #     self.results["review_result"] = review_result
            #     if review_result.get("success"):
            #         self._log_step("auto_review", "success", f"verdict={review_result.get('verdict')}")
            #
            #         # レビューが承認されてタスクがCOMPLETEDになった場合、後続タスクをチェック
            #         verdict = review_result.get("verdict", "")
            #         if verdict == "APPROVE":
            #             self._step_check_successor_tasks()
            #
            #         # Step 7.5: バグ学習フック
            #         self._step_bug_learning(review_result)
            #     else:
            #         self._log_step("auto_review", "warning", review_result.get("error", "レビュー失敗"))
            if self.auto_review:
                self._log_step("auto_review", "skipped", "レビューはreview_workerで実行されます")

            # Step 8: 次タスク検出（--loop 指定時）
            if self.loop:
                next_task = self._get_next_queued_task()
                if next_task:
                    self.results["next_task"] = next_task
                    self._log_step("next_task", "found", f"next={next_task}")
                else:
                    self.results["next_task"] = None
                    self._log_step("next_task", "none", "QUEUEDタスクなし")

            self.results["success"] = True
            self._log_step("complete", "success", "Worker処理完了")

        except WorkerExecutionError as e:
            self.results["error"] = str(e)
            self._log_step("error", "failed", str(e))
            # 自動ロールバック＋リトライ判定
            self._handle_execution_failure(e)
            # エラー時もファイルロックを解放
            self._release_locks_on_error()
        except Exception as e:
            self.results["error"] = f"予期しないエラー: {e}"
            self._log_step("error", "failed", str(e))
            if self.verbose:
                logger.exception("詳細エラー")
            # 自動ロールバック＋リトライ判定
            self._handle_execution_failure(e)
            # エラー時もファイルロックを解放
            self._release_locks_on_error()

        return self.results

    def _release_locks_on_error(self) -> None:
        """エラー発生時にファイルロックを解放"""
        try:
            from utils.file_lock import FileLockManager
            FileLockManager.release_locks(self.project_id, self.task_id)
            self._log_step("file_lock_release", "success", "エラー時ロック解放")

            # NOTE: エラー時の auto_kick は削除（BACKLOG_167修正）
            # エラー状態のタスクで後続を解除すべきではない。
            # レビュー承認後に正規フローで解除する。

        except ImportError:
            pass
        except Exception as e:
            self._log_step("file_lock_release", "warning", f"エラー時ロック解放失敗: {e}")

    def _handle_execution_failure(self, error: Exception) -> None:
        """
        Handle task execution failure with auto-rollback and retry.

        This method is called when _step_execute_task() raises an exception.
        It performs:
        1. Rollback to checkpoint if available
        2. Record the failure in INCIDENTS table
        3. Check retry eligibility
        4. Update task status (REWORK if retryable, REJECTED if limit exceeded)

        ORDER_109: AutoRecoveryEngine統合
        - HAS_AUTO_RECOVERY=True: AutoRecoveryEngine経由でエラー分析→戦略決定→リカバリ
        - HAS_AUTO_RECOVERY=False: 従来ロジック（フォールバック）

        Args:
            error: The exception that caused the failure
        """
        self._log_step("self_healing", "start", f"Handling execution failure: {error}")

        # --- ORDER_109: AutoRecoveryEngine統合 ---
        if HAS_AUTO_RECOVERY:
            try:
                # db_path: AutoRecoveryEngine側でデフォルト解決するためNone渡し
                recovery_engine = AutoRecoveryEngine(
                    db_path=None,
                    project_id=self.project_id,
                )

                # エラーメッセージとトレースバック取得
                import traceback
                tb_text = traceback.format_exc()
                error_msg = str(error)

                # ワンショットリカバリ実行
                result = recovery_engine.recover(
                    task_id=self.task_id,
                    order_id=self.order_id,
                    error_message=error_msg,
                    traceback_text=tb_text,
                    snapshot_id=self.snapshot_id,
                    checkpoint_id=self.checkpoint_id,
                )

                self.results["auto_recovery_result"] = {
                    "success": result.success,
                    "action_taken": result.action_taken.value,
                    "message": result.message,
                    "next_status": result.next_status,
                    "retry_count": result.retry_count,
                }
                self.results["self_healing_action"] = result.next_status

                self._log_step(
                    "self_healing", "complete",
                    f"AutoRecovery: action={result.action_taken.value}, "
                    f"next_status={result.next_status}, "
                    f"success={result.success}"
                )
                return  # AutoRecoveryEngine処理完了、既存ロジックをスキップ

            except Exception as ar_error:
                self._log_step(
                    "self_healing", "warning",
                    f"AutoRecoveryEngine failed, falling back to legacy: {ar_error}"
                )
                # フォールバック: 以下の既存ロジックを実行

        # --- 既存ロジック（フォールバック） ---
        # Step 1: Attempt rollback if checkpoint exists
        rollback_success = False
        if self.checkpoint_id:
            try:
                from rollback.auto_rollback import rollback_to_checkpoint

                rollback_result = rollback_to_checkpoint(
                    project_id=self.project_id,
                    task_id=self.task_id,
                    checkpoint_id=self.checkpoint_id,
                    verbose=self.verbose,
                )

                if rollback_result.success:
                    rollback_success = True
                    self._log_step(
                        "self_healing_rollback", "success",
                        f"Rolled back to checkpoint={self.checkpoint_id}, "
                        f"db_restored={rollback_result.db_restored}"
                    )
                    self.results["rollback_result"] = rollback_result.to_dict()
                else:
                    self._log_step(
                        "self_healing_rollback", "warning",
                        f"Rollback returned failure: {rollback_result.error_message}"
                    )
            except ImportError:
                self._log_step(
                    "self_healing_rollback", "skip",
                    "rollback module not available"
                )
            except Exception as rb_error:
                self._log_step(
                    "self_healing_rollback", "warning",
                    f"Rollback error: {rb_error}"
                )
        else:
            self._log_step(
                "self_healing_rollback", "skip",
                "No checkpoint_id available for rollback"
            )

        # Step 2: Record the failure in INCIDENTS table
        incident_id = None
        try:
            from incidents.create import create_incident

            incident_id = create_incident(
                project_id=self.project_id,
                task_id=self.task_id,
                category="WORKER_FAILURE",
                description=f"Task execution failed: {error}",
                root_cause=str(type(error).__name__),
                severity="HIGH",
                order_id=self.order_id,
            )
            self._log_step(
                "self_healing_incident", "success",
                f"Incident recorded: {incident_id}"
            )
            self.results["failure_incident_id"] = incident_id
        except ImportError:
            self._log_step(
                "self_healing_incident", "skip",
                "incidents module not available"
            )
        except Exception as inc_error:
            self._log_step(
                "self_healing_incident", "warning",
                f"Failed to record incident: {inc_error}"
            )

        # Step 3: Check retry eligibility
        try:
            from retry.retry_handler import RetryHandler

            handler = RetryHandler(
                self.project_id,
                self.task_id,
                max_retries=2,
                verbose=self.verbose,
            )
            retry_result = handler.prepare_retry()
            self.results["retry_result"] = retry_result.to_dict()

            # Step 4: Update task status
            try:
                from task.update import update_task

                if retry_result.should_retry:
                    # Set to REWORK for retry
                    update_task(
                        self.project_id,
                        self.task_id,
                        status="REWORK",
                        role="PM",
                        reason=(
                            f"Auto-recovery: execution failed ({error}), "
                            f"retry {retry_result.retry_count + 1}/"
                            f"{retry_result.max_retries}"
                        ),
                    )
                    self._log_step(
                        "self_healing_status", "success",
                        f"Task set to REWORK for retry "
                        f"(attempt {retry_result.retry_count + 1}/"
                        f"{retry_result.max_retries})"
                    )
                    self.results["self_healing_action"] = "REWORK"
                else:
                    # Retry limit exceeded - mark as REJECTED
                    update_task(
                        self.project_id,
                        self.task_id,
                        status="REJECTED",
                        role="PM",
                        reason=(
                            f"Auto-recovery: retry limit exceeded "
                            f"({retry_result.retry_count}/"
                            f"{retry_result.max_retries}), "
                            f"error: {error}"
                        ),
                    )
                    self._log_step(
                        "self_healing_status", "warning",
                        f"Task set to REJECTED (retry limit exceeded: "
                        f"{retry_result.retry_count}/{retry_result.max_retries})"
                    )
                    self.results["self_healing_action"] = "REJECTED"

            except Exception as status_error:
                self._log_step(
                    "self_healing_status", "warning",
                    f"Failed to update task status: {status_error}"
                )

        except ImportError:
            self._log_step(
                "self_healing_retry", "skip",
                "retry module not available"
            )
        except Exception as retry_error:
            self._log_step(
                "self_healing_retry", "warning",
                f"Retry evaluation error: {retry_error}"
            )

        self._log_step(
            "self_healing", "complete",
            f"rollback={'OK' if rollback_success else 'SKIP'}, "
            f"action={self.results.get('self_healing_action', 'UNKNOWN')}"
        )

    def _step_get_task_info(self) -> None:
        """Step 1: タスク情報を取得"""
        self._log_step("get_task_info", "start", self.task_id)

        conn = get_connection()
        try:
            # プロジェクト存在確認
            if not project_exists(conn, self.project_id):
                raise WorkerExecutionError(f"プロジェクトが見つかりません: {self.project_id}")

            # タスク存在確認
            if not task_exists(conn, self.task_id, self.project_id):
                raise WorkerExecutionError(f"タスクが見つかりません: {self.task_id}")

            # タスク情報取得
            task = fetch_one(
                conn,
                """
                SELECT t.*, o.title as order_title
                FROM tasks t
                LEFT JOIN orders o ON t.order_id = o.id AND t.project_id = o.project_id
                WHERE t.id = ? AND t.project_id = ?
                """,
                (self.task_id, self.project_id)
            )

            self.task_info = row_to_dict(task)
            self.order_id = self.task_info.get("order_id")
            self.results["task_info"] = self.task_info

            # 推奨モデル設定（REWORK回数に応じた自動昇格を含む）
            recommended = self.task_info.get("recommended_model", "").lower()
            reject_count = self.task_info.get("reject_count", 0)

            # REWORK 2回目以降の場合、モデルを自動昇格
            if reject_count >= 2:
                # Sonnet → Opus に自動昇格
                if recommended in ("haiku", "sonnet"):
                    original_model = recommended
                    recommended = "opus"
                    self._log_step(
                        "model_upgrade",
                        "info",
                        f"REWORK {reject_count}回目: モデル自動昇格 {original_model} → opus"
                    )

                    # エスカレーションログ記録
                    try:
                        from escalation.log_escalation import log_escalation, EscalationType
                        log_escalation(
                            project_id=self.project_id,
                            task_id=self.task_id,
                            escalation_type=EscalationType.MODEL_UPGRADE,
                            description=f"REWORK {reject_count}回目: モデル自動昇格を実施",
                            order_id=self.order_id,
                            metadata={
                                "from_model": original_model,
                                "to_model": "opus",
                                "rework_count": reject_count,
                            }
                        )
                    except Exception as e:
                        logger.warning(f"エスカレーションログ記録失敗: {e}")

            if not self.model and recommended in ("haiku", "sonnet", "opus"):
                self.model = recommended
            elif not self.model:
                self.model = "sonnet"

            self._log_step("get_task_info", "success", f"order={self.order_id}, model={self.model}, reject_count={reject_count}")

        finally:
            conn.close()

        # 権限プロファイル自動判定（allowed_toolsが未指定の場合のみ）
        if self._needs_profile_resolution and self.task_info:
            try:
                resolver = PermissionResolver()
                self._resolved_profile = resolver.resolve(self.task_info)
                resolved_tools = resolver.resolve_tools(self.task_info)
                self.allowed_tools = resolved_tools
                self._log_step(
                    "permission_profile", "success",
                    f"profile={self._resolved_profile}, tools={len(resolved_tools)}個: {resolved_tools}"
                )
            except Exception as e:
                # プロファイル解決失敗時はデフォルトのallowed_toolsを維持
                self._log_step(
                    "permission_profile", "warning",
                    f"プロファイル判定失敗、デフォルト権限を使用: {e}"
                )

    def _step_assign_worker(self) -> None:
        """Step 2: Worker割当・ステータス更新"""
        mode_label = "リワーク" if self.is_rework else "通常"
        self._log_step("assign_worker", "start", f"mode={mode_label}")

        # Worker識別子を取得
        try:
            from worker.assign import get_next_worker
            self.worker_id = get_next_worker(self.project_id)
        except Exception as e:
            # Worker取得失敗時は "Auto" を使用
            self.worker_id = "Auto"
            logger.warning(f"Worker識別子取得失敗、'Auto' を使用: {e}")

        self.results["worker_id"] = self.worker_id

        if self.dry_run:
            self._log_step("assign_worker", "dry_run", f"worker={self.worker_id}")
            return

        # REWORK再実行時のロック整合処理
        # IN_PROGRESS遷移前に既存ロックを一旦解放してから再取得
        # これによりREWORKループでのロック蓄積を防止（BUG_008対策）
        current_status = self.task_info.get("status", "") if self.task_info else ""
        if current_status in ("REWORK", "IN_PROGRESS"):
            try:
                from utils.file_lock import FileLockManager

                # 既存ロックを解放
                FileLockManager.release_locks(self.project_id, self.task_id)
                self._log_step(
                    "file_lock_cleanup",
                    "success",
                    f"REWORK再実行前にロック解放 (status={current_status})"
                )
            except ImportError:
                self._log_step("file_lock_cleanup", "skip", "FileLockManager利用不可")
            except Exception as e:
                # ロック解放失敗は警告のみ（ロックが存在しない場合も含む）
                self._log_step("file_lock_cleanup", "warning", f"ロック解放エラー: {e}")

        # ファイルロックの取得を試みる
        try:
            from utils.file_lock import FileLockManager

            # タスクの対象ファイルを取得
            target_files_json = self.task_info.get("target_files")
            target_files = FileLockManager.parse_target_files(target_files_json)

            if target_files:
                # ファイルロックを取得
                lock_acquired = FileLockManager.acquire_locks(
                    self.project_id,
                    self.task_id,
                    target_files
                )

                if not lock_acquired:
                    # ファイルロック競合
                    conflicts = FileLockManager.check_conflicts(self.project_id, target_files)
                    blocking_tasks = list(set(c["task_id"] for c in conflicts))
                    raise WorkerExecutionError(
                        f"ファイルロック競合: タスク {', '.join(blocking_tasks)} が対象ファイルをロック中です"
                    )

                self._log_step("file_lock", "success", f"ロック取得: {len(target_files)}ファイル")
                self.results["locked_files"] = target_files
            else:
                self._log_step("file_lock", "skip", "対象ファイル未指定")

        except ImportError:
            self._log_step("file_lock", "skip", "FileLockManager利用不可")
        except Exception as e:
            self._log_step("file_lock", "warning", f"ロック取得エラー: {e}")
            # ロック取得失敗は致命的エラーとして扱う
            raise WorkerExecutionError(f"ファイルロック取得失敗: {e}")

        # 現在のステータスを取得
        current_status = self.task_info.get("status", "") if self.task_info else ""

        # IN_PROGRESS再実行対応: 既にIN_PROGRESSの場合の安全な処理
        if current_status == "IN_PROGRESS":
            self._log_step(
                "assign_worker",
                "info",
                f"タスクは既にIN_PROGRESS状態 - 再実行モード (assignee={self.task_info.get('assignee')})"
            )

            # Workerが異なる場合は警告を出す（別Workerが実行中の可能性）
            current_assignee = self.task_info.get("assignee")
            if current_assignee and current_assignee != self.worker_id:
                self._log_step(
                    "assign_worker",
                    "warning",
                    f"Workerが変更されます: {current_assignee} → {self.worker_id}"
                )

            # assigneeのみを更新（status遷移なし）
            from task.update import update_task
            try:
                update_task(
                    self.project_id,
                    self.task_id,
                    assignee=self.worker_id,
                    role="Worker",
                    reason="IN_PROGRESS再実行 - Worker割当更新",
                )
                self._log_step(
                    "assign_worker",
                    "success",
                    f"worker={self.worker_id} (再実行モード)"
                )
            except Exception as e:
                # assignee更新失敗時も続行可能（既存のassigneeで実行）
                self._log_step(
                    "assign_worker",
                    "warning",
                    f"Worker割当更新失敗: {e} - 既存assigneeで続行"
                )

            # 再実行フラグをセット
            self.results["is_reexecution"] = True
            return

        # 通常のステータス更新（IN_PROGRESS以外 → IN_PROGRESS）
        from task.update import update_task

        try:
            # リワークモードの場合、REWORK → IN_PROGRESS への遷移
            if self.is_rework and current_status == "REWORK":
                self._log_step("assign_worker", "info", "REWORK → IN_PROGRESS (リワーク開始)")

            update_task(
                self.project_id,
                self.task_id,
                status="IN_PROGRESS",
                assignee=self.worker_id,
                role="Worker",
            )
            self._log_step("assign_worker", "success", f"worker={self.worker_id}")
        except TransitionError as e:
            # 予期しない遷移エラー
            raise WorkerExecutionError(f"ステータス更新失敗: {e}")

    def _create_checkpoint(self) -> None:
        """
        チェックポイント作成（タスク実行前）

        DBスナップショットとファイル状態を保存します。
        失敗時は警告ログを出力しますが、タスク実行は続行します。
        """
        self._log_step("create_checkpoint", "start", f"task={self.task_id}")

        try:
            from checkpoint.create import create_checkpoint, CheckpointError

            # チェックポイント作成
            checkpoint_id = create_checkpoint(
                project_id=self.project_id,
                task_id=self.task_id,
                order_id=self.order_id,
                verbose=self.verbose
            )

            self.checkpoint_id = checkpoint_id
            self.results["checkpoint_id"] = checkpoint_id
            self._log_step("create_checkpoint", "success", f"checkpoint={checkpoint_id}")

        except ImportError:
            self._log_step("create_checkpoint", "skip", "checkpoint module not available")
        except Exception as e:
            # チェックポイント作成失敗は警告のみ（タスク実行は続行）
            self._log_step("create_checkpoint", "warning", f"チェックポイント作成失敗: {e}")
            if self.verbose:
                logger.exception("create_checkpoint詳細エラー")

        # ファイルスナップショット作成 (ORDER_109)
        try:
            from worker.snapshot_manager import SnapshotManager
            sm = SnapshotManager(self.project_id)
            # target_filesの取得: タスク情報のtarget_filesか、ORDER成果物ディレクトリ
            target_files = None
            if self.task_info and self.task_info.get("target_files"):
                tf = self.task_info["target_files"]
                target_files = tf.split(",") if isinstance(tf, str) else tf
            self.snapshot_id = sm.create_snapshot(self.task_id, self.order_id, target_files)
            self.results["snapshot_id"] = self.snapshot_id
            self._log_step("create_snapshot", "success", f"snapshot={self.snapshot_id}")
        except ImportError:
            self._log_step("create_snapshot", "skip", "snapshot_manager not available")
        except Exception as e:
            self._log_step("create_snapshot", "warning", f"スナップショット作成失敗: {e}")

    def _check_migration_safety(self) -> None:
        """
        マイグレーション実行前の安全チェック

        Worker実行中にマイグレーションスクリプトを呼び出す際の安全ガード。
        他のWorkerが実行中の場合、スキーマ変更は危険なため警告またはブロックする。

        Raises:
            WorkerExecutionError: 他のWorkerが実行中で安全でない場合
        """
        # マイグレーションスクリプトかどうかを判定
        task_title = self.task_info.get("title", "").lower()
        task_desc = self.task_info.get("description", "").lower()

        migration_keywords = [
            "migration", "マイグレーション", "schema", "スキーマ",
            "alter table", "drop table", "create table",
            "pragma", "foreign_keys"
        ]

        is_migration_task = any(
            keyword in task_title or keyword in task_desc
            for keyword in migration_keywords
        )

        if not is_migration_task:
            # マイグレーションタスクでない場合はチェック不要
            return

        self._log_step("migration_safety_check", "start", "マイグレーションタスク検出")

        # 他のWorker実行中タスクを検出
        conn = get_connection()
        try:
            running_tasks = fetch_all(
                conn,
                """
                SELECT t.id, t.project_id, t.title, t.assignee, t.updated_at
                FROM tasks t
                WHERE t.status = 'IN_PROGRESS'
                  AND t.id != ?
                ORDER BY t.updated_at DESC
                """,
                (self.task_id,)
            )

            if running_tasks:
                # 実行中タスクがある場合は警告
                self._log_step(
                    "migration_safety_check",
                    "warning",
                    f"他のWorkerが実行中: {len(running_tasks)}件"
                )

                for task in running_tasks:
                    logger.warning(
                        f"  - {task['id']} ({task['project_id']}): {task['title']} "
                        f"[assignee={task['assignee']}, updated={task['updated_at']}]"
                    )

                # 警告メッセージ
                logger.warning(
                    "⚠️  他のWorkerが実行中です。マイグレーション実行はスキーマ変更により"
                    "他のタスクが失敗する原因となる可能性があります。"
                )
                logger.warning(
                    "マイグレーションスクリプト内でMigrationRunnerを使用する場合、"
                    "MigrationRunnerが自動的に安全チェックを行います。"
                )

                # エラーとして扱わず警告のみ（MigrationRunnerが最終判断を行う）
                self._log_step(
                    "migration_safety_check",
                    "warning",
                    "他Worker実行中 - MigrationRunnerによる最終判断待ち"
                )
            else:
                self._log_step(
                    "migration_safety_check",
                    "success",
                    "他のWorker実行なし - 安全"
                )

        finally:
            conn.close()

    def _step_execute_task(self) -> None:
        """Step 3: claude -p でタスク実行"""
        if not CLAUDE_RUNNER_AVAILABLE:
            self._log_step("execute_task", "skip", "claude_runner 利用不可")
            return

        profile_label = f", profile={self._resolved_profile}" if self._resolved_profile else ""
        self._log_step("execute_task", "start", f"model={self.model}{profile_label}, allowed_tools={len(self.allowed_tools)}個")

        # チェックポイント作成（タスク実行前）
        self._create_checkpoint()

        # マイグレーション安全チェック
        self._check_migration_safety()

        # claude_runner 初期化
        self.runner = create_runner(
            model=self.model,
            max_turns=50,
            timeout_seconds=self.timeout,
            allowed_tools=self.allowed_tools,
        )

        # TASKファイルから詳細情報を取得
        task_content = self._read_task_file()

        # プロンプト構築
        prompt = self._build_execution_prompt(task_content)

        # claude -p 実行
        result = self.runner.run(prompt)

        if not result.success:
            raise WorkerExecutionError(f"タスク実行に失敗: {result.error_message}")

        self.results["execution_result"] = result.result_text
        self.results["cost_usd"] = result.cost_usd

        self._log_step(
            "execute_task",
            "success",
            f"cost=${result.cost_usd:.4f}" if result.cost_usd else ""
        )

    def _step_self_verification(self) -> None:
        """Step 3.5: 成果物の自己検証＋自己修正ループ

        Worker実行完了後の成果物に対してlint/test/型チェックを自動実行し、
        失敗時は最大3回の自己修正ループを行う。
        検証対象がない場合や検証モジュールが利用できない場合はスキップする。
        """
        self._log_step("self_verification", "start", "")

        try:
            from worker.self_verification import SelfVerificationRunner
        except ImportError:
            self._log_step("self_verification", "skip", "self_verification モジュール利用不可")
            return

        # 実行結果から成果物パスを取得
        exec_result = self.results.get("execution_result", "")
        try:
            result_data = json.loads(exec_result)
            artifacts = result_data.get("artifacts", [])
        except (json.JSONDecodeError, AttributeError, TypeError):
            self._log_step("self_verification", "skip", "成果物パス取得不可")
            return

        if not artifacts:
            self._log_step("self_verification", "skip", "成果物なし")
            return

        # 検証ランナー初期化
        runner = SelfVerificationRunner(
            project_dir=self.project_dir,
            artifacts=artifacts,
            timeout=120,
        )

        # ツール検出
        tools = runner.detect_tools()
        if not tools.lint and not tools.test and not tools.typecheck:
            self._log_step("self_verification", "skip", "検証ツール未検出")
            return

        # 自己修正ループ（最大3回）
        MAX_FIX_ITERATIONS = 3
        verification_history = []
        last_result = None

        for iteration in range(MAX_FIX_ITERATIONS + 1):
            # 検証実行
            vresult = runner.run_verification()
            last_result = vresult
            verification_history.append({
                "iteration": iteration,
                "success": vresult.success,
                "checks": [c.to_dict() for c in vresult.checks],
                "skipped": vresult.skipped_checks,
                "duration": round(vresult.duration_seconds, 2),
            })

            if vresult.success:
                self._log_step(
                    "self_verification", "success",
                    f"全検証パス（試行{iteration + 1}回目）"
                )
                break

            if iteration >= MAX_FIX_ITERATIONS:
                self._log_step(
                    "self_verification", "warning",
                    f"自己修正上限到達（{MAX_FIX_ITERATIONS}回）- PMレビューへエスカレーション"
                )
                break

            # 自己修正プロンプト生成＋実行
            if not CLAUDE_RUNNER_AVAILABLE or self.runner is None:
                self._log_step("self_verification", "warning", "claude_runner利用不可 - 自己修正スキップ")
                break

            task_content = self._read_task_file()
            fix_prompt = runner.build_fix_prompt(vresult, task_content)

            self._log_step(
                "self_verification", "info",
                f"自己修正実行 (試行{iteration + 2}回目)"
            )

            try:
                fix_result = self.runner.run(fix_prompt)
                if not fix_result.success:
                    self._log_step("self_verification", "warning", "自己修正実行失敗")
                    break
                # 修正結果で execution_result を更新
                self.results["execution_result"] = fix_result.result_text
            except Exception as e:
                self._log_step("self_verification", "warning", f"自己修正中にエラー: {e}")
                break

        # 検証結果を保存
        self.results["verification"] = {
            "final_success": last_result.success if last_result else False,
            "total_iterations": len(verification_history),
            "fix_attempts": max(0, len(verification_history) - 1),
            "history": verification_history,
        }

        self._log_step(
            "self_verification", "complete",
            f"検証完了: success={last_result.success if last_result else False}, "
            f"iterations={len(verification_history)}"
        )

    def _read_task_file(self) -> str:
        """TASKファイルを読み込む"""
        # ORDER配下のTASKファイルを検索
        if self.order_id:
            # パスコンポーネント検証（絶対パス混入防止）
            validate_path_components(self.order_id, self.task_id)

            task_file = safe_path_join(
                self.project_dir, "RESULT", self.order_id, "04_TASKS",
                f"{self.task_id}.md"
            )
            if task_file.exists():
                return task_file.read_text(encoding="utf-8")

        # STAFFINGから検索
        if self.order_id:
            # パスコンポーネント検証
            validate_path_components(self.order_id)

            staffing_file = safe_path_join(
                self.project_dir, "RESULT", self.order_id, "03_STAFFING.md"
            )
            if staffing_file.exists():
                return staffing_file.read_text(encoding="utf-8")

        # タスク情報のみで実行
        return f"タスク: {self.task_info.get('title', 'Untitled')}"

    def _get_rework_history(self) -> tuple[int, str]:
        """
        REWORK履歴を取得（REWORK回数と過去のレビューコメント）

        Returns:
            tuple[int, str]: (REWORK回数, フォーマット済みREWORK履歴テキスト)
        """
        try:
            conn = get_connection()
            try:
                # 1. reject_countからREWORK回数を取得
                task = fetch_one(
                    conn,
                    "SELECT reject_count FROM tasks WHERE id = ? AND project_id = ?",
                    (self.task_id, self.project_id)
                )
                rework_count = task["reject_count"] if task else 0

                if rework_count == 0:
                    return (0, "")

                # 2. 過去のREJECTED判定とコメントをchange_historyから取得
                # change_historyにはDONE→REWORKの遷移が記録されている
                past_reviews = fetch_all(
                    conn,
                    """
                    SELECT change_reason as comment, changed_at as reviewed_at
                    FROM change_history
                    WHERE entity_type = 'task'
                      AND entity_id = ?
                      AND field_name = 'status'
                      AND new_value = 'REWORK'
                    ORDER BY changed_at DESC
                    """,
                    (self.task_id,)
                )

                if not past_reviews:
                    return (rework_count, "")

                # 3. フォーマット
                history_entries = []
                for idx, review in enumerate(rows_to_dicts(past_reviews), 1):
                    reviewed_at = review.get("reviewed_at", "不明")
                    comment = review.get("comment", "（コメントなし）")
                    history_entries.append(f"""### REWORK #{idx} ({reviewed_at})
{comment}""")

                history_section = "\n\n".join(history_entries)

                return (rework_count, f"""
## 🔄 REWORK履歴（必読）

このタスクは過去に{rework_count}回差し戻されています。以下の過去の指摘事項を確認し、同じ問題を繰り返さないように注意してください。

{history_section}

""")
            finally:
                conn.close()

        except Exception as e:
            logger.warning(f"REWORK履歴取得に失敗: {e}")
            return (0, "")

    def _get_known_bugs(self) -> str:
        """既知のバグパターンをDBから取得してフォーマット"""
        try:
            conn = get_connection()
            try:
                # プロジェクト固有 + 汎用パターンを取得（ACTIVEのみ）
                bugs = fetch_all(
                    conn,
                    """
                    SELECT id, title, description, pattern_type, severity, solution,
                           effectiveness_score
                    FROM bugs
                    WHERE (project_id = ? OR project_id IS NULL)
                      AND status = 'ACTIVE'
                    ORDER BY
                        severity DESC,
                        occurrence_count DESC
                    """,
                    (self.project_id,)
                )

                if not bugs:
                    return ""

                bugs_list = rows_to_dicts(bugs)

                # バグパターン注入を記録（有効性評価用）
                try:
                    from quality.bug_learner import EffectivenessEvaluator
                    evaluator = EffectivenessEvaluator(self.project_id)
                    for bug in bugs_list:
                        try:
                            evaluator.record_injection(bug["id"])
                        except Exception:
                            pass  # 個別の記録失敗は無視
                except ImportError:
                    pass  # quality.bug_learner 利用不可時は記録をスキップ
                except Exception:
                    pass  # 記録失敗は元の動作に影響させない

                # バグパターンをフォーマット
                bug_entries = []
                for bug in bugs_list:
                    scope = "汎用" if bug.get("project_id") is None else "固有"
                    pattern_label = f" [{bug['pattern_type']}]" if bug.get("pattern_type") else ""
                    eff_score = bug.get("effectiveness_score")
                    eff_label = f" [有効性: {eff_score:.2f}]" if eff_score is not None else ""

                    entry = f"""### {bug['id']}{pattern_label} - {bug['title']} ({scope}, {bug['severity']}){eff_label}
{bug['description']}"""

                    if bug.get("solution"):
                        entry += f"\n**解決策**: {bug['solution']}"

                    bug_entries.append(entry)

                bug_section = "\n\n".join(bug_entries)

                return f"""
## ⚠️ 既知バグパターン（必読）

このプロジェクトおよびフレームワーク全体で過去に発生したバグパターンです。
実装前に必ず確認し、同じミスを繰り返さないように注意してください。

{bug_section}

"""
            finally:
                conn.close()

        except Exception as e:
            logger.warning(f"既知バグ取得に失敗: {e}")
            return ""

    def _build_execution_prompt(self, task_content: str) -> str:
        """タスク実行用プロンプトを構築"""
        # リワークモードの場合、差し戻しコメントを追加
        rework_section = ""
        if self.is_rework and self.rework_comment:
            rework_section = f"""
## リワーク情報（差し戻し対応）
このタスクはレビューで差し戻されたリワークです。以下の指摘事項に対応してください。

### 差し戻しコメント
{self.rework_comment}

### 対応方針
1. 上記の問題点を確認し、該当箇所を特定してください
2. 修正指針に従って修正を行ってください
3. 修正後、問題が解決されたことを確認してください

"""

        # 前回失敗時のコンテキストを追加（リトライ時）
        failure_context_section = ""
        try:
            from retry.retry_handler import RetryHandler
            handler = RetryHandler(self.project_id, self.task_id)
            failure_context = handler.get_failure_context()
            if failure_context:
                failure_context_section = f"""
## 🔄 Previous Failure Context (Auto-Retry)

This task previously failed. Review the following context from INCIDENTS table:

{failure_context}

### Retry Instructions:
1. Analyze the root cause and understand what went wrong
2. Implement fixes to address the specific failure
3. Verify the fix resolves the issue before completing
4. Document the changes made to prevent recurrence

"""
        except Exception as e:
            logger.debug(f"Failed to get failure context: {e}")
            pass

        # マイグレーションタスクの場合、安全ガイドラインを追加
        migration_section = ""
        task_title = self.task_info.get("title", "").lower()
        task_desc = self.task_info.get("description", "").lower()

        migration_keywords = [
            "migration", "マイグレーション", "schema", "スキーマ",
            "alter table", "drop table", "create table"
        ]

        is_migration_task = any(
            keyword in task_title or keyword in task_desc
            for keyword in migration_keywords
        )

        if is_migration_task:
            migration_section = """
## ⚠️ マイグレーション安全ガイドライン

このタスクはデータベーススキーマの変更を含む可能性があります。
必ず以下の安全機構を使用してください:

### 必須事項
1. **MigrationRunnerの使用**
   - `backend/utils/migration_base.py` の `MigrationRunner` を使用すること
   - 直接SQLを実行せず、必ずMigrationRunnerを経由すること

2. **安全機能の活用**
   - MigrationRunnerは自動的に以下を実行します:
     * 他のWorker実行中タスクの検出と警告
     * PRAGMA foreign_keys の自動制御（CASCADE削除防止）
     * 自動バックアップ作成
     * トランザクション管理

3. **実装例**
   ```python
   from utils.migration_base import MigrationRunner, MigrationError

   def my_migration(conn):
       cursor = conn.cursor()
       cursor.execute("ALTER TABLE ...")
       return True

   runner = MigrationRunner("migration_name", verbose=True)
   success = runner.run(my_migration)
   ```

### 禁止事項
- ❌ 直接 `sqlite3.connect()` でDB接続しない
- ❌ 直接 `DROP TABLE` や `ALTER TABLE` を実行しない
- ❌ `PRAGMA foreign_keys = OFF` を手動で実行しない

MigrationRunnerを使用しない場合、CASCADE削除によるデータ損失のリスクがあります。

"""

        # Worker環境制約セクション（常に注入）
        worker_env_section = """
## ⚠️ Worker環境制約（必須遵守）

Workerはターミナル（CLI）操作のみ可能です。以下のGUI操作は**実行不可能**です:
- アプリケーション起動・画面操作
- スクリーンショット撮影・目視確認
- ブラウザ起動・Web画面操作
- GUIテスト（E2Eテスト等の画面操作を伴うもの）

**品質確認の代替手段**: GUI操作の代わりに以下を使用してください:
- `npm run build` （ビルド成功確認）
- `tsc --noEmit` （型チェック）
- `npm test` （ユニットテスト実行）

GUI操作を含むタスクが割り当てられた場合は、上記の代替手段で品質確認を行ってください。

"""

        # REWORK履歴を取得
        rework_count, rework_history_section = self._get_rework_history()

        # 既知バグパターンを取得
        known_bugs_section = self._get_known_bugs()

        # テストファイル出力ルールを追加
        test_file_rules_section = """
## 📝 テストファイル・一時ファイル出力ルール（必読）

**CRITICAL**: テストファイルやデバッグ用の一時ファイルは必ず `tmp/` ディレクトリに出力してください。

### ルール
1. **出力先**: `AI_PM/tmp/` ディレクトリ（プロジェクトルート直下のtmp/）
2. **禁止**: プロジェクトルート直下への直接作成（例: `test_*.py`, `tmp_*.json` など）
3. **対象ファイル**:
   - テストスクリプト（`test_*.py`, `*_test.py`）
   - 一時JSONファイル（`tmp_*.json`, `temp_*.json`）
   - デバッグ用ファイル（`debug_*.txt`, `*.log`）
   - その他の一時ファイル

### 理由
- プロジェクトルート直下が散らかるのを防ぐ
- Git管理対象外とする（tmp/は.gitignoreに追加済み）
- 一時ファイルの削除・管理を容易にする

### 例
```python
# ❌ 禁止
output_file = "test_output.json"
output_file = "tmp_results.json"

# ✅ 正しい
output_file = "tmp/test_output.json"
output_file = "tmp/tmp_results.json"
```

"""

        mode_label = "【リワーク】" if self.is_rework else ""

        # REWORK回数に応じた警告メッセージ
        rework_warning = ""
        if rework_count >= 2:
            rework_warning = f"""
⚠️ **重要**: このタスクは{rework_count}回差し戻されています。
- 使用モデル: **{self.model.upper()}** (自動昇格適用済み)
- 過去の指摘事項を必ず確認し、同じ問題を繰り返さないでください
- より慎重に実装し、テストを徹底してください

"""

        return f"""{mode_label}以下のタスクを実行してください。
{rework_warning}
## プロジェクト情報
- プロジェクトID: {self.project_id}
- タスクID: {self.task_id}
- ORDER ID: {self.order_id}

## タスク情報
- タイトル: {self.task_info.get('title', 'Untitled')}
- 説明: {self.task_info.get('description', '（なし）')}
- 優先度: {self.task_info.get('priority', 'P1')}
{rework_section}{rework_history_section}{failure_context_section}{migration_section}{worker_env_section}{test_file_rules_section}{known_bugs_section}
## タスク定義
{task_content}

## 指示
1. タスクの内容を理解し、完了条件を確認してください
2. 必要な実装・作業を行ってください
3. 完了したら、実施内容と結果をJSON形式で報告してください

## 出力形式
JSON形式で以下の構造を返してください:
{{
  "completed": true/false,
  "summary": "実施内容の要約",
  "details": ["詳細1", "詳細2", ...],
  "artifacts": ["作成/更新したファイルパス1", ...],
  "issues": ["発生した問題があれば記載"]
}}

JSONのみを出力し、説明文は含めないでください。"""

    def _step_create_report(self) -> None:
        """Step 4: REPORTを作成（書き込み検証付き）"""
        self._log_step("create_report", "start", "")

        if not self.order_id:
            self._log_step("create_report", "skip", "ORDER ID なし")
            return

        # パスコンポーネント検証（絶対パス混入防止）
        validate_path_components(self.order_id, self.task_id)

        # REPORTディレクトリ
        report_dir = safe_path_join(
            self.project_dir, "RESULT", self.order_id, "05_REPORT"
        )
        report_dir.mkdir(parents=True, exist_ok=True)

        report_file = safe_path_join(
            report_dir, f"REPORT_{self.task_id.replace('TASK_', '')}.md"
        )

        # execution_resultの内容チェック
        exec_result = self.results.get("execution_result", "")
        if not exec_result or len(exec_result.strip()) < 20:
            raise WorkerExecutionError(
                f"REPORT作成不可: execution_resultが空または短すぎます "
                f"({len(exec_result.strip()) if exec_result else 0}文字). "
                f"Worker実行が正常に完了していない可能性があります。"
            )

        # REPORT内容作成
        report_content = self._format_report(exec_result)

        if len(report_content.strip()) < 100:
            raise WorkerExecutionError(
                f"REPORT内容が短すぎます ({len(report_content.strip())}文字): "
                f"REPORT生成に問題があった可能性があります。"
            )

        # ファイル書き込みと検証
        report_file.write_text(report_content, encoding="utf-8")

        # 書き込み後の存在・サイズ検証
        if not report_file.exists():
            raise WorkerExecutionError(f"REPORTファイルの書き込みに失敗しました: {report_file}")

        written_size = report_file.stat().st_size
        if written_size < 100:
            raise WorkerExecutionError(
                f"REPORTファイルが異常に小さいです ({written_size}バイト): {report_file}"
            )

        self.results["report_file"] = str(report_file)
        self.results["report_size_bytes"] = written_size

        self._log_step("create_report", "success", f"{report_file} ({written_size}バイト)")

    def _format_report(self, exec_result: str) -> str:
        """REPORT内容をフォーマット"""
        lines = [
            f"# {self.task_id} 完了報告",
            "",
            "## 基本情報",
            "",
            "| 項目 | 内容 |",
            "|------|------|",
            f"| タスクID | {self.task_id} |",
            f"| 実行日時 | {datetime.now().strftime('%Y-%m-%d %H:%M')} |",
            f"| 担当 | {self.worker_id} |",
            f"| ステータス | 完了 |",
            "",
        ]

        # 実行結果をパース
        try:
            result_data = json.loads(exec_result)
            lines.append("## 実施内容")
            lines.append("")
            lines.append(result_data.get("summary", "（要約なし）"))
            lines.append("")

            if result_data.get("details"):
                lines.append("### 詳細")
                for detail in result_data["details"]:
                    lines.append(f"- {detail}")
                lines.append("")

            if result_data.get("artifacts"):
                lines.append("### 成果物")
                for artifact in result_data["artifacts"]:
                    lines.append(f"- `{artifact}`")
                lines.append("")

            if result_data.get("issues"):
                lines.append("### 発生した問題")
                for issue in result_data["issues"]:
                    lines.append(f"- {issue}")
                lines.append("")

        except json.JSONDecodeError:
            # JSONパースに失敗した場合はそのまま記載
            lines.append("## 実行結果")
            lines.append("")
            lines.append(exec_result)

        # 自己検証結果セクション（データがある場合のみ）
        verification = self.results.get("verification")
        if verification:
            lines.append("## 自己検証結果")
            lines.append("")
            lines.append("| 項目 | 結果 |")
            lines.append("|------|------|")
            final_status = "PASSED" if verification.get("final_success") else "FAILED"
            lines.append(f"| 検証結果 | {final_status} |")
            lines.append(f"| 試行回数 | {verification.get('total_iterations', 0)}回 |")
            lines.append(f"| 自己修正 | {verification.get('fix_attempts', 0)}回実施 |")
            lines.append("")

            # 最後の検証詳細
            history = verification.get("history", [])
            if history:
                last_entry = history[-1]
                checks = last_entry.get("checks", [])
                skipped = last_entry.get("skipped", [])

                if checks or skipped:
                    lines.append("### 検証詳細")
                    for check in checks:
                        status = "PASS" if check.get("passed") else "FAIL"
                        lines.append(f"- [{status}] {check.get('type', '?')}: `{check.get('command', '?')}`")
                        if not check.get("passed") and check.get("errors"):
                            for err in check["errors"][:3]:
                                lines.append(f"  - {err}")
                    for skip_name in skipped:
                        lines.append(f"- [SKIP] {skip_name}: ツール未検出")
                    lines.append("")

        return "\n".join(lines)

    def _step_static_analysis(self) -> None:
        """Step 4.5: 成果物に対して静的解析を自動実行

        StaticAnalyzer + AutoFixer を使用して、Worker成果物の品質チェックを行う。
        解析結果はREPORTに追記し、tasksテーブルのstatic_analysis_scoreを更新する。
        解析失敗時もタスク処理は続行する（グレースフルスキップ）。
        """
        self._log_step("static_analysis", "start", "")

        try:
            from quality.static_analyzer import StaticAnalyzer
            from quality.auto_fixer import AutoFixer
        except ImportError as e:
            self._log_step("static_analysis", "skip", f"quality module not available: {e}")
            return

        # 成果物ファイルリストを取得
        artifact_files = self._get_artifact_files()
        if not artifact_files:
            self._log_step("static_analysis", "skip", "成果物ファイルなし")
            self.results["static_analysis"] = {"score": 100, "skipped": True}
            return

        try:
            # プロジェクトルートを推定
            project_root = str(_project_root)

            # 1. 自動修正を先に実行
            fixer = AutoFixer(project_root)
            fix_result = fixer.fix(artifact_files)
            self._log_step("static_analysis", "info",
                f"auto_fix: {fix_result.get('fixed_count', 0)} files fixed")

            # 2. 静的解析を実行
            analyzer = StaticAnalyzer(project_root)
            analysis_result = analyzer.analyze(artifact_files)
            score = analysis_result.get("score", 100)
            self._log_step("static_analysis", "info",
                f"score={score}, errors={len(analysis_result.get('errors', []))}, "
                f"warnings={len(analysis_result.get('warnings', []))}")

            # 3. 結果を保持
            self.results["static_analysis"] = {
                "score": score,
                "errors": analysis_result.get("errors", []),
                "warnings": analysis_result.get("warnings", []),
                "tools_used": analysis_result.get("tools_used", []),
                "fix_result": fix_result,
            }

            # 4. REPORTに追記
            self._append_static_analysis_to_report(analysis_result, fix_result)

            # 5. DBのstatic_analysis_scoreを更新
            self._update_static_analysis_score(score)

            self._log_step("static_analysis", "success", f"score={score}")

        except Exception as e:
            self._log_step("static_analysis", "warning", f"解析失敗（続行）: {e}")
            self.results["static_analysis"] = {"score": None, "error": str(e)}

    def _get_artifact_files(self) -> list:
        """Worker実行結果から成果物ファイルリストを取得"""
        artifact_files = []

        # 方法1: execution_resultのartifactsからファイルパスを取得
        exec_result = self.results.get("execution_result", "")
        try:
            result_data = json.loads(exec_result)
            artifacts = result_data.get("artifacts", [])
            for artifact in artifacts:
                artifact_path = Path(artifact)
                if artifact_path.exists() and artifact_path.is_file():
                    artifact_files.append(str(artifact_path))
        except (json.JSONDecodeError, TypeError):
            pass

        # 方法2: 成果物が取れなかった場合、REPORTから探索は省略
        # （方法1で十分な情報が得られるはず）

        return artifact_files

    def _append_static_analysis_to_report(
        self, analysis_result: dict, fix_result: dict
    ) -> None:
        """REPORTファイルに静的解析結果セクションを追記"""
        report_file_str = self.results.get("report_file")
        if not report_file_str:
            return

        report_file = Path(report_file_str)
        if not report_file.exists():
            return

        lines = ["", "## 静的解析結果", ""]
        score = analysis_result.get("score", 100)
        lines.append(f"### スコア: {score}/100")
        lines.append("")

        tools_used = analysis_result.get("tools_used", [])
        skipped = analysis_result.get("skipped_tools", [])
        if tools_used:
            lines.append(f"### 使用ツール: {', '.join(tools_used)}")
            lines.append("")
        if skipped:
            lines.append(f"### スキップツール: {', '.join(skipped)}")
            lines.append("")

        # 自動修正結果
        fixes = fix_result.get("fixes", [])
        if fixes:
            lines.append(f"### 自動修正済み ({len(fixes)}件)")
            lines.append("")
            lines.append("| ファイル | ツール | 内容 |")
            lines.append("|---------|--------|------|")
            for fix in fixes:
                lines.append(f"| `{fix.get('file', '')}` | {fix.get('tool', '')} | {fix.get('description', '')} |")
            lines.append("")

        # エラー
        errors = analysis_result.get("errors", [])
        if errors:
            lines.append(f"### エラー ({len(errors)}件)")
            lines.append("")
            lines.append("| ファイル | 行 | ツール | 内容 |")
            lines.append("|---------|-----|--------|------|")
            for err in errors[:20]:  # 最大20件
                lines.append(
                    f"| `{err.get('file', '')}` | {err.get('line', '')} | "
                    f"{err.get('tool', '')} | {err.get('message', '')} |"
                )
            if len(errors) > 20:
                lines.append(f"| ... | ... | ... | 他{len(errors) - 20}件省略 |")
            lines.append("")

        # 警告
        warnings = analysis_result.get("warnings", [])
        if warnings:
            lines.append(f"### 警告 ({len(warnings)}件)")
            lines.append("")
            lines.append("| ファイル | 行 | ツール | 内容 |")
            lines.append("|---------|-----|--------|------|")
            for warn in warnings[:10]:  # 最大10件
                lines.append(
                    f"| `{warn.get('file', '')}` | {warn.get('line', '')} | "
                    f"{warn.get('tool', '')} | {warn.get('message', '')} |"
                )
            if len(warnings) > 10:
                lines.append(f"| ... | ... | ... | 他{len(warnings) - 10}件省略 |")
            lines.append("")

        # REPORTファイルに追記
        existing = report_file.read_text(encoding="utf-8")
        report_file.write_text(existing + "\n".join(lines), encoding="utf-8")

    def _update_static_analysis_score(self, score: int) -> None:
        """tasksテーブルのstatic_analysis_scoreを更新"""
        try:
            conn = get_connection()
            conn.execute(
                "UPDATE tasks SET static_analysis_score = ? WHERE id = ? AND project_id = ?",
                (score, self.task_id, self.project_id)
            )
            conn.commit()
        except Exception as e:
            # カラム未追加時はスキップ（グレースフルデグレード）
            logger.warning(f"static_analysis_score更新スキップ: {e}")

    def _step_destructive_sql_check(self) -> None:
        """Step 4.6: 成果物に対して破壊的SQL操作を検出

        DestructiveSqlDetectorを使用して、Worker成果物に破壊的なDB変更（DROP TABLE,
        ALTER TABLE DROP COLUMN等）が含まれていないかをチェックする。
        検出結果はREPORTに追記し、PMレビュー時に確認できるようにする。
        検出失敗時もタスク処理は続行する（グレースフルスキップ）。
        """
        self._log_step("destructive_sql_check", "start", "")

        try:
            from utils.sql_safety import DestructiveSqlDetector
        except ImportError as e:
            self._log_step("destructive_sql_check", "skip", f"sql_safety module not available: {e}")
            return

        # 成果物ファイルリストを取得
        artifact_files = self._get_artifact_files()
        if not artifact_files:
            self._log_step("destructive_sql_check", "skip", "成果物ファイルなし")
            self.results["destructive_sql_check"] = {"checked": False, "skipped": True}
            return

        try:
            # DestructiveSqlDetector初期化
            detector = DestructiveSqlDetector()

            # 各ファイルをスキャン
            all_results = []
            total_matches = 0
            critical_count = 0
            high_count = 0
            medium_count = 0

            for artifact_path in artifact_files:
                # ファイルパスを絶対パスに変換
                if not Path(artifact_path).is_absolute():
                    artifact_path = _project_root / artifact_path

                scan_result = detector.scan_file(artifact_path)
                if scan_result.has_destructive_operations:
                    all_results.append(scan_result)
                    total_matches += len(scan_result.matches)
                    critical_count += scan_result.critical_count
                    high_count += scan_result.high_count
                    medium_count += scan_result.medium_count

            # 結果を保持
            self.results["destructive_sql_check"] = {
                "checked": True,
                "has_destructive_operations": len(all_results) > 0,
                "total_files_scanned": len(artifact_files),
                "files_with_issues": len(all_results),
                "total_matches": total_matches,
                "critical_count": critical_count,
                "high_count": high_count,
                "medium_count": medium_count,
                "results": [r.to_dict() for r in all_results],
            }

            if len(all_results) > 0:
                self._log_step(
                    "destructive_sql_check",
                    "warning",
                    f"破壊的SQL検出: {total_matches}件 (CRITICAL:{critical_count}, HIGH:{high_count}, MEDIUM:{medium_count})"
                )
            else:
                self._log_step("destructive_sql_check", "success", "破壊的SQL操作なし")

            # REPORTに追記
            self._append_destructive_sql_to_report(self.results["destructive_sql_check"])

        except Exception as e:
            # 検出エラー時もタスク処理は続行
            self._log_step("destructive_sql_check", "error", f"破壊的SQL検出エラー: {e}")
            self.results["destructive_sql_check"] = {
                "checked": False,
                "error": str(e),
            }

    def _append_destructive_sql_to_report(self, check_result: Dict[str, Any]) -> None:
        """破壊的SQL検出結果をREPORTに追記"""
        if not self.order_id:
            return

        # パスコンポーネント検証（絶対パス混入防止）
        validate_path_components(self.order_id, self.task_id)

        report_dir = safe_path_join(
            self.project_dir, "RESULT", self.order_id, "05_REPORT"
        )
        report_file = safe_path_join(
            report_dir, f"REPORT_{self.task_id.replace('TASK_', '')}.md"
        )

        if not report_file.exists():
            return

        lines = [
            "",
            "## 破壊的SQL検出結果",
            "",
        ]

        if not check_result.get("checked"):
            lines.append("⚠️ 破壊的SQL検出をスキップしました")
            if check_result.get("error"):
                lines.append(f"エラー: `{check_result['error']}`")
            lines.append("")
        elif not check_result.get("has_destructive_operations"):
            lines.append("✅ 破壊的SQL操作は検出されませんでした")
            lines.append("")
        else:
            # 検出あり - 警告表示
            critical = check_result.get("critical_count", 0)
            high = check_result.get("high_count", 0)
            medium = check_result.get("medium_count", 0)
            total = check_result.get("total_matches", 0)

            lines.append(f"⚠️ **破壊的SQL操作が検出されました** ({total}件)")
            lines.append("")
            lines.append(f"- CRITICAL: {critical}件")
            lines.append(f"- HIGH: {high}件")
            lines.append(f"- MEDIUM: {medium}件")
            lines.append("")

            # 詳細リスト
            lines.append("### 検出詳細")
            lines.append("")
            lines.append("| ファイル | 行 | 重要度 | 説明 | コード |")
            lines.append("|---------|-------|--------|------|--------|")

            for result in check_result.get("results", []):
                file_path = result.get("file_path", "")
                # プロジェクトルートからの相対パスに変換
                try:
                    file_path = str(Path(file_path).relative_to(_project_root))
                except ValueError:
                    pass

                for match in result.get("matches", []):
                    severity = match.get("severity", "")
                    line_num = match.get("line_number", "")
                    desc = match.get("description", "")
                    code = match.get("line_content", "").strip()
                    # コード部分を短縮（長すぎる場合）
                    if len(code) > 60:
                        code = code[:57] + "..."

                    severity_icon = {
                        "CRITICAL": "🔴",
                        "HIGH": "🟠",
                        "MEDIUM": "🟡",
                    }.get(severity, "")

                    lines.append(
                        f"| `{file_path}` | {line_num} | {severity_icon} {severity} | {desc} | `{code}` |"
                    )

            lines.append("")
            lines.append("⚠️ **PM確認事項**: このタスクには破壊的なDB変更が含まれます。")
            lines.append("マイグレーション実行タイミングと影響範囲を確認してください。")
            lines.append("")

        # REPORTファイルに追記
        existing = report_file.read_text(encoding="utf-8")
        report_file.write_text(existing + "\n".join(lines), encoding="utf-8")

    def _step_update_status_done(self) -> None:
        """Step 6: ステータスをDONEに更新"""
        self._log_step("update_status_done", "start", "")

        from task.update import update_task

        try:
            update_task(
                self.project_id,
                self.task_id,
                status="DONE",
                role="Worker",
            )
            self._log_step("update_status_done", "success", "status=DONE")

            # ファイルロックを解放
            try:
                from utils.file_lock import FileLockManager
                FileLockManager.release_locks(self.project_id, self.task_id)
                self._log_step("file_lock_release", "success", "ロック解放完了")

                # NOTE: ロック解放後の auto_kick は削除（BACKLOG_167修正）
                # DONEステータスでは後続タスクを解除しない。
                # レビュー承認（COMPLETED）後に _step_check_successor_tasks() で解除する。

            except ImportError:
                self._log_step("file_lock_release", "skip", "FileLockManager利用不可")
            except Exception as e:
                # ロック解放失敗は警告のみ（タスクは完了している）
                self._log_step("file_lock_release", "warning", f"ロック解放エラー: {e}")

        except Exception as e:
            # ステータス更新失敗は警告のみ
            self._log_step("update_status_done", "warning", str(e))

        # 自己検証結果をchange_historyに記録
        self._record_verification_history()

    def _record_verification_history(self) -> None:
        """自己検証結果をchange_historyテーブルに記録"""
        verification = self.results.get("verification")
        if not verification:
            return

        try:
            conn = get_connection()
            try:
                description = json.dumps({
                    "final_success": verification.get("final_success", False),
                    "total_iterations": verification.get("total_iterations", 0),
                    "fix_attempts": verification.get("fix_attempts", 0),
                }, ensure_ascii=False)

                execute_query(
                    conn,
                    """
                    INSERT INTO change_history
                        (project_id, entity_type, entity_id, change_type, description, changed_by, changed_at)
                    VALUES (?, 'task', ?, 'self_verification', ?, 'Worker', ?)
                    """,
                    (self.project_id, self.task_id, description, datetime.now().isoformat())
                )
                conn.commit()
                self._log_step("verification_history", "success", "change_historyに記録")
            finally:
                conn.close()
        except Exception as e:
            # 記録失敗は警告のみ（タスクフローをブロックしない）
            self._log_step("verification_history", "warning", f"記録失敗: {e}")

    def _get_next_queued_task(self) -> Optional[str]:
        """
        同一ORDER内の次の実行可能タスクを取得
        QUEUED状態とREWORK状態のタスクを対象とする
        依存関係を考慮し、依存タスクがすべてCOMPLETEDのタスクのみを返す

        Returns:
            次のタスクID、なければNone
        """
        if not self.order_id:
            return None

        conn = get_connection()
        try:
            # 同一ORDER内のQUEUED/REWORKタスクを優先度順、作成日時順で取得
            # BLOCKEDタスクは除外（依存関係保護）
            # REWORKタスクを優先（差し戻し対応を先に処理）
            tasks = fetch_all(
                conn,
                """
                SELECT id, status FROM tasks
                WHERE project_id = ?
                  AND order_id = ?
                  AND status IN ('QUEUED', 'REWORK')
                ORDER BY
                    CASE status
                        WHEN 'REWORK' THEN 0
                        WHEN 'QUEUED' THEN 1
                        ELSE 2
                    END,
                    CASE priority
                        WHEN 'P0' THEN 0
                        WHEN 'P1' THEN 1
                        WHEN 'P2' THEN 2
                        ELSE 3
                    END,
                    created_at ASC
                """,
                (self.project_id, self.order_id)
            )

            # 各タスクの依存関係をチェックし、実行可能なタスクを返す
            for task in tasks:
                task_id = task["id"]
                if self._is_task_ready_to_execute(conn, task_id):
                    self._log_step("next_task_check", "info", f"次タスク選定: {task_id} (依存関係クリア)")
                    return task_id
                else:
                    self._log_step("next_task_check", "debug", f"タスク {task_id} は依存待ち")

            return None

        finally:
            conn.close()

    def _is_task_ready_to_execute(self, conn, task_id: str) -> bool:
        """
        タスクが実行可能かどうかをチェック
        依存タスクがすべてCOMPLETEDであり、ファイルロック競合がなければTrue

        Args:
            conn: データベース接続
            task_id: チェック対象のタスクID

        Returns:
            実行可能ならTrue、依存待ちまたはファイルロック競合ならFalse
        """
        # 依存タスクのうち、まだCOMPLETEDでないものの数をカウント
        pending_deps = fetch_one(
            conn,
            """
            SELECT COUNT(*) as count
            FROM task_dependencies td
            JOIN tasks t ON td.depends_on_task_id = t.id AND td.project_id = t.project_id
            WHERE td.task_id = ? AND td.project_id = ?
            AND t.status != 'COMPLETED'
            """,
            (task_id, self.project_id)
        )

        # 未完了の依存があれば実行不可
        if pending_deps and pending_deps["count"] > 0:
            return False

        # ファイルロック競合をチェック
        try:
            from utils.file_lock import FileLockManager
            can_start, blocking_tasks = FileLockManager.can_task_start(self.project_id, task_id)

            if not can_start:
                self._log_step(
                    "file_lock_check",
                    "debug",
                    f"タスク {task_id} はファイルロック競合（ブロック元: {', '.join(blocking_tasks)}）"
                )
                return False

        except ImportError:
            # FileLockManagerがない場合はロックチェックをスキップ
            pass
        except Exception as e:
            # ロックチェック失敗は警告のみ
            self._log_step("file_lock_check", "warning", f"ロックチェックエラー: {e}")

        return True

    def _auto_kick_unblocked_tasks(self) -> None:
        """
        ファイルロック解放後、待機タスクを自動再評価してキック

        タスク完了時に、同一ORDER内のBLOCKED/QUEUEDタスクの依存関係と
        ファイルロック状態を再評価し、実行可能になったタスクを
        BLOCKED → QUEUED に自動更新する。
        """
        if not self.order_id:
            self._log_step("auto_kick", "skip", "ORDER ID なし")
            return

        self._log_step("auto_kick", "start", f"order={self.order_id}")

        try:
            from utils.task_unblock import TaskUnblocker

            # 待機タスクを検出してキック
            kicked_tasks = TaskUnblocker.auto_kick_unblocked_tasks(
                self.project_id,
                self.order_id,
                exclude_task_id=self.task_id,
                max_kicks=10  # 一度に最大10タスクまでキック
            )

            if kicked_tasks:
                task_ids = [t["id"] for t in kicked_tasks]
                self.results["kicked_tasks"] = task_ids
                self._log_step(
                    "auto_kick",
                    "success",
                    f"{len(kicked_tasks)}タスクをキック: {', '.join(task_ids)}"
                )
            else:
                self._log_step("auto_kick", "info", "キック可能なタスクなし")

        except ImportError:
            self._log_step("auto_kick", "skip", "TaskUnblocker利用不可")
        except Exception as e:
            # キック失敗は警告のみ（タスク完了は成功している）
            self._log_step("auto_kick", "warning", f"自動キックエラー: {e}")
            if self.verbose:
                logger.exception("auto_kick詳細エラー")

    def _step_auto_review(self) -> Dict[str, Any]:
        """Step 7: レビューを自動実行"""
        self._log_step("auto_review", "start", f"model={self.review_model}")

        try:
            # ReviewProcessorをインポート
            from review.process_review import ReviewProcessor

            # レビュー処理を実行
            processor = ReviewProcessor(
                self.project_id,
                self.task_id,
                dry_run=self.dry_run,
                skip_ai=self.skip_ai,
                auto_approve=False,  # AIレビューを実行
                verbose=self.verbose,
                timeout=self.timeout,
                model=self.review_model,
            )

            result = processor.process()
            return result

        except ImportError as e:
            self._log_step("auto_review", "error", f"ReviewProcessorのインポート失敗: {e}")
            return {"success": False, "error": f"ReviewProcessorのインポート失敗: {e}"}
        except Exception as e:
            self._log_step("auto_review", "error", f"レビュー処理エラー: {e}")
            return {"success": False, "error": str(e)}

    def _step_bug_learning(self, review_result: Dict[str, Any]) -> None:
        """Step 7.5: バグパターン自動学習

        レビュー結果に応じてバグ学習を実行:
        - APPROVE: EffectivenessEvaluator.evaluate_all() を呼び出し（低頻度で実行）
        - REJECT: BugLearner.learn_from_failure() を呼び出し
        """
        try:
            from quality.bug_learner import BugLearner, EffectivenessEvaluator

            verdict = review_result.get("verdict", "")

            if verdict == "REJECT":
                # 差し戻し時: バグパターン学習を実行
                learner = BugLearner(self.project_id)
                comment = review_result.get("comment", review_result.get("review_comment", ""))
                task_title = self.task_info.get("title", "")

                learn_result = learner.learn_from_failure(
                    self.task_id, comment, task_title
                )

                self.results["bug_learning"] = learn_result
                action = learn_result.get("action_taken", "unknown")
                self._log_step("bug_learning", "info", f"action={action}")

                if learn_result.get("matched_patterns"):
                    best = learn_result["matched_patterns"][0]
                    self._log_step(
                        "bug_learning", "info",
                        f"既存パターンマッチ: {best['bug_id']} (similarity={best['similarity']})"
                    )
                elif learn_result.get("new_pattern_proposal"):
                    proposal = learn_result["new_pattern_proposal"]
                    self._log_step(
                        "bug_learning", "info",
                        f"新規パターン提案: {proposal.get('proposed_id')} - {proposal.get('title')}"
                    )

            elif verdict == "APPROVE":
                # 承認時: 有効性評価を実行（10タスクごとに実行 = タスクIDの末尾0判定）
                task_num = int(self.task_id.replace("TASK_", "")) if self.task_id.startswith("TASK_") else 0
                if task_num % 10 == 0:
                    evaluator = EffectivenessEvaluator(self.project_id)
                    eval_results = evaluator.evaluate_all()
                    deactivated = evaluator.deactivate_low_effectiveness()

                    self._log_step(
                        "bug_learning", "info",
                        f"有効性評価完了: {len(eval_results)}パターン, 非アクティブ化: {len(deactivated)}件"
                    )

        except ImportError:
            self._log_step("bug_learning", "skip", "quality.bug_learner 利用不可")
        except Exception as e:
            # バグ学習失敗は警告のみ（メインフローをブロックしない）
            self._log_step("bug_learning", "warning", f"バグ学習エラー: {e}")

    def _step_check_successor_tasks(self) -> None:
        """Step 8: 後続タスクの依存関係チェックと自動起動"""
        self._log_step("check_successors", "start", f"task={self.task_id}")

        try:
            from utils.task_unblock import TaskUnblocker

            # 後続タスクを検出し、実行可能なタスクを特定
            ready_tasks = TaskUnblocker.check_successor_dependencies(
                self.project_id,
                self.task_id
            )

            if not ready_tasks:
                self._log_step("check_successors", "info", "実行可能な後続タスクなし")
                return

            # 実行可能な後続タスクをBLOCKED → QUEUEDに更新
            kicked_successors = []
            for task in ready_tasks:
                task_id = task["id"]
                updated, new_status = TaskUnblocker.update_task_status_if_unblocked(
                    self.project_id,
                    task_id
                )

                if updated:
                    kicked_successors.append(task_id)
                    self._log_step(
                        "successor_kick",
                        "success",
                        f"{task_id}: {task.get('status')} → {new_status}"
                    )

            if kicked_successors:
                self.results["kicked_successors"] = kicked_successors
                self._log_step(
                    "check_successors",
                    "success",
                    f"{len(kicked_successors)}タスクを自動起動: {', '.join(kicked_successors)}"
                )
            else:
                self._log_step("check_successors", "info", "後続タスクは既にQUEUED/実行中")

        except ImportError:
            self._log_step("check_successors", "skip", "TaskUnblocker利用不可")
        except Exception as e:
            # 後続タスクチェック失敗は警告のみ（現在のタスクは完了している）
            self._log_step("check_successors", "warning", f"後続タスクチェックエラー: {e}")
            if self.verbose:
                logger.exception("check_successors詳細エラー")


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="Worker処理を1コマンドで実行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("task_id", help="タスクID（例: 602 または TASK_602）")
    parser.add_argument("--dry-run", action="store_true", help="実行計画のみ表示")
    parser.add_argument("--skip-ai", action="store_true", help="AI処理をスキップ")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--timeout", type=int, default=1800, help="タイムアウト秒数（デフォルト: 1800秒=30分）")
    parser.add_argument("--model", help="AIモデル（haiku/sonnet/opus）")
    parser.add_argument("--auto-review", action="store_true", default=True, help="Worker完了後にレビューを自動実行（デフォルト: 有効）")
    parser.add_argument("--no-review", action="store_true", help="自動レビューを無効化（手動レビューする場合）")
    parser.add_argument("--review-model", default="sonnet", help="レビュー用AIモデル（デフォルト: sonnet）")
    parser.add_argument("--loop", action="store_true", help="タスク完了後に次のQUEUEDタスクを自動起動（連続実行モード）")
    parser.add_argument("--max-tasks", type=int, default=100, help="連続実行時の最大タスク数（デフォルト: 100）")
    parser.add_argument("--is-rework", action="store_true", help="リワークモードで実行（差し戻し対応）")
    parser.add_argument("--rework-comment", help="差し戻しコメント（問題点・修正指針）")
    parser.add_argument("--parallel", action="store_true", help="並列起動モード（ORDER開始時に並列タスクを自動検出・起動）")
    parser.add_argument("--max-workers", type=int, default=5, help="並列起動時の最大Worker数（デフォルト: 5）")
    parser.add_argument("--allowed-tools", type=str, default=None,
                        help="カンマ区切りの許可ツールリスト（例: Read,Write,Bash）。未指定時はデフォルト権限を使用")

    args = parser.parse_args()

    # 詳細ログモード
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 並列起動モード
    if args.parallel:
        try:
            from worker.parallel_launcher import ParallelWorkerLauncher

            # タスクIDからORDER_IDを取得
            conn = get_connection()
            try:
                task_row = fetch_one(
                    conn,
                    "SELECT order_id FROM tasks WHERE id = ? AND project_id = ?",
                    (f"TASK_{args.task_id}" if not args.task_id.startswith("TASK_") else args.task_id, args.project_id)
                )

                if not task_row or not task_row["order_id"]:
                    print("エラー: タスクに紐付くORDERが見つかりません", file=sys.stderr)
                    sys.exit(1)

                order_id = task_row["order_id"]

            finally:
                conn.close()

            # allowed_tools パース（並列起動モード用）
            parallel_allowed_tools = None
            if args.allowed_tools:
                parallel_allowed_tools = [t.strip() for t in args.allowed_tools.split(",") if t.strip()]

            # 並列Workerを起動
            launcher = ParallelWorkerLauncher(
                args.project_id,
                order_id,
                max_workers=args.max_workers,
                dry_run=args.dry_run,
                verbose=args.verbose,
                timeout=args.timeout,
                model=args.model,
                no_review=args.no_review,
                allowed_tools=parallel_allowed_tools,
            )

            results = launcher.launch()

            # 結果表示
            if args.json:
                print(json.dumps(results, ensure_ascii=False, indent=2))
            else:
                from worker.parallel_launcher import display_results
                display_results(results, json_output=False)

            # Exit code
            if results["launched_count"] > 0:
                sys.exit(0)
            else:
                sys.exit(1)

        except ImportError as e:
            print(f"エラー: 並列起動モジュールのインポート失敗 - {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"エラー: 並列起動失敗 - {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    # ループ実行用変数
    current_task_id = args.task_id
    executed_count = 0
    all_results = []

    while True:
        executed_count += 1

        # 最大タスク数チェック
        if executed_count > args.max_tasks:
            logger.warning(f"最大タスク数 ({args.max_tasks}) に達しました。ループを終了します。")
            break

        # allowed_tools パース
        allowed_tools = None
        if args.allowed_tools:
            allowed_tools = [t.strip() for t in args.allowed_tools.split(",") if t.strip()]

        # Worker処理実行
        executor = WorkerExecutor(
            args.project_id,
            current_task_id,
            dry_run=args.dry_run,
            skip_ai=args.skip_ai,
            verbose=args.verbose,
            timeout=args.timeout,
            model=args.model,
            auto_review=args.auto_review and not args.no_review,
            review_model=args.review_model,
            loop=args.loop,
            max_tasks=args.max_tasks,
            is_rework=args.is_rework,
            rework_comment=args.rework_comment,
            allowed_tools=allowed_tools,
        )

        results = executor.execute()
        all_results.append(results)

        # 出力
        if args.json:
            # 大きなコンテンツは除外
            output = {k: v for k, v in results.items() if k not in ("execution_result",)}
            print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        else:
            if results["success"]:
                print(f"【Worker処理完了】{results['task_id']} ({executed_count}/{args.max_tasks if args.loop else 1})")
                print(f"  プロジェクト: {results['project_id']}")
                print(f"  Worker: {results.get('worker_id', 'Auto')}")
                if results.get("report_file"):
                    print(f"  REPORT: {results['report_file']}")
                # 自動レビュー結果の表示
                review_result = results.get("review_result")
                if review_result:
                    if review_result.get("success"):
                        verdict = review_result.get("verdict", "UNKNOWN")
                        print(f"  【自動レビュー】{verdict}")
                        if review_result.get("review_file"):
                            print(f"  REVIEW: {review_result['review_file']}")
                    else:
                        print(f"  【自動レビュー】失敗: {review_result.get('error', '不明')}")
            else:
                print(f"【Worker処理失敗】{results.get('error', '不明なエラー')}", file=sys.stderr)
                sys.exit(1)

        # ループモードでない場合、または次タスクがない場合は終了
        if not args.loop:
            break

        next_task = results.get("next_task")
        if not next_task:
            print("\n【連続実行完了】QUEUEDタスクがなくなりました。")
            print(f"  実行タスク数: {executed_count}")
            break

        # 次タスクへ
        print(f"\n【次タスク起動】{next_task}")
        current_task_id = next_task


if __name__ == "__main__":
    main()
