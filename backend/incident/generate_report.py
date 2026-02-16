"""
AI PM Framework - Incident Report Generator

Generates comprehensive incident reports with pattern analysis and recommendations.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import get_connection, fetch_all, fetch_one
from utils.incident_logger import IncidentLogger
from analyze_patterns import IncidentPatternAnalyzer


class IncidentReportGenerator:
    """Generates detailed incident reports"""

    @staticmethod
    def generate_summary_report(
        days: int = 30,
        project_id: Optional[str] = None,
        output_format: str = 'markdown'
    ) -> str:
        """
        Generate comprehensive incident summary report

        Args:
            days: Number of days to analyze
            project_id: Filter by project ID (optional)
            output_format: Output format ('markdown' or 'text')

        Returns:
            str: Formatted report
        """
        # Get summary statistics
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        summary = IncidentLogger.get_incidents_summary(
            start_date=start_date,
            project_id=project_id
        )

        # Get all category analyses
        category_analyses = IncidentPatternAnalyzer.analyze_all_categories(
            days=days,
            project_id=project_id,
            min_incidents=0
        )

        # Get high-risk patterns
        high_risk = IncidentPatternAnalyzer.identify_high_risk_patterns(
            days=days,
            project_id=project_id,
            recurrence_threshold=0.3
        )

        # Generate report
        if output_format == 'markdown':
            return IncidentReportGenerator._generate_markdown_report(
                days=days,
                project_id=project_id,
                summary=summary,
                category_analyses=category_analyses,
                high_risk=high_risk
            )
        else:
            return IncidentReportGenerator._generate_text_report(
                days=days,
                project_id=project_id,
                summary=summary,
                category_analyses=category_analyses,
                high_risk=high_risk
            )

    @staticmethod
    def _generate_markdown_report(
        days: int,
        project_id: Optional[str],
        summary: Dict[str, Any],
        category_analyses: List[Dict[str, Any]],
        high_risk: Dict[str, Any]
    ) -> str:
        """Generate report in Markdown format"""
        lines = []

        # Header
        lines.append("# Incident Analysis Report")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Analysis Period:** {days} days")
        if project_id:
            lines.append(f"**Project:** {project_id}")
        lines.append("")

        # Executive Summary
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(f"- **Total Incidents:** {summary['total']}")
        lines.append(f"- **High Severity:** {summary['by_severity'].get('HIGH', 0)}")
        lines.append(f"- **High-Risk Categories:** {len(high_risk['high_risk_categories'])}")
        lines.append(f"- **Increasing Trends:** {len(high_risk['increasing_trends'])}")
        lines.append("")

        # Severity Distribution
        lines.append("## Severity Distribution")
        lines.append("")
        lines.append("| Severity | Count | Percentage |")
        lines.append("|----------|-------|------------|")
        for severity in ['HIGH', 'MEDIUM', 'LOW']:
            count = summary['by_severity'].get(severity, 0)
            pct = (count / summary['total'] * 100) if summary['total'] > 0 else 0
            lines.append(f"| {severity} | {count} | {pct:.1f}% |")
        lines.append("")

        # Category Distribution
        lines.append("## Category Distribution")
        lines.append("")
        lines.append("| Category | Count | Rate (per day) | Trend | Resolution Rate |")
        lines.append("|----------|-------|----------------|-------|-----------------|")
        for analysis in category_analyses:
            if analysis['incident_count'] > 0:
                category = analysis['category']
                count = analysis['incident_count']
                rate = analysis['recurrence_stats']['recurrence_rate']
                trend = analysis['recurrence_stats']['trend']
                resolution = analysis['resolution_rate']

                # Add trend emoji
                trend_emoji = {
                    'increasing': '📈',
                    'decreasing': '📉',
                    'stable': '➡️'
                }.get(trend, '➡️')

                lines.append(
                    f"| {category} | {count} | {rate} | {trend_emoji} {trend} | {resolution}% |"
                )
        lines.append("")

        # High-Risk Categories
        if high_risk['high_risk_categories']:
            lines.append("## 🔴 High-Risk Categories")
            lines.append("")
            lines.append("Categories with high recurrence rates requiring immediate attention:")
            lines.append("")

            for risk in high_risk['high_risk_categories']:
                lines.append(f"### {risk['category']}")
                lines.append("")
                lines.append(f"- **Recurrence Rate:** {risk['recurrence_rate']} incidents/day")
                lines.append(f"- **Total Incidents:** {risk['incident_count']}")
                lines.append(f"- **Trend:** {risk['trend'].upper()}")
                lines.append("")

                # Find analysis for this category
                analysis = next(
                    (a for a in category_analyses if a['category'] == risk['category']),
                    None
                )
                if analysis:
                    lines.append("**Recommended Countermeasures:**")
                    lines.append("")
                    for measure in analysis['countermeasures']:
                        lines.append(f"- {measure}")
                    lines.append("")

        # Increasing Trends
        if high_risk['increasing_trends']:
            lines.append("## ⚠️ Increasing Trends")
            lines.append("")
            lines.append("Categories showing increasing incident rates:")
            lines.append("")
            lines.append("| Category | Rate | First Half | Second Half | Increase |")
            lines.append("|----------|------|------------|-------------|----------|")

            for trend in high_risk['increasing_trends']:
                lines.append(
                    f"| {trend['category']} | {trend['recurrence_rate']} | "
                    f"{trend['first_half']} | {trend['second_half']} | +{trend['increase_pct']}% |"
                )
            lines.append("")

        # Recent High Severity Incidents
        if high_risk['high_severity_incidents']:
            lines.append("## 🚨 Recent High Severity Incidents")
            lines.append("")
            lines.append("| ID | Date | Category | Description |")
            lines.append("|----|------|----------|-------------|")

            for incident in high_risk['high_severity_incidents'][:5]:
                date = incident['timestamp'][:10]
                description = incident['description'][:60] + '...' if len(incident['description']) > 60 else incident['description']
                lines.append(
                    f"| {incident['incident_id']} | {date} | {incident['category']} | {description} |"
                )
            lines.append("")

        # Recommendations
        if high_risk['recommendations']:
            lines.append("## 📋 Prioritized Recommendations")
            lines.append("")

            for i, rec in enumerate(high_risk['recommendations'], 1):
                priority_emoji = {
                    'HIGH': '🔴',
                    'MEDIUM': '🟡',
                    'LOW': '🟢'
                }.get(rec['priority'], '⚪')

                lines.append(f"### {i}. {priority_emoji} [{rec['priority']}] {rec['category']}")
                lines.append("")
                lines.append(f"**Reason:** {rec['reason']}")
                lines.append("")
                lines.append("**Countermeasures:**")
                lines.append("")
                for measure in rec['countermeasures']:
                    lines.append(f"- {measure}")
                lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append("*This report was automatically generated by AI PM Framework Incident Analysis System*")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _generate_text_report(
        days: int,
        project_id: Optional[str],
        summary: Dict[str, Any],
        category_analyses: List[Dict[str, Any]],
        high_risk: Dict[str, Any]
    ) -> str:
        """Generate report in plain text format"""
        lines = []
        width = 80

        # Header
        lines.append("=" * width)
        lines.append("INCIDENT ANALYSIS REPORT".center(width))
        lines.append("=" * width)
        lines.append("")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Analysis Period: {days} days")
        if project_id:
            lines.append(f"Project: {project_id}")
        lines.append("")

        # Executive Summary
        lines.append("-" * width)
        lines.append("EXECUTIVE SUMMARY")
        lines.append("-" * width)
        lines.append(f"Total Incidents: {summary['total']}")
        lines.append(f"High Severity: {summary['by_severity'].get('HIGH', 0)}")
        lines.append(f"High-Risk Categories: {len(high_risk['high_risk_categories'])}")
        lines.append(f"Increasing Trends: {len(high_risk['increasing_trends'])}")
        lines.append("")

        # Severity Distribution
        lines.append("-" * width)
        lines.append("SEVERITY DISTRIBUTION")
        lines.append("-" * width)
        for severity in ['HIGH', 'MEDIUM', 'LOW']:
            count = summary['by_severity'].get(severity, 0)
            pct = (count / summary['total'] * 100) if summary['total'] > 0 else 0
            lines.append(f"  {severity:10} {count:5} ({pct:5.1f}%)")
        lines.append("")

        # Category Distribution
        lines.append("-" * width)
        lines.append("CATEGORY DISTRIBUTION")
        lines.append("-" * width)
        for analysis in category_analyses:
            if analysis['incident_count'] > 0:
                category = analysis['category']
                count = analysis['incident_count']
                rate = analysis['recurrence_stats']['recurrence_rate']
                trend = analysis['recurrence_stats']['trend']
                resolution = analysis['resolution_rate']

                lines.append(f"\n{category}")
                lines.append(f"  Incidents: {count}")
                lines.append(f"  Rate: {rate} per day")
                lines.append(f"  Trend: {trend.upper()}")
                lines.append(f"  Resolution Rate: {resolution}%")
        lines.append("")

        # High-Risk Categories
        if high_risk['high_risk_categories']:
            lines.append("-" * width)
            lines.append("HIGH-RISK CATEGORIES")
            lines.append("-" * width)
            lines.append("")

            for risk in high_risk['high_risk_categories']:
                lines.append(f"[HIGH RISK] {risk['category']}")
                lines.append(f"  Recurrence Rate: {risk['recurrence_rate']} incidents/day")
                lines.append(f"  Total Incidents: {risk['incident_count']}")
                lines.append(f"  Trend: {risk['trend'].upper()}")

                # Find analysis for this category
                analysis = next(
                    (a for a in category_analyses if a['category'] == risk['category']),
                    None
                )
                if analysis:
                    lines.append(f"\n  Recommended Countermeasures:")
                    for i, measure in enumerate(analysis['countermeasures'], 1):
                        lines.append(f"    {i}. {measure}")
                lines.append("")

        # Recommendations
        if high_risk['recommendations']:
            lines.append("-" * width)
            lines.append("PRIORITIZED RECOMMENDATIONS")
            lines.append("-" * width)
            lines.append("")

            for i, rec in enumerate(high_risk['recommendations'], 1):
                lines.append(f"{i}. [{rec['priority']}] {rec['category']}")
                lines.append(f"   Reason: {rec['reason']}")
                lines.append(f"   Countermeasures:")
                for measure in rec['countermeasures']:
                    lines.append(f"     - {measure}")
                lines.append("")

        # Footer
        lines.append("=" * width)
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def generate_category_detail_report(
        category: str,
        days: int = 30,
        project_id: Optional[str] = None,
        output_format: str = 'markdown'
    ) -> str:
        """
        Generate detailed report for a specific category

        Args:
            category: Incident category
            days: Number of days to analyze
            project_id: Filter by project ID (optional)
            output_format: Output format ('markdown' or 'text')

        Returns:
            str: Formatted report
        """
        analysis = IncidentPatternAnalyzer.analyze_category_patterns(
            category=category,
            days=days,
            project_id=project_id
        )

        comparison = IncidentPatternAnalyzer.compare_periods(
            category=category,
            current_days=days,
            previous_days=days,
            project_id=project_id
        )

        if output_format == 'markdown':
            lines = []

            # Header
            lines.append(f"# Incident Detail Report: {category}")
            lines.append("")
            lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"**Analysis Period:** {days} days")
            if project_id:
                lines.append(f"**Project:** {project_id}")
            lines.append("")

            # Overview
            lines.append("## Overview")
            lines.append("")
            lines.append(f"- **Total Incidents:** {analysis['incident_count']}")
            lines.append(f"- **Recurrence Rate:** {analysis['recurrence_stats']['recurrence_rate']} incidents/day")
            lines.append(f"- **Trend:** {analysis['recurrence_stats']['trend'].upper()}")
            lines.append(f"- **Resolution Rate:** {analysis['resolution_rate']}%")
            lines.append("")

            # Period Comparison
            lines.append("## Period Comparison")
            lines.append("")
            lines.append("| Period | Count | Rate | Status |")
            lines.append("|--------|-------|------|--------|")
            lines.append(
                f"| Current ({comparison['current_period']['days']} days) | "
                f"{comparison['current_period']['count']} | "
                f"{comparison['current_period']['rate']} | "
                f"{comparison['status']} |"
            )
            lines.append(
                f"| Previous ({comparison['previous_period']['days']} days) | "
                f"{comparison['previous_period']['count']} | "
                f"{comparison['previous_period']['rate']} | "
                f"- |"
            )
            lines.append(f"| **Change** | **{comparison['change_pct']:+.1f}%** | - | - |")
            lines.append("")

            # Severity Distribution
            lines.append("## Severity Distribution")
            lines.append("")
            total = sum(analysis['severity_distribution'].values())
            for severity, count in analysis['severity_distribution'].items():
                pct = (count / total * 100) if total > 0 else 0
                lines.append(f"- **{severity}:** {count} ({pct:.1f}%)")
            lines.append("")

            # Recent Incidents
            lines.append("## Recent Incidents")
            lines.append("")
            lines.append("| ID | Date | Severity | Description | Resolved |")
            lines.append("|----|------|----------|-------------|----------|")

            for incident in analysis['incidents'][:10]:
                date = incident['timestamp'][:10]
                description = incident['description'][:50] + '...' if len(incident['description']) > 50 else incident['description']
                resolved = '✅' if incident.get('resolution') else '❌'
                lines.append(
                    f"| {incident['incident_id']} | {date} | {incident['severity']} | {description} | {resolved} |"
                )
            lines.append("")

            # Countermeasures
            lines.append("## Recommended Countermeasures")
            lines.append("")
            for i, measure in enumerate(analysis['countermeasures'], 1):
                lines.append(f"{i}. {measure}")
            lines.append("")

            return "\n".join(lines)

        else:
            lines = []
            width = 80

            # Header
            lines.append("=" * width)
            lines.append(f"INCIDENT DETAIL REPORT: {category}".center(width))
            lines.append("=" * width)
            lines.append("")
            lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"Analysis Period: {days} days")
            if project_id:
                lines.append(f"Project: {project_id}")
            lines.append("")

            # Overview
            lines.append("-" * width)
            lines.append("OVERVIEW")
            lines.append("-" * width)
            lines.append(f"Total Incidents: {analysis['incident_count']}")
            lines.append(f"Recurrence Rate: {analysis['recurrence_stats']['recurrence_rate']} incidents/day")
            lines.append(f"Trend: {analysis['recurrence_stats']['trend'].upper()}")
            lines.append(f"Resolution Rate: {analysis['resolution_rate']}%")
            lines.append("")

            # Period Comparison
            lines.append("-" * width)
            lines.append("PERIOD COMPARISON")
            lines.append("-" * width)
            lines.append(f"Current Period ({comparison['current_period']['days']} days):")
            lines.append(f"  Count: {comparison['current_period']['count']}")
            lines.append(f"  Rate: {comparison['current_period']['rate']} incidents/day")
            lines.append(f"Previous Period ({comparison['previous_period']['days']} days):")
            lines.append(f"  Count: {comparison['previous_period']['count']}")
            lines.append(f"  Rate: {comparison['previous_period']['rate']} incidents/day")
            lines.append(f"Change: {comparison['change_pct']:+.1f}%")
            lines.append(f"Status: {comparison['status']}")
            lines.append("")

            # Countermeasures
            lines.append("-" * width)
            lines.append("RECOMMENDED COUNTERMEASURES")
            lines.append("-" * width)
            for i, measure in enumerate(analysis['countermeasures'], 1):
                lines.append(f"{i}. {measure}")
            lines.append("")

            lines.append("=" * width)

            return "\n".join(lines)


def main():
    """Main entry point for command-line usage"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate incident analysis reports'
    )
    parser.add_argument(
        '--type',
        choices=['summary', 'category'],
        default='summary',
        help='Report type (default: summary)'
    )
    parser.add_argument(
        '--category',
        help='Category for detail report (required if type=category)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Number of days to analyze (default: 30)'
    )
    parser.add_argument(
        '--project-id',
        help='Filter by project ID'
    )
    parser.add_argument(
        '--format',
        choices=['markdown', 'text', 'json'],
        default='markdown',
        help='Output format (default: markdown)'
    )
    parser.add_argument(
        '--output',
        help='Output file path (default: stdout)'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.type == 'category' and not args.category:
        parser.error("--category is required when --type=category")

    # Generate report
    if args.type == 'summary':
        if args.format == 'json':
            # Generate JSON summary
            start_date = (datetime.now() - timedelta(days=args.days)).isoformat()
            summary = IncidentLogger.get_incidents_summary(
                start_date=start_date,
                project_id=args.project_id
            )
            category_analyses = IncidentPatternAnalyzer.analyze_all_categories(
                days=args.days,
                project_id=args.project_id
            )
            high_risk = IncidentPatternAnalyzer.identify_high_risk_patterns(
                days=args.days,
                project_id=args.project_id
            )
            report = json.dumps({
                'summary': summary,
                'category_analyses': category_analyses,
                'high_risk': high_risk
            }, indent=2, default=str)
        else:
            report = IncidentReportGenerator.generate_summary_report(
                days=args.days,
                project_id=args.project_id,
                output_format=args.format
            )
    else:
        if args.format == 'json':
            analysis = IncidentPatternAnalyzer.analyze_category_patterns(
                category=args.category,
                days=args.days,
                project_id=args.project_id
            )
            comparison = IncidentPatternAnalyzer.compare_periods(
                category=args.category,
                current_days=args.days,
                previous_days=args.days,
                project_id=args.project_id
            )
            report = json.dumps({
                'analysis': analysis,
                'comparison': comparison
            }, indent=2, default=str)
        else:
            report = IncidentReportGenerator.generate_category_detail_report(
                category=args.category,
                days=args.days,
                project_id=args.project_id,
                output_format=args.format
            )

    # Output report
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding='utf-8')
        print(f"Report saved to: {output_path}")
    else:
        print(report)


if __name__ == '__main__':
    main()
