#!/usr/bin/env python3
"""
AI PM Framework - Incidents Analysis Dashboard Generator

Analyzes INCIDENTS table and generates visualization data for dashboard:
- Incident trends over time
- Category breakdown
- Severity distribution
- Most affected projects/tasks
- Recovery success rate

Usage:
    python backend/dashboard/incidents_analysis.py
    python backend/dashboard/incidents_analysis.py --output data/incidents_dashboard.json
"""

import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

# Path setup
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, fetch_all, rows_to_dicts

logger = logging.getLogger(__name__)


class IncidentsAnalyzer:
    """Analyzes incidents data and generates dashboard statistics"""

    def __init__(self, days_back: int = 30, verbose: bool = False):
        """
        Args:
            days_back: Number of days of history to analyze
            verbose: Verbose logging
        """
        self.days_back = days_back
        self.verbose = verbose

        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)

    def analyze(self) -> Dict[str, Any]:
        """
        Perform complete incident analysis

        Returns:
            Dictionary with all analysis results
        """
        logger.info(f"Analyzing incidents (last {self.days_back} days)...")

        conn = get_connection()
        try:
            # Get all incidents within timeframe
            cutoff_date = (datetime.now() - timedelta(days=self.days_back)).isoformat()

            incidents_rows = fetch_all(
                conn,
                """
                SELECT incident_id, timestamp, project_id, order_id, task_id,
                       category, severity, description, root_cause, resolution
                FROM incidents
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
                """,
                (cutoff_date,)
            )

            incidents = rows_to_dicts(incidents_rows)

            logger.info(f"Found {len(incidents)} incidents to analyze")

            # Perform various analyses
            analysis = {
                "generated_at": datetime.now().isoformat(),
                "days_analyzed": self.days_back,
                "total_incidents": len(incidents),
                "summary": self._generate_summary(incidents),
                "trends": self._analyze_trends(incidents),
                "categories": self._analyze_categories(incidents),
                "severity": self._analyze_severity(incidents),
                "top_affected": self._analyze_top_affected(incidents),
                "recovery_rate": self._analyze_recovery_rate(incidents),
                "recent_incidents": self._get_recent_incidents(incidents, limit=10),
            }

            logger.info("Analysis complete")
            return analysis

        finally:
            conn.close()

    def _generate_summary(self, incidents: List[Dict]) -> Dict[str, Any]:
        """Generate high-level summary"""
        if not incidents:
            return {
                "total": 0,
                "high_severity": 0,
                "resolved": 0,
                "unresolved": 0,
            }

        high_severity = sum(1 for i in incidents if i.get("severity") == "HIGH")
        resolved = sum(1 for i in incidents if i.get("resolution"))

        return {
            "total": len(incidents),
            "high_severity": high_severity,
            "high_severity_pct": round(high_severity / len(incidents) * 100, 1) if incidents else 0,
            "resolved": resolved,
            "unresolved": len(incidents) - resolved,
            "resolution_rate": round(resolved / len(incidents) * 100, 1) if incidents else 0,
        }

    def _analyze_trends(self, incidents: List[Dict]) -> Dict[str, Any]:
        """Analyze incident trends over time"""
        # Group by day
        daily_counts = defaultdict(int)

        for incident in incidents:
            timestamp_str = incident.get("timestamp")
            if timestamp_str:
                try:
                    dt = datetime.fromisoformat(timestamp_str)
                    day_key = dt.strftime("%Y-%m-%d")
                    daily_counts[day_key] += 1
                except (ValueError, TypeError):
                    continue

        # Sort by date
        sorted_days = sorted(daily_counts.items())

        return {
            "daily": [
                {"date": day, "count": count}
                for day, count in sorted_days
            ],
            "peak_day": max(sorted_days, key=lambda x: x[1]) if sorted_days else None,
            "avg_per_day": round(sum(daily_counts.values()) / len(daily_counts), 1) if daily_counts else 0,
        }

    def _analyze_categories(self, incidents: List[Dict]) -> Dict[str, Any]:
        """Analyze incidents by category"""
        category_counts = defaultdict(int)
        category_severity = defaultdict(lambda: {"HIGH": 0, "MEDIUM": 0, "LOW": 0})

        for incident in incidents:
            category = incident.get("category", "UNKNOWN")
            severity = incident.get("severity", "MEDIUM")

            category_counts[category] += 1
            category_severity[category][severity] += 1

        # Sort by count
        sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)

        return {
            "breakdown": [
                {
                    "category": cat,
                    "count": count,
                    "percentage": round(count / len(incidents) * 100, 1) if incidents else 0,
                    "severity_breakdown": dict(category_severity[cat])
                }
                for cat, count in sorted_categories
            ],
            "top_category": sorted_categories[0] if sorted_categories else None,
        }

    def _analyze_severity(self, incidents: List[Dict]) -> Dict[str, Any]:
        """Analyze severity distribution"""
        severity_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

        for incident in incidents:
            severity = incident.get("severity", "MEDIUM")
            severity_counts[severity] += 1

        total = len(incidents)

        return {
            "distribution": {
                severity: {
                    "count": count,
                    "percentage": round(count / total * 100, 1) if total > 0 else 0
                }
                for severity, count in severity_counts.items()
            }
        }

    def _analyze_top_affected(self, incidents: List[Dict]) -> Dict[str, Any]:
        """Analyze most affected projects and tasks"""
        project_counts = defaultdict(int)
        task_counts = defaultdict(int)

        for incident in incidents:
            project_id = incident.get("project_id")
            task_id = incident.get("task_id")

            if project_id:
                project_counts[project_id] += 1
            if task_id:
                task_counts[task_id] += 1

        # Top 5 projects
        top_projects = sorted(project_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        # Top 5 tasks
        top_tasks = sorted(task_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "projects": [
                {"project_id": proj, "incident_count": count}
                for proj, count in top_projects
            ],
            "tasks": [
                {"task_id": task, "incident_count": count}
                for task, count in top_tasks
            ]
        }

    def _analyze_recovery_rate(self, incidents: List[Dict]) -> Dict[str, Any]:
        """Analyze recovery success rate by category"""
        category_stats = defaultdict(lambda: {"total": 0, "resolved": 0})

        for incident in incidents:
            category = incident.get("category", "UNKNOWN")
            has_resolution = bool(incident.get("resolution"))

            category_stats[category]["total"] += 1
            if has_resolution:
                category_stats[category]["resolved"] += 1

        # Calculate success rates
        recovery_rates = []
        for category, stats in category_stats.items():
            total = stats["total"]
            resolved = stats["resolved"]
            rate = round(resolved / total * 100, 1) if total > 0 else 0

            recovery_rates.append({
                "category": category,
                "total": total,
                "resolved": resolved,
                "success_rate": rate
            })

        # Sort by success rate
        recovery_rates.sort(key=lambda x: x["success_rate"], reverse=True)

        return {
            "by_category": recovery_rates,
            "overall_rate": round(
                sum(s["resolved"] for s in category_stats.values()) /
                sum(s["total"] for s in category_stats.values()) * 100, 1
            ) if category_stats else 0
        }

    def _get_recent_incidents(self, incidents: List[Dict], limit: int = 10) -> List[Dict[str, Any]]:
        """Get most recent incidents"""
        # Sort by timestamp (already sorted DESC from query)
        recent = incidents[:limit]

        return [
            {
                "incident_id": inc.get("incident_id"),
                "timestamp": inc.get("timestamp"),
                "category": inc.get("category"),
                "severity": inc.get("severity"),
                "project_id": inc.get("project_id"),
                "task_id": inc.get("task_id"),
                "description": inc.get("description"),
                "resolved": bool(inc.get("resolution")),
            }
            for inc in recent
        ]

    def save_to_file(self, analysis: Dict[str, Any], output_path: Path) -> None:
        """Save analysis results to JSON file"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)

        logger.info(f"Analysis saved to: {output_path}")


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Incidents analysis dashboard generator")
    parser.add_argument("--days", type=int, default=30, help="Days of history to analyze")
    parser.add_argument("--output", type=str,
                        default=str(_project_root / "data" / "incidents_dashboard.json"),
                        help="Output file path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--print", action="store_true", help="Print results to console")

    args = parser.parse_args()

    # Logging setup
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Run analysis
    analyzer = IncidentsAnalyzer(days_back=args.days, verbose=args.verbose)
    analysis = analyzer.analyze()

    # Save to file
    output_path = Path(args.output)
    analyzer.save_to_file(analysis, output_path)

    # Print summary
    print("\n" + "="*70)
    print("INCIDENTS ANALYSIS SUMMARY")
    print("="*70)
    print(f"Total Incidents: {analysis['summary']['total']}")
    print(f"High Severity: {analysis['summary']['high_severity']} ({analysis['summary']['high_severity_pct']}%)")
    print(f"Resolution Rate: {analysis['summary']['resolution_rate']}%")
    print(f"\nTop Category: {analysis['categories']['top_category']}")
    print(f"Average Incidents/Day: {analysis['trends']['avg_per_day']}")
    print("="*70)

    if args.print:
        print("\nFull Analysis:")
        print(json.dumps(analysis, ensure_ascii=False, indent=2))

    print(f"\n✓ Analysis saved to: {output_path}\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
