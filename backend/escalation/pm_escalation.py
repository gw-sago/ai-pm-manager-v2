#!/usr/bin/env python3
"""
AI PM Framework - PM Escalation Module

REWORK回数がエスカレーション閾値に到達した場合、
PMにタスク再設計を依頼し、以下の対策を実施する:
- 要件再定義
- サブタスク分割
- アプローチ変更指示
- 先行タスク追加

Usage:
    from escalation.pm_escalation import PMEscalationHandler

    handler = PMEscalationHandler(
        project_id="ai_pm_manager",
        task_id="TASK_123",
        order_id="ORDER_100",
    )
    result = handler.escalate()
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

logger = logging.getLogger(__name__)

from utils.db import (
    get_connection, execute_query, fetch_one, fetch_all,
    row_to_dict, rows_to_dicts, DatabaseError
)
from escalation.log_escalation import log_escalation, EscalationType


class PMEscalationError(Exception):
    """PMエスカレーションエラー"""
    pass


class PMEscalationResult:
    """PMエスカレーション処理結果"""

    def __init__(self):
        self.success: bool = False
        self.action: str = ""  # "redesign", "subtask_split", "approach_change", "rejected"
        self.original_task_id: str = ""
        self.new_task_ids: List[str] = []
        self.redesign_summary: str = ""
        self.error: Optional[str] = None
        self.escalation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "original_task_id": self.original_task_id,
            "new_task_ids": self.new_task_ids,
            "redesign_summary": self.redesign_summary,
            "error": self.error,
            "escalation_id": self.escalation_id,
        }


class PMEscalationHandler:
    """
    PMエスカレーション処理ハンドラ

    REWORK回数がエスカレーション閾値に到達した場合に呼び出される。
    PMとしてタスクを再分析し、以下のアクションを実施:
    1. 要件再定義（タスク説明・完了条件の修正）
    2. サブタスク分割（複雑なタスクを分割）
    3. アプローチ変更指示（別の実装方法を指示）
    4. 先行タスク追加（前提条件が不足している場合）
    """

    # デフォルトのエスカレーション閾値
    DEFAULT_ESCALATION_THRESHOLD = 2

    def __init__(
        self,
        project_id: str,
        task_id: str,
        order_id: Optional[str] = None,
        *,
        escalation_threshold: int = DEFAULT_ESCALATION_THRESHOLD,
        verbose: bool = False,
        timeout: int = 600,
        model: str = "sonnet",
    ):
        self.project_id = project_id
        self.task_id = task_id if task_id.startswith("TASK_") else f"TASK_{task_id}"
        self.order_id = order_id
        self.escalation_threshold = escalation_threshold
        self.verbose = verbose
        self.timeout = timeout
        self.model = model

        # タスク情報（後で取得）
        self.task_info: Optional[Dict] = None
        self.rework_history: List[Dict] = []

    def should_escalate(self, rework_count: int) -> bool:
        """
        エスカレーションが必要かどうかを判定

        Args:
            rework_count: 現在のREWORK回数

        Returns:
            エスカレーションが必要な場合True
        """
        return rework_count >= self.escalation_threshold

    def escalate(self) -> PMEscalationResult:
        """
        PMエスカレーション処理を実行

        Returns:
            PMEscalationResult: エスカレーション結果
        """
        result = PMEscalationResult()
        result.original_task_id = self.task_id

        try:
            # 1. タスク情報と履歴を取得
            self._load_task_info()
            self._load_rework_history()

            # 2. エスカレーションログ記録
            result.escalation_id = self._log_escalation()

            # 3. タスク再設計（AI実行）
            redesign = self._execute_redesign()

            if not redesign:
                # AI利用不可の場合はフォールバック: タスクをREJECTEDに
                result.action = "rejected"
                result.error = "AI処理が利用できないため、REJECTEDに遷移"
                self._reject_task(result)
                return result

            # 4. 再設計結果を適用
            self._apply_redesign(redesign, result)

            result.success = True
            logger.info(
                f"PMエスカレーション完了: {self.task_id} → "
                f"action={result.action}, new_tasks={result.new_task_ids}"
            )

        except PMEscalationError as e:
            result.error = str(e)
            logger.error(f"PMエスカレーションエラー: {e}")
        except Exception as e:
            result.error = f"予期しないエラー: {e}"
            logger.error(f"PMエスカレーション予期しないエラー: {e}")

        return result

    def _load_task_info(self) -> None:
        """タスク情報を取得"""
        conn = get_connection()
        try:
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
            if not task:
                raise PMEscalationError(f"タスクが見つかりません: {self.task_id}")

            self.task_info = row_to_dict(task)
            if not self.order_id:
                self.order_id = self.task_info.get("order_id")
        finally:
            conn.close()

    def _load_rework_history(self) -> None:
        """REWORK履歴（差し戻しコメント）を取得"""
        conn = get_connection()
        try:
            reviews = fetch_all(
                conn,
                """
                SELECT comment, reviewed_at, status
                FROM review_queue
                WHERE task_id = ? AND project_id = ? AND status = 'REJECTED'
                ORDER BY reviewed_at DESC
                """,
                (self.task_id, self.project_id)
            )
            self.rework_history = rows_to_dicts(reviews) if reviews else []
        finally:
            conn.close()

    def _log_escalation(self) -> str:
        """エスカレーションログを記録"""
        rework_count = self.task_info.get("reject_count", 0) if self.task_info else 0
        return log_escalation(
            project_id=self.project_id,
            task_id=self.task_id,
            escalation_type=EscalationType.PM_REDESIGN,
            description=(
                f"REWORK {rework_count}回目でPMエスカレーション発動。"
                f"タスク再設計を実施。"
            ),
            order_id=self.order_id,
            metadata={
                "rework_count": rework_count,
                "threshold": self.escalation_threshold,
                "task_title": self.task_info.get("title", "") if self.task_info else "",
            }
        )

    def _execute_redesign(self) -> Optional[Dict[str, Any]]:
        """
        AIを使ってタスク再設計を実行

        Returns:
            再設計結果のdict、AI利用不可の場合None
        """
        try:
            from utils.claude_cli import create_runner
        except ImportError:
            logger.warning("claude_cli が利用できません。フォールバック処理を実行。")
            return None

        runner = create_runner(
            model=self.model,
            max_turns=1,
            timeout_seconds=self.timeout,
        )

        prompt = self._build_redesign_prompt()
        result = runner.run(prompt)

        if not result.success:
            logger.warning(f"AI再設計実行失敗: {result.error_message}")
            return None

        # 結果をパース
        try:
            text = result.result_text.strip()
            # コードブロック除去
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines)
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"AI再設計結果のJSONパース失敗")
            return None

    def _build_redesign_prompt(self) -> str:
        """タスク再設計用プロンプトを構築"""
        task_title = self.task_info.get("title", "Untitled") if self.task_info else "Unknown"
        task_desc = self.task_info.get("description", "") if self.task_info else ""
        rework_count = self.task_info.get("reject_count", 0) if self.task_info else 0

        # REWORK履歴をフォーマット
        history_text = ""
        for idx, review in enumerate(self.rework_history, 1):
            comment = review.get("comment", "（コメントなし）")
            reviewed_at = review.get("reviewed_at", "不明")
            history_text += f"\n### REWORK #{idx} ({reviewed_at})\n{comment}\n"

        return f"""【PMエスカレーション】タスク再設計を実施してください。

以下のタスクは{rework_count}回のREWORKを経ても完了できませんでした。
タスクを再分析し、実行可能な形に再設計してください。

## 元タスク情報
- タスクID: {self.task_id}
- タイトル: {task_title}
- 説明: {task_desc}
- REWORK回数: {rework_count}回

## 過去の差し戻し履歴
{history_text if history_text else "（履歴なし）"}

## 再設計指針
以下のいずれかまたは組み合わせで対策を検討してください:
1. **要件再定義**: タスクの説明・完了条件が曖昧な場合、明確にする
2. **サブタスク分割**: 複雑すぎるタスクを小さなサブタスクに分割する
3. **アプローチ変更**: 過去の指摘から、別の実装アプローチを指示する
4. **先行タスク追加**: 前提条件が不足している場合、先行タスクを追加する

## 出力形式（JSONのみ）
```json
{{
  "action": "redesign" | "subtask_split" | "approach_change",
  "summary": "再設計の概要",
  "original_task_update": {{
    "title": "更新後のタスク名（変更がある場合）",
    "description": "更新後のタスク説明（変更がある場合）"
  }},
  "new_subtasks": [
    {{
      "title": "サブタスク名",
      "description": "サブタスク説明",
      "priority": "P0",
      "model": "Sonnet",
      "depends_on": []
    }}
  ],
  "approach_guidance": "新しいアプローチ・実装方針の指示（Workerへの指示文）"
}}
```

【ルール】
- actionは必須。主な対策を1つ選択
- original_task_updateは元タスクの説明を更新する場合のみ記載
- new_subtasksは分割する場合のみ記載（元タスクの代わりに新タスクを実行）
- approach_guidanceはアプローチ変更する場合に記載
- JSONのみを出力（説明文・質問は不要）"""

    def _apply_redesign(self, redesign: Dict[str, Any], result: PMEscalationResult) -> None:
        """
        再設計結果をDB/タスクに適用

        Args:
            redesign: AI再設計結果
            result: エスカレーション結果（更新される）
        """
        action = redesign.get("action", "redesign")
        result.action = action
        result.redesign_summary = redesign.get("summary", "")

        # 1. 元タスクの更新（説明・アプローチ変更指示）
        self._update_original_task(redesign)

        # 2. サブタスク分割がある場合
        new_subtasks = redesign.get("new_subtasks", [])
        if new_subtasks:
            created_ids = self._create_subtasks(new_subtasks)
            result.new_task_ids = created_ids

        # 3. 元タスクをQUEUEDに戻す（再実行可能に）
        self._reset_task_for_retry(redesign)

    def _update_original_task(self, redesign: Dict[str, Any]) -> None:
        """元タスクの説明を更新"""
        update = redesign.get("original_task_update", {})
        approach = redesign.get("approach_guidance", "")

        if not update and not approach:
            return

        conn = get_connection()
        try:
            updates = []
            params = []

            new_title = update.get("title")
            new_desc = update.get("description", "")

            # アプローチ変更指示がある場合、descriptionに追記
            if approach:
                current_desc = self.task_info.get("description", "") if self.task_info else ""
                if new_desc:
                    new_desc = f"{new_desc}\n\n## PMアプローチ変更指示\n{approach}"
                else:
                    new_desc = f"{current_desc}\n\n## PMアプローチ変更指示\n{approach}"

            if new_title:
                updates.append("title = ?")
                params.append(new_title)

            if new_desc:
                updates.append("description = ?")
                params.append(new_desc)

            if updates:
                updates.append("updated_at = ?")
                params.append(datetime.now().isoformat())
                params.append(self.task_id)
                params.append(self.project_id)

                execute_query(
                    conn,
                    f"UPDATE tasks SET {', '.join(updates)} WHERE id = ? AND project_id = ?",
                    tuple(params)
                )
                conn.commit()

                logger.info(f"タスク更新: {self.task_id} (title={new_title}, desc_updated={bool(new_desc)})")

        finally:
            conn.close()

    def _create_subtasks(self, subtasks: List[Dict]) -> List[str]:
        """
        サブタスクをDBに作成

        Args:
            subtasks: サブタスク定義のリスト

        Returns:
            作成されたタスクIDのリスト
        """
        created_ids = []

        try:
            from task.create import create_task
        except ImportError:
            logger.warning("task.create モジュールのインポート失敗。サブタスク作成をスキップ。")
            return created_ids

        for subtask_def in subtasks:
            try:
                task_result = create_task(
                    self.project_id,
                    self.order_id,
                    subtask_def.get("title", "Untitled Subtask"),
                    description=subtask_def.get("description"),
                    priority=subtask_def.get("priority", "P0"),
                    recommended_model=subtask_def.get("model"),
                    depends_on=subtask_def.get("depends_on"),
                )
                created_ids.append(task_result["id"])
                logger.info(f"サブタスク作成: {task_result['id']} - {subtask_def.get('title')}")
            except Exception as e:
                logger.error(f"サブタスク作成失敗: {subtask_def.get('title')} - {e}")

        return created_ids

    def _reset_task_for_retry(self, redesign: Dict[str, Any]) -> None:
        """
        元タスクをQUEUEDに戻して再実行可能にする

        サブタスクが作成された場合:
        - 元タスクはサブタスク完了後に実行（depends_onを設定）
        - もしくは元タスクを完了扱いにしてサブタスクに置き換え

        サブタスクがない場合:
        - 元タスクをREWORK→QUEUEDに戻して再実行
        """
        new_subtasks = redesign.get("new_subtasks", [])

        conn = get_connection()
        try:
            if new_subtasks:
                # サブタスクが作成された場合、元タスクは保留
                # reject_countをリセットして再試行可能に
                execute_query(
                    conn,
                    """
                    UPDATE tasks
                    SET reject_count = 0, updated_at = ?
                    WHERE id = ? AND project_id = ?
                    """,
                    (datetime.now().isoformat(), self.task_id, self.project_id)
                )
                conn.commit()

                logger.info(f"タスク {self.task_id}: reject_countリセット（サブタスク作成済み）")
            else:
                # サブタスクなし → 元タスクをQUEUEDに戻す
                # REWORK → REJECTED → QUEUED の遷移
                # ただしreject_countをリセットして再試行可能にする
                current_status = self.task_info.get("status", "") if self.task_info else ""

                # reject_countをリセット
                execute_query(
                    conn,
                    """
                    UPDATE tasks
                    SET reject_count = 0, updated_at = ?
                    WHERE id = ? AND project_id = ?
                    """,
                    (datetime.now().isoformat(), self.task_id, self.project_id)
                )

                # ステータスをQUEUEDに戻す
                if current_status == "REWORK":
                    # REWORK → REJECTED → QUEUED は遷移テーブルで許可されている
                    execute_query(
                        conn,
                        """
                        UPDATE tasks
                        SET status = 'REJECTED', updated_at = ?
                        WHERE id = ? AND project_id = ?
                        """,
                        (datetime.now().isoformat(), self.task_id, self.project_id)
                    )

                    from utils.transition import record_transition
                    record_transition(
                        conn, "task", self.task_id,
                        "REWORK", "REJECTED", "System",
                        "PMエスカレーション: タスク再設計のためREJECTED遷移"
                    )

                    execute_query(
                        conn,
                        """
                        UPDATE tasks
                        SET status = 'QUEUED', updated_at = ?
                        WHERE id = ? AND project_id = ?
                        """,
                        (datetime.now().isoformat(), self.task_id, self.project_id)
                    )

                    record_transition(
                        conn, "task", self.task_id,
                        "REJECTED", "QUEUED", "PM",
                        "PMエスカレーション: タスク再設計完了、再実行のためQUEUED遷移"
                    )

                conn.commit()
                logger.info(f"タスク {self.task_id}: QUEUED遷移 + reject_countリセット")

        finally:
            conn.close()

    def _reject_task(self, result: PMEscalationResult) -> None:
        """AI利用不可時のフォールバック: タスクをREJECTEDにする"""
        conn = get_connection()
        try:
            current_status = self.task_info.get("status", "") if self.task_info else ""
            if current_status == "REWORK":
                execute_query(
                    conn,
                    """
                    UPDATE tasks
                    SET status = 'REJECTED', updated_at = ?
                    WHERE id = ? AND project_id = ?
                    """,
                    (datetime.now().isoformat(), self.task_id, self.project_id)
                )

                from utils.transition import record_transition
                record_transition(
                    conn, "task", self.task_id,
                    "REWORK", "REJECTED", "System",
                    "PMエスカレーション: AI利用不可のためREJECTED遷移"
                )
                conn.commit()

            result.action = "rejected"
            logger.info(f"タスク {self.task_id}: フォールバックREJECTED遷移")
        finally:
            conn.close()
