#!/usr/bin/env python3
"""
AI PM Framework - プロジェクト情報最新化スクリプト

プロジェクトIDを受け取り、ORDER履歴・RESULT・タスク完了状況をDB
およびファイルから収集し、AIへプロンプトを送信してPROJECT_INFO.md
の内容を再生成・上書き保存する。

Usage:
    python backend/project/refresh_info.py PROJECT_ID [options]

Arguments:
    PROJECT_ID          プロジェクトID

Options:
    --model MODEL       AIモデル（haiku/sonnet/opus、デフォルト: sonnet）
    --timeout SEC       タイムアウト秒数（デフォルト: 600）
    --skip-ai           AI処理をスキップ（コンテキスト収集のみ）
    --json              JSON形式で出力

Example:
    python backend/project/refresh_info.py ai_pm_manager_v2
    python backend/project/refresh_info.py ai_pm_manager_v2 --model opus --json
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# 内部モジュールインポート
try:
    from config.db_config import get_project_paths, setup_utf8_output
    from utils.db import (
        DatabaseError,
        fetch_all,
        fetch_one,
        get_connection,
        rows_to_dicts,
    )
    from utils.validation import ValidationError, project_exists, validate_project_name
except ImportError as e:
    logger.error(f"内部モジュールのインポートに失敗: {e}")
    sys.exit(1)

# claude_cli インポート
try:
    from utils.claude_cli import ClaudeResult, ClaudeRunner, create_runner

    CLAUDE_RUNNER_AVAILABLE = True
except ImportError:
    CLAUDE_RUNNER_AVAILABLE = False
    logger.warning("claude_cli が利用できません。--skip-ai オプションのみ利用可能です。")


class RefreshInfoError(Exception):
    """プロジェクト情報最新化エラー"""
    pass


class ProjectInfoRefresher:
    """プロジェクト情報（PROJECT_INFO.md）を最新化するクラス"""

    def __init__(
        self,
        project_id: str,
        *,
        model: str = "sonnet",
        timeout: int = 600,
        skip_ai: bool = False,
    ):
        self.project_id = project_id
        self.model = model
        self.timeout = timeout
        self.skip_ai = skip_ai

        # Roamingパスを使用（get_project_paths()経由）
        _paths = get_project_paths(project_id)
        self.project_dir: Path = _paths["base"]
        self.orders_dir: Path = _paths["orders"]
        self.result_dir: Path = _paths["result"]
        self.project_info_path: Path = self.project_dir / "PROJECT_INFO.md"

        # 処理結果
        self.results: Dict[str, Any] = {
            "project_id": project_id,
            "success": False,
            "error": None,
            "context_summary": {},
            "project_info_path": str(self.project_info_path),
        }

        # claude_runner インスタンス
        self.runner: Optional[ClaudeRunner] = None
        if CLAUDE_RUNNER_AVAILABLE and not skip_ai:
            try:
                self.runner = create_runner(
                    model=model,
                    max_turns=1,
                    timeout_seconds=timeout,
                )
            except RuntimeError as e:
                logger.warning(f"ClaudeRunnerの初期化に失敗: {e}")

    # ------------------------------------------------------------------
    # 公開メソッド
    # ------------------------------------------------------------------

    def refresh(self) -> Dict[str, Any]:
        """
        プロジェクト情報を最新化する

        Returns:
            処理結果の辞書
        """
        try:
            # Step 1: プロジェクト存在確認
            self._validate_project()

            # Step 2: コンテキスト収集
            context = self._collect_context()
            self.results["context_summary"] = {
                "order_count": len(context.get("orders", [])),
                "completed_task_count": context.get("completed_task_count", 0),
                "total_task_count": context.get("total_task_count", 0),
                "result_files_count": context.get("result_files_count", 0),
                "current_project_info_exists": context.get("current_project_info_exists", False),
            }

            if self.skip_ai or not self.runner:
                logger.info("AI処理をスキップします（コンテキスト収集のみ）")
                self.results["success"] = True
                self.results["skipped_ai"] = True
                return self.results

            # Step 3: プロンプト構築
            prompt = self._build_prompt(context)

            # Step 4: AI呼び出し
            logger.info(f"AI呼び出し開始 (model={self.model})")
            result = self.runner.run(prompt)

            if not result.success:
                raise RefreshInfoError(f"AI呼び出しに失敗: {result.error_message}")

            # Step 5: PROJECT_INFO.md を生成・保存
            new_content = self._extract_markdown(result.result_text)
            self._save_project_info(new_content)

            self.results["success"] = True
            logger.info(f"PROJECT_INFO.md を更新しました: {self.project_info_path}")

        except RefreshInfoError as e:
            self.results["error"] = str(e)
            logger.error(f"プロジェクト情報最新化エラー: {e}")
        except Exception as e:
            self.results["error"] = f"予期しないエラー: {e}"
            logger.exception("詳細エラー")

        return self.results

    # ------------------------------------------------------------------
    # 内部メソッド: バリデーション
    # ------------------------------------------------------------------

    def _validate_project(self) -> None:
        """プロジェクト存在確認"""
        validate_project_name(self.project_id)
        conn = get_connection()
        try:
            if not project_exists(conn, self.project_id):
                raise RefreshInfoError(
                    f"プロジェクトが見つかりません: {self.project_id}"
                )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 内部メソッド: コンテキスト収集
    # ------------------------------------------------------------------

    def _collect_context(self) -> Dict[str, Any]:
        """DBおよびファイルからコンテキストを収集する"""
        context: Dict[str, Any] = {}

        conn = get_connection()
        try:
            # プロジェクト基本情報
            project_row = fetch_one(
                conn,
                "SELECT id, name, status, created_at, updated_at FROM projects WHERE id = ?",
                (self.project_id,),
            )
            context["project"] = dict(project_row) if project_row else {}

            # ORDER履歴（全件）
            order_rows = fetch_all(
                conn,
                """
                SELECT id, title, priority, status, started_at, completed_at, created_at
                FROM orders
                WHERE project_id = ?
                ORDER BY created_at ASC
                """,
                (self.project_id,),
            )
            context["orders"] = rows_to_dicts(order_rows)

            # タスク完了状況（ORDERごとの集計）
            task_stats_rows = fetch_all(
                conn,
                """
                SELECT
                    order_id,
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN status IN ('QUEUED', 'IN_PROGRESS', 'BLOCKED', 'REWORK') THEN 1 ELSE 0 END) AS in_progress
                FROM tasks
                WHERE project_id = ?
                GROUP BY order_id
                """,
                (self.project_id,),
            )
            context["task_stats_by_order"] = rows_to_dicts(task_stats_rows)

            # 全タスク合計
            total_row = fetch_one(
                conn,
                "SELECT COUNT(*) AS total FROM tasks WHERE project_id = ?",
                (self.project_id,),
            )
            completed_row = fetch_one(
                conn,
                "SELECT COUNT(*) AS cnt FROM tasks WHERE project_id = ? AND status = 'COMPLETED'",
                (self.project_id,),
            )
            context["total_task_count"] = total_row["total"] if total_row else 0
            context["completed_task_count"] = completed_row["cnt"] if completed_row else 0

            # バックログ件数
            backlog_row = fetch_one(
                conn,
                "SELECT COUNT(*) AS cnt FROM backlog_items WHERE project_id = ? AND status != 'DONE'",
                (self.project_id,),
            )
            context["pending_backlog_count"] = backlog_row["cnt"] if backlog_row else 0

        finally:
            conn.close()

        # RESULTディレクトリのファイル一覧収集
        result_files = self._collect_result_files()
        context["result_files"] = result_files
        context["result_files_count"] = len(result_files)

        # 現在のPROJECT_INFO.md（存在する場合）
        if self.project_info_path.exists():
            try:
                current_content = self.project_info_path.read_text(encoding="utf-8")
                # 最大5000文字に制限（プロンプトサイズ管理）
                context["current_project_info"] = current_content[:5000]
                context["current_project_info_exists"] = True
                context["current_project_info_truncated"] = len(current_content) > 5000
            except Exception as e:
                logger.warning(f"現在のPROJECT_INFO.md読み込み失敗: {e}")
                context["current_project_info"] = ""
                context["current_project_info_exists"] = False
        else:
            context["current_project_info"] = ""
            context["current_project_info_exists"] = False

        return context

    def _collect_result_files(self) -> List[Dict[str, str]]:
        """RESULTディレクトリ配下の主要ファイル一覧を収集"""
        files = []
        if not self.result_dir.exists():
            return files

        try:
            for order_dir in sorted(self.result_dir.iterdir()):
                if not order_dir.is_dir():
                    continue
                order_id = order_dir.name
                for f in sorted(order_dir.rglob("*.md")):
                    relative = str(f.relative_to(self.result_dir))
                    files.append({"order_id": order_id, "path": relative})
        except Exception as e:
            logger.warning(f"RESULTファイル一覧収集失敗: {e}")

        return files

    # ------------------------------------------------------------------
    # 内部メソッド: プロンプト構築
    # ------------------------------------------------------------------

    def _build_prompt(self, context: Dict[str, Any]) -> str:
        """PROJECT_INFO.md再生成用プロンプトを構築"""

        project = context.get("project", {})
        orders = context.get("orders", [])
        task_stats = context.get("task_stats_by_order", [])
        total_tasks = context.get("total_task_count", 0)
        completed_tasks = context.get("completed_task_count", 0)
        pending_backlog = context.get("pending_backlog_count", 0)
        current_info = context.get("current_project_info", "")
        result_files = context.get("result_files", [])

        # ORDERサマリ生成
        order_lines = []
        task_stat_map = {s["order_id"]: s for s in task_stats}
        for o in orders:
            oid = o.get("id", "")
            stats = task_stat_map.get(oid, {})
            total = stats.get("total", 0)
            done = stats.get("completed", 0)
            progress = f"{done}/{total}" if total > 0 else "0/0"
            order_lines.append(
                f"- {oid} [{o.get('status', '?')}] {o.get('title', '（タイトル不明）')} "
                f"(優先度:{o.get('priority','?')}, タスク進捗:{progress})"
            )
        order_summary = "\n".join(order_lines) if order_lines else "（ORDERなし）"

        # RESULTファイルサマリ（最大30件）
        result_file_lines = [f"- {f['path']}" for f in result_files[:30]]
        result_file_summary = "\n".join(result_file_lines) if result_file_lines else "（ファイルなし）"

        today = datetime.now().strftime("%Y-%m-%d")

        prompt = f"""あなたはAI PMプロジェクト管理システムのドキュメント自動更新エージェントです。
以下のプロジェクト情報をもとに、PROJECT_INFO.md の内容を最新の状態に再生成してください。

## プロジェクト基本情報

- プロジェクトID: {project.get('id', self.project_id)}
- プロジェクト名: {project.get('name', self.project_id)}
- ステータス: {project.get('status', '不明')}
- 作成日: {project.get('created_at', '不明')}
- 最終更新: {project.get('updated_at', '不明')}
- 今日の日付: {today}

## ORDER履歴（全{len(orders)}件）

{order_summary}

## タスク完了状況

- 総タスク数: {total_tasks}件
- 完了タスク数: {completed_tasks}件
- 完了率: {round(completed_tasks / total_tasks * 100) if total_tasks > 0 else 0}%
- 未完了バックログ: {pending_backlog}件

## RESULTディレクトリの主要ファイル（最大30件）

{result_file_summary}

## 現在のPROJECT_INFO.md（参考・最大5000文字）

```markdown
{current_info if current_info else "（PROJECT_INFO.md が存在しません）"}
```

## 出力ルール

- Markdownのみを出力してください（説明文・コードブロック囲みは不要）
- 以下の構成でPROJECT_INFO.mdを再生成してください:

# AI PM Manager V2 - プロジェクト情報

> **最終更新**: {today}
> **ステータス**: （現在のステータス）

---

## 目次

（適切な目次を生成）

---

## 1. プロジェクト概要

（プロジェクトID、名前、概要、目的、技術スタック等）

## 2. フォルダ構成と各ディレクトリの責務

（既存の情報を維持しつつ最新化）

## 3. DBテーブル設計書

（既存の情報を維持）

## 4. アーキテクチャ図・シーケンス図・フロー図

（既存の情報を維持）

## 5. 運用ルール・設計思想

（既存の情報を維持）

## 6. ORDER履歴サマリ

（収集したORDER履歴を反映）

## 7. 開発ルール・バグ修正履歴

（既存の情報を維持しつつ最新化）

【重要】
- 既存のPROJECT_INFO.mdの内容は極力保持してください
- ORDER履歴・タスク完了状況は今回収集したデータで上書きしてください
- 最終更新日は今日の日付（{today}）を使用してください
- Markdownテキストのみを出力し、前置き・後置きの説明文は不要です
"""
        return prompt

    # ------------------------------------------------------------------
    # 内部メソッド: 結果処理
    # ------------------------------------------------------------------

    def _extract_markdown(self, ai_response: str) -> str:
        """AI応答からMarkdownを抽出する"""
        text = ai_response.strip()

        # コードブロック（```markdown ... ``` または ``` ... ```）を除去
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        return text

    def _save_project_info(self, content: str) -> None:
        """PROJECT_INFO.md を上書き保存する（Roamingパス使用）"""
        # ディレクトリが存在しない場合は作成
        self.project_info_path.parent.mkdir(parents=True, exist_ok=True)

        # バックアップ（既存ファイルがある場合）
        if self.project_info_path.exists():
            backup_path = self.project_info_path.with_suffix(".md.bak")
            try:
                import shutil
                shutil.copy2(str(self.project_info_path), str(backup_path))
                logger.info(f"バックアップ作成: {backup_path}")
            except Exception as e:
                logger.warning(f"バックアップ作成失敗（処理を継続）: {e}")

        # 上書き保存
        self.project_info_path.write_text(content, encoding="utf-8")
        logger.info(f"PROJECT_INFO.md 保存完了: {len(content)} bytes")


# ----------------------------------------------------------------------
# CLIエントリーポイント
# ----------------------------------------------------------------------

def refresh_project_info(
    project_id: str,
    *,
    model: str = "sonnet",
    timeout: int = 600,
    skip_ai: bool = False,
) -> Dict[str, Any]:
    """
    プロジェクト情報を最新化する（Python API）

    Args:
        project_id: プロジェクトID
        model: AIモデル
        timeout: タイムアウト秒数
        skip_ai: AI処理をスキップするか

    Returns:
        処理結果の辞書
    """
    refresher = ProjectInfoRefresher(
        project_id,
        model=model,
        timeout=timeout,
        skip_ai=skip_ai,
    )
    return refresher.refresh()


def main():
    """CLI エントリーポイント"""
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="PROJECT_INFO.md を最新化する",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument(
        "--model",
        default="sonnet",
        help="AIモデル（haiku/sonnet/opus、デフォルト: sonnet）",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="タイムアウト秒数（デフォルト: 600）",
    )
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="AI処理をスキップ（コンテキスト収集のみ）",
    )
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        result = refresh_project_info(
            args.project_id,
            model=args.model,
            timeout=args.timeout,
            skip_ai=args.skip_ai,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            if result["success"]:
                print(f"[OK] プロジェクト情報を最新化しました: {result['project_id']}")
                print(f"  PROJECT_INFO.md: {result.get('project_info_path', '')}")
                summary = result.get("context_summary", {})
                print(f"  収集したORDER数: {summary.get('order_count', 0)}件")
                print(
                    f"  タスク完了率: {summary.get('completed_task_count', 0)}"
                    f"/{summary.get('total_task_count', 0)}"
                )
            else:
                print(
                    f"[ERROR] プロジェクト情報最新化に失敗: {result.get('error', '不明')}",
                    file=sys.stderr,
                )
                sys.exit(1)

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
