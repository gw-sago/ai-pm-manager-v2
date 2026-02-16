#!/usr/bin/env python3
"""
AI PM Framework - Task Complexity Scoring Module

タスクの難易度を 0-100 のスコアで算出する純粋ルールベースモジュール。
AI呼び出しなし・決定論的・再現可能。

Scoring factors:
  1. Technical domain keywords (primary driver)
  2. Description length and richness
  3. Dependency count
  4. Target file count

Usage (CLI):
    python backend/cost/task_complexity.py \\
        --title "Refactor authentication module" \\
        --description "Restructure OAuth flow with parallel token refresh" \\
        --deps 3 --files 8

Usage (import):
    from cost.task_complexity import calculate_complexity
    score = calculate_complexity(title="Setup config", dependency_count=0)
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path setup (follows project convention)
# ---------------------------------------------------------------------------
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

# ---------------------------------------------------------------------------
# Keyword tiers (sorted by weight within each tier)
# ---------------------------------------------------------------------------

# Low complexity keywords (base contribution: 10-25)
LOW_KEYWORDS: List[Tuple[str, int]] = [
    ("init", 10),
    ("setup", 12),
    ("config", 14),
    ("rename", 12),
    ("directory", 10),
    ("template", 15),
    ("copy", 10),
    ("move", 10),
    ("delete", 10),
    ("cleanup", 15),
    ("lint", 12),
    ("format", 10),
    ("readme", 10),
    ("docs", 12),
    ("document", 14),
    ("comment", 10),
    ("log", 12),
    ("env", 10),
]

# Medium complexity keywords (base contribution: 30-55)
MEDIUM_KEYWORDS: List[Tuple[str, int]] = [
    ("implement", 45),
    ("create", 40),
    ("add", 35),
    ("test", 38),
    ("fix", 40),
    ("update", 35),
    ("modify", 38),
    ("extend", 42),
    ("validate", 40),
    ("parse", 42),
    ("query", 38),
    ("filter", 35),
    ("sort", 33),
    ("api", 45),
    ("endpoint", 42),
    ("handler", 40),
    ("middleware", 45),
    ("schema", 42),
    ("migration", 48),
    ("cli", 38),
    ("command", 35),
    ("module", 40),
    ("class", 38),
    ("interface", 40),
    ("component", 42),
    ("debug", 38),
    ("error", 35),
    ("exception", 38),
    ("batch", 42),
    ("report", 35),
    ("dashboard", 45),
    ("export", 38),
    ("import", 38),
]

# High complexity keywords (base contribution: 55-90)
HIGH_KEYWORDS: List[Tuple[str, int]] = [
    ("refactor", 70),
    ("architecture", 80),
    ("optimize", 72),
    ("migrate", 65),
    ("security", 68),
    ("parallel", 75),
    ("concurrent", 78),
    ("async", 65),
    ("distributed", 82),
    ("cache", 60),
    ("performance", 68),
    ("scalab", 75),        # scalable, scalability
    ("orchestrat", 78),    # orchestrate, orchestration
    ("pipeline", 65),
    ("workflow", 62),
    ("integration", 65),
    ("auth", 60),          # auth, authentication, authorization
    ("encrypt", 65),
    ("transaction", 68),
    ("deadlock", 80),
    ("race condition", 85),
    ("backward compat", 72),
    ("breaking change", 75),
    ("state machine", 70),
    ("plugin", 60),
    ("framework", 68),
    ("engine", 65),
    ("compiler", 85),
    ("parser", 62),
    ("algorithm", 70),
    ("recursive", 60),
    ("dynamic programm", 80),
]

# All tiers combined for lookup
_ALL_KEYWORDS: List[Tuple[str, int, str]] = (
    [(kw, score, "low") for kw, score in LOW_KEYWORDS]
    + [(kw, score, "medium") for kw, score in MEDIUM_KEYWORDS]
    + [(kw, score, "high") for kw, score in HIGH_KEYWORDS]
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _match_keywords(text: str) -> List[Dict[str, Any]]:
    """Find all matching keywords in the given text.

    Returns list of dicts with keyword, score, and tier info.
    """
    text_lower = text.lower()
    matches = []
    seen = set()

    for keyword, base_score, tier in _ALL_KEYWORDS:
        if keyword in text_lower and keyword not in seen:
            seen.add(keyword)
            matches.append({
                "keyword": keyword,
                "base_score": base_score,
                "tier": tier,
            })

    return matches


def _keyword_score(title: str, description: str) -> Tuple[float, List[Dict[str, Any]]]:
    """Calculate keyword-based score component.

    Strategy:
      - Take the maximum base_score from matched keywords as the anchor.
      - Each additional keyword adds a diminishing bonus (+3, +2, +1, ...).
      - This ensures a single "refactor" keyword yields ~70, but multiple
        keywords can push higher.

    Returns (score, matched_keywords_list).
    """
    combined_text = f"{title} {description}"
    matches = _match_keywords(combined_text)

    if not matches:
        return (25.0, [])  # neutral default when no keywords match

    # Sort by base_score descending
    matches_sorted = sorted(matches, key=lambda m: m["base_score"], reverse=True)

    anchor = matches_sorted[0]["base_score"]
    bonus = 0.0
    for i, m in enumerate(matches_sorted[1:], start=1):
        increment = max(1, 4 - i)  # 3, 2, 1, 1, 1, ...
        bonus += increment

    return (min(anchor + bonus, 95.0), matches_sorted)


def _description_length_score(description: str) -> float:
    """Score based on description length / richness.

    Longer, more detailed descriptions often correlate with more complex tasks.
    Uses a log scale to avoid runaway scores on very long descriptions.

    Returns 0-15 (additive modifier).
    """
    word_count = len(description.split())
    if word_count <= 5:
        return 0.0
    # log2 curve: 10 words ~1.3, 50 words ~4.6, 200 words ~7.6, 500 words ~9.9
    return min(math.log2(word_count) * 1.5, 15.0)


def _dependency_score(dependency_count: int) -> float:
    """Score modifier based on number of task dependencies.

    More dependencies => more integration complexity.
    Returns 0-15 (additive modifier).
    """
    if dependency_count <= 0:
        return 0.0
    # 1 dep = 3, 2 deps = 5.5, 3 deps = 7.5, 5 deps = 10.5, 10 deps = 15
    return min(dependency_count * 3.0 / (1.0 + dependency_count * 0.2), 15.0)


def _file_count_score(target_file_count: int) -> float:
    """Score modifier based on number of target files.

    More files => wider blast radius => higher complexity.
    Returns 0-10 (additive modifier).
    """
    if target_file_count <= 1:
        return 0.0
    # 2 files = 1.5, 5 files = 3.0, 10 files = 4.5, 20+ files ~6+
    return min(math.log2(target_file_count) * 2.0, 10.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_complexity(
    title: str,
    description: Optional[str] = None,
    dependency_count: int = 0,
    target_file_count: int = 0,
) -> int:
    """Calculate a task complexity score from 0 to 100.

    Pure rule-based, deterministic, no AI calls.

    Args:
        title: Task title (required).
        description: Task description text. Defaults to empty string
                     (BUG_001: mutable default avoidance).
        dependency_count: Number of dependency tasks.
        target_file_count: Number of target files affected.

    Returns:
        Integer complexity score clamped to [0, 100].
    """
    # BUG_001: avoid mutable default - use None sentinel
    if description is None:
        description = ""

    kw_score, kw_matches = _keyword_score(title, description)
    desc_score = _description_length_score(description)
    dep_score = _dependency_score(dependency_count)
    file_score = _file_count_score(target_file_count)

    raw = kw_score + desc_score + dep_score + file_score
    clamped = max(0, min(100, int(round(raw))))

    return clamped


def calculate_complexity_detailed(
    title: str,
    description: Optional[str] = None,
    dependency_count: int = 0,
    target_file_count: int = 0,
) -> Dict[str, Any]:
    """Calculate complexity with full breakdown of contributing factors.

    Same logic as calculate_complexity but returns a detailed dict.

    Args:
        title: Task title (required).
        description: Task description text.
        dependency_count: Number of dependency tasks.
        target_file_count: Number of target files affected.

    Returns:
        Dict with complexity_score and detailed factors breakdown.
    """
    if description is None:
        description = ""

    kw_score, kw_matches = _keyword_score(title, description)
    desc_score = _description_length_score(description)
    dep_score = _dependency_score(dependency_count)
    file_score = _file_count_score(target_file_count)

    raw = kw_score + desc_score + dep_score + file_score
    clamped = max(0, min(100, int(round(raw))))

    # Determine tier label
    if clamped <= 30:
        tier = "low"
    elif clamped <= 65:
        tier = "medium"
    else:
        tier = "high"

    return {
        "complexity_score": clamped,
        "tier": tier,
        "factors": {
            "keyword_score": round(kw_score, 1),
            "description_length_score": round(desc_score, 1),
            "dependency_score": round(dep_score, 1),
            "file_count_score": round(file_score, 1),
            "raw_total": round(raw, 1),
        },
        "matched_keywords": [
            {"keyword": m["keyword"], "base_score": m["base_score"], "tier": m["tier"]}
            for m in kw_matches
        ],
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main():
    """CLI interface for task complexity scoring."""
    parser = argparse.ArgumentParser(
        description="AI PM Framework - Task Complexity Scorer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python task_complexity.py --title "Setup project config"
  python task_complexity.py --title "Refactor auth" --description "Restructure OAuth" --deps 3 --files 8
  python task_complexity.py --title "Add unit tests" --verbose
        """,
    )
    parser.add_argument(
        "--title", required=True,
        help="Task title (required)",
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
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show detailed factor breakdown",
    )

    args = parser.parse_args()

    result = calculate_complexity_detailed(
        title=args.title,
        description=args.description,
        dependency_count=args.deps,
        target_file_count=args.files,
    )

    if args.verbose:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # Compact output matching the spec
        output = {
            "complexity_score": result["complexity_score"],
            "factors": result["factors"],
        }
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
