#!/usr/bin/env python3
"""
AI PM Framework - Model Selection Module

Automatically select the recommended Claude model based on task complexity score.

Model selection rules:
  - 0-30: "Haiku" (simple tasks: directory setup, config changes)
  - 31-65: "Sonnet" (moderate: feature implementation, testing)
  - 66-100: "Opus" (complex: architecture, optimization, migration)

Usage (CLI):
    # Select model from score
    python backend/cost/model_selector.py --score 72

    # Auto-select from task info
    python backend/cost/model_selector.py --auto \\
        --title "Refactor DB layer" \\
        --description "Complex migration" \\
        --deps 3

Usage (import):
    from cost.model_selector import select_model, auto_select_model

    # From score
    model = select_model(72)  # "Opus"

    # Full pipeline
    result = auto_select_model(
        title="Refactor auth",
        description="Complex OAuth restructure",
        dependency_count=3,
        target_file_count=8
    )
    # {"complexity_score": 85, "recommended_model": "Opus", "factors": {...}}
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Path setup (follows project convention)
# ---------------------------------------------------------------------------
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

# Import task_complexity module
from cost.task_complexity import calculate_complexity_detailed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def select_model(complexity_score: int) -> str:
    """
    Select recommended model based on complexity score.

    Rules:
    - 0-30: "Haiku" (simple tasks: directory setup, config changes)
    - 31-65: "Sonnet" (moderate: feature implementation, testing)
    - 66-100: "Opus" (complex: architecture, optimization, migration)

    Args:
        complexity_score: Integer score from 0 to 100.

    Returns:
        Model name: "Haiku", "Sonnet", or "Opus"

    Raises:
        ValueError: If complexity_score is out of range [0, 100]
    """
    if not isinstance(complexity_score, int):
        raise ValueError(f"complexity_score must be an integer, got {type(complexity_score).__name__}")

    if complexity_score < 0 or complexity_score > 100:
        raise ValueError(f"complexity_score must be in range [0, 100], got {complexity_score}")

    if complexity_score <= 30:
        return "Haiku"
    elif complexity_score <= 65:
        return "Sonnet"
    else:
        return "Opus"


def auto_select_model(
    title: str,
    description: Optional[str] = None,
    dependency_count: int = 0,
    target_file_count: int = 0
) -> Dict[str, Any]:
    """
    Full pipeline: calculate complexity → select model.

    This is the main entry point that combines complexity calculation
    and model selection into a single operation.

    Args:
        title: Task title (required).
        description: Task description text (optional).
        dependency_count: Number of dependency tasks (default: 0).
        target_file_count: Number of target files affected (default: 0).

    Returns:
        Dict with:
        - complexity_score: int (0-100)
        - recommended_model: str ("Haiku", "Sonnet", or "Opus")
        - factors: dict (breakdown of complexity calculation)
        - matched_keywords: list (keywords found in title/description)

    Example:
        >>> result = auto_select_model(
        ...     title="Refactor authentication module",
        ...     description="Restructure OAuth flow",
        ...     dependency_count=3,
        ...     target_file_count=8
        ... )
        >>> result["recommended_model"]
        'Opus'
        >>> result["complexity_score"]
        85
    """
    # BUG_001: avoid mutable default - already handled in calculate_complexity_detailed

    # Calculate complexity with full breakdown
    complexity_result = calculate_complexity_detailed(
        title=title,
        description=description,
        dependency_count=dependency_count,
        target_file_count=target_file_count
    )

    # Select model based on score
    recommended_model = select_model(complexity_result["complexity_score"])

    # Combine results
    return {
        "complexity_score": complexity_result["complexity_score"],
        "recommended_model": recommended_model,
        "factors": complexity_result["factors"],
        "matched_keywords": complexity_result["matched_keywords"],
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main():
    """CLI interface for model selection."""
    parser = argparse.ArgumentParser(
        description="AI PM Framework - Model Selector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Select model from score
  python model_selector.py --score 72

  # Auto-select from task info
  python model_selector.py --auto --title "Refactor DB layer" --description "Complex migration" --deps 3

  # With all parameters
  python model_selector.py --auto --title "Add unit tests" --description "Test coverage" --deps 2 --files 5
        """,
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--score", type=int,
        help="Complexity score (0-100) for model selection",
    )
    mode_group.add_argument(
        "--auto", action="store_true",
        help="Auto-select model from task information",
    )

    # Auto mode parameters
    parser.add_argument(
        "--title",
        help="Task title (required with --auto)",
    )
    parser.add_argument(
        "--description", default="",
        help="Task description text",
    )
    parser.add_argument(
        "--deps", type=int, default=0,
        help="Number of dependency tasks (default: 0)",
    )
    parser.add_argument(
        "--files", type=int, default=0,
        help="Number of target files (default: 0)",
    )

    args = parser.parse_args()

    try:
        if args.score is not None:
            # Simple mode: score → model
            model = select_model(args.score)
            output = {
                "recommended_model": model,
                "complexity_score": args.score,
            }
            print(json.dumps(output, ensure_ascii=False))

        else:  # args.auto
            # Auto mode: task info → score → model
            if not args.title:
                parser.error("--title is required when using --auto")

            result = auto_select_model(
                title=args.title,
                description=args.description,
                dependency_count=args.deps,
                target_file_count=args.files,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))

    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"Unexpected error: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
