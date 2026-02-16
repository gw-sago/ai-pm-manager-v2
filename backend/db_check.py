#!/usr/bin/env python3
"""
AI PM Manager - Database Health Check

Checks database integrity, schema version, and provides diagnostics.

Usage:
    python db_check.py [--db-path PATH] [--json]

Options:
    --db-path PATH  Database file path (default: ../data/aipm.db)
    --json          Output result as JSON
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def get_default_db_path() -> Path:
    """Get default database path"""
    script_dir = Path(__file__).resolve().parent
    return script_dir.parent / "data" / "aipm.db"


def check_database_health(
    db_path: Path,
    verbose: bool = True
) -> Tuple[bool, Dict]:
    """
    Check database health and integrity

    Args:
        db_path: Database file path
        verbose: Print diagnostic messages

    Returns:
        (is_healthy, diagnostics): Health status and diagnostic info
    """
    diagnostics = {
        "exists": False,
        "readable": False,
        "tables": [],
        "row_counts": {},
        "indexes": [],
        "views": [],
        "triggers": [],
        "schema_version": None,
        "foreign_keys_enabled": False,
        "integrity_ok": False,
        "errors": []
    }

    # Check file exists
    if not db_path.exists():
        diagnostics["errors"].append(f"Database file not found: {db_path}")
        return False, diagnostics

    diagnostics["exists"] = True
    diagnostics["file_size_mb"] = round(db_path.stat().st_size / (1024 * 1024), 2)

    try:
        # Open database
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        diagnostics["readable"] = True

        # Check foreign keys setting
        cursor = conn.execute("PRAGMA foreign_keys")
        fk_enabled = cursor.fetchone()[0]
        diagnostics["foreign_keys_enabled"] = bool(fk_enabled)

        # Get tables
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        diagnostics["tables"] = tables

        # Get row counts
        row_counts = {}
        for table in tables:
            cursor = conn.execute(f"SELECT COUNT(*) as count FROM {table}")
            count = cursor.fetchone()[0]
            row_counts[table] = count
        diagnostics["row_counts"] = row_counts

        # Get indexes
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        indexes = [row[0] for row in cursor.fetchall()]
        diagnostics["indexes"] = indexes

        # Get views
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='view'
            ORDER BY name
        """)
        views = [row[0] for row in cursor.fetchall()]
        diagnostics["views"] = views

        # Get triggers
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='trigger'
            ORDER BY name
        """)
        triggers = [row[0] for row in cursor.fetchall()]
        diagnostics["triggers"] = triggers

        # Check schema_version table
        if "schema_version" in tables:
            cursor = conn.execute("""
                SELECT version, description, applied_at
                FROM schema_version
                ORDER BY applied_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                diagnostics["schema_version"] = {
                    "version": row[0],
                    "description": row[1],
                    "applied_at": row[2]
                }

        # Run integrity check
        cursor = conn.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        diagnostics["integrity_ok"] = (result == "ok")

        if result != "ok":
            diagnostics["errors"].append(f"Integrity check failed: {result}")

        # Required tables check
        required_tables = {
            'projects', 'orders', 'tasks', 'task_dependencies',
            'backlog_items', 'status_transitions', 'bugs', 'error_patterns'
        }
        missing_tables = required_tables - set(tables)

        if missing_tables:
            diagnostics["errors"].append(
                f"Missing required tables: {', '.join(missing_tables)}"
            )

        conn.close()

        # Determine overall health
        is_healthy = (
            diagnostics["readable"] and
            diagnostics["integrity_ok"] and
            len(missing_tables) == 0
        )

        if verbose:
            print(f"Database Health Check: {db_path}")
            print(f"  Exists: {'✓' if diagnostics['exists'] else '✗'}")
            print(f"  Readable: {'✓' if diagnostics['readable'] else '✗'}")
            print(f"  Size: {diagnostics['file_size_mb']} MB")
            print(f"  Integrity: {'✓' if diagnostics['integrity_ok'] else '✗'}")
            print(f"  Foreign Keys: {'ON' if diagnostics['foreign_keys_enabled'] else 'OFF'}")
            print(f"\n  Tables: {len(diagnostics['tables'])}")
            for table, count in sorted(diagnostics['row_counts'].items()):
                print(f"    {table}: {count} rows")
            print(f"\n  Indexes: {len(diagnostics['indexes'])}")
            print(f"  Views: {len(diagnostics['views'])}")
            print(f"  Triggers: {len(diagnostics['triggers'])}")

            if diagnostics["schema_version"]:
                sv = diagnostics["schema_version"]
                print(f"\n  Schema Version: {sv['version']}")
                print(f"    Description: {sv['description']}")
                print(f"    Applied: {sv['applied_at']}")

            if diagnostics["errors"]:
                print(f"\n  ✗ Errors:")
                for error in diagnostics["errors"]:
                    print(f"    - {error}")
            else:
                print(f"\n  ✓ Health: {'OK' if is_healthy else 'DEGRADED'}")

        return is_healthy, diagnostics

    except Exception as e:
        diagnostics["errors"].append(f"{type(e).__name__}: {e}")
        if verbose:
            print(f"  ✗ Error: {e}")
        return False, diagnostics


def main():
    parser = argparse.ArgumentParser(
        description="AI PM Manager - Database Health Check"
    )

    default_db_path = get_default_db_path()

    parser.add_argument(
        "--db-path",
        type=Path,
        default=default_db_path,
        help=f"Database file path (default: {default_db_path})"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output messages"
    )

    args = parser.parse_args()

    verbose = not args.quiet

    # Run health check
    is_healthy, diagnostics = check_database_health(
        db_path=args.db_path,
        verbose=verbose and not args.json
    )

    # Output result
    if args.json:
        import json
        result = {
            "healthy": is_healthy,
            "diagnostics": diagnostics
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))

    sys.exit(0 if is_healthy else 1)


if __name__ == "__main__":
    main()
