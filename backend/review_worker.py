#!/usr/bin/env python3
"""
AI PM Framework - Review Worker

DONEタスクのレビューを独立プロセスとして実行します。
daemon_loopから起動され、ReviewProcessorを呼び出してレビュー処理を実行します。

Usage:
    python backend/review_worker.py PROJECT_NAME TASK_ID [options]

Options:
    --dry-run       実行計画のみ表示（AI呼び出し・DB更新なし）
    --skip-ai       AI処理をスキップ（自動承認）
    --verbose       詳細ログ出力
    --json          JSON形式で出力
    --timeout SEC   claude -p タイムアウト秒数（デフォルト: 300）
    --model MODEL   AIモデル（haiku/sonnet/opus、デフォルト: sonnet）
    --auto-approve  レビューなしで自動承認

Example:
    python backend/review_worker.py ai_pm_manager TASK_1140
    python backend/review_worker.py ai_pm_manager TASK_1140 --dry-run
    python backend/review_worker.py ai_pm_manager TASK_1140 --model opus

処理フロー:
1. タスク情報取得（status='DONE'チェック）
2. ReviewProcessor経由でレビュー実行
3. 結果をログ・DBに記録
4. 終了ステータスを返却（0=成功、1=失敗）
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
_package_root = _current_dir
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
    from utils.db import get_connection, fetch_one, DatabaseError
    from utils.validation import (
        validate_project_name, validate_task_id,
        project_exists, task_exists, ValidationError
    )
except ImportError as e:
    logger.error(f"内部モジュールのインポートに失敗: {e}")
    sys.exit(1)


class ReviewWorkerError(Exception):
    """Review Worker エラー"""
    pass


class ReviewWorker:
    """Review Worker クラス - DONEタスクのレビューを実行"""

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

        # 処理結果
        self.results: Dict[str, Any] = {
            "task_id": self.task_id,
            "project_id": project_id,
            "success": False,
            "verdict": None,
            "error": None,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
        }

    def _log_step(self, step: str, status: str, detail: str = "") -> None:
        """ステップログ出力"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"[{timestamp}] [{step.upper()}] {status}"
        if detail:
            message += f" - {detail}"

        if status == "error":
            logger.error(message)
        elif status == "warning":
            logger.warning(message)
        else:
            logger.info(message)

    def process(self) -> Dict[str, Any]:
        """レビュー処理を実行"""
        try:
            # Step 1: バリデーション
            self._step_validate()

            # Step 2: タスク状態確認
            self._step_check_task_status()

            # Step 3: レビュー実行
            review_result = self._step_execute_review()

            # Step 4: 結果記録
            self.results["success"] = review_result.get("success", False)
            self.results["verdict"] = review_result.get("verdict")
            self.results["completed_at"] = datetime.now().isoformat()

            if not self.results["success"]:
                self.results["error"] = review_result.get("error", "レビュー失敗")

            return self.results

        except ValidationError as e:
            self._log_step("validation", "error", str(e))
            self.results["error"] = f"バリデーションエラー: {e}"
            return self.results
        except ReviewWorkerError as e:
            self._log_step("review_worker", "error", str(e))
            self.results["error"] = str(e)
            return self.results
        except Exception as e:
            self._log_step("review_worker", "error", f"予期しないエラー: {e}")
            self.results["error"] = f"予期しないエラー: {e}"
            if self.verbose:
                logger.exception("詳細エラー")
            return self.results

    def _step_validate(self) -> None:
        """Step 1: バリデーション"""
        self._log_step("validate", "start", f"{self.project_id}/{self.task_id}")

        # プロジェクト名バリデーション
        validate_project_name(self.project_id)

        # タスクID バリデーション
        validate_task_id(self.task_id)

        # プロジェクト存在確認
        try:
            with get_connection() as conn:
                if not project_exists(conn, self.project_id):
                    raise ValidationError(f"プロジェクトが存在しません: {self.project_id}")

                # タスク存在確認
                if not task_exists(conn, self.task_id, self.project_id):
                    raise ValidationError(f"タスクが存在しません: {self.task_id}")

        except DatabaseError as e:
            raise ValidationError(f"データベースエラー: {e}")

        self._log_step("validate", "success", "バリデーション完了")

    def _step_check_task_status(self) -> None:
        """Step 2: タスク状態確認（DONE状態チェック）"""
        self._log_step("check_status", "start", f"task={self.task_id}")

        try:
            with get_connection() as conn:
                task = fetch_one(
                    conn,
                    """
                    SELECT id, status, reviewed_at
                    FROM tasks
                    WHERE id = ? AND project_id = ?
                    """,
                    (self.task_id, self.project_id)
                )

                if not task:
                    raise ReviewWorkerError(f"タスクが見つかりません: {self.task_id}")

                status = task["status"]
                reviewed_at = task["reviewed_at"]

                # DONE状態チェック
                if status != "DONE":
                    raise ReviewWorkerError(
                        f"タスクがDONE状態ではありません: status={status}"
                    )

                # 既にレビュー済みの場合（reviewed_at が NULL でない）
                if reviewed_at:
                    self._log_step(
                        "check_status",
                        "warning",
                        f"既にレビュー済みのタスク（reviewed_at={reviewed_at}）"
                    )
                    # レビュー済みだが、再レビューを許可する場合は続行
                    # 必要に応じてここでエラーにすることも可能

                self._log_step("check_status", "success", f"status={status}")

        except DatabaseError as e:
            raise ReviewWorkerError(f"データベースエラー: {e}")

    def _step_execute_review(self) -> Dict[str, Any]:
        """Step 3: レビュー実行（ReviewProcessorを呼び出し）"""
        self._log_step("execute_review", "start", f"model={self.model}")

        try:
            # ReviewProcessorをインポート
            from review.process_review import ReviewProcessor

            # レビュー処理を実行
            processor = ReviewProcessor(
                self.project_id,
                self.task_id,
                dry_run=self.dry_run,
                skip_ai=self.skip_ai,
                auto_approve=self.auto_approve,
                verbose=self.verbose,
                timeout=self.timeout,
                model=self.model,
            )

            result = processor.process()

            # 結果ログ
            if result.get("success"):
                verdict = result.get("verdict", "UNKNOWN")
                self._log_step(
                    "execute_review",
                    "success",
                    f"verdict={verdict}"
                )
            else:
                error = result.get("error", "不明")
                self._log_step("execute_review", "error", f"レビュー失敗: {error}")

            return result

        except ImportError as e:
            self._log_step("execute_review", "error", f"ReviewProcessorのインポート失敗: {e}")
            return {"success": False, "error": f"ReviewProcessorのインポート失敗: {e}"}
        except Exception as e:
            self._log_step("execute_review", "error", f"レビュー処理エラー: {e}")
            if self.verbose:
                logger.exception("詳細エラー")
            return {"success": False, "error": str(e)}


def main():
    """コマンドライン実行"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="Review Worker - DONEタスクのレビューを実行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 通常レビュー
  python review_worker.py ai_pm_manager TASK_1140

  # Dry-runモード
  python review_worker.py ai_pm_manager TASK_1140 --dry-run

  # カスタムモデル指定
  python review_worker.py ai_pm_manager TASK_1140 --model opus

  # 自動承認
  python review_worker.py ai_pm_manager TASK_1140 --auto-approve

  # JSON出力
  python review_worker.py ai_pm_manager TASK_1140 --json
"""
    )

    parser.add_argument(
        "project_name",
        help="プロジェクト名 (例: ai_pm_manager)"
    )
    parser.add_argument(
        "task_id",
        help="タスクID (例: TASK_1140 または 1140)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実行計画のみ表示（AI呼び出し・DB更新なし）"
    )
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="AI処理をスキップ（自動承認）"
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="レビューなしで自動承認"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細ログ出力"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="claude -p タイムアウト秒数（デフォルト: 300）"
    )
    parser.add_argument(
        "--model",
        default="sonnet",
        choices=["haiku", "sonnet", "opus"],
        help="AIモデル（デフォルト: sonnet）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON形式で出力"
    )

    args = parser.parse_args()

    # Review Worker 実行
    worker = ReviewWorker(
        project_id=args.project_name,
        task_id=args.task_id,
        dry_run=args.dry_run,
        skip_ai=args.skip_ai,
        auto_approve=args.auto_approve,
        verbose=args.verbose,
        timeout=args.timeout,
        model=args.model,
    )

    result = worker.process()

    # 出力
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            verdict = result.get("verdict", "UNKNOWN")
            print(f"[OK] レビュー完了: {args.task_id} → {verdict}")
        else:
            error = result.get("error", "不明なエラー")
            print(f"[ERROR] レビュー失敗: {error}", file=sys.stderr)

    # 終了ステータス
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
