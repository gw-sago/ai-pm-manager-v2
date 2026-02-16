#!/usr/bin/env python3
"""
AI PM Framework - コスト記録モジュール

トークン使用量の記録・コスト計算・見積もり機能を提供。

Usage:
    # Record actual token usage
    python backend/cost/cost_tracker.py record AI_PM_PJ TASK_1028 \\
        --model Opus --input-tokens 5000 --output-tokens 15000

    # Estimate cost for a given model and token count
    python backend/cost/cost_tracker.py estimate --model Opus --tokens 20000
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    close_connection,
    transaction,
    execute_query,
    fetch_one,
    row_to_dict,
    DatabaseError,
)
from config import setup_utf8_output

# ============================================================================
# Model Pricing (per 1M tokens, as of 2026)
# ============================================================================

MODEL_PRICING = {
    "Haiku": {"input": 0.80, "output": 4.00},
    "Sonnet": {"input": 3.00, "output": 15.00},
    "Opus": {"input": 15.00, "output": 75.00},
}

# Default input/output token ratio for estimation
_DEFAULT_INPUT_RATIO = 0.30
_DEFAULT_OUTPUT_RATIO = 0.70


# ============================================================================
# Core Functions
# ============================================================================

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    モデルとトークン数からコスト(USD)を計算する。

    Args:
        model: モデル名 (Haiku/Sonnet/Opus)
        input_tokens: 入力トークン数
        output_tokens: 出力トークン数

    Returns:
        float: コスト（USD）

    Raises:
        ValueError: 未知のモデル名が指定された場合
    """
    if model not in MODEL_PRICING:
        raise ValueError(
            f"Unknown model: {model}. "
            f"Available models: {', '.join(MODEL_PRICING.keys())}"
        )

    pricing = MODEL_PRICING[model]
    cost_usd = (
        input_tokens * pricing["input"] + output_tokens * pricing["output"]
    ) / 1_000_000

    return round(cost_usd, 6)


def record_cost(
    db_path: str,
    project_id: str,
    task_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> dict:
    """
    トークン使用量とコストをtasksテーブルに記録する。

    Args:
        db_path: データベースファイルパス
        project_id: プロジェクトID (e.g., AI_PM_PJ)
        task_id: タスクID (e.g., TASK_1028)
        model: モデル名 (Haiku/Sonnet/Opus)
        input_tokens: 入力トークン数
        output_tokens: 出力トークン数

    Returns:
        dict: {"actual_tokens": int, "cost_usd": float}

    Raises:
        ValueError: 未知のモデル名、または不正なトークン数
        DatabaseError: DB操作エラー
    """
    if input_tokens < 0:
        raise ValueError(f"input_tokens must be non-negative: {input_tokens}")
    if output_tokens < 0:
        raise ValueError(f"output_tokens must be non-negative: {output_tokens}")

    cost_usd = calculate_cost(model, input_tokens, output_tokens)
    actual_tokens = input_tokens + output_tokens

    db_path_obj = Path(db_path) if db_path else None

    with transaction(db_path=db_path_obj) as conn:
        # タスクの存在確認
        row = fetch_one(
            conn,
            "SELECT id FROM tasks WHERE id = ? AND project_id = ?",
            (task_id, project_id),
        )
        if row is None:
            raise DatabaseError(
                f"Task not found: {task_id} in project {project_id}"
            )

        # tasksテーブルを更新
        execute_query(
            conn,
            """
            UPDATE tasks
            SET actual_tokens = ?,
                cost_usd = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND project_id = ?
            """,
            (actual_tokens, cost_usd, task_id, project_id),
        )

    result = {
        "actual_tokens": actual_tokens,
        "cost_usd": cost_usd,
    }
    return result


def estimate_cost(model: str, estimated_tokens: int) -> dict:
    """
    モデルとトークン数からコストを見積もる。
    入力30%、出力70%の比率を仮定。

    Args:
        model: モデル名 (Haiku/Sonnet/Opus)
        estimated_tokens: 推定総トークン数

    Returns:
        dict: {"estimated_cost_usd": float, "model": str}

    Raises:
        ValueError: 未知のモデル名、または不正なトークン数
    """
    if estimated_tokens < 0:
        raise ValueError(
            f"estimated_tokens must be non-negative: {estimated_tokens}"
        )

    input_tokens = int(estimated_tokens * _DEFAULT_INPUT_RATIO)
    output_tokens = estimated_tokens - input_tokens  # 端数を出力に寄せる

    cost_usd = calculate_cost(model, input_tokens, output_tokens)

    return {
        "estimated_cost_usd": cost_usd,
        "model": model,
    }


# ============================================================================
# CLI Interface
# ============================================================================

def _build_parser() -> argparse.ArgumentParser:
    """CLIパーサーを構築する。"""
    parser = argparse.ArgumentParser(
        description="AI PM Framework - Cost Tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Record actual usage
  python backend/cost/cost_tracker.py record AI_PM_PJ TASK_1028 \\
      --model Opus --input-tokens 5000 --output-tokens 15000

  # Estimate cost
  python backend/cost/cost_tracker.py estimate --model Opus --tokens 20000
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # --- record sub-command ---
    record_parser = subparsers.add_parser(
        "record",
        help="Record actual token usage and cost",
    )
    record_parser.add_argument(
        "project_id",
        help="Project ID (e.g., AI_PM_PJ)",
    )
    record_parser.add_argument(
        "task_id",
        help="Task ID (e.g., TASK_1028)",
    )
    record_parser.add_argument(
        "--model",
        required=True,
        choices=list(MODEL_PRICING.keys()),
        help="AI model name",
    )
    record_parser.add_argument(
        "--input-tokens",
        type=int,
        required=True,
        help="Number of input tokens",
    )
    record_parser.add_argument(
        "--output-tokens",
        type=int,
        required=True,
        help="Number of output tokens",
    )
    record_parser.add_argument(
        "--db-path",
        default=None,
        help="Database file path (default: data/aipm.db)",
    )
    record_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output in JSON format",
    )

    # --- estimate sub-command ---
    estimate_parser = subparsers.add_parser(
        "estimate",
        help="Estimate cost for a given model and token count",
    )
    estimate_parser.add_argument(
        "--model",
        required=True,
        choices=list(MODEL_PRICING.keys()),
        help="AI model name",
    )
    estimate_parser.add_argument(
        "--tokens",
        type=int,
        required=True,
        help="Estimated total token count",
    )
    estimate_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output in JSON format",
    )

    return parser


def main() -> int:
    """CLI エントリーポイント。"""
    setup_utf8_output()

    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "record":
            result = record_cost(
                db_path=args.db_path,
                project_id=args.project_id,
                task_id=args.task_id,
                model=args.model,
                input_tokens=args.input_tokens,
                output_tokens=args.output_tokens,
            )

            if args.output_json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"[OK] Cost recorded for {args.task_id}")
                print(f"  Model:         {args.model}")
                print(f"  Input tokens:  {args.input_tokens:,}")
                print(f"  Output tokens: {args.output_tokens:,}")
                print(f"  Total tokens:  {result['actual_tokens']:,}")
                print(f"  Cost (USD):    ${result['cost_usd']:.6f}")

            return 0

        elif args.command == "estimate":
            result = estimate_cost(
                model=args.model,
                estimated_tokens=args.tokens,
            )

            if args.output_json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                input_tokens = int(args.tokens * _DEFAULT_INPUT_RATIO)
                output_tokens = args.tokens - input_tokens
                print(f"[Estimate] {args.model} - {args.tokens:,} tokens")
                print(f"  Input tokens (30%):  {input_tokens:,}")
                print(f"  Output tokens (70%): {output_tokens:,}")
                print(f"  Estimated cost:      ${result['estimated_cost_usd']:.6f}")

            return 0

        else:
            parser.print_help()
            return 1

    except ValueError as e:
        print(f"[ERROR] Validation error: {e}", file=sys.stderr)
        return 1
    except DatabaseError as e:
        print(f"[ERROR] Database error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
