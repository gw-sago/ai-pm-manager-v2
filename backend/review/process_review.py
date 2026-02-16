#!/usr/bin/env python3
"""
AI PM Framework - Review処理親スクリプト

REPORT読み込み → claude -p でレビュー実施 → 判定(APPROVED/REJECTED/ESCALATED) → DB更新
を1コマンドで完結させる。

Usage:
    python backend/review/process_review.py PROJECT_NAME TASK_ID [options]

Options:
    --dry-run       実行計画のみ表示（AI呼び出し・DB更新なし）
    --skip-ai       AI処理をスキップ（自動承認）
    --verbose       詳細ログ出力
    --json          JSON形式で出力
    --timeout SEC   claude -p タイムアウト秒数（デフォルト: 300）
    --model MODEL   AIモデル（haiku/sonnet/opus、デフォルト: sonnet）
    --auto-approve  レビューなしで自動承認

Example:
    python backend/review/process_review.py AI_PM_PJ TASK_602
    python backend/review/process_review.py AI_PM_PJ TASK_602 --dry-run
    python backend/review/process_review.py AI_PM_PJ TASK_602 --auto-approve

内部処理（ORDER_124更新版）:
1. タスク・REPORT情報取得（status='DONE' AND reviewed_at IS NULL）
2. レビュー開始（review_queueは使用しない）
3. claude -p でレビュー実施（完了条件確認）
4. 判定結果に応じてDB更新
   - APPROVED: reviewed_at設定 → タスク→COMPLETED
   - REJECTED: reviewed_at設定 → タスク→REWORK
   - ESCALATED: reviewed_at設定 → エスカレーション記録
5. REVIEWファイル作成

※ ORDER_124: review_queueテーブルを使用せず、tasks.reviewed_atでレビュー管理
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
    from task.update import update_task_status
    from utils.file_lock import FileLockManager
except ImportError as e:
    logger.error(f"内部モジュールのインポートに失敗: {e}")
    sys.exit(1)

# claude_runner インポート（オプション）
try:
    from claude_runner import create_runner, ClaudeRunner, ClaudeResult
    CLAUDE_RUNNER_AVAILABLE = True
except ImportError:
    CLAUDE_RUNNER_AVAILABLE = False
    logger.warning("claude_runner が利用できません。--skip-ai または --auto-approve オプションのみ利用可能です。")


class ReviewProcessError(Exception):
    """レビュー処理エラー"""
    pass


class ReviewVerdict:
    """レビュー判定結果"""
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


class ReviewProcessor:
    """レビュー処理を実行するクラス"""

    def __init__(
        self,
        project_id: str,
        task_id: str,
        *,
        dry_run: bool = False,
        skip_ai: bool = False,
        auto_approve: bool = False,
        verbose: bool = False,
        timeout: int = 300,
        model: str = "sonnet",
        auto_rework: bool = True,
        rework_model: Optional[str] = None,
        max_rework: int = 3,
    ):
        self.project_id = project_id
        # TASK_XXX 形式に正規化
        self.task_id = f"TASK_{task_id}" if not task_id.startswith("TASK_") else task_id
        self.dry_run = dry_run
        self.skip_ai = skip_ai
        self.auto_approve = auto_approve
        self.verbose = verbose
        self.timeout = timeout
        self.model = model
        self.auto_rework = auto_rework
        self.rework_model = rework_model or model
        self.max_rework = max_rework

        # プロジェクトパス
        self.project_dir = _project_root / "PROJECTS" / project_id

        # 処理結果
        self.results: Dict[str, Any] = {
            "task_id": self.task_id,
            "project_id": project_id,
            "steps": [],
            "success": False,
            "verdict": None,
            "error": None,
            "rework_triggered": False,
        }

        # タスク・REPORT情報（後で設定）
        self.task_info: Optional[Dict] = None
        self.order_id: Optional[str] = None
        self.report_content: Optional[str] = None
        self.reject_comment: Optional[str] = None

        # claude_runner インスタンス（後で設定）
        self.runner: Optional[ClaudeRunner] = None

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

    def process(self) -> Dict[str, Any]:
        """
        レビュー処理を実行

        Returns:
            処理結果の辞書
        """
        try:
            # Step 1: タスク・REPORT情報取得
            self._step_get_task_and_report()

            # Step 2: レビューステータス更新（IN_REVIEW）
            self._step_start_review()

            if self.dry_run:
                self._log_step("dry_run", "info", "ドライランモード - 以降の処理をスキップ")
                self.results["success"] = True
                return self.results

            # Step 3: レビュー実施（AI or 自動承認）
            verdict = self._step_execute_review()

            # Step 4: 判定結果に応じてDB更新
            self._step_update_status(verdict)

            # Step 5: REVIEWファイル作成
            self._step_create_review_file(verdict)

            # Step 6: REJECTED時のWorker自動リワーク（--auto-rework有効時）
            if verdict == ReviewVerdict.REJECTED and self.auto_rework:
                rework_result = self._step_auto_rework()
                self.results["rework_result"] = rework_result
                if rework_result.get("success"):
                    self.results["rework_triggered"] = True
                    self._log_step("auto_rework", "success", f"リワーク完了、verdict={rework_result.get('verdict')}")
                else:
                    self._log_step("auto_rework", "warning", rework_result.get("error", "リワーク失敗"))

            self.results["success"] = True
            self.results["verdict"] = verdict
            self._log_step("complete", "success", f"レビュー完了: {verdict}")

        except ReviewProcessError as e:
            self.results["error"] = str(e)
            self._log_step("error", "failed", str(e))
        except Exception as e:
            self.results["error"] = f"予期しないエラー: {e}"
            self._log_step("error", "failed", str(e))
            if self.verbose:
                logger.exception("詳細エラー")

        return self.results

    def _step_get_task_and_report(self) -> None:
        """Step 1: タスク・REPORT情報を取得"""
        self._log_step("get_task_info", "start", self.task_id)

        conn = get_connection()
        try:
            # プロジェクト存在確認
            if not project_exists(conn, self.project_id):
                raise ReviewProcessError(f"プロジェクトが見つかりません: {self.project_id}")

            # タスク存在確認
            if not task_exists(conn, self.task_id, self.project_id):
                raise ReviewProcessError(f"タスクが見つかりません: {self.task_id}")

            # タスク情報取得（status='DONE' AND reviewed_at IS NULL を確認）
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

            # レビュー対象であることを確認
            if self.task_info.get("status") != "DONE":
                raise ReviewProcessError(f"タスクステータスがDONEではありません: {self.task_info.get('status')}")

            if self.task_info.get("reviewed_at") is not None:
                raise ReviewProcessError(f"タスクは既にレビュー済みです: reviewed_at={self.task_info.get('reviewed_at')}")

            self._log_step("get_task_info", "success", f"order={self.order_id}, status=DONE, reviewed_at=NULL")

        finally:
            conn.close()

        # REPORTファイル読み込み
        self._read_report()

    def _read_report(self) -> None:
        """REPORTファイルを読み込む（存在・内容バリデーション付き）"""
        if not self.order_id:
            self._log_step("read_report", "skip", "ORDER ID なし")
            return

        # REPORT番号を抽出
        report_num = self.task_id.replace("TASK_", "")
        report_file = self.project_dir / "RESULT" / self.order_id / "05_REPORT" / f"REPORT_{report_num}.md"

        # REPORTファイル存在チェック（必須）
        if not report_file.exists():
            raise ReviewProcessError(
                f"REPORTファイルが見つかりません: {report_file}. "
                f"タスクはDONEですがREPORTが未作成です。Workerの実行に問題があった可能性があります。"
            )

        self.report_content = report_file.read_text(encoding="utf-8")
        self.results["report_file"] = str(report_file)

        # REPORT内容バリデーション（空・極端に短いREPORTを検出）
        content_length = len(self.report_content.strip()) if self.report_content else 0
        if content_length < 50:
            raise ReviewProcessError(
                f"REPORTファイルが空または内容不足です: {report_file} "
                f"({content_length}文字). Workerの実行が正常に完了していない可能性があります。"
            )

        self._log_step("read_report", "success", f"{report_file} ({content_length}文字)")

    def _step_start_review(self) -> None:
        """Step 2: レビュー開始（review_queueは使用しない）"""
        self._log_step("start_review", "start", "")

        if self.dry_run:
            self._log_step("start_review", "dry_run", "レビュー開始（ドライラン）")
            return

        # ORDER_124: review_queueを使用せず、tasks.reviewed_atでレビュー管理
        # タスクステータスはDONEのままでレビュー実施
        self._log_step("start_review", "success", "レビュー開始（tasks.status=DONE, reviewed_at=NULL）")

    def _step_execute_review(self) -> str:
        """Step 3: レビューを実施"""
        # 自動承認モード
        if self.auto_approve:
            self._log_step("execute_review", "auto_approve", "自動承認")
            return ReviewVerdict.APPROVED

        # AI処理スキップ
        if self.skip_ai:
            self._log_step("execute_review", "skip", "AI処理スキップ - 自動承認")
            return ReviewVerdict.APPROVED

        # claude_runner利用不可
        if not CLAUDE_RUNNER_AVAILABLE:
            self._log_step("execute_review", "fallback", "claude_runner利用不可 - 自動承認")
            return ReviewVerdict.APPROVED

        self._log_step("execute_review", "start", f"model={self.model}")

        # claude_runner 初期化
        self.runner = create_runner(
            model=self.model,
            max_turns=20,
            timeout_seconds=self.timeout,
        )

        # プロンプト構築
        prompt = self._build_review_prompt()

        # claude -p 実行
        result = self.runner.run(prompt)

        if not result.success:
            self._log_step("execute_review", "warning", f"AI実行失敗: {result.error_message}")
            # AI失敗時はエスカレーション
            return ReviewVerdict.ESCALATED

        self.results["review_result"] = result.result_text
        self.results["cost_usd"] = result.cost_usd

        # 判定結果をパース
        verdict = self._parse_verdict(result.result_text)

        self._log_step(
            "execute_review",
            "success",
            f"verdict={verdict}, cost=${result.cost_usd:.4f}" if result.cost_usd else f"verdict={verdict}"
        )

        return verdict

    def _build_review_prompt(self) -> str:
        """レビュー用プロンプトを構築（REWORK回数に応じて基準を調整）"""
        task_title = self.task_info.get("title", "Untitled") if self.task_info else "Unknown"
        task_desc = self.task_info.get("description", "") if self.task_info else ""

        # REWORK回数を取得
        rework_count = self._get_rework_count()

        # REWORK回数に応じた基準を設定
        review_criteria_note = self._get_criteria_by_rework_count(rework_count)

        # 判定基準緩和のエスカレーションログ記録（REWORK 2回目以降）
        if rework_count >= 2:
            try:
                from escalation.log_escalation import log_escalation, EscalationType
                criteria_level = "緩和基準" if rework_count == 2 else "最低限基準"
                log_escalation(
                    project_id=self.project_id,
                    task_id=self.task_id,
                    escalation_type=EscalationType.CRITERIA_RELAXATION,
                    description=f"レビュー判定基準緩和を適用 (REWORK #{rework_count}, 基準={criteria_level})",
                    order_id=self.task_info.get("order_id") if self.task_info else None,
                    metadata={
                        "rework_count": rework_count,
                        "criteria_level": criteria_level,
                    }
                )
            except Exception as e:
                logger.warning(f"エスカレーションログ記録失敗: {e}")

        return f"""以下のタスクのREPORTをレビューし、完了条件が達成されているか判定してください。

## タスク情報
- タスクID: {self.task_id}
- タイトル: {task_title}
- 説明: {task_desc}
- REWORK回数: {rework_count}回

## REPORT内容
```markdown
{self.report_content or '（REPORTなし）'}
```

## レビュー基準
{review_criteria_note}

## 出力形式
JSON形式で以下の構造を返してください:
{{
  "verdict": "APPROVED" | "REJECTED" | "ESCALATED",
  "summary": "判定理由の要約",
  "checklist": [
    {{"item": "チェック項目", "passed": true/false, "comment": "コメント"}}
  ],
  "issues": ["問題点があれば記載"],
  "recommendations": ["改善提案があれば記載"]
}}

判定基準:
- APPROVED: 完了条件達成、品質問題なし
- REJECTED: 完了条件未達または品質問題あり（要修正）
- ESCALATED: 判断困難、ユーザー確認が必要

JSONのみを出力し、説明文は含めないでください。"""

    def _parse_verdict(self, ai_response: str) -> str:
        """AI応答から判定結果をパース"""
        try:
            data = json.loads(ai_response)
            verdict = data.get("verdict", "").upper()
            if verdict in (ReviewVerdict.APPROVED, ReviewVerdict.REJECTED, ReviewVerdict.ESCALATED):
                self.results["review_details"] = data
                return verdict
        except json.JSONDecodeError:
            pass

        # パース失敗時はキーワードで判定
        upper_response = ai_response.upper()
        if "APPROVED" in upper_response:
            return ReviewVerdict.APPROVED
        elif "REJECTED" in upper_response:
            return ReviewVerdict.REJECTED
        else:
            return ReviewVerdict.ESCALATED

    def _step_update_status(self, verdict: str) -> None:
        """Step 4: 判定結果に応じてDB更新"""
        self._log_step("update_status", "start", verdict)

        # ORDER_124: review_queueを使用せず、tasks.reviewed_atでレビュー管理
        if verdict == ReviewVerdict.APPROVED:
            self._update_approved()
        elif verdict == ReviewVerdict.REJECTED:
            self._update_rejected()
        else:  # ESCALATED
            self._handle_escalation()

    def _update_approved(self) -> None:
        """APPROVED時の更新処理"""
        conn = get_connection()
        try:
            # reviewed_atを現在時刻に設定
            current_time = datetime.now().isoformat()
            execute_query(
                conn,
                """
                UPDATE tasks
                SET reviewed_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (current_time, self.task_id, self.project_id)
            )
            conn.commit()
            conn.close()

            # タスクステータス更新（DONE → COMPLETED）
            try:
                result = update_task_status(
                    self.project_id,
                    self.task_id,
                    "COMPLETED",
                    role="PM",
                    reason="レビュー承認",
                    render=False
                )
                unblocked = result.get("unblocked_tasks", [])
                if unblocked:
                    self._log_step("update_status", "success", f"COMPLETED, reviewed_at={current_time}, ブロック解除: {unblocked}")
                else:
                    self._log_step("update_status", "success", f"COMPLETED, reviewed_at={current_time}")
            except Exception as e:
                self._log_step("update_status", "warning", f"update_task_status失敗: {e}")

            # ロック解放処理 (DONE → COMPLETED遷移時)
            self._release_task_locks()
            # APPROVED後フック: 影響分析 & 再計画
            self._post_approved_hook()

        except Exception as e:
            self._log_step("update_status", "error", f"APPROVED更新失敗: {e}")
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    def _update_rejected(self) -> None:
        """REJECTED時の更新処理"""
        issues = self.results.get("review_details", {}).get("issues", [])
        recommendations = self.results.get("review_details", {}).get("recommendations", [])
        comment_parts = []
        if issues:
            comment_parts.append("問題点: " + "; ".join(issues))
        if recommendations:
            comment_parts.append("修正指針: " + "; ".join(recommendations))
        comment = " | ".join(comment_parts) if comment_parts else "要修正"
        self.reject_comment = comment  # リワーク用に保存

        conn = get_connection()
        try:
            # reviewed_atを現在時刻に設定
            current_time = datetime.now().isoformat()
            execute_query(
                conn,
                """
                UPDATE tasks
                SET reviewed_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (current_time, self.task_id, self.project_id)
            )
            conn.commit()

            # reject_count をインクリメント
            execute_query(
                conn,
                """
                UPDATE tasks
                SET reject_count = COALESCE(reject_count, 0) + 1
                WHERE id = ? AND project_id = ?
                """,
                (self.task_id, self.project_id)
            )
            conn.commit()

            # 更新後のreject_countを取得
            updated_task = fetch_one(
                conn,
                "SELECT reject_count FROM tasks WHERE id = ? AND project_id = ?",
                (self.task_id, self.project_id)
            )
            new_reject_count = updated_task["reject_count"] if updated_task else 0
            self._log_step("update_status", "info", f"reject_count インクリメント → {new_reject_count}, reviewed_at={current_time}")

            conn.close()

            # タスクステータス更新（DONE → REWORK）
            try:
                update_task_status(
                    self.project_id,
                    self.task_id,
                    "REWORK",
                    role="PM",
                    reason="レビュー差し戻し",
                    render=False
                )
                self._log_step("update_status", "success", f"REWORK (reject_count={new_reject_count}, reviewed_at={current_time})")
            except Exception as e:
                self._log_step("update_status", "warning", f"update_task_status失敗: {e}")

            # ロック解放処理 (DONE → REWORK遷移時)
            self._release_task_locks()

            # エスカレーションログ記録（PM差し戻し）
            try:
                from escalation.log_escalation import log_escalation, EscalationType
                rework_count = self._get_rework_count()
                log_escalation(
                    project_id=self.project_id,
                    task_id=self.task_id,
                    escalation_type=EscalationType.REVIEW_REJECTION,
                    description=f"PMレビュー差し戻し (REWORK #{rework_count})",
                    order_id=self.task_info.get("order_id") if self.task_info else None,
                    metadata={
                        "rework_count": rework_count,
                        "issues": issues,
                        "recommendations": recommendations,
                        "comment": comment,
                    }
                )
            except Exception as e:
                logger.warning(f"エスカレーションログ記録失敗: {e}")

        except Exception as e:
            self._log_step("update_status", "error", f"REJECTED更新失敗: {e}")
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass


    def _handle_escalation(self) -> None:
        """エスカレーション処理（PM自動判断付き）

        1. タスクをESCALATEDに更新（従来通り）
        2. PMEscalationHandlerを使ってAI再設計を試行
        3. 再設計成功 → ESCALATED→QUEUED（再実行へ）
        4. 再設計不可/上限超過 → ESCALATED→REJECTED（終端化）
        """
        self._log_step("escalation", "start", "")

        # Step 1: タスクをESCALATEDに更新（正式な遷移ルートを使用）
        from utils.transition import validate_transition, record_transition

        conn = get_connection()
        try:
            current_time = datetime.now().isoformat()
            current_status = self.task_info.get("status", "DONE") if self.task_info else "DONE"

            # reviewed_atを更新
            execute_query(
                conn,
                """
                UPDATE tasks SET reviewed_at = ? WHERE id = ? AND project_id = ?
                """,
                (current_time, self.task_id, self.project_id)
            )

            # 正式な遷移ルートで検証
            validate_transition(conn, "task", current_status, "ESCALATED", "PM")

            execute_query(
                conn,
                """
                UPDATE tasks SET status = 'ESCALATED' WHERE id = ? AND project_id = ?
                """,
                (self.task_id, self.project_id)
            )

            record_transition(
                conn, "task", self.task_id,
                current_status, "ESCALATED", "PM",
                "レビューESCALATED"
            )
            conn.commit()
            self._log_step("escalation", "info", f"task={current_status}→ESCALATED, reviewed_at={current_time}")
        except Exception as e:
            self._log_step("escalation", "warning", f"ESCALATED更新失敗: {e}")
            return
        finally:
            conn.close()

        # Step 2: PM自動判断（AI再設計）を試行
        try:
            self._pm_auto_judge_on_escalation()
        except Exception as e:
            # PM自動判断が失敗してもESCALATEDステータスは保持
            # parallel_launcherのタイムアウト安全弁でカバーされる
            self._log_step("escalation", "warning", f"PM自動判断エラー（安全弁でカバー）: {e}")

    def _pm_auto_judge_on_escalation(self) -> None:
        """レビューESCALATED時のPM自動判断

        PMEscalationHandlerを使い、AI再設計を試行する。
        - 再設計成功: ESCALATED → QUEUED（reject_countリセット、再実行へ）
        - 再設計不可/上限超過: ESCALATED → REJECTED（終端化）
        """
        MAX_ESCALATION_COUNT = 2  # エスカレーション回数上限

        # エスカレーション回数を取得
        escalation_count = self._get_escalation_count()
        self._log_step("pm_auto_judge", "start", f"escalation_count={escalation_count}/{MAX_ESCALATION_COUNT}")

        # エスカレーション回数上限チェック
        if escalation_count >= MAX_ESCALATION_COUNT:
            self._log_step("pm_auto_judge", "info", f"エスカレーション回数上限到達 ({escalation_count}/{MAX_ESCALATION_COUNT}) → REJECTED")
            self._escalated_to_rejected(f"エスカレーション回数上限到達 ({escalation_count}/{MAX_ESCALATION_COUNT})")
            return

        # PMEscalationHandlerでAI再設計を試行
        try:
            from escalation.pm_escalation import PMEscalationHandler

            handler = PMEscalationHandler(
                project_id=self.project_id,
                task_id=self.task_id,
                order_id=self.task_info.get("order_id") if self.task_info else None,
                verbose=self.verbose,
                timeout=self.timeout,
                model=self.model,
            )

            result = handler.escalate()

            # エスカレーション履歴を記録
            try:
                from escalation.log_escalation import log_escalation, EscalationType
                log_escalation(
                    project_id=self.project_id,
                    task_id=self.task_id,
                    escalation_type=EscalationType.REVIEW_ESCALATION,
                    description=f"レビューESCALATED → PM自動判断 (#{escalation_count + 1})",
                    order_id=self.task_info.get("order_id") if self.task_info else None,
                    metadata={
                        "escalation_count": escalation_count + 1,
                        "max_escalation_count": MAX_ESCALATION_COUNT,
                        "action": result.action if result else "unknown",
                        "success": result.success if result else False,
                        "review_issues": self.results.get("review_details", {}).get("issues", []),
                        "review_recommendations": self.results.get("review_details", {}).get("recommendations", []),
                    }
                )
            except Exception as log_err:
                logger.warning(f"エスカレーションログ記録失敗: {log_err}")

            if result.success:
                self._log_step(
                    "pm_auto_judge", "success",
                    f"AI再設計完了: action={result.action}, new_tasks={result.new_task_ids}"
                )
                # PMEscalationHandler._reset_task_for_retry()で既にQUEUED遷移済み
                self.results["pm_escalation"] = result.to_dict()
            else:
                self._log_step(
                    "pm_auto_judge", "warning",
                    f"AI再設計失敗: {result.error} → REJECTED"
                )
                self._escalated_to_rejected(f"AI再設計失敗: {result.error}")

        except ImportError:
            self._log_step("pm_auto_judge", "warning", "PMEscalationHandler利用不可 → REJECTED")
            self._escalated_to_rejected("PMEscalationHandlerモジュール利用不可")
        except Exception as e:
            self._log_step("pm_auto_judge", "error", f"PM自動判断エラー: {e} → REJECTED")
            self._escalated_to_rejected(f"PM自動判断エラー: {e}")

    def _get_escalation_count(self) -> int:
        """レビューESCALATEDの累積回数を取得"""
        conn = get_connection()
        try:
            result = fetch_one(
                conn,
                """
                SELECT COUNT(*) as count
                FROM change_history
                WHERE entity_type = 'task'
                  AND entity_id = ?
                  AND field_name = 'status'
                  AND new_value = 'ESCALATED'
                """,
                (self.task_id,)
            )
            return result["count"] if result else 0
        except Exception as e:
            logger.warning(f"エスカレーション回数取得失敗: {e}")
            return 0
        finally:
            conn.close()

    def _escalated_to_rejected(self, reason: str) -> None:
        """ESCALATED → REJECTED遷移"""
        conn = get_connection()
        try:
            execute_query(
                conn,
                """
                UPDATE tasks
                SET status = 'REJECTED', updated_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (datetime.now().isoformat(), self.task_id, self.project_id)
            )
            conn.commit()

            # 遷移記録
            try:
                from utils.transition import record_transition
                record_transition(
                    conn, "task", self.task_id,
                    "ESCALATED", "REJECTED", "System",
                    f"レビューESCALATED→PM自動判断→REJECTED: {reason}"
                )
            except Exception:
                pass

            self._log_step("escalation", "success", f"ESCALATED→REJECTED: {reason}")

        except Exception as e:
            self._log_step("escalation", "error", f"REJECTED遷移失敗: {e}")
        finally:
            conn.close()

    def _step_create_review_file(self, verdict: str) -> None:
        """Step 5: REVIEWファイルを作成"""
        self._log_step("create_review_file", "start", "")

        if not self.order_id:
            self._log_step("create_review_file", "skip", "ORDER ID なし")
            return

        # REVIEWディレクトリ
        review_dir = self.project_dir / "RESULT" / self.order_id / "07_REVIEW"
        review_dir.mkdir(parents=True, exist_ok=True)

        review_num = self.task_id.replace("TASK_", "")
        review_file = review_dir / f"REVIEW_{review_num}.md"

        # REVIEW内容作成
        review_content = self._format_review(verdict)
        review_file.write_text(review_content, encoding="utf-8")

        self.results["review_file"] = str(review_file)
        self._log_step("create_review_file", "success", str(review_file))

    def _step_auto_rework(self) -> Dict[str, Any]:
        """
        Step 6: REJECTED時にWorkerを自動起動してリワーク実行

        Returns:
            リワーク処理結果の辞書
        """
        self._log_step("auto_rework", "start", f"task={self.task_id}")

        # リワーク回数チェック
        rework_count = self._get_rework_count()
        if rework_count >= self.max_rework:
            self._log_step("auto_rework", "escalation", f"リワーク上限到達 ({rework_count}/{self.max_rework}) - PMエスカレーション発動")

            # ORDER_102: リワーク上限超過時はPMエスカレーション（タスク再設計）を実施
            try:
                from escalation.pm_escalation import PMEscalationHandler

                handler = PMEscalationHandler(
                    project_id=self.project_id,
                    task_id=self.task_id,
                    order_id=self.task_info.get("order_id") if self.task_info else None,
                    verbose=self.verbose,
                    timeout=self.timeout,
                    model=self.model,
                )

                escalation_result = handler.escalate()

                if escalation_result.success:
                    self._log_step(
                        "pm_escalation", "success",
                        f"タスク再設計完了: action={escalation_result.action}, "
                        f"new_tasks={escalation_result.new_task_ids}"
                    )
                    return {
                        "success": True,
                        "error": None,
                        "rework_count": rework_count,
                        "status_changed_to": "QUEUED",
                        "pm_escalation": escalation_result.to_dict(),
                    }
                else:
                    self._log_step(
                        "pm_escalation", "warning",
                        f"PMエスカレーション失敗: {escalation_result.error}"
                    )
                    # フォールバック: REJECTED遷移
                    self._fallback_reject_task(rework_count)
                    return {
                        "success": False,
                        "error": f"PMエスカレーション失敗 - REJECTEDに遷移: {escalation_result.error}",
                        "rework_count": rework_count,
                        "status_changed_to": "REJECTED",
                        "pm_escalation": escalation_result.to_dict(),
                    }

            except ImportError:
                self._log_step("pm_escalation", "skip", "pm_escalation モジュール利用不可 - フォールバックREJECTED遷移")
                self._fallback_reject_task(rework_count)
                return {
                    "success": False,
                    "error": f"リワーク回数上限 ({self.max_rework}) に到達 - REJECTEDに遷移（PMエスカレーション利用不可）",
                    "rework_count": rework_count,
                    "status_changed_to": "REJECTED",
                }
            except Exception as e:
                self._log_step("pm_escalation", "error", f"PMエスカレーションエラー: {e}")
                self._fallback_reject_task(rework_count)
                return {
                    "success": False,
                    "error": f"PMエスカレーションエラー: {e} - REJECTEDに遷移",
                    "rework_count": rework_count,
                    "status_changed_to": "REJECTED",
                }

        try:
            # WorkerExecutorをインポート
            from worker.execute_task import WorkerExecutor

            # Workerにリワークとして実行させる
            executor = WorkerExecutor(
                self.project_id,
                self.task_id,
                dry_run=self.dry_run,
                skip_ai=self.skip_ai,
                verbose=self.verbose,
                timeout=self.timeout,
                model=self.rework_model,
                auto_review=True,  # リワーク後も自動レビュー
                review_model=self.model,
                loop=False,
                is_rework=True,  # リワークモード
                rework_comment=self.reject_comment,  # 差し戻しコメントを渡す
            )

            result = executor.execute()

            # リワーク結果にレビュー結果が含まれる場合
            review_result = result.get("review_result")
            if review_result and review_result.get("success"):
                result["verdict"] = review_result.get("verdict")

            return result

        except ImportError as e:
            self._log_step("auto_rework", "error", f"WorkerExecutorのインポート失敗: {e}")
            return {"success": False, "error": f"WorkerExecutorのインポート失敗: {e}"}
        except Exception as e:
            self._log_step("auto_rework", "error", f"リワーク処理エラー: {e}")
            return {"success": False, "error": str(e)}

    def _fallback_reject_task(self, rework_count: int) -> None:
        """
        PMエスカレーション失敗時のフォールバック: REWORK → REJECTED遷移

        Args:
            rework_count: 現在のリワーク回数
        """
        try:
            conn = get_connection()
            try:
                task_status = fetch_one(
                    conn,
                    "SELECT status, reject_count FROM tasks WHERE id = ? AND project_id = ?",
                    (self.task_id, self.project_id)
                )
                if task_status and task_status["status"] == "REWORK":
                    execute_query(
                        conn,
                        """
                        UPDATE tasks
                        SET status = 'REJECTED', updated_at = ?
                        WHERE id = ? AND project_id = ?
                        """,
                        (datetime.now().isoformat(), self.task_id, self.project_id)
                    )
                    conn.commit()

                    from utils.transition import record_transition
                    record_transition(
                        conn, "task", self.task_id,
                        "REWORK", "REJECTED", "System",
                        f"リワーク回数上限 ({self.max_rework}) 超過 + PMエスカレーション失敗により自動REJECTED遷移"
                    )

                    self._log_step("fallback_reject", "success", f"REWORK → REJECTED (reject_count={task_status['reject_count']})")

                    # エスカレーションログ記録
                    try:
                        from escalation.log_escalation import log_escalation, EscalationType
                        log_escalation(
                            project_id=self.project_id,
                            task_id=self.task_id,
                            escalation_type=EscalationType.REWORK_LIMIT_EXCEEDED,
                            description=f"リワーク回数上限超過 ({rework_count}/{self.max_rework}) - PMエスカレーション失敗のためREJECTED遷移",
                            order_id=self.task_info.get("order_id") if self.task_info else None,
                            metadata={
                                "rework_count": rework_count,
                                "max_rework": self.max_rework,
                                "reject_count": task_status["reject_count"],
                            }
                        )
                    except Exception as log_err:
                        logger.warning(f"エスカレーションログ記録失敗: {log_err}")
            finally:
                conn.close()
        except Exception as e:
            self._log_step("fallback_reject", "warning", f"フォールバックREJECTED遷移失敗: {e}")

    def _get_rework_count(self) -> int:
        """
        タスクのリワーク回数を取得

        Returns:
            リワーク回数
        """
        conn = get_connection()
        try:
            # 変更履歴からREWORKへの遷移回数をカウント
            result = fetch_one(
                conn,
                """
                SELECT COUNT(*) as count
                FROM change_history
                WHERE entity_type = 'task'
                  AND entity_id = ?
                  AND field_name = 'status'
                  AND new_value = 'REWORK'
                """,
                (self.task_id,)
            )
            return result["count"] if result else 0
        except Exception as e:
            logger.warning(f"リワーク回数取得失敗: {e}")
            return 0
        finally:
            conn.close()

    def _release_task_locks(self) -> None:
        """
        タスクのファイルロックを解放

        DONE → COMPLETED/REWORK遷移時に呼び出される。
        ロック解放失敗時はログ記録のみ行い、遷移自体はブロックしない。
        """
        try:
            FileLockManager.release_locks(self.project_id, self.task_id)
            self._log_step("release_locks", "success", f"task={self.task_id}のロック解放完了")
        except Exception as e:
            # ロック解放失敗は警告ログのみ（遷移はブロックしない）
            self._log_step("release_locks", "warning", f"ロック解放失敗（非致命的）: {e}")
            logger.warning(f"ファイルロック解放失敗 (task={self.task_id}): {e}")

    def _get_criteria_by_rework_count(self, rework_count: int) -> str:
        """
        REWORK回数に応じたレビュー基準を返す

        Args:
            rework_count: リワーク回数

        Returns:
            レビュー基準の説明文
        """
        if rework_count == 0:
            # 初回レビュー: 通常基準
            return """【通常基準】
1. 完了条件が明確に達成されているか
2. 成果物が要件を満たしているか
3. 品質に問題がないか
4. コードの可読性・保守性が適切か
5. テストが適切に実施されているか"""

        elif rework_count == 1:
            # REWORK 1回目: 通常基準（変更なし）
            return """【通常基準】（REWORK 1回目）
1. 完了条件が明確に達成されているか
2. 成果物が要件を満たしているか
3. 品質に問題がないか
4. コードの可読性・保守性が適切か
5. テストが適切に実施されているか

※ 前回の指摘事項が修正されているかを重点的に確認してください。"""

        elif rework_count == 2:
            # REWORK 2回目: 致命的でない差異を許容
            return """【緩和基準】（REWORK 2回目）
**致命的でない差異は許容します。以下を重点的に確認:**
1. **必須**: 完了条件の本質的な部分が達成されているか
2. **必須**: 機能的に動作するか、重大なバグがないか
3. **許容**: コードスタイルの細かい違い
4. **許容**: 命名規則の軽微な違い
5. **許容**: コメント・ドキュメントの表現の違い
6. **許容**: テストカバレッジが完璧でない（基本的なケースがカバーされていればOK）

※ 重大な機能的欠陥や完了条件の本質的な未達がない限り、APPROVEDを検討してください。
※ 細かい改善提案はrecommendationsに記載し、APPROVEDとしても構いません。"""

        else:
            # REWORK 3回目以降: 最低限の要件充足でAPPROVED
            return """【最低限基準】（REWORK 3回目以降）
**品質よりも完了を優先します。以下の最低限の要件のみ確認:**
1. **最低限**: タスクの主要な目的が達成されているか
2. **最低限**: 致命的なバグや動作不良がないか
3. **最低限**: 既存機能が破壊されていないか

**以下は許容します:**
- コード品質の問題（可読性、保守性の低さ）
- テストの不足
- ドキュメントの不備
- 命名規則やスタイルの問題
- パフォーマンスの非最適化

※ タスクの主要目的が達成され、致命的な問題がなければAPPROVEDとしてください。
※ 改善が必要な点はrecommendationsに記載し、次のタスクで対応を検討します。
※ これ以上のREWORKループを避けるため、可能な限りAPPROVEDを検討してください。"""

    def _post_approved_hook(self) -> None:
        """
        APPROVED後の影響分析 & 再計画フック

        完了タスクのREPORT内容と後続タスク（QUEUED/BLOCKED）を比較して影響分析し、
        影響がある場合は後続タスクのdescriptionを更新する。

        エラーが発生してもレビュープロセス自体は成功として扱う（ログ記録のみ）
        """
        self._log_step("post_approved_hook", "start", "影響分析開始")

        # ORDER IDとREPORT内容が必要
        if not self.order_id:
            self._log_step("post_approved_hook", "skip", "ORDER ID なし")
            return

        if not self.report_content:
            self._log_step("post_approved_hook", "skip", "REPORT内容なし")
            return

        try:
            # 影響分析モジュールをインポート
            from review.impact_analysis import analyze_impact

            # 影響分析実行
            self._log_step("impact_analysis", "start", f"order={self.order_id}")
            analysis_result = analyze_impact(
                project_id=self.project_id,
                completed_task_id=self.task_id,
                order_id=self.order_id,
                report_content=self.report_content,
                model=self.model,
                timeout=self.timeout,
                verbose=self.verbose,
            )

            if not analysis_result.success:
                self._log_step("impact_analysis", "warning", f"影響分析失敗: {analysis_result.error}")
                return

            # 影響分析結果を記録
            self.results["impact_analysis"] = analysis_result.to_dict()

            if not analysis_result.has_impact:
                self._log_step("impact_analysis", "success", "影響なし - 後続タスク更新不要")
                return

            # 影響ありの場合、後続タスクを再計画
            self._log_step("task_replan", "start", f"{len(analysis_result.task_updates)}件のタスクを再計画")

            from task.update import replan_task

            replanned_tasks = []
            for task_id, task_update in analysis_result.task_updates.items():
                if not task_update.has_changes():
                    continue

                try:
                    # タスク再計画実行
                    replan_result = replan_task(
                        project_id=self.project_id,
                        task_id=task_id,
                        updated_description=task_update.updated_description,
                        reason=task_update.reason,
                        changed_by="PM",
                        completed_task_id=self.task_id,
                    )

                    replanned_tasks.append(task_id)
                    self._log_step("task_replan", "success", f"{task_id} 更新完了")

                except Exception as e:
                    self._log_step("task_replan", "warning", f"{task_id} 更新失敗: {e}")

            if replanned_tasks:
                self._log_step("post_approved_hook", "success", f"再計画完了: {replanned_tasks}")
                self.results["replanned_tasks"] = replanned_tasks
            else:
                self._log_step("post_approved_hook", "info", "再計画対象タスクなし")

        except ImportError as e:
            self._log_step("post_approved_hook", "warning", f"モジュールインポート失敗: {e}")
        except Exception as e:
            self._log_step("post_approved_hook", "error", f"影響分析・再計画エラー: {e}")
            if self.verbose:
                logger.exception("詳細エラー")

    def _format_review(self, verdict: str) -> str:
        """REVIEW内容をフォーマット（REPORT内容統合版）"""
        task_title = self.task_info.get("title", "Untitled") if self.task_info else "Unknown"
        details = self.results.get("review_details", {})

        verdict_emoji = {
            ReviewVerdict.APPROVED: "✅",
            ReviewVerdict.REJECTED: "❌",
            ReviewVerdict.ESCALATED: "⚠️",
        }.get(verdict, "")

        lines = [
            f"# {self.task_id} レビュー結果",
            "",
            "## 基本情報",
            "",
            "| 項目 | 内容 |",
            "|------|------|",
            f"| タスクID | {self.task_id} |",
            f"| タスク名 | {task_title} |",
            f"| レビュー日時 | {datetime.now().strftime('%Y-%m-%d %H:%M')} |",
            f"| 判定 | {verdict_emoji} {verdict} |",
            "",
        ]

        # ORDER_099: REPORT内容を統合
        if self.report_content:
            lines.append("## 実施内容")
            lines.append("")
            lines.append(self.report_content)
            lines.append("")

        # 判定結果セクション
        lines.append("## 判定結果")
        lines.append("")

        if details.get("summary"):
            lines.append("### 判定理由")
            lines.append("")
            lines.append(details["summary"])
            lines.append("")

        if details.get("checklist"):
            lines.append("### チェックリスト")
            lines.append("")
            for item in details["checklist"]:
                status = "✅" if item.get("passed") else "❌"
                lines.append(f"- {status} {item.get('item', '')}")
                if item.get("comment"):
                    lines.append(f"  - {item['comment']}")
            lines.append("")

        if details.get("issues"):
            lines.append("### 指摘事項")
            lines.append("")
            for issue in details["issues"]:
                lines.append(f"- {issue}")
            lines.append("")

        if details.get("recommendations"):
            lines.append("### 改善提案")
            lines.append("")
            for rec in details["recommendations"]:
                lines.append(f"- {rec}")
            lines.append("")

        return "\n".join(lines)


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="レビュー処理を1コマンドで実行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("task_id", help="タスクID（例: 602 または TASK_602）")
    parser.add_argument("--dry-run", action="store_true", help="実行計画のみ表示")
    parser.add_argument("--skip-ai", action="store_true", help="AI処理をスキップ")
    parser.add_argument("--auto-approve", action="store_true", help="自動承認")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--timeout", type=int, default=300, help="タイムアウト秒数")
    parser.add_argument("--model", default="sonnet", help="AIモデル（haiku/sonnet/opus）")
    parser.add_argument("--auto-rework", action="store_true", default=True, help="REJECTED時にWorkerを自動起動してリワーク（デフォルト: 有効）")
    parser.add_argument("--no-rework", action="store_true", help="自動リワークを無効化")
    parser.add_argument("--rework-model", help="リワーク用AIモデル（デフォルト: レビューと同じ）")
    parser.add_argument("--max-rework", type=int, default=3, help="リワーク回数上限（デフォルト: 3）")

    args = parser.parse_args()

    # 詳細ログモード
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # レビュー処理実行
    processor = ReviewProcessor(
        args.project_id,
        args.task_id,
        dry_run=args.dry_run,
        skip_ai=args.skip_ai,
        auto_approve=args.auto_approve,
        verbose=args.verbose,
        timeout=args.timeout,
        model=args.model,
        auto_rework=args.auto_rework and not args.no_rework,
        rework_model=args.rework_model,
        max_rework=args.max_rework,
    )

    results = processor.process()

    # 出力
    if args.json:
        output = {k: v for k, v in results.items() if k not in ("review_result",)}
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    else:
        if results["success"]:
            verdict = results.get("verdict", "UNKNOWN")
            print(f"【レビュー完了】{results['task_id']}")
            print(f"  プロジェクト: {results['project_id']}")
            print(f"  判定: {verdict}")
            if results.get("review_file"):
                print(f"  REVIEW: {results['review_file']}")
            # リワーク結果の表示
            if results.get("rework_triggered"):
                rework_result = results.get("rework_result", {})
                rework_verdict = rework_result.get("verdict", "UNKNOWN")
                print(f"  【自動リワーク】verdict={rework_verdict}")
                if rework_result.get("review_file"):
                    print(f"  リワークREVIEW: {rework_result['review_file']}")
        else:
            print(f"【レビュー失敗】{results.get('error', '不明なエラー')}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
