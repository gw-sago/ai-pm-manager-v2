#!/usr/bin/env python3
"""
AI PM Framework - 影響分析ロジック

APPROVED後に後続タスク（QUEUED/BLOCKED）を取得し、完了タスクのREPORT内容と
後続タスクのdescription/target_filesを比較してAI判定で影響あり/なしを判定する。
影響ありの場合は更新案（新しいdescription/target_files）を生成して返す。

Usage:
    from review.impact_analysis import analyze_impact, ImpactAnalysisResult

    result = analyze_impact(
        project_id="ai_pm_manager",
        completed_task_id="TASK_976",
        order_id="ORDER_103",
        report_content="...",
        model="sonnet",
        timeout=300,
    )

    if result.success and result.has_impact:
        for task_id, updates in result.task_updates.items():
            print(f"Task {task_id} needs update: {updates}")
"""

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

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
        get_connection, fetch_one, fetch_all,
        row_to_dict, rows_to_dicts, DatabaseError
    )
    from config.db_config import get_project_paths
except ImportError as e:
    logger.error(f"内部モジュールのインポートに失敗: {e}")
    sys.exit(1)

# claude_cli インポート（ORDER_168: claude_runner → claude_cli移行）
try:
    from utils.claude_cli import create_runner, ClaudeRunner, ClaudeResult
    CLAUDE_RUNNER_AVAILABLE = True
except ImportError:
    CLAUDE_RUNNER_AVAILABLE = False
    logger.warning("claude_cli が利用できません。影響分析はスキップされます。")


@dataclass
class TaskUpdate:
    """タスク更新内容"""
    task_id: str
    current_description: str
    updated_description: Optional[str] = None
    current_target_files: Optional[str] = None
    updated_target_files: Optional[str] = None
    reason: str = ""

    def has_changes(self) -> bool:
        """更新があるか"""
        return (self.updated_description is not None or
                self.updated_target_files is not None)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "task_id": self.task_id,
            "current_description": self.current_description,
            "updated_description": self.updated_description,
            "current_target_files": self.current_target_files,
            "updated_target_files": self.updated_target_files,
            "reason": self.reason,
            "has_changes": self.has_changes(),
        }


@dataclass
class ImpactAnalysisResult:
    """影響分析結果"""
    success: bool
    has_impact: bool = False
    task_updates: Dict[str, TaskUpdate] = field(default_factory=dict)
    error: Optional[str] = None
    ai_response: Optional[str] = None
    cost_usd: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "success": self.success,
            "has_impact": self.has_impact,
            "task_updates": {k: v.to_dict() for k, v in self.task_updates.items()},
            "error": self.error,
            "cost_usd": self.cost_usd,
        }


def analyze_impact(
    project_id: str,
    completed_task_id: str,
    order_id: str,
    report_content: str,
    *,
    model: str = "sonnet",
    timeout: int = 300,
    verbose: bool = False,
) -> ImpactAnalysisResult:
    """
    完了タスクのREPORT内容と後続タスクを比較して影響分析を実行

    Args:
        project_id: プロジェクトID
        completed_task_id: 完了したタスクID
        order_id: ORDER ID
        report_content: 完了タスクのREPORT内容
        model: AIモデル（haiku/sonnet/opus）
        timeout: タイムアウト秒数
        verbose: 詳細ログ出力

    Returns:
        ImpactAnalysisResult: 影響分析結果
    """
    if verbose:
        logger.setLevel(logging.DEBUG)

    logger.info(f"影響分析開始: {completed_task_id} (ORDER: {order_id})")

    # claude_runner利用不可
    if not CLAUDE_RUNNER_AVAILABLE:
        logger.warning("claude_runner利用不可 - 影響分析をスキップ")
        return ImpactAnalysisResult(
            success=True,
            has_impact=False,
            error="claude_runner not available"
        )

    try:
        # 1. 後続タスク（QUEUED/BLOCKED）を取得
        successor_tasks = _get_successor_tasks(project_id, order_id, completed_task_id)

        if not successor_tasks:
            logger.info("後続タスクなし - 影響分析不要")
            return ImpactAnalysisResult(success=True, has_impact=False)

        logger.info(f"後続タスク {len(successor_tasks)}件を分析対象にします")

        # 2. AI判定でREPORT内容と後続タスクの整合性を確認
        analysis_result = _analyze_with_ai(
            completed_task_id=completed_task_id,
            report_content=report_content,
            successor_tasks=successor_tasks,
            model=model,
            timeout=timeout,
        )

        if not analysis_result.success:
            return ImpactAnalysisResult(
                success=False,
                error=analysis_result.error_message or "AI分析失敗"
            )

        # 3. AI応答をパースして影響判定と更新案を抽出
        task_updates = _parse_ai_response(analysis_result.result_text, successor_tasks)

        has_impact = any(update.has_changes() for update in task_updates.values())

        if has_impact:
            logger.info(f"影響あり: {len([u for u in task_updates.values() if u.has_changes()])}件のタスク更新が必要")
        else:
            logger.info("影響なし: 後続タスクの更新は不要")

        return ImpactAnalysisResult(
            success=True,
            has_impact=has_impact,
            task_updates=task_updates,
            ai_response=analysis_result.result_text,
            cost_usd=analysis_result.cost_usd,
        )

    except Exception as e:
        logger.exception(f"影響分析エラー: {e}")
        return ImpactAnalysisResult(
            success=False,
            error=f"影響分析エラー: {e}"
        )


def _get_successor_tasks(
    project_id: str,
    order_id: str,
    completed_task_id: str
) -> List[Dict[str, Any]]:
    """
    後続タスク（QUEUED/BLOCKED）を取得

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        completed_task_id: 完了したタスクID

    Returns:
        後続タスクのリスト
    """
    conn = get_connection()
    try:
        # 同じORDER内のQUEUED/BLOCKEDタスクを取得
        # 完了したタスクより後に実行される可能性があるタスクが対象
        rows = fetch_all(
            conn,
            """
            SELECT
                id,
                title,
                description,
                status,
                priority,
                recommended_model
            FROM tasks
            WHERE project_id = ?
              AND order_id = ?
              AND status IN ('QUEUED', 'BLOCKED')
            ORDER BY priority, id
            """,
            (project_id, order_id)
        )

        return rows_to_dicts(rows)

    finally:
        conn.close()


def _analyze_with_ai(
    completed_task_id: str,
    report_content: str,
    successor_tasks: List[Dict[str, Any]],
    model: str,
    timeout: int,
) -> ClaudeResult:
    """
    AIで影響分析を実行

    Args:
        completed_task_id: 完了したタスクID
        report_content: REPORT内容
        successor_tasks: 後続タスクのリスト
        model: AIモデル
        timeout: タイムアウト秒数

    Returns:
        ClaudeResult: AI実行結果
    """
    # プロンプト構築
    prompt = _build_impact_analysis_prompt(
        completed_task_id,
        report_content,
        successor_tasks
    )

    # claude_runner 初期化
    runner = create_runner(
        model=model,
        max_turns=20,
        timeout_seconds=timeout,
    )

    # AI実行
    logger.debug("AI影響分析を実行中...")
    result = runner.run(prompt)

    return result


def _build_impact_analysis_prompt(
    completed_task_id: str,
    report_content: str,
    successor_tasks: List[Dict[str, Any]],
) -> str:
    """影響分析用プロンプトを構築"""

    # 後続タスク一覧を整形
    successor_list = []
    for task in successor_tasks:
        successor_list.append(f"""
### {task['id']}: {task['title']}
- **ステータス**: {task['status']}
- **優先度**: {task['priority']}
- **説明**:
{task['description'] or '（説明なし）'}
""")

    successor_text = "\n".join(successor_list)

    return f"""あなたはプロジェクトマネージャーです。完了したタスクの実装内容（REPORT）と後続タスクの整合性を分析してください。

## 完了タスク
- **タスクID**: {completed_task_id}
- **REPORT内容**:
```markdown
{report_content}
```

## 後続タスク（QUEUED/BLOCKED）
{successor_text}

## 分析観点
1. 完了タスクのREPORT内容と後続タスクのdescription/前提条件の整合性
2. 新規作成・変更されたファイルが後続タスクの前提と矛盾しないか
3. interface/スキーマ変更が後続タスクに影響しないか
4. 想定外のファイル構成変更が後続タスクの実行可能性を損なわないか

## 出力形式
JSON形式で以下の構造を返してください:
{{
  "has_impact": true/false,
  "summary": "影響分析の要約（1-2文）",
  "task_updates": [
    {{
      "task_id": "TASK_XXX",
      "needs_update": true/false,
      "reason": "更新が必要な理由（影響の内容）",
      "updated_description": "更新後のdescription（必要な場合のみ）",
      "updated_target_files": "更新後のtarget_files（必要な場合のみ、カンマ区切り）"
    }}
  ]
}}

## 判定基準
- **needs_update = true**: 完了タスクの実装結果が後続タスクの前提を変更している場合
  - 例: ファイル構成変更、interface変更、実装方針変更など
  - updated_description/updated_target_filesに具体的な更新案を記載
- **needs_update = false**: 影響がない、または後続タスクがそのまま実行可能な場合

## 重要
- JSONのみを出力し、説明文は含めないでください
- needs_update=falseのタスクも task_updates に含めてください（reason は "影響なし" など）
- updated_description/updated_target_files は needs_update=true の場合のみ設定してください
"""


def _parse_ai_response(
    ai_response: str,
    successor_tasks: List[Dict[str, Any]]
) -> Dict[str, TaskUpdate]:
    """
    AI応答をパースして TaskUpdate に変換

    Args:
        ai_response: AI応答（JSON）
        successor_tasks: 後続タスクのリスト

    Returns:
        タスクID -> TaskUpdate のマップ
    """
    task_updates = {}

    try:
        # JSON パース
        data = json.loads(ai_response)

        # 後続タスクの現在の情報をマップ化
        task_map = {task["id"]: task for task in successor_tasks}

        # AI応答から更新情報を抽出
        for update_info in data.get("task_updates", []):
            task_id = update_info.get("task_id")
            if not task_id or task_id not in task_map:
                continue

            current_task = task_map[task_id]
            needs_update = update_info.get("needs_update", False)

            task_update = TaskUpdate(
                task_id=task_id,
                current_description=current_task.get("description", ""),
                current_target_files=None,  # スキーマにtarget_filesカラムがないため
                reason=update_info.get("reason", ""),
            )

            # 更新が必要な場合のみ更新案を設定
            if needs_update:
                if "updated_description" in update_info:
                    task_update.updated_description = update_info["updated_description"]
                if "updated_target_files" in update_info:
                    task_update.updated_target_files = update_info["updated_target_files"]

            task_updates[task_id] = task_update

        logger.info(f"AI応答パース完了: {len(task_updates)}件のタスク分析")

    except json.JSONDecodeError as e:
        logger.warning(f"AI応答のJSONパース失敗: {e}")
        # パース失敗時は影響なしとして扱う
        for task in successor_tasks:
            task_updates[task["id"]] = TaskUpdate(
                task_id=task["id"],
                current_description=task.get("description", ""),
                reason="AI応答パース失敗 - 影響なしと仮定",
            )

    return task_updates


# CLI実行用（デバッグ・テスト用）
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="影響分析を実行")
    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("task_id", help="完了したタスクID")
    parser.add_argument("order_id", help="ORDER ID")
    parser.add_argument("--report-file", help="REPORTファイルパス")
    parser.add_argument("--model", default="sonnet", help="AIモデル")
    parser.add_argument("--timeout", type=int, default=300, help="タイムアウト秒数")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ")

    args = parser.parse_args()

    # REPORTファイル読み込み
    if args.report_file:
        report_content = Path(args.report_file).read_text(encoding="utf-8")
    else:
        # デフォルトREPORTパスを推測
        report_num = args.task_id.replace("TASK_", "")
        _paths = get_project_paths(args.project_id)
        report_file = (
            _paths["result"] / args.order_id / "05_REPORT" / f"REPORT_{report_num}.md"
        )
        if report_file.exists():
            report_content = report_file.read_text(encoding="utf-8")
        else:
            print(f"エラー: REPORTファイルが見つかりません: {report_file}", file=sys.stderr)
            sys.exit(1)

    # 影響分析実行
    result = analyze_impact(
        project_id=args.project_id,
        completed_task_id=args.task_id,
        order_id=args.order_id,
        report_content=report_content,
        model=args.model,
        timeout=args.timeout,
        verbose=args.verbose,
    )

    # 結果出力
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
