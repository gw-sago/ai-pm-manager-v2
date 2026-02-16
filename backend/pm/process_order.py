#!/usr/bin/env python3
"""
AI PM Framework - PM処理親スクリプト

ORDER.md読み込み → claude -p で要件定義/タスク分割 → DB登録 → ファイル生成
を1コマンドで完結させる。

Usage:
    python backend/pm/process_order.py PROJECT_NAME ORDER_NUMBER [options]

Options:
    --dry-run       実行計画のみ表示（AI呼び出し・DB更新なし）
    --skip-ai       AI処理をスキップ（DB登録のみ）
    --verbose       詳細ログ出力
    --json          JSON形式で出力
    --timeout SEC   claude -p タイムアウト秒数（デフォルト: 600）
    --model MODEL   AI呼び出しモデル（haiku/sonnet/opus、デフォルト: sonnet）

Example:
    python backend/pm/process_order.py AI_PM_PJ 095
    python backend/pm/process_order.py AI_PM_PJ 095 --dry-run
    python backend/pm/process_order.py AI_PM_PJ 095 --model opus --timeout 900

内部処理:
1. ORDER.md 読み込み
2. claude -p で要件定義生成（GOAL/REQUIREMENTS/STAFFING）
3. claude -p でタスク分割生成
4. order/create.py でDB登録
5. task/create.py でタスク作成
6. Markdown成果物生成
"""

import argparse
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
        validate_project_name, validate_order_id,
        project_exists, order_exists, ValidationError
    )
    from utils.transition import (
        validate_transition, record_transition, TransitionError
    )
    from utils.incident_logger import log_incident
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

# spec_generator / spec_validator インポート（オプション）
try:
    from pm.spec_generator import SpecGenerator
    from pm.spec_validator import SpecValidator
    SPEC_MODULES_AVAILABLE = True
except ImportError:
    SPEC_MODULES_AVAILABLE = False
    logger.warning("spec_generator/spec_validator が利用できません")


class PMProcessError(Exception):
    """PM処理エラー"""
    pass


class PMProcessor:
    """PM処理を実行するクラス"""

    def __init__(
        self,
        project_id: str,
        order_number: str,
        *,
        dry_run: bool = False,
        skip_ai: bool = False,
        verbose: bool = False,
        timeout: int = 600,
        model: str = "sonnet",
        stream_output: bool = True,  # デフォルトでリアルタイム出力有効
    ):
        self.project_id = project_id
        self.order_number = order_number
        self.order_id = f"ORDER_{order_number}" if not order_number.startswith("ORDER_") else order_number
        self.dry_run = dry_run
        self.skip_ai = skip_ai
        self.verbose = verbose
        self.timeout = timeout
        self.model = model
        self.stream_output = stream_output

        # パス設定
        self.project_dir = _project_root / "PROJECTS" / project_id
        self.order_file = self.project_dir / "ORDERS" / f"{self.order_id}.md"
        self.result_dir = self.project_dir / "RESULT" / self.order_id

        # 処理結果
        self.results: Dict[str, Any] = {
            "order_id": self.order_id,
            "project_id": project_id,
            "steps": [],
            "success": False,
            "error": None,
        }

        # claude_runner インスタンス
        self.runner: Optional[ClaudeRunner] = None
        if CLAUDE_RUNNER_AVAILABLE and not skip_ai:
            self.runner = create_runner(
                model=model,
                max_turns=1,  # JSON出力のみ、追加質問を許さない
                timeout_seconds=timeout,
                stream_output=stream_output,  # リアルタイム出力を有効化
            )

        # Spec Generator & Validator（オプション）
        self.spec_generator = SpecGenerator() if SPEC_MODULES_AVAILABLE else None
        self.spec_validator = SpecValidator() if SPEC_MODULES_AVAILABLE else None

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
        PM処理を実行

        Returns:
            処理結果の辞書
        """
        try:
            # Step 1: ORDER.md 読み込み
            self._step_read_order()

            # Step 2: プロジェクト存在確認
            self._step_validate_project()

            # Step 3: ORDER状態確認
            order_status = self._step_check_order_status()

            if self.dry_run:
                self._log_step("dry_run", "info", "ドライランモード - 以降の処理をスキップ")
                self.results["success"] = True
                return self.results

            # Step 4-5の成功フラグ
            requirements_generated = False
            tasks_created = False

            # Step 4: 要件定義生成（AI）
            if not self.skip_ai and order_status in (None, "PLANNING"):
                self._step_generate_requirements()
                # 要件定義が正常に生成されたか確認
                if self.results.get("requirements"):
                    requirements_generated = True
                else:
                    self._log_step("generate_requirements", "warning", "要件定義が生成されませんでした")

            # Step 5: タスク分割・DB登録
            if not self.skip_ai and order_status in (None, "PLANNING"):
                self._step_create_tasks()
                # タスクが作成されたか確認
                if self.results.get("created_tasks"):
                    tasks_created = True
                else:
                    self._log_step("create_tasks", "warning", "タスクが作成されませんでした")

            # Step 6: ORDERステータス更新（全ステップ成功時のみ）
            # skip_aiモードの場合はDB登録のみなのでステータス更新を実行
            if self.skip_ai or (requirements_generated and tasks_created):
                self._step_update_order_status()
            else:
                self._log_step("update_order", "skip",
                    "要件定義またはタスク作成が未完了のため、PLANNINGステータスを維持します")
                # PLANNINGのまま維持 - ステータス更新はスキップ

            self.results["success"] = True
            self._log_step("complete", "success", "PM処理完了")

        except PMProcessError as e:
            self.results["error"] = str(e)
            self._log_step("error", "failed", str(e))
            # Record incident for PM process error
            try:
                log_incident(
                    category='WORKER_FAILURE',
                    description=f"PM処理エラー: {str(e)}",
                    severity='MEDIUM',
                    project_id=self.project_id,
                    order_id=self.order_id
                )
            except Exception as inc_err:
                logger.warning(f"インシデント記録に失敗: {inc_err}")
        except Exception as e:
            self.results["error"] = f"予期しないエラー: {e}"
            self._log_step("error", "failed", str(e))
            if self.verbose:
                logger.exception("詳細エラー")
            # Record incident for unexpected error
            try:
                log_incident(
                    category='SYSTEM_ERROR',
                    description=f"PM処理で予期しないエラーが発生: {str(e)}",
                    severity='HIGH',
                    project_id=self.project_id,
                    order_id=self.order_id
                )
            except Exception as inc_err:
                logger.warning(f"インシデント記録に失敗: {inc_err}")

        return self.results

    def _step_read_order(self) -> str:
        """Step 1: ORDER.md を読み込む"""
        self._log_step("read_order", "start", str(self.order_file))

        if not self.order_file.exists():
            raise PMProcessError(f"ORDER.md が見つかりません: {self.order_file}")

        content = self.order_file.read_text(encoding="utf-8")
        self.results["order_content"] = content
        self._log_step("read_order", "success", f"{len(content)} bytes")
        return content

    def _step_validate_project(self) -> None:
        """Step 2: プロジェクト存在確認"""
        self._log_step("validate_project", "start", self.project_id)

        conn = get_connection()
        try:
            if not project_exists(conn, self.project_id):
                raise PMProcessError(f"プロジェクトが見つかりません: {self.project_id}")
            self._log_step("validate_project", "success", "")
        finally:
            conn.close()

    def _step_check_order_status(self) -> Optional[str]:
        """Step 3: ORDER状態確認"""
        self._log_step("check_order", "start", self.order_id)

        conn = get_connection()
        try:
            # ORDER存在確認
            order = fetch_one(
                conn,
                "SELECT id, status, title FROM orders WHERE id = ? AND project_id = ?",
                (self.order_id, self.project_id)
            )

            if order:
                order_dict = row_to_dict(order)
                status = order_dict.get("status")
                self.results["existing_order"] = order_dict
                self._log_step("check_order", "exists", f"status={status}")
                return status
            else:
                self._log_step("check_order", "not_found", "新規作成対象")
                return None
        finally:
            conn.close()

    def _step_generate_requirements(self) -> None:
        """Step 4: claude -p で要件定義を生成"""
        if not self.runner:
            self._log_step("generate_requirements", "skip", "AI処理スキップ")
            return

        self._log_step("generate_requirements", "start", f"model={self.model}")

        try:
            # 成果物ディレクトリ作成
            self.result_dir.mkdir(parents=True, exist_ok=True)

            # プロンプト作成
            order_content = self.results.get("order_content", "")
            prompt = self._build_requirements_prompt(order_content)

            # claude -p 実行
            result = self.runner.run(prompt)

            if not result.success:
                raise PMProcessError(f"要件定義生成に失敗: {result.error_message}")

            # 結果をファイルに保存
            self._save_requirements(result.result_text)
            self._log_step("generate_requirements", "success", f"cost=${result.cost_usd:.4f}" if result.cost_usd else "")
        except PMProcessError:
            raise
        except Exception as e:
            # Record incident for requirements generation failure
            try:
                log_incident(
                    category='WORKER_FAILURE',
                    description=f"要件定義生成中のエラー: {str(e)}",
                    severity='HIGH',
                    project_id=self.project_id,
                    order_id=self.order_id
                )
            except Exception as inc_err:
                logger.warning(f"インシデント記録に失敗: {inc_err}")
            raise PMProcessError(f"要件定義生成中にエラーが発生: {e}")

    def _build_requirements_prompt(self, order_content: str) -> str:
        """要件定義生成用プロンプトを構築"""
        # SpecGeneratorが利用可能ならAC生成指示付きの改善プロンプトを使用
        if self.spec_generator:
            return self.spec_generator.enhance_prompt(order_content)

        # フォールバック: 元のプロンプト（SpecGenerator未導入時）
        return f"""【重要】以下のORDER内容のみを分析してJSON形式で出力してください。
ファイルを探したり、質問したりせず、与えられた情報だけで要件定義を作成してください。

## 分析対象ORDER内容
```markdown
{order_content}
```

## 必須出力形式（JSONのみ、他の文章は禁止）
```json
{{
  "goal": {{
    "summary": "ゴールの要約（1-2文）",
    "objectives": ["目標1", "目標2"],
    "success_criteria": ["成功基準1", "成功基準2"]
  }},
  "requirements": {{
    "functional": ["機能要件1", "機能要件2"],
    "non_functional": ["非機能要件1"],
    "constraints": ["制約事項1"]
  }},
  "tasks": [
    {{
      "title": "タスク名",
      "description": "タスク説明",
      "priority": "P0",
      "model": "Sonnet",
      "depends_on": [],
      "target_files": ["path/to/file1.py", "path/to/file2.py"]
    }}
  ]
}}
```

【出力ルール】
- JSONのみを出力（説明文、質問、確認は一切不要）
- 上記ORDER内容から要件を抽出してタスク分解する
- tasksは実装に必要な具体的作業を2-5個程度に分割
- target_filesには各タスクが変更対象とするファイルパスを配列で指定（省略可能）"""

    def _extract_json_from_response(self, response: str) -> str:
        """AI応答からJSONを抽出（コードブロック対応）"""
        text = response.strip()
        # コードブロック（```json ... ``` または ``` ... ```）を除去
        if text.startswith("```"):
            lines = text.split("\n")
            # 最初の```行を除去
            if lines[0].startswith("```"):
                lines = lines[1:]
            # 最後の```行を除去
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return text.strip()

    def _save_requirements(self, ai_response: str) -> None:
        """要件定義をファイルに保存"""
        try:
            # JSONをパース（コードブロック対応）
            json_text = self._extract_json_from_response(ai_response)
            data = json.loads(json_text)

            # --- Acceptance Criteria 補完（SpecGenerator利用時） ---
            if self.spec_generator and "tasks" in data:
                for task_def in data["tasks"]:
                    ai_ac = task_def.get("acceptance_criteria")
                    generated_ac = self.spec_generator.generate_acceptance_criteria(task_def)
                    if not ai_ac:
                        # AIがACを返さなかった場合: 推論生成ACを付与
                        task_def["acceptance_criteria"] = generated_ac
                    else:
                        # AIがACを返した場合: 推論生成ACでマージ補完
                        task_def["acceptance_criteria"] = self.spec_generator.merge_acceptance_criteria(
                            ai_ac, generated_ac
                        )

            # --- Spec バリデーション（SpecValidator利用時） ---
            if self.spec_validator and "tasks" in data:
                validation_result = self.spec_validator.validate_spec(
                    data["tasks"],
                    project_root=str(_project_root),
                )
                self.results["spec_validation"] = validation_result.to_dict()
                # 警告をログ出力
                for warning in validation_result.warnings:
                    logger.warning(f"[SpecValidator] {warning.get('message', '')}")
                for error in validation_result.errors:
                    logger.warning(f"[SpecValidator:ERROR] {error.get('message', '')}")
                self._log_step(
                    "spec_validation", "done",
                    f"score={validation_result.score:.2f}, "
                    f"errors={len(validation_result.errors)}, "
                    f"warnings={len(validation_result.warnings)}"
                )

            self.results["requirements"] = data

            # 2-1: GOAL作成
            self._log_step("step2_1_goal", "start", "01_GOAL.md作成開始")
            try:
                goal_file = self.result_dir / "01_GOAL.md"
                goal_content = self._format_goal(data.get("goal", {}))
                goal_file.write_text(goal_content, encoding="utf-8")
                self._log_step("step2_1_goal", "success", f"01_GOAL.md作成完了 ({len(goal_content)} bytes)")
            except Exception as e:
                self._log_step("step2_1_goal", "failed", f"01_GOAL.md作成失敗: {e}")
                raise

            # 2-2: 要件定義作成
            self._log_step("step2_2_requirements", "start", "02_REQUIREMENTS.md作成開始")
            try:
                req_file = self.result_dir / "02_REQUIREMENTS.md"
                req_content = self._format_requirements(data.get("requirements", {}))
                req_file.write_text(req_content, encoding="utf-8")
                self._log_step("step2_2_requirements", "success", f"02_REQUIREMENTS.md作成完了 ({len(req_content)} bytes)")
            except Exception as e:
                self._log_step("step2_2_requirements", "failed", f"02_REQUIREMENTS.md作成失敗: {e}")
                raise

            # 2-3: 要員計画作成
            self._log_step("step2_3_staffing", "start", "03_STAFFING.md作成開始")
            try:
                staff_file = self.result_dir / "03_STAFFING.md"
                staff_content = self._format_staffing(data.get("tasks", []))
                staff_file.write_text(staff_content, encoding="utf-8")
                self._log_step("step2_3_staffing", "success", f"03_STAFFING.md作成完了 ({len(staff_content)} bytes)")
            except Exception as e:
                self._log_step("step2_3_staffing", "failed", f"03_STAFFING.md作成失敗: {e}")
                raise

        except json.JSONDecodeError as e:
            logger.warning(f"JSON パースエラー: {e}")
            # プレーンテキストとして保存（デバッグ用）
            self._log_step("step2_1_goal", "failed", f"JSONパースエラー: {e}")
            (self.result_dir / "01_GOAL.md").write_text(ai_response, encoding="utf-8")
            # requirements を None に設定してエラーを明示
            self.results["requirements"] = None
            self._log_step("save_requirements", "failed", f"JSONパースエラー: {e}")

    def _format_goal(self, goal: Dict) -> str:
        """GOALドキュメントをフォーマット"""
        lines = [f"# {self.order_id} ゴール定義", ""]
        lines.append(f"## 概要\n{goal.get('summary', '（未定義）')}\n")

        if goal.get("objectives"):
            lines.append("## 目標")
            for obj in goal["objectives"]:
                lines.append(f"- {obj}")
            lines.append("")

        if goal.get("success_criteria"):
            lines.append("## 成功基準")
            for crit in goal["success_criteria"]:
                lines.append(f"- [ ] {crit}")
            lines.append("")

        return "\n".join(lines)

    def _format_requirements(self, req: Dict) -> str:
        """要件ドキュメントをフォーマット"""
        lines = [f"# {self.order_id} 要件定義", ""]

        if req.get("functional"):
            lines.append("## 機能要件")
            for r in req["functional"]:
                lines.append(f"- {r}")
            lines.append("")

        if req.get("non_functional"):
            lines.append("## 非機能要件")
            for r in req["non_functional"]:
                lines.append(f"- {r}")
            lines.append("")

        if req.get("constraints"):
            lines.append("## 制約事項")
            for c in req["constraints"]:
                lines.append(f"- {c}")
            lines.append("")

        return "\n".join(lines)

    def _format_staffing(self, tasks: List[Dict]) -> str:
        """STAFFINGドキュメントをフォーマット"""
        lines = [f"# {self.order_id} タスク計画", ""]
        lines.append("## タスク一覧\n")
        lines.append("| # | タスク名 | 優先度 | 推奨モデル | 依存 |")
        lines.append("|---|---------|--------|-----------|------|")

        for i, task in enumerate(tasks, 1):
            deps = ", ".join(str(d) for d in task.get("depends_on", [])) or "-"
            lines.append(
                f"| {i} | {task.get('title', '?')} | "
                f"{task.get('priority', 'P1')} | "
                f"{task.get('model', 'Sonnet')} | {deps} |"
            )

        lines.append("")
        lines.append("## タスク詳細\n")
        for i, task in enumerate(tasks, 1):
            lines.append(f"### {i}. {task.get('title', '?')}")
            lines.append(f"\n{task.get('description', '（説明なし）')}\n")

            # 対象ファイルリストの追加
            target_files = task.get("target_files", [])
            if target_files:
                lines.append("**対象ファイル**:")
                for file_path in target_files:
                    lines.append(f"- `{file_path}`")
                lines.append("")

        return "\n".join(lines)

    def _is_destructive_db_change(self, task_def: Dict) -> bool:
        """
        タスクが破壊的DB変更を含むかどうかを判定（ORDER_146）

        Args:
            task_def: タスク定義辞書

        Returns:
            破壊的DB変更を含む場合True
        """
        # 破壊的DB変更を示すキーワード
        DESTRUCTIVE_KEYWORDS = [
            "DROP TABLE",
            "DROP COLUMN",
            "ALTER TABLE",  # ALTER TABLEは一般的に破壊的
            "TRUNCATE",
            "DELETE FROM",  # DELETEは一般的に破壊的
            "REVIEW_QUEUE",  # review_queue関連
            "テーブル削除",
            "テーブル廃止",
            "カラム削除",
        ]

        title = task_def.get("title", "").upper()
        description = task_def.get("description", "").upper()
        text = f"{title} {description}"

        # キーワードマッチング
        for keyword in DESTRUCTIVE_KEYWORDS:
            if keyword.upper() in text:
                return True

        return False

    def _reorganize_destructive_db_tasks(self, tasks: List[Dict]) -> List[Dict]:
        """
        破壊的DB変更タスクを最終フェーズに配置（ORDER_146）

        Args:
            tasks: タスク定義のリスト

        Returns:
            再配置されたタスクリスト
        """
        if not tasks:
            return tasks

        # 破壊的タスクと通常タスクを分離
        destructive_tasks = []
        normal_tasks = []

        for task_def in tasks:
            if self._is_destructive_db_change(task_def):
                destructive_tasks.append(task_def)
                self._log_step(
                    "reorganize_tasks",
                    "warning",
                    f"破壊的DB変更タスク検出: {task_def.get('title', '?')}"
                )
            else:
                normal_tasks.append(task_def)

        if not destructive_tasks:
            # 破壊的タスクがない場合はそのまま返す
            return tasks

        # 破壊的タスクの依存関係をチェック
        all_task_titles = {task.get("title") for task in tasks}
        warnings = []

        for destructive_task in destructive_tasks:
            task_title = destructive_task.get("title", "")
            # 他のタスクがこの破壊的タスクに依存しているかチェック
            for task in normal_tasks:
                depends_on = task.get("depends_on", [])
                if task_title in depends_on:
                    warning_msg = (
                        f"【警告】通常タスク '{task.get('title')}' が "
                        f"破壊的DB変更タスク '{task_title}' に依存しています。"
                    )
                    warnings.append(warning_msg)
                    self._log_step("reorganize_tasks", "warning", warning_msg)

        # 破壊的タスクに通常タスクへの依存を追加（最終フェーズに配置）
        # 通常タスクのタイトルリストを取得
        normal_task_titles = [task.get("title") for task in normal_tasks if task.get("title")]

        for destructive_task in destructive_tasks:
            # 既存の依存関係を取得
            existing_deps = destructive_task.get("depends_on", [])
            if not isinstance(existing_deps, list):
                existing_deps = []

            # 通常タスクへの依存を追加（重複を避ける）
            new_deps = list(set(existing_deps + normal_task_titles))
            destructive_task["depends_on"] = new_deps

            self._log_step(
                "reorganize_tasks",
                "info",
                f"破壊的タスク '{destructive_task.get('title')}' を最終フェーズに配置 "
                f"(依存: {len(new_deps)}件)"
            )

        # 再配置: 通常タスク → 破壊的タスク
        reorganized = normal_tasks + destructive_tasks

        if warnings:
            logger.warning(f"破壊的DB変更タスク依存関係の警告が{len(warnings)}件発生しました")

        return reorganized

    def _step_create_tasks(self) -> None:
        """Step 5: タスクをDB登録"""
        self._log_step("create_tasks", "start", "")

        requirements = self.results.get("requirements", {})
        tasks = requirements.get("tasks", [])

        if not tasks:
            self._log_step("create_tasks", "skip", "タスクなし")
            return

        try:
            # ORDER作成（未作成の場合）
            conn = get_connection()
            try:
                if not order_exists(conn, self.order_id, self.project_id):
                    self._create_order_in_db(conn, requirements)
            finally:
                conn.close()

            # 破壊的DB変更タスクの再配置（ORDER_146）
            tasks = self._reorganize_destructive_db_tasks(tasks)

            # 2-4: タスク作成
            self._log_step("step2_4_tasks", "start", f"タスク作成開始 ({len(tasks)}件)")
            created_tasks = []
            task_id_map = {}  # タスク名 → TASK_ID マッピング

            for i, task_def in enumerate(tasks):
                task_title = task_def.get("title", f"Task {i+1}")
                try:
                    # 依存関係の解決
                    depends_on = []
                    for dep_name in task_def.get("depends_on", []):
                        if dep_name in task_id_map:
                            depends_on.append(task_id_map[dep_name])

                    task_result = self._create_task_in_db(task_def, depends_on)
                    created_tasks.append(task_result)
                    task_id_map[task_title] = task_result["id"]
                    self._log_step("step2_4_tasks", "progress", f"タスク作成: {task_result['id']} - {task_title}")
                except Exception as e:
                    self._log_step("step2_4_tasks", "failed", f"タスク作成失敗: {task_title} - {e}")
                    # Record incident for task creation failure
                    try:
                        log_incident(
                            category='DATA_INTEGRITY',
                            description=f"タスク作成失敗 ({task_title}): {str(e)}",
                            severity='MEDIUM',
                            project_id=self.project_id,
                            order_id=self.order_id
                        )
                    except Exception as inc_err:
                        logger.warning(f"インシデント記録に失敗: {inc_err}")
                    raise

            self.results["created_tasks"] = created_tasks
            self._log_step("step2_4_tasks", "success", f"タスク作成完了 ({len(created_tasks)}件)")

            # 2-5: TASK markdown生成
            self._generate_task_markdowns(created_tasks)

            self._log_step("create_tasks", "success", f"{len(created_tasks)} tasks")
        except Exception as e:
            # Record incident for overall task creation process failure
            if "DATA_INTEGRITY" not in str(e):  # Avoid duplicate logging
                try:
                    log_incident(
                        category='SYSTEM_ERROR',
                        description=f"タスク作成処理全体の失敗: {str(e)}",
                        severity='HIGH',
                        project_id=self.project_id,
                        order_id=self.order_id
                    )
                except Exception as inc_err:
                    logger.warning(f"インシデント記録に失敗: {inc_err}")
            raise

    def _create_order_in_db(self, conn, requirements: Dict) -> None:
        """ORDERをDBに作成"""
        from order.create import create_order

        goal = requirements.get("goal", {})
        title = goal.get("summary", self.order_id)

        # ORDER.md からタイトルを取得（あれば）
        order_content = self.results.get("order_content", "")
        for line in order_content.split("\n"):
            if line.startswith("# "):
                # "# ORDER_095: タイトル" 形式から抽出
                parts = line[2:].split(":", 1)
                if len(parts) > 1:
                    title = parts[1].strip()
                break

        create_order(
            self.project_id,
            title,
            order_id=self.order_id,
            priority="P1",
        )
        self._log_step("create_order_db", "success", f"ORDER={self.order_id}")

    def _create_task_in_db(self, task_def: Dict, depends_on: List[str]) -> Dict:
        """タスクをDBに作成"""
        from task.create import create_task

        # target_filesをJSON文字列に変換（あれば）
        target_files = task_def.get("target_files")
        target_files_json = None
        if target_files:
            import json
            target_files_json = json.dumps(target_files, ensure_ascii=False)

        # 破壊的DB変更フラグを設定（ORDER_146）
        is_destructive = self._is_destructive_db_change(task_def)

        result = create_task(
            self.project_id,
            self.order_id,
            task_def.get("title", "Untitled Task"),
            description=task_def.get("description"),
            priority=task_def.get("priority", "P1"),
            recommended_model=task_def.get("model"),
            depends_on=depends_on if depends_on else None,
            target_files=target_files_json,
            is_destructive_db_change=is_destructive,
        )
        return result

    def _generate_task_markdowns(self, created_tasks: List[Dict]) -> None:
        """
        タスクごとにTASK_XXX.mdファイルを生成

        Args:
            created_tasks: 作成されたタスク情報のリスト
        """
        self._log_step("step2_5_task_markdowns", "start", f"TASK markdown生成開始 ({len(created_tasks)}件)")

        # 04_QUEUEディレクトリ作成
        queue_dir = self.result_dir / "04_QUEUE"
        queue_dir.mkdir(parents=True, exist_ok=True)

        generated_count = 0
        for task in created_tasks:
            try:
                task_id = task.get("id", "UNKNOWN")
                task_file = queue_dir / f"{task_id}.md"

                # タスクのmarkdown内容を生成
                content = self._format_task_markdown(task)

                # ファイルに書き込み
                task_file.write_text(content, encoding="utf-8")
                generated_count += 1

                self._log_step("step2_5_task_markdowns", "progress", f"{task_id}.md 生成完了")

            except Exception as e:
                self._log_step("step2_5_task_markdowns", "warning", f"{task.get('id', '?')} 生成失敗: {e}")

        self._log_step("step2_5_task_markdowns", "success", f"TASK markdown生成完了 ({generated_count}件)")

    def _format_task_markdown(self, task: Dict) -> str:
        """
        TASKファイルのMarkdown内容をフォーマット

        Args:
            task: タスク情報辞書

        Returns:
            Markdown形式のタスク内容
        """
        task_id = task.get("id", "UNKNOWN")
        title = task.get("title", "Untitled Task")
        description = task.get("description", "（説明なし）")
        priority = task.get("priority", "P1")
        model = task.get("recommended_model", "Sonnet")
        depends_on = task.get("depends_on", [])
        target_files_json = task.get("target_files")

        # 依存タスクの表示
        depends_display = ", ".join(depends_on) if depends_on else "なし"

        # 対象ファイルのパース
        target_files = []
        if target_files_json:
            try:
                import json
                target_files = json.loads(target_files_json)
            except Exception:
                pass

        lines = [
            f"# {task_id}: {title}",
            "",
            "## 基本情報",
            "",
            "| 項目 | 内容 |",
            "|------|------|",
            f"| タスクID | {task_id} |",
            f"| ORDER | {self.order_id} |",
            f"| 推奨モデル | {model} |",
            f"| 優先度 | {priority} |",
            f"| 依存 | {depends_display} |",
            "",
            "---",
            "",
        ]

        # 実施内容セクション（descriptionを構造化して表示）
        lines.append("## 実施内容")
        lines.append("")

        # descriptionが複数行の場合は箇条書きとして表示
        if description and description.strip():
            desc_lines = description.strip().split("\n")
            if len(desc_lines) == 1:
                lines.append(description)
            else:
                for line in desc_lines:
                    line = line.strip()
                    if line:
                        if not line.startswith("-") and not line.startswith("*"):
                            lines.append(f"- {line}")
                        else:
                            lines.append(line)
        else:
            lines.append("（タスク説明を参照）")

        lines.append("")
        lines.append("---")
        lines.append("")

        # Acceptance Criteria セクション（SpecGenerator利用時）
        acceptance_criteria = task.get("acceptance_criteria")
        if self.spec_generator and acceptance_criteria:
            lines.append("## Acceptance Criteria")
            lines.append("")
            ac_markdown = self.spec_generator.format_acceptance_criteria_markdown(acceptance_criteria)
            lines.append(ac_markdown)
            lines.append("---")
            lines.append("")

        # 完了条件セクション
        lines.append("## 完了条件")
        lines.append("")
        if acceptance_criteria:
            # ACがある場合はAC準拠の具体的な完了条件を生成
            lines.append("- [ ] 全てのAcceptance Criteriaが満たされていること")
            for file_path in target_files:
                lines.append(f"- [ ] `{file_path}` が正常に作成/更新されていること")
            lines.append("- [ ] Python構文エラーがないこと（`py_compile`通過）")
        else:
            # フォールバック（AC未生成時）
            lines.append("- [ ] タスクの実施内容がすべて完了していること")
            for file_path in target_files:
                lines.append(f"- [ ] `{file_path}` が正常に作成/更新されていること")
            lines.append("- [ ] エラーや警告が残っていないこと")
        lines.append("")
        lines.append("---")
        lines.append("")

        # 対象ファイルセクション
        if target_files:
            lines.append("## 対象ファイル")
            lines.append("")
            for file_path in target_files:
                lines.append(f"- `{file_path}`")
            lines.append("")
            lines.append("---")
            lines.append("")

        # 注意事項セクション
        lines.append("## 注意事項")
        lines.append("")

        # 依存タスクがある場合は警告
        if depends_on:
            lines.append(f"**依存タスク**: このタスクは以下のタスクが完了するまで実行できません")
            for dep in depends_on:
                lines.append(f"- {dep}")
            lines.append("")

        # 既知バグパターン参照を追加
        lines.append("**既知バグパターン**: 実装前に必ず既知バグパターン（DBのbugsテーブル）を確認してください")
        lines.append("")

        lines.append("---")
        lines.append("")

        return "\n".join(lines)

    def _step_update_order_status(self) -> None:
        """Step 6: ORDERステータスを更新"""
        self._log_step("update_order", "start", "")

        from order.update import update_order_status

        try:
            update_order_status(
                self.project_id,
                self.order_id,
                "IN_PROGRESS",
                role="PM",
            )
            self._log_step("update_order", "success", "status=IN_PROGRESS")
        except Exception as e:
            # ステータス更新失敗は警告のみ
            self._log_step("update_order", "warning", str(e))


def main():
    """CLI エントリーポイント"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="PM処理を1コマンドで実行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("order_number", help="ORDER番号（例: 095）")
    parser.add_argument("--dry-run", action="store_true", help="実行計画のみ表示")
    parser.add_argument("--skip-ai", action="store_true", help="AI処理をスキップ")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--timeout", type=int, default=600, help="タイムアウト秒数")
    parser.add_argument("--model", default="sonnet", help="AIモデル（haiku/sonnet/opus）")
    parser.add_argument("--no-stream", action="store_true", help="リアルタイム出力を無効化")

    args = parser.parse_args()

    # 詳細ログモード
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # PM処理実行
    processor = PMProcessor(
        args.project_id,
        args.order_number,
        dry_run=args.dry_run,
        skip_ai=args.skip_ai,
        verbose=args.verbose,
        timeout=args.timeout,
        model=args.model,
        stream_output=not args.no_stream,  # --no-stream指定時は無効化
    )

    results = processor.process()

    # 出力
    if args.json:
        # 大きなコンテンツは除外
        output = {k: v for k, v in results.items() if k != "order_content"}
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    else:
        if results["success"]:
            print(f"【PM処理完了】{results['order_id']}")
            print(f"  プロジェクト: {results['project_id']}")
            if results.get("created_tasks"):
                print(f"  作成タスク: {len(results['created_tasks'])}件")
        else:
            print(f"【PM処理失敗】{results.get('error', '不明なエラー')}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
