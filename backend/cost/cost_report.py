#!/usr/bin/env python3
"""
AI PM Framework - Cost Analysis Report CLI

Generate cost analysis reports from task data with support for multiple report types.

Usage:
    python -m cost.cost_report project [PROJECT_ID] [options]
    python -m cost.cost_report order PROJECT_ID [ORDER_ID] [options]
    python -m cost.cost_report model [PROJECT_ID] [options]
    python -m cost.cost_report summary [PROJECT_ID] [options]

Report Types:
    project     Project-level cost summary
    order       ORDER-level cost summary
    model       Model-level cost summary (Haiku/Sonnet/Opus)
    summary     Overall summary (all dimensions)

Options:
    --json          JSON output
    --table         Table output (default)
    --from DATE     Filter from date (YYYY-MM-DD)
    --to DATE       Filter to date (YYYY-MM-DD)

Examples:
    # Project summary (all projects)
    python cost_report.py project

    # Project summary (specific project)
    python cost_report.py project AI_PM_PJ

    # ORDER summary (all orders in project)
    python cost_report.py order AI_PM_PJ

    # ORDER summary (specific order)
    python cost_report.py order AI_PM_PJ ORDER_106

    # Model summary (all projects)
    python cost_report.py model

    # Model summary (specific project)
    python cost_report.py model AI_PM_PJ

    # Overall summary with date filter
    python cost_report.py summary AI_PM_PJ --from 2026-02-01 --to 2026-02-10

    # JSON output
    python cost_report.py project AI_PM_PJ --json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Path setup (follows project convention)
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    close_connection,
    fetch_all,
    fetch_one,
    row_to_dict,
    rows_to_dicts,
    DatabaseError,
)
from utils.validation import (
    validate_project_name,
    validate_order_id,
    project_exists,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Report Functions
# ---------------------------------------------------------------------------

def report_by_project(
    db_path: Optional[Path] = None,
    project_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Project-level cost summary.

    Args:
        db_path: Database path (None = default)
        project_id: Filter by project (None = all projects)
        from_date: Filter from date (YYYY-MM-DD)
        to_date: Filter to date (YYYY-MM-DD)

    Returns:
        Dict with success, data, and summary fields
    """
    try:
        conn = get_connection(db_path)

        # Build query
        query = """
        SELECT
            project_id,
            COUNT(*) as task_count,
            COALESCE(SUM(cost_usd), 0) as total_cost_usd,
            COALESCE(AVG(complexity_score), 0) as avg_complexity,
            COALESCE(SUM(actual_tokens), 0) as total_tokens
        FROM tasks
        WHERE 1=1
        """
        params = []

        # Project filter
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        # Date filters
        if from_date:
            query += " AND DATE(created_at) >= DATE(?)"
            params.append(from_date)
        if to_date:
            query += " AND DATE(created_at) <= DATE(?)"
            params.append(to_date)

        query += " GROUP BY project_id ORDER BY project_id"

        rows = fetch_all(conn, query, tuple(params))
        data = rows_to_dicts(rows)

        # Calculate summary
        summary = {
            "total_projects": len(data),
            "total_tasks": sum(row["task_count"] for row in data),
            "total_cost_usd": sum(row["total_cost_usd"] for row in data),
            "avg_complexity": (
                sum(row["avg_complexity"] * row["task_count"] for row in data) /
                sum(row["task_count"] for row in data)
            ) if data and sum(row["task_count"] for row in data) > 0 else 0,
            "total_tokens": sum(row["total_tokens"] for row in data),
        }

        conn.close()

        return {
            "success": True,
            "report_type": "project",
            "generated_at": datetime.now().isoformat(),
            "filters": {
                "project_id": project_id,
                "from": from_date,
                "to": to_date,
            },
            "data": data,
            "summary": summary,
        }

    except (DatabaseError, ValidationError) as e:
        return {
            "success": False,
            "error": str(e),
        }


def report_by_order(
    project_id: str,
    order_id: Optional[str] = None,
    db_path: Optional[Path] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    ORDER-level cost summary.

    Args:
        project_id: Project ID (required)
        order_id: Filter by order (None = all orders in project)
        db_path: Database path (None = default)
        from_date: Filter from date (YYYY-MM-DD)
        to_date: Filter to date (YYYY-MM-DD)

    Returns:
        Dict with success, data, and summary fields
    """
    try:
        # Validate inputs
        validate_project_name(project_id)
        if order_id:
            validate_order_id(order_id)

        conn = get_connection(db_path)

        # Check project exists
        if not project_exists(conn, project_id):
            conn.close()
            return {
                "success": False,
                "error": f"Project not found: {project_id}",
            }

        # Build query
        query = """
        SELECT
            order_id,
            COUNT(*) as task_count,
            COALESCE(SUM(cost_usd), 0) as total_cost_usd,
            COALESCE(AVG(complexity_score), 0) as avg_complexity,
            COALESCE(SUM(actual_tokens), 0) as total_tokens
        FROM tasks
        WHERE project_id = ?
        """
        params = [project_id]

        # Order filter
        if order_id:
            query += " AND order_id = ?"
            params.append(order_id)

        # Date filters
        if from_date:
            query += " AND DATE(created_at) >= DATE(?)"
            params.append(from_date)
        if to_date:
            query += " AND DATE(created_at) <= DATE(?)"
            params.append(to_date)

        query += " GROUP BY order_id ORDER BY order_id"

        rows = fetch_all(conn, query, tuple(params))
        data = rows_to_dicts(rows)

        # Calculate summary
        summary = {
            "total_orders": len(data),
            "total_tasks": sum(row["task_count"] for row in data),
            "total_cost_usd": sum(row["total_cost_usd"] for row in data),
            "avg_complexity": (
                sum(row["avg_complexity"] * row["task_count"] for row in data) /
                sum(row["task_count"] for row in data)
            ) if data and sum(row["task_count"] for row in data) > 0 else 0,
            "total_tokens": sum(row["total_tokens"] for row in data),
        }

        conn.close()

        return {
            "success": True,
            "report_type": "order",
            "generated_at": datetime.now().isoformat(),
            "filters": {
                "project_id": project_id,
                "order_id": order_id,
                "from": from_date,
                "to": to_date,
            },
            "data": data,
            "summary": summary,
        }

    except (DatabaseError, ValidationError) as e:
        return {
            "success": False,
            "error": str(e),
        }


def report_by_model(
    db_path: Optional[Path] = None,
    project_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Model-level cost summary.

    Args:
        db_path: Database path (None = default)
        project_id: Filter by project (None = all projects)
        from_date: Filter from date (YYYY-MM-DD)
        to_date: Filter to date (YYYY-MM-DD)

    Returns:
        Dict with success, data, and summary fields
    """
    try:
        conn = get_connection(db_path)

        # Build query
        query = """
        SELECT
            COALESCE(recommended_model, 'Unknown') as model,
            COUNT(*) as task_count,
            COALESCE(SUM(cost_usd), 0) as total_cost_usd,
            COALESCE(AVG(complexity_score), 0) as avg_complexity,
            COALESCE(SUM(actual_tokens), 0) as total_tokens
        FROM tasks
        WHERE 1=1
        """
        params = []

        # Project filter
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        # Date filters
        if from_date:
            query += " AND DATE(created_at) >= DATE(?)"
            params.append(from_date)
        if to_date:
            query += " AND DATE(created_at) <= DATE(?)"
            params.append(to_date)

        query += " GROUP BY recommended_model ORDER BY total_cost_usd DESC"

        rows = fetch_all(conn, query, tuple(params))
        data = rows_to_dicts(rows)

        # Calculate summary
        summary = {
            "total_models": len(data),
            "total_tasks": sum(row["task_count"] for row in data),
            "total_cost_usd": sum(row["total_cost_usd"] for row in data),
            "avg_complexity": (
                sum(row["avg_complexity"] * row["task_count"] for row in data) /
                sum(row["task_count"] for row in data)
            ) if data and sum(row["task_count"] for row in data) > 0 else 0,
            "total_tokens": sum(row["total_tokens"] for row in data),
        }

        conn.close()

        return {
            "success": True,
            "report_type": "model",
            "generated_at": datetime.now().isoformat(),
            "filters": {
                "project_id": project_id,
                "from": from_date,
                "to": to_date,
            },
            "data": data,
            "summary": summary,
        }

    except (DatabaseError, ValidationError) as e:
        return {
            "success": False,
            "error": str(e),
        }


def generate_summary_report(
    project_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Overall summary report combining project, order, and model dimensions.

    Provides a comprehensive overview with totals, per-project breakdown,
    per-model breakdown, and top orders by cost.

    Args:
        project_id: Filter by project (None = all projects)
        start_date: Filter from date (YYYY-MM-DD)
        end_date: Filter to date (YYYY-MM-DD)
        db_path: Database path (None = default)

    Returns:
        Dict with success, data (overview, by_project, by_model, top_orders),
        and filters fields.
    """
    try:
        conn = get_connection(db_path)

        # --- Build common WHERE clause ---
        where_parts = []
        params = []  # type: List[Any]

        if project_id:
            where_parts.append("project_id = ?")
            params.append(project_id)
        if start_date:
            where_parts.append("DATE(created_at) >= DATE(?)")
            params.append(start_date)
        if end_date:
            where_parts.append("DATE(created_at) <= DATE(?)")
            params.append(end_date)

        where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # --- Overview ---
        overview_query = f"""
        SELECT
            COUNT(*) as total_tasks,
            COUNT(DISTINCT project_id) as total_projects,
            COUNT(DISTINCT order_id) as total_orders,
            COALESCE(SUM(cost_usd), 0) as total_cost_usd,
            COALESCE(AVG(cost_usd), 0) as avg_cost_per_task,
            COALESCE(SUM(actual_tokens), 0) as total_tokens,
            COALESCE(AVG(complexity_score), 0) as avg_complexity
        FROM tasks
        {where_clause}
        """
        overview_row = fetch_one(conn, overview_query, tuple(params))
        overview = row_to_dict(overview_row) if overview_row else {
            "total_tasks": 0,
            "total_projects": 0,
            "total_orders": 0,
            "total_cost_usd": 0,
            "avg_cost_per_task": 0,
            "total_tokens": 0,
            "avg_complexity": 0,
        }

        # --- By project ---
        by_project_query = f"""
        SELECT
            project_id,
            COUNT(*) as task_count,
            COALESCE(SUM(cost_usd), 0) as total_cost_usd,
            COALESCE(AVG(complexity_score), 0) as avg_complexity,
            COALESCE(SUM(actual_tokens), 0) as total_tokens
        FROM tasks
        {where_clause}
        GROUP BY project_id
        ORDER BY total_cost_usd DESC
        """
        by_project_rows = fetch_all(conn, by_project_query, tuple(params))
        by_project = rows_to_dicts(by_project_rows)

        # --- By model ---
        by_model_query = f"""
        SELECT
            COALESCE(recommended_model, 'Unknown') as model,
            COUNT(*) as task_count,
            COALESCE(SUM(cost_usd), 0) as total_cost_usd,
            COALESCE(AVG(complexity_score), 0) as avg_complexity,
            COALESCE(SUM(actual_tokens), 0) as total_tokens
        FROM tasks
        {where_clause}
        GROUP BY recommended_model
        ORDER BY total_cost_usd DESC
        """
        by_model_rows = fetch_all(conn, by_model_query, tuple(params))
        by_model = rows_to_dicts(by_model_rows)

        # --- Top orders by cost ---
        top_orders_query = f"""
        SELECT
            project_id,
            order_id,
            COUNT(*) as task_count,
            COALESCE(SUM(cost_usd), 0) as total_cost_usd,
            COALESCE(SUM(actual_tokens), 0) as total_tokens
        FROM tasks
        {where_clause}
        GROUP BY project_id, order_id
        ORDER BY total_cost_usd DESC
        LIMIT 10
        """
        top_orders_rows = fetch_all(conn, top_orders_query, tuple(params))
        top_orders = rows_to_dicts(top_orders_rows)

        close_connection(conn)

        return {
            "success": True,
            "report_type": "summary",
            "generated_at": datetime.now().isoformat(),
            "filters": {
                "project_id": project_id,
                "from": start_date,
                "to": end_date,
            },
            "data": {
                "overview": overview,
                "by_project": by_project,
                "by_model": by_model,
                "top_orders": top_orders,
            },
        }

    except (DatabaseError, ValidationError) as e:
        return {
            "success": False,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Public API Aliases (matching task spec naming convention)
# ---------------------------------------------------------------------------

def generate_project_report(
    project_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Alias for report_by_project (task spec naming)."""
    return report_by_project(
        db_path=db_path,
        project_id=project_id,
        from_date=start_date,
        to_date=end_date,
    )


def generate_order_report(
    project_id: str,
    order_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Alias for report_by_order (task spec naming)."""
    return report_by_order(
        project_id=project_id,
        order_id=order_id,
        db_path=db_path,
        from_date=start_date,
        to_date=end_date,
    )


def generate_model_report(
    project_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Alias for report_by_model (task spec naming)."""
    return report_by_model(
        db_path=db_path,
        project_id=project_id,
        from_date=start_date,
        to_date=end_date,
    )


# ---------------------------------------------------------------------------
# Formatting Functions
# ---------------------------------------------------------------------------

def format_currency(amount: float) -> str:
    """Format amount as USD currency."""
    if amount == 0:
        return "$0.00"
    return f"${amount:,.2f}"


def format_number(num: int) -> str:
    """Format number with thousands separator."""
    return f"{num:,}"


def format_table_project(data: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    """Format project report as table."""
    if not data:
        return "データがありません (コスト情報が未設定の可能性があります)"

    lines = []
    lines.append("=== コスト分析レポート: プロジェクト別 ===\n")

    # Header
    lines.append(f"{'プロジェクトID':<20} | {'タスク数':>8} | {'総コスト':>12} | {'平均複雑度':>10} | {'総トークン':>12}")
    lines.append("-" * 80)

    # Data rows
    for row in data:
        lines.append(
            f"{row['project_id']:<20} | "
            f"{row['task_count']:>8} | "
            f"{format_currency(row['total_cost_usd']):>12} | "
            f"{row['avg_complexity']:>10.1f} | "
            f"{format_number(int(row['total_tokens'])):>12}"
        )

    # Summary
    lines.append("-" * 80)
    lines.append(
        f"{'合計':<20} | "
        f"{summary['total_tasks']:>8} | "
        f"{format_currency(summary['total_cost_usd']):>12} | "
        f"{summary['avg_complexity']:>10.1f} | "
        f"{format_number(int(summary['total_tokens'])):>12}"
    )

    return "\n".join(lines)


def format_table_order(data: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    """Format order report as table."""
    if not data:
        return "データがありません (コスト情報が未設定の可能性があります)"

    lines = []
    lines.append("=== コスト分析レポート: ORDER別 ===\n")

    # Header
    lines.append(f"{'ORDER ID':<15} | {'タスク数':>8} | {'総コスト':>12} | {'平均複雑度':>10} | {'総トークン':>12}")
    lines.append("-" * 75)

    # Data rows
    for row in data:
        lines.append(
            f"{row['order_id']:<15} | "
            f"{row['task_count']:>8} | "
            f"{format_currency(row['total_cost_usd']):>12} | "
            f"{row['avg_complexity']:>10.1f} | "
            f"{format_number(int(row['total_tokens'])):>12}"
        )

    # Summary
    lines.append("-" * 75)
    lines.append(
        f"{'合計':<15} | "
        f"{summary['total_tasks']:>8} | "
        f"{format_currency(summary['total_cost_usd']):>12} | "
        f"{summary['avg_complexity']:>10.1f} | "
        f"{format_number(int(summary['total_tokens'])):>12}"
    )

    return "\n".join(lines)


def format_table_model(data: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    """Format model report as table."""
    if not data:
        return "データがありません (コスト情報が未設定の可能性があります)"

    lines = []
    lines.append("=== コスト分析レポート: モデル別 ===\n")

    # Header
    lines.append(f"{'モデル':<10} | {'タスク数':>8} | {'総コスト':>12} | {'平均複雑度':>10} | {'総トークン':>12}")
    lines.append("-" * 70)

    # Data rows
    for row in data:
        lines.append(
            f"{row['model']:<10} | "
            f"{row['task_count']:>8} | "
            f"{format_currency(row['total_cost_usd']):>12} | "
            f"{row['avg_complexity']:>10.1f} | "
            f"{format_number(int(row['total_tokens'])):>12}"
        )

    # Summary
    lines.append("-" * 70)
    lines.append(
        f"{'合計':<10} | "
        f"{summary['total_tasks']:>8} | "
        f"{format_currency(summary['total_cost_usd']):>12} | "
        f"{summary['avg_complexity']:>10.1f} | "
        f"{format_number(int(summary['total_tokens'])):>12}"
    )

    return "\n".join(lines)


def format_table_summary(data: Dict[str, Any]) -> str:
    """Format summary report as table."""
    overview = data.get("overview", {})
    by_project = data.get("by_project", [])
    by_model = data.get("by_model", [])
    top_orders = data.get("top_orders", [])

    lines = []
    lines.append("=== コスト分析レポート: 総合サマリー ===\n")

    # --- Overview ---
    lines.append("[概要]")
    lines.append(f"  総タスク数:       {format_number(overview.get('total_tasks', 0))}")
    lines.append(f"  総プロジェクト数: {overview.get('total_projects', 0)}")
    lines.append(f"  総ORDER数:        {overview.get('total_orders', 0)}")
    lines.append(f"  総コスト:         {format_currency(overview.get('total_cost_usd', 0))}")
    lines.append(f"  タスク平均コスト: {format_currency(overview.get('avg_cost_per_task', 0))}")
    lines.append(f"  総トークン:       {format_number(int(overview.get('total_tokens', 0)))}")
    lines.append(f"  平均複雑度:       {overview.get('avg_complexity', 0):.1f}")
    lines.append("")

    # --- By Project ---
    if by_project:
        lines.append("[プロジェクト別]")
        lines.append(f"  {'プロジェクト':<20} | {'タスク数':>8} | {'コスト':>12} | {'トークン':>12}")
        lines.append("  " + "-" * 65)
        for row in by_project:
            lines.append(
                f"  {row['project_id']:<20} | "
                f"{row['task_count']:>8} | "
                f"{format_currency(row['total_cost_usd']):>12} | "
                f"{format_number(int(row['total_tokens'])):>12}"
            )
        lines.append("")

    # --- By Model ---
    if by_model:
        lines.append("[モデル別]")
        lines.append(f"  {'モデル':<10} | {'タスク数':>8} | {'コスト':>12} | {'トークン':>12}")
        lines.append("  " + "-" * 55)
        for row in by_model:
            lines.append(
                f"  {row['model']:<10} | "
                f"{row['task_count']:>8} | "
                f"{format_currency(row['total_cost_usd']):>12} | "
                f"{format_number(int(row['total_tokens'])):>12}"
            )
        lines.append("")

    # --- Top Orders ---
    if top_orders:
        lines.append("[ORDER別 (上位10)]")
        lines.append(f"  {'プロジェクト':<15} {'ORDER':<15} | {'タスク数':>8} | {'コスト':>12}")
        lines.append("  " + "-" * 60)
        for row in top_orders:
            order_id = row.get("order_id", "N/A") or "N/A"
            lines.append(
                f"  {row['project_id']:<15} {order_id:<15} | "
                f"{row['task_count']:>8} | "
                f"{format_currency(row['total_cost_usd']):>12}"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI Main
# ---------------------------------------------------------------------------

def main():
    """CLI entrypoint."""
    # Windows UTF-8 output setup
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="AI PM Framework - Cost Analysis Report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="report_type", help="Report type")
    subparsers.required = True

    # Common arguments helper
    def _add_common_args(sub_parser):
        """Add common output/filter arguments to a subparser."""
        output_group = sub_parser.add_mutually_exclusive_group()
        output_group.add_argument("--json", action="store_true", help="JSON output")
        output_group.add_argument("--table", action="store_true", help="Table output (default)")
        sub_parser.add_argument("--from", dest="from_date", help="Filter from date (YYYY-MM-DD)")
        sub_parser.add_argument("--to", dest="to_date", help="Filter to date (YYYY-MM-DD)")

    # Project report
    project_parser = subparsers.add_parser("project", help="Project-level cost summary")
    project_parser.add_argument("project_id", nargs="?", help="Project ID (optional, all projects if not specified)")
    _add_common_args(project_parser)

    # Order report
    order_parser = subparsers.add_parser("order", help="ORDER-level cost summary")
    order_parser.add_argument("project_id", help="Project ID")
    order_parser.add_argument("order_id", nargs="?", help="Order ID (optional, all orders if not specified)")
    _add_common_args(order_parser)

    # Model report
    model_parser = subparsers.add_parser("model", help="Model-level cost summary")
    model_parser.add_argument("project_id", nargs="?", help="Project ID (optional, all projects if not specified)")
    _add_common_args(model_parser)

    # Summary report
    summary_parser = subparsers.add_parser("summary", help="Overall summary (all dimensions)")
    summary_parser.add_argument("project_id", nargs="?", help="Project ID (optional, all projects if not specified)")
    _add_common_args(summary_parser)

    args = parser.parse_args()

    # Execute report
    if args.report_type == "project":
        result = report_by_project(
            project_id=args.project_id,
            from_date=args.from_date,
            to_date=args.to_date,
        )
    elif args.report_type == "order":
        result = report_by_order(
            project_id=args.project_id,
            order_id=args.order_id,
            from_date=args.from_date,
            to_date=args.to_date,
        )
    elif args.report_type == "model":
        result = report_by_model(
            project_id=args.project_id,
            from_date=args.from_date,
            to_date=args.to_date,
        )
    elif args.report_type == "summary":
        result = generate_summary_report(
            project_id=args.project_id,
            start_date=args.from_date,
            end_date=args.to_date,
        )
    else:
        print(f"Unknown report type: {args.report_type}", file=sys.stderr)
        sys.exit(1)

    # Check for errors
    if not result.get("success", False):
        print(f"[ERROR] {result.get('error', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)

    # Output
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        # Table format (default, also when --table is explicitly given)
        if args.report_type == "project":
            print(format_table_project(result["data"], result["summary"]))
        elif args.report_type == "order":
            print(format_table_order(result["data"], result["summary"]))
        elif args.report_type == "model":
            print(format_table_model(result["data"], result["summary"]))
        elif args.report_type == "summary":
            print(format_table_summary(result["data"]))

        # Show filters if applied
        filters = result.get("filters", {})
        filter_parts = []
        if filters.get("project_id"):
            filter_parts.append(f"プロジェクト: {filters['project_id']}")
        if filters.get("order_id"):
            filter_parts.append(f"ORDER: {filters['order_id']}")
        if filters.get("from"):
            filter_parts.append(f"開始日: {filters['from']}")
        if filters.get("to"):
            filter_parts.append(f"終了日: {filters['to']}")

        if filter_parts:
            print(f"\nフィルタ: {', '.join(filter_parts)}")

        print(f"\n生成日時: {result['generated_at']}")


if __name__ == "__main__":
    main()
