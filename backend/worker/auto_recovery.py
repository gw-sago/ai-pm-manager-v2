#!/usr/bin/env python3
"""
統合リカバリ戦略エンジン

エラー発生時に:
1. error_patternsテーブルからエラーを自動分類
2. エラー種別に応じた最適なリカバリ戦略を選択
3. リカバリを実行（RETRY/SKIP/ROLLBACK/ESCALATE）

既存モジュール（retry_handler, incidents, rollback, snapshot_manager）を統合する。
"""

from dataclasses import dataclass, field
from enum import Enum
import re
import logging
import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# プロジェクトルートの解決
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent

# sys.path にパッケージルートを追加（既存モジュールのインポート用）
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

# --- 既存モジュールの条件付きインポート ---
# 各モジュールが利用不可の場合は内部実装にフォールバック

try:
    from worker.snapshot_manager import SnapshotManager
    HAS_SNAPSHOT_MANAGER = True
except ImportError:
    HAS_SNAPSHOT_MANAGER = False
    logger.debug("snapshot_manager が利用不可。内部フォールバックを使用。")

try:
    from rollback.auto_rollback import rollback_to_checkpoint
    HAS_AUTO_ROLLBACK = True
except ImportError:
    HAS_AUTO_ROLLBACK = False
    logger.debug("auto_rollback が利用不可。DB復元はスキップ。")

try:
    from incidents.create import create_incident
    HAS_INCIDENTS = True
except ImportError:
    HAS_INCIDENTS = False
    logger.debug("incidents.create が利用不可。直接SQL記録にフォールバック。")

try:
    from retry.retry_handler import RetryHandler
    HAS_RETRY_HANDLER = True
except ImportError:
    HAS_RETRY_HANDLER = False
    logger.debug("retry_handler が利用不可。内部カウントを使用。")


class ErrorCategory(Enum):
    """エラーカテゴリ（error_patternsテーブルのcategory列と対応）"""
    RETRYABLE = "RETRYABLE"
    SYSTEM = "SYSTEM"
    LOGIC = "LOGIC"
    ENVIRONMENT = "ENVIRONMENT"
    UNKNOWN = "UNKNOWN"


class RecoveryAction(Enum):
    """リカバリアクション"""
    RETRY = "RETRY"
    SKIP = "SKIP"
    ROLLBACK = "ROLLBACK"
    ESCALATE = "ESCALATE"


@dataclass
class ErrorAnalysis:
    """エラー分析結果"""
    pattern_id: Optional[str]       # マッチしたパターンID（EP_001等）、未マッチはNone
    pattern_name: Optional[str]     # パターン名
    category: ErrorCategory         # エラーカテゴリ
    confidence: float               # 0.0-1.0（パターンマッチ=1.0、ヒューリスティック<1.0）
    error_message: str              # 元のエラーメッセージ
    matched_regex: Optional[str]    # マッチした正規表現


@dataclass
class RecoveryStrategy:
    """リカバリ戦略"""
    action: RecoveryAction          # 実行するアクション
    max_retries: int                # このパターンの最大リトライ回数
    current_retry: int              # 現在のリトライ回数
    should_rollback_files: bool     # ファイルスナップショット復元するか
    should_rollback_db: bool        # DBチェックポイント復元するか
    reason: str                     # 戦略選択理由


@dataclass
class RecoveryResult:
    """リカバリ実行結果"""
    success: bool                   # リカバリ成功したか
    action_taken: RecoveryAction    # 実行したアクション
    message: str                    # 結果メッセージ
    next_status: str                # タスクの次ステータス（REWORK/SKIPPED等）
    retry_count: int                # 現在のリトライカウント


# タスクのステータスCHECK制約に存在する有効ステータス一覧
_VALID_TASK_STATUSES = {
    "QUEUED", "BLOCKED", "IN_PROGRESS", "DONE", "IN_REVIEW",
    "REWORK", "COMPLETED", "CANCELLED", "SKIPPED", "REJECTED",
}


class AutoRecoveryEngine:
    """統合リカバリ戦略エンジン

    エラー発生時にerror_patternsテーブルを参照してエラーを自動分類し、
    最適なリカバリ戦略（RETRY/SKIP/ROLLBACK/ESCALATE）を選択・実行する。
    """

    def __init__(self, db_path: Optional[str] = None, project_id: Optional[str] = None):
        """
        Args:
            db_path: DBパス（デフォルト: data/aipm.db）
            project_id: プロジェクトID
        """
        # BUG_001対策: ミュータブルデフォルト引数を使わずNoneで初期化
        if db_path is None:
            db_path = str(_project_root / "data" / "aipm.db")
        self.db_path = db_path
        self.project_id = project_id
        self._pattern_cache = None  # パターンキャッシュ（list[dict] or None）

    def analyze_error(self, error_message: str, traceback_text: Optional[str] = None) -> ErrorAnalysis:
        """
        エラーメッセージをerror_patternsテーブルと照合して分類

        処理:
        1. error_patternsテーブルから全パターンを取得（キャッシュ利用）
        2. 各パターンのregex_patternでerror_messageをマッチ
        3. traceback_textも参照（あれば）
        4. マッチした場合: パターン情報を返す（confidence=1.0）
        5. マッチしない場合: ヒューリスティック分析

        Args:
            error_message: エラーメッセージ
            traceback_text: トレースバック文字列（任意）

        Returns:
            ErrorAnalysis: エラー分析結果
        """
        # 検索対象テキスト（エラーメッセージ + トレースバック）
        search_text = error_message
        if traceback_text:
            search_text = f"{error_message}\n{traceback_text}"

        # error_patternsテーブルから全パターンを取得
        patterns = self._load_patterns()

        # 各パターンの正規表現でマッチを試行
        for pattern in patterns:
            regex_str = pattern.get("regex_pattern", "")
            if not regex_str:
                continue

            try:
                if re.search(regex_str, search_text, re.IGNORECASE):
                    # パターンマッチ成功
                    category_str = pattern.get("category", "UNKNOWN")
                    try:
                        category = ErrorCategory(category_str)
                    except ValueError:
                        category = ErrorCategory.UNKNOWN

                    logger.info(
                        "エラーパターンマッチ: %s (%s) - category=%s",
                        pattern.get("id"),
                        pattern.get("pattern_name"),
                        category_str,
                    )

                    return ErrorAnalysis(
                        pattern_id=pattern.get("id"),
                        pattern_name=pattern.get("pattern_name"),
                        category=category,
                        confidence=1.0,
                        error_message=error_message,
                        matched_regex=regex_str,
                    )
            except re.error as e:
                logger.warning(
                    "無効な正規表現: pattern_id=%s, regex=%s, error=%s",
                    pattern.get("id"),
                    regex_str,
                    e,
                )
                continue

        # マッチしない場合: ヒューリスティック分析
        return self._heuristic_analysis(error_message)

    def determine_strategy(
        self,
        analysis: ErrorAnalysis,
        task_id: str,
        retry_count: int = 0,
    ) -> RecoveryStrategy:
        """
        エラー分析結果とタスク状態からリカバリ戦略を決定

        ロジック:
        - パターンマッチあり（confidence=1.0）:
          - recommended_action=RETRY かつ retry_count < max_retries -> RETRY
          - recommended_action=RETRY かつ retry_count >= max_retries -> ESCALATE
          - recommended_action=SKIP -> SKIP
          - recommended_action=ROLLBACK -> ROLLBACK（ファイル復元+リトライ）
          - recommended_action=ESCALATE -> ESCALATE
        - ヒューリスティック（confidence<1.0）:
          - RETRYABLE -> RETRY（max_retries=2）
          - SYSTEM -> SKIP
          - UNKNOWN -> ESCALATE

        Args:
            analysis: エラー分析結果
            task_id: タスクID
            retry_count: 現在のリトライ回数

        Returns:
            RecoveryStrategy: リカバリ戦略
        """
        # パターンマッチ時の戦略決定（confidence == 1.0）
        if analysis.confidence >= 1.0 and analysis.pattern_id is not None:
            return self._strategy_from_pattern(analysis, task_id, retry_count)

        # ヒューリスティック分析時の戦略決定
        return self._strategy_from_heuristic(analysis, task_id, retry_count)

    def execute_recovery(
        self,
        task_id: str,
        order_id: str,
        strategy: RecoveryStrategy,
        snapshot_id: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
    ) -> RecoveryResult:
        """
        戦略に基づいてリカバリ実行

        処理:
        - RETRY: タスクステータスをREWORKに更新
        - SKIP: タスクステータスをSKIPPEDに更新
        - ROLLBACK: スナップショット/チェックポイント復元 + REWORKに更新
        - ESCALATE: タスクステータスをCANCELLEDに更新（ESCALATED非対応のためフォールバック）

        全ケースでincident記録を行う。

        Args:
            task_id: タスクID
            order_id: ORDER ID
            strategy: 実行するリカバリ戦略
            snapshot_id: ファイルスナップショットID（ROLLBACK時に使用）
            checkpoint_id: DBチェックポイントID（ROLLBACK時に使用）

        Returns:
            RecoveryResult: リカバリ実行結果
        """
        action = strategy.action

        try:
            if action == RecoveryAction.RETRY:
                result = self._execute_retry(task_id, strategy)

            elif action == RecoveryAction.SKIP:
                result = self._execute_skip(task_id, strategy)

            elif action == RecoveryAction.ROLLBACK:
                result = self._execute_rollback(
                    task_id, order_id, strategy, snapshot_id, checkpoint_id
                )

            elif action == RecoveryAction.ESCALATE:
                result = self._execute_escalate(task_id, strategy)

            else:
                # 未知のアクション -> ESCALATEにフォールバック
                logger.warning("未知のリカバリアクション: %s -> ESCALATEにフォールバック", action)
                result = self._execute_escalate(task_id, strategy)

        except Exception as e:
            logger.error("リカバリ実行中にエラー: %s", e)
            result = RecoveryResult(
                success=False,
                action_taken=action,
                message=f"リカバリ実行失敗: {e}",
                next_status="REWORK",
                retry_count=strategy.current_retry,
            )

        logger.info(
            "リカバリ結果: task=%s, action=%s, success=%s, next_status=%s",
            task_id,
            result.action_taken.value,
            result.success,
            result.next_status,
        )

        return result

    def record_incident(
        self,
        task_id: str,
        order_id: str,
        analysis: ErrorAnalysis,
        strategy: RecoveryStrategy,
        result: RecoveryResult,
    ):
        """
        インシデント記録

        既存 incidents/create.py を可能なら利用。
        利用できない場合は直接SQLで記録。
        pattern_idがあればincidentsテーブルに記録。

        Args:
            task_id: タスクID
            order_id: ORDER ID
            analysis: エラー分析結果
            strategy: 実行したリカバリ戦略
            result: リカバリ実行結果
        """
        description = (
            f"AutoRecovery: {result.action_taken.value} - "
            f"{analysis.error_message[:200]}"
        )
        root_cause = (
            f"Pattern: {analysis.pattern_id or 'heuristic'} "
            f"({analysis.category.value}, confidence={analysis.confidence:.1f})"
        )
        resolution = (
            f"Action: {result.action_taken.value}, "
            f"Success: {result.success}, "
            f"NextStatus: {result.next_status}, "
            f"Reason: {strategy.reason}"
        )

        if HAS_INCIDENTS and self.project_id:
            try:
                incident_id = create_incident(
                    project_id=self.project_id,
                    task_id=task_id,
                    category="WORKER_FAILURE",
                    description=description,
                    root_cause=root_cause,
                    severity="MEDIUM",
                    order_id=order_id,
                )
                logger.info("インシデント記録（incidents.create利用）: %s", incident_id)
                return
            except Exception as e:
                logger.warning(
                    "incidents.create によるインシデント記録に失敗: %s -> 直接SQLにフォールバック",
                    e,
                )

        # 直接SQLによるインシデント記録（フォールバック）
        self._record_incident_direct(
            task_id=task_id,
            order_id=order_id,
            description=description,
            root_cause=root_cause,
            resolution=resolution,
            pattern_id=analysis.pattern_id,
        )

    # -----------------------------------------------------------------------
    # 内部メソッド
    # -----------------------------------------------------------------------

    def _load_patterns(self) -> list:
        """
        error_patternsテーブルから全パターンを取得（キャッシュ利用）

        Returns:
            list[dict]: パターン辞書のリスト
        """
        if self._pattern_cache is not None:
            return self._pattern_cache

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM error_patterns ORDER BY id"
            ).fetchall()
            # BUG_003対策: sqlite3.Row.get()は使用禁止。dictに変換して使う
            self._pattern_cache = [dict(row) for row in rows]
            logger.debug(
                "error_patterns ロード完了: %d パターン", len(self._pattern_cache)
            )
            return self._pattern_cache
        except sqlite3.OperationalError as e:
            logger.warning("error_patternsテーブルの読み込みに失敗: %s", e)
            self._pattern_cache = []
            return self._pattern_cache
        finally:
            conn.close()

    def _heuristic_analysis(self, error_message: str) -> ErrorAnalysis:
        """
        パターン未マッチ時のヒューリスティックエラー分析

        ルール:
        - "Error"を含む -> RETRYABLE (confidence=0.5)
        - "Fatal"/"Critical"を含む -> SYSTEM (confidence=0.4)
        - それ以外 -> UNKNOWN (confidence=0.3)

        Args:
            error_message: エラーメッセージ

        Returns:
            ErrorAnalysis: ヒューリスティック分析結果
        """
        msg_lower = error_message.lower()

        if "fatal" in msg_lower or "critical" in msg_lower:
            category = ErrorCategory.SYSTEM
            confidence = 0.4
        elif "error" in msg_lower:
            category = ErrorCategory.RETRYABLE
            confidence = 0.5
        else:
            category = ErrorCategory.UNKNOWN
            confidence = 0.3

        logger.info(
            "ヒューリスティック分析: category=%s, confidence=%.1f",
            category.value,
            confidence,
        )

        return ErrorAnalysis(
            pattern_id=None,
            pattern_name=None,
            category=category,
            confidence=confidence,
            error_message=error_message,
            matched_regex=None,
        )

    def _strategy_from_pattern(
        self,
        analysis: ErrorAnalysis,
        task_id: str,
        retry_count: int,
    ) -> RecoveryStrategy:
        """
        パターンマッチ結果からリカバリ戦略を決定

        Args:
            analysis: エラー分析結果（パターンマッチ済み）
            task_id: タスクID
            retry_count: 現在のリトライ回数

        Returns:
            RecoveryStrategy: リカバリ戦略
        """
        # パターンからrecommended_actionとmax_retriesを取得
        patterns = self._load_patterns()
        pattern_data = None
        for p in patterns:
            if p.get("id") == analysis.pattern_id:
                pattern_data = p
                break

        if pattern_data is None:
            # パターンが見つからない場合（キャッシュ不整合等）
            return self._strategy_from_heuristic(analysis, task_id, retry_count)

        recommended_action_str = pattern_data.get("recommended_action", "ESCALATE")
        max_retries = pattern_data.get("max_retries", 3)

        try:
            recommended_action = RecoveryAction(recommended_action_str)
        except ValueError:
            recommended_action = RecoveryAction.ESCALATE

        # RETRY の場合: リトライ上限チェック
        if recommended_action == RecoveryAction.RETRY:
            if retry_count < max_retries:
                return RecoveryStrategy(
                    action=RecoveryAction.RETRY,
                    max_retries=max_retries,
                    current_retry=retry_count,
                    should_rollback_files=False,
                    should_rollback_db=False,
                    reason=(
                        f"パターン {analysis.pattern_id} ({analysis.pattern_name}): "
                        f"RETRY推奨, リトライ {retry_count + 1}/{max_retries}"
                    ),
                )
            else:
                return RecoveryStrategy(
                    action=RecoveryAction.ESCALATE,
                    max_retries=max_retries,
                    current_retry=retry_count,
                    should_rollback_files=False,
                    should_rollback_db=False,
                    reason=(
                        f"パターン {analysis.pattern_id} ({analysis.pattern_name}): "
                        f"リトライ上限到達 ({retry_count}/{max_retries}), ESCALATEに昇格"
                    ),
                )

        # SKIP の場合
        if recommended_action == RecoveryAction.SKIP:
            return RecoveryStrategy(
                action=RecoveryAction.SKIP,
                max_retries=max_retries,
                current_retry=retry_count,
                should_rollback_files=False,
                should_rollback_db=False,
                reason=(
                    f"パターン {analysis.pattern_id} ({analysis.pattern_name}): "
                    f"SKIP推奨（リトライ不適切なエラー種別）"
                ),
            )

        # ROLLBACK の場合: ファイル復元 + DB復元 + リトライ
        if recommended_action == RecoveryAction.ROLLBACK:
            return RecoveryStrategy(
                action=RecoveryAction.ROLLBACK,
                max_retries=max_retries,
                current_retry=retry_count,
                should_rollback_files=True,
                should_rollback_db=True,
                reason=(
                    f"パターン {analysis.pattern_id} ({analysis.pattern_name}): "
                    f"ROLLBACK推奨（ファイル・DB復元後にリトライ）"
                ),
            )

        # ESCALATE の場合
        return RecoveryStrategy(
            action=RecoveryAction.ESCALATE,
            max_retries=max_retries,
            current_retry=retry_count,
            should_rollback_files=False,
            should_rollback_db=False,
            reason=(
                f"パターン {analysis.pattern_id} ({analysis.pattern_name}): "
                f"ESCALATE推奨（人手介入が必要）"
            ),
        )

    def _strategy_from_heuristic(
        self,
        analysis: ErrorAnalysis,
        task_id: str,
        retry_count: int,
    ) -> RecoveryStrategy:
        """
        ヒューリスティック分析結果からリカバリ戦略を決定

        ルール:
        - RETRYABLE -> RETRY（max_retries=2）
        - SYSTEM -> SKIP
        - UNKNOWN/その他 -> ESCALATE

        Args:
            analysis: ヒューリスティック分析結果
            task_id: タスクID
            retry_count: 現在のリトライ回数

        Returns:
            RecoveryStrategy: リカバリ戦略
        """
        if analysis.category == ErrorCategory.RETRYABLE:
            max_retries = 2
            if retry_count < max_retries:
                return RecoveryStrategy(
                    action=RecoveryAction.RETRY,
                    max_retries=max_retries,
                    current_retry=retry_count,
                    should_rollback_files=False,
                    should_rollback_db=False,
                    reason=(
                        f"ヒューリスティック: RETRYABLE (confidence={analysis.confidence:.1f}), "
                        f"リトライ {retry_count + 1}/{max_retries}"
                    ),
                )
            else:
                return RecoveryStrategy(
                    action=RecoveryAction.ESCALATE,
                    max_retries=max_retries,
                    current_retry=retry_count,
                    should_rollback_files=False,
                    should_rollback_db=False,
                    reason=(
                        f"ヒューリスティック: RETRYABLE だがリトライ上限到達 "
                        f"({retry_count}/{max_retries})"
                    ),
                )

        if analysis.category == ErrorCategory.SYSTEM:
            return RecoveryStrategy(
                action=RecoveryAction.SKIP,
                max_retries=0,
                current_retry=retry_count,
                should_rollback_files=False,
                should_rollback_db=False,
                reason=(
                    f"ヒューリスティック: SYSTEM (confidence={analysis.confidence:.1f}), "
                    f"リトライ不適切のためSKIP"
                ),
            )

        # UNKNOWN, ENVIRONMENT, LOGIC, その他 -> ESCALATE
        return RecoveryStrategy(
            action=RecoveryAction.ESCALATE,
            max_retries=0,
            current_retry=retry_count,
            should_rollback_files=False,
            should_rollback_db=False,
            reason=(
                f"ヒューリスティック: {analysis.category.value} "
                f"(confidence={analysis.confidence:.1f}), 人手介入が必要"
            ),
        )

    def _execute_retry(self, task_id: str, strategy: RecoveryStrategy) -> RecoveryResult:
        """RETRY実行: タスクステータスをREWORKに更新"""
        self._update_task_status(task_id, "REWORK")

        return RecoveryResult(
            success=True,
            action_taken=RecoveryAction.RETRY,
            message=(
                f"タスク {task_id} をREWORKに更新。"
                f"リトライ {strategy.current_retry + 1}/{strategy.max_retries}"
            ),
            next_status="REWORK",
            retry_count=strategy.current_retry + 1,
        )

    def _execute_skip(self, task_id: str, strategy: RecoveryStrategy) -> RecoveryResult:
        """SKIP実行: タスクステータスをSKIPPEDに更新"""
        self._update_task_status(task_id, "SKIPPED")

        return RecoveryResult(
            success=True,
            action_taken=RecoveryAction.SKIP,
            message=f"タスク {task_id} をSKIPPEDに更新。理由: {strategy.reason}",
            next_status="SKIPPED",
            retry_count=strategy.current_retry,
        )

    def _execute_rollback(
        self,
        task_id: str,
        order_id: str,
        strategy: RecoveryStrategy,
        snapshot_id: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
    ) -> RecoveryResult:
        """ROLLBACK実行: スナップショット/チェックポイント復元後、REWORKに更新"""
        rollback_details = []

        # 1. ファイルスナップショット復元
        if strategy.should_rollback_files and snapshot_id:
            if HAS_SNAPSHOT_MANAGER and self.project_id:
                try:
                    sm = SnapshotManager(self.project_id)
                    restore_result = sm.restore_snapshot(snapshot_id)
                    if restore_result.get("success"):
                        file_count = len(restore_result.get("restored_files", []))
                        rollback_details.append(
                            f"ファイル復元成功: {file_count}件"
                        )
                    else:
                        errors = restore_result.get("errors", [])
                        rollback_details.append(
                            f"ファイル復元に一部エラー: {len(errors)}件"
                        )
                except Exception as e:
                    logger.warning("ファイルスナップショット復元失敗: %s", e)
                    rollback_details.append(f"ファイル復元失敗: {e}")
            else:
                rollback_details.append("snapshot_manager 利用不可、ファイル復元スキップ")

        # 2. DBチェックポイント復元
        if strategy.should_rollback_db and checkpoint_id:
            if HAS_AUTO_ROLLBACK and self.project_id:
                try:
                    rb_result = rollback_to_checkpoint(
                        project_id=self.project_id,
                        task_id=task_id,
                        checkpoint_id=checkpoint_id,
                    )
                    if rb_result.success:
                        rollback_details.append("DB復元成功")
                    else:
                        rollback_details.append(
                            f"DB復元失敗: {rb_result.error_message}"
                        )
                except Exception as e:
                    logger.warning("DBチェックポイント復元失敗: %s", e)
                    rollback_details.append(f"DB復元失敗: {e}")
            else:
                rollback_details.append("auto_rollback 利用不可、DB復元スキップ")

        # 3. タスクステータスをREWORKに更新
        self._update_task_status(task_id, "REWORK")

        detail_str = "; ".join(rollback_details) if rollback_details else "復元対象なし"

        return RecoveryResult(
            success=True,
            action_taken=RecoveryAction.ROLLBACK,
            message=f"タスク {task_id} をROLLBACK+REWORKに更新。{detail_str}",
            next_status="REWORK",
            retry_count=strategy.current_retry + 1,
        )

    def _execute_escalate(self, task_id: str, strategy: RecoveryStrategy) -> RecoveryResult:
        """ESCALATE実行: 人手介入が必要

        NOTE: tasksテーブルのCHECK制約に'ESCALATED'は含まれないため、
        CANCELLEDステータスを使用し、インシデント記録でESCALATE情報を残す。
        """
        # CANCELLEDをESCALATEのフォールバックステータスとして使用
        # （tasksテーブルのCHECK制約に'ESCALATED'が存在しないため）
        fallback_status = "CANCELLED"
        self._update_task_status(task_id, fallback_status)

        return RecoveryResult(
            success=True,
            action_taken=RecoveryAction.ESCALATE,
            message=(
                f"タスク {task_id} をESCALATE（{fallback_status}に更新）。"
                f"理由: {strategy.reason}"
            ),
            next_status=fallback_status,
            retry_count=strategy.current_retry,
        )

    def _update_task_status(self, task_id: str, new_status: str):
        """タスクステータスをDB上で更新（直接SQL）

        BUG_004対策: DONE -> REJECTED は絶対に行わない。
        ステータスがDONEの場合、REJECTEDには遷移させず常にREWORKを経由する。

        Args:
            task_id: タスクID
            new_status: 新しいステータス
        """
        # 有効ステータスかチェック
        if new_status not in _VALID_TASK_STATUSES:
            logger.warning(
                "無効なステータス '%s' が指定されました。更新をスキップ。",
                new_status,
            )
            return

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            # 現在のステータスを取得
            if self.project_id:
                row = conn.execute(
                    "SELECT status FROM tasks WHERE id = ? AND project_id = ?",
                    (task_id, self.project_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT status FROM tasks WHERE id = ?",
                    (task_id,),
                ).fetchone()

            if row is None:
                logger.warning("タスクが見つかりません: %s", task_id)
                return

            # BUG_003対策: sqlite3.Rowはdict変換またはキーアクセス
            current_status = row["status"]

            # BUG_004対策: DONE -> REJECTED 禁止
            if current_status == "DONE" and new_status == "REJECTED":
                logger.warning(
                    "BUG_004: DONE -> REJECTED は禁止。REWORK に変更します。"
                )
                new_status = "REWORK"

            # ステータス更新
            now = datetime.now().isoformat()
            if self.project_id:
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ? AND project_id = ?",
                    (new_status, now, task_id, self.project_id),
                )
            else:
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                    (new_status, now, task_id),
                )
            conn.commit()

            logger.info(
                "タスクステータス更新: %s: %s -> %s",
                task_id,
                current_status,
                new_status,
            )

        except sqlite3.Error as e:
            logger.error("タスクステータス更新失敗: %s - %s", task_id, e)
            raise
        finally:
            conn.close()

    def _record_incident_direct(
        self,
        task_id: str,
        order_id: str,
        description: str,
        root_cause: str,
        resolution: str,
        pattern_id: Optional[str] = None,
    ):
        """直接SQLによるインシデント記録（incidents.createが使えない場合のフォールバック）

        Args:
            task_id: タスクID
            order_id: ORDER ID
            description: インシデント説明
            root_cause: 根本原因
            resolution: 解決策
            pattern_id: マッチしたパターンID（あれば）
        """
        timestamp = datetime.now().isoformat()
        incident_id = f"INC_{timestamp.replace(':', '').replace('-', '').replace('.', '_')}"

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """INSERT INTO incidents
                   (incident_id, timestamp, project_id, order_id, task_id,
                    category, severity, description, root_cause, resolution, pattern_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    incident_id,
                    timestamp,
                    self.project_id or "",
                    order_id,
                    task_id,
                    "WORKER_FAILURE",
                    "MEDIUM",
                    description,
                    root_cause,
                    resolution,
                    pattern_id,
                ),
            )
            conn.commit()
            logger.info("インシデント記録（直接SQL）: %s", incident_id)
        except sqlite3.Error as e:
            logger.error("インシデント記録失敗: %s", e)
        finally:
            conn.close()

    def clear_pattern_cache(self):
        """パターンキャッシュをクリア（テスト用・パターン更新後に使用）"""
        self._pattern_cache = None
        logger.debug("パターンキャッシュをクリアしました")

    def get_retry_count(self, task_id: str) -> int:
        """
        既存のRetryHandlerを利用してリトライ回数を取得（利用可能な場合）

        利用不可の場合はincidentsテーブルから直接カウント。

        Args:
            task_id: タスクID

        Returns:
            int: リトライ回数
        """
        if HAS_RETRY_HANDLER and self.project_id:
            try:
                handler = RetryHandler(self.project_id, task_id)
                return handler.get_retry_count()
            except Exception as e:
                logger.warning("RetryHandler からのリトライ数取得に失敗: %s", e)

        # フォールバック: 直接SQLでカウント
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """SELECT COUNT(*) as count FROM incidents
                   WHERE task_id = ? AND category = 'WORKER_FAILURE'""",
                (task_id,),
            ).fetchone()
            # BUG_003対策: dict変換またはキーアクセス
            return row["count"] if row else 0
        except sqlite3.Error as e:
            logger.warning("リトライ数の取得に失敗: %s", e)
            return 0
        finally:
            conn.close()

    def recover(
        self,
        task_id: str,
        order_id: str,
        error_message: str,
        traceback_text: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
    ) -> RecoveryResult:
        """
        エラーからの統合リカバリ（ワンショットAPI）

        analyze_error -> determine_strategy -> execute_recovery -> record_incident
        を一貫して実行する便利メソッド。

        Args:
            task_id: タスクID
            order_id: ORDER ID
            error_message: エラーメッセージ
            traceback_text: トレースバック文字列（任意）
            snapshot_id: ファイルスナップショットID（任意）
            checkpoint_id: DBチェックポイントID（任意）

        Returns:
            RecoveryResult: リカバリ実行結果
        """
        # 1. エラー分析
        analysis = self.analyze_error(error_message, traceback_text)
        logger.info(
            "エラー分析完了: pattern=%s, category=%s, confidence=%.1f",
            analysis.pattern_id or "N/A",
            analysis.category.value,
            analysis.confidence,
        )

        # 2. リトライ回数取得
        retry_count = self.get_retry_count(task_id)

        # 3. 戦略決定
        strategy = self.determine_strategy(analysis, task_id, retry_count)
        logger.info(
            "戦略決定: action=%s, reason=%s",
            strategy.action.value,
            strategy.reason,
        )

        # 4. リカバリ実行
        result = self.execute_recovery(
            task_id, order_id, strategy, snapshot_id, checkpoint_id
        )

        # 5. インシデント記録
        try:
            self.record_incident(task_id, order_id, analysis, strategy, result)
        except Exception as e:
            logger.error("インシデント記録に失敗（リカバリ自体は完了）: %s", e)

        return result
