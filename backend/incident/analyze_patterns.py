"""
AI PM Framework - Incident Pattern Analysis

Analyzes incident patterns to identify recurring issues and calculate recurrence rates.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import get_connection, fetch_all, fetch_one
from utils.incident_logger import IncidentLogger


class IncidentPatternAnalyzer:
    """Analyzes incident patterns and provides recommendations"""

    # Recommended countermeasures by category
    COUNTERMEASURES = {
        'MIGRATION_ERROR': [
            'Test migrations in development environment first',
            'Implement rollback procedures before migration',
            'Use migration version control',
            'Review schema changes with team before applying'
        ],
        'CASCADE_DELETE': [
            'Review foreign key relationships before deletion',
            'Implement soft deletes for critical data',
            'Add confirmation steps for cascade operations',
            'Use database triggers to log cascade deletions'
        ],
        'CONSTRAINT_VIOLATION': [
            'Validate data before insertion/update',
            'Document all database constraints',
            'Implement application-level validation',
            'Add meaningful error messages for constraint failures'
        ],
        'DATA_INTEGRITY': [
            'Implement regular data integrity checks',
            'Use database transactions for multi-step operations',
            'Add audit logging for data modifications',
            'Implement data validation at multiple layers'
        ],
        'CONCURRENCY_ERROR': [
            'Implement optimistic locking with version fields',
            'Use database-level locking for critical sections',
            'Add retry logic with exponential backoff',
            'Review transaction isolation levels'
        ],
        'FILE_LOCK_ERROR': [
            'Implement timeout mechanisms for file locks',
            'Use advisory locks instead of mandatory locks',
            'Add lock release on error/exception',
            'Monitor lock duration and identify long-running operations'
        ],
        'WORKER_FAILURE': [
            'Implement worker health checks',
            'Add automatic worker restart on failure',
            'Use circuit breaker pattern for external dependencies',
            'Implement comprehensive error logging'
        ],
        'REVIEW_ERROR': [
            'Standardize review checklists',
            'Implement automated review criteria checks',
            'Add review training for common issues',
            'Track review approval/rejection patterns'
        ],
        'SYSTEM_ERROR': [
            'Implement comprehensive monitoring',
            'Add graceful degradation for system failures',
            'Create detailed error reporting',
            'Implement automatic recovery procedures'
        ],
        'OTHER': [
            'Analyze incident details to categorize properly',
            'Document root cause for future reference',
            'Create specific countermeasures based on analysis',
            'Review and update incident categories as needed'
        ]
    }

    @staticmethod
    def analyze_category_patterns(
        category: str,
        days: int = 30,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze patterns for a specific incident category

        Args:
            category: Incident category to analyze
            days: Number of days to look back (default: 30)
            project_id: Filter by project ID (optional)

        Returns:
            Dict containing:
                - category: Category name
                - recurrence_stats: Recurrence statistics
                - incidents: List of incidents in this category
                - countermeasures: Recommended countermeasures
                - severity_distribution: Distribution by severity
        """
        # Get recurrence rate
        recurrence_stats = IncidentLogger.get_recurrence_rate(
            category=category,
            days=days,
            project_id=project_id
        )

        # Get incidents in category
        incidents = IncidentLogger.get_incidents_by_category(
            category=category,
            project_id=project_id
        )

        # Filter by date range
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        filtered_incidents = [
            inc for inc in incidents
            if inc['timestamp'] >= start_date
        ]

        # Calculate severity distribution
        severity_distribution = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        for incident in filtered_incidents:
            severity_distribution[incident['severity']] += 1

        # Get countermeasures
        countermeasures = IncidentPatternAnalyzer.COUNTERMEASURES.get(
            category,
            IncidentPatternAnalyzer.COUNTERMEASURES['OTHER']
        )

        # Calculate resolution rate
        resolved_count = sum(1 for inc in filtered_incidents if inc.get('resolution'))
        resolution_rate = (resolved_count / len(filtered_incidents) * 100) if filtered_incidents else 0

        return {
            'category': category,
            'recurrence_stats': recurrence_stats,
            'incident_count': len(filtered_incidents),
            'incidents': filtered_incidents,
            'countermeasures': countermeasures,
            'severity_distribution': severity_distribution,
            'resolution_rate': round(resolution_rate, 1),
            'analysis_period_days': days
        }

    @staticmethod
    def analyze_all_categories(
        days: int = 30,
        project_id: Optional[str] = None,
        min_incidents: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Analyze patterns across all incident categories

        Args:
            days: Number of days to look back
            project_id: Filter by project ID (optional)
            min_incidents: Minimum incidents to include category (default: 1)

        Returns:
            List of analysis results for each category, sorted by recurrence rate
        """
        results = []

        for category in IncidentLogger.CATEGORIES:
            analysis = IncidentPatternAnalyzer.analyze_category_patterns(
                category=category,
                days=days,
                project_id=project_id
            )

            # Only include categories with minimum incident count
            if analysis['incident_count'] >= min_incidents:
                results.append(analysis)

        # Sort by recurrence rate (descending)
        results.sort(
            key=lambda x: x['recurrence_stats']['recurrence_rate'],
            reverse=True
        )

        return results

    @staticmethod
    def identify_high_risk_patterns(
        days: int = 30,
        project_id: Optional[str] = None,
        recurrence_threshold: float = 0.5
    ) -> Dict[str, Any]:
        """
        Identify high-risk incident patterns requiring immediate attention

        Args:
            days: Number of days to analyze
            project_id: Filter by project ID (optional)
            recurrence_threshold: Recurrence rate threshold (incidents/day)

        Returns:
            Dict containing:
                - high_risk_categories: Categories exceeding threshold
                - increasing_trends: Categories with increasing trend
                - high_severity_incidents: Recent high severity incidents
                - recommendations: Prioritized recommendations
        """
        all_analyses = IncidentPatternAnalyzer.analyze_all_categories(
            days=days,
            project_id=project_id,
            min_incidents=1
        )

        # Categories exceeding recurrence threshold
        high_risk_categories = [
            {
                'category': analysis['category'],
                'recurrence_rate': analysis['recurrence_stats']['recurrence_rate'],
                'incident_count': analysis['incident_count'],
                'trend': analysis['recurrence_stats']['trend']
            }
            for analysis in all_analyses
            if analysis['recurrence_stats']['recurrence_rate'] >= recurrence_threshold
        ]

        # Categories with increasing trends
        increasing_trends = [
            {
                'category': analysis['category'],
                'recurrence_rate': analysis['recurrence_stats']['recurrence_rate'],
                'first_half': analysis['recurrence_stats']['first_half_count'],
                'second_half': analysis['recurrence_stats']['second_half_count'],
                'increase_pct': round(
                    (analysis['recurrence_stats']['second_half_count'] -
                     analysis['recurrence_stats']['first_half_count']) /
                    max(analysis['recurrence_stats']['first_half_count'], 1) * 100,
                    1
                )
            }
            for analysis in all_analyses
            if analysis['recurrence_stats']['trend'] == 'increasing'
        ]

        # Get high severity incidents
        summary = IncidentLogger.get_incidents_summary(
            start_date=(datetime.now() - timedelta(days=days)).isoformat(),
            project_id=project_id
        )
        high_severity_incidents = summary['recent_high']

        # Generate prioritized recommendations
        recommendations = []

        # Add recommendations for high-risk categories
        for risk in high_risk_categories:
            category = risk['category']
            countermeasures = IncidentPatternAnalyzer.COUNTERMEASURES.get(
                category,
                IncidentPatternAnalyzer.COUNTERMEASURES['OTHER']
            )
            recommendations.append({
                'priority': 'HIGH',
                'category': category,
                'reason': f"High recurrence rate: {risk['recurrence_rate']} incidents/day",
                'countermeasures': countermeasures
            })

        # Add recommendations for increasing trends
        for trend in increasing_trends:
            if trend['category'] not in [r['category'] for r in recommendations]:
                category = trend['category']
                countermeasures = IncidentPatternAnalyzer.COUNTERMEASURES.get(
                    category,
                    IncidentPatternAnalyzer.COUNTERMEASURES['OTHER']
                )
                recommendations.append({
                    'priority': 'MEDIUM',
                    'category': category,
                    'reason': f"Increasing trend: {trend['increase_pct']}% increase",
                    'countermeasures': countermeasures
                })

        return {
            'analysis_period_days': days,
            'high_risk_categories': high_risk_categories,
            'increasing_trends': increasing_trends,
            'high_severity_incidents': high_severity_incidents,
            'recommendations': recommendations
        }

    @staticmethod
    def compare_periods(
        category: str,
        current_days: int = 30,
        previous_days: int = 30,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compare incident patterns between two time periods

        Args:
            category: Incident category to compare
            current_days: Days in current period
            previous_days: Days in previous period
            project_id: Filter by project ID (optional)

        Returns:
            Dict containing comparison metrics
        """
        # Current period
        current_start = (datetime.now() - timedelta(days=current_days)).isoformat()
        current_end = datetime.now().isoformat()

        # Previous period
        previous_start = (datetime.now() - timedelta(days=current_days + previous_days)).isoformat()
        previous_end = current_start

        conn = get_connection()
        try:
            # Build WHERE clause
            where_base = "WHERE category = ? AND timestamp >= ? AND timestamp < ?"
            params_base = [category]

            if project_id:
                where_base += " AND project_id = ?"

            # Current period count
            current_params = params_base + [current_start, current_end]
            if project_id:
                current_params.append(project_id)

            current_row = fetch_one(
                conn,
                f"SELECT COUNT(*) as count FROM incidents {where_base}",
                tuple(current_params)
            )
            current_count = current_row['count'] if current_row else 0

            # Previous period count
            previous_params = params_base + [previous_start, previous_end]
            if project_id:
                previous_params.append(project_id)

            previous_row = fetch_one(
                conn,
                f"SELECT COUNT(*) as count FROM incidents {where_base}",
                tuple(previous_params)
            )
            previous_count = previous_row['count'] if previous_row else 0

            # Calculate change
            if previous_count > 0:
                change_pct = ((current_count - previous_count) / previous_count) * 100
            else:
                change_pct = 100.0 if current_count > 0 else 0.0

            # Determine status
            if change_pct > 20:
                status = 'WORSENING'
            elif change_pct < -20:
                status = 'IMPROVING'
            else:
                status = 'STABLE'

            return {
                'category': category,
                'current_period': {
                    'days': current_days,
                    'count': current_count,
                    'rate': round(current_count / current_days, 2)
                },
                'previous_period': {
                    'days': previous_days,
                    'count': previous_count,
                    'rate': round(previous_count / previous_days, 2)
                },
                'change_pct': round(change_pct, 1),
                'status': status
            }

        finally:
            conn.close()


def main():
    """Main entry point for command-line usage"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Analyze incident patterns and calculate recurrence rates'
    )
    parser.add_argument(
        '--category',
        help='Analyze specific category'
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
        '--high-risk',
        action='store_true',
        help='Show high-risk patterns only'
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=0.5,
        help='Recurrence threshold for high-risk (default: 0.5)'
    )
    parser.add_argument(
        '--compare',
        action='store_true',
        help='Compare with previous period'
    )
    parser.add_argument(
        '--output',
        choices=['text', 'json'],
        default='text',
        help='Output format (default: text)'
    )

    args = parser.parse_args()

    if args.high_risk:
        # High-risk pattern analysis
        result = IncidentPatternAnalyzer.identify_high_risk_patterns(
            days=args.days,
            project_id=args.project_id,
            recurrence_threshold=args.threshold
        )

        if args.output == 'json':
            print(json.dumps(result, indent=2))
        else:
            print("\n" + "="*60)
            print("HIGH-RISK INCIDENT PATTERN ANALYSIS")
            print("="*60)
            print(f"\nAnalysis Period: {result['analysis_period_days']} days\n")

            if result['high_risk_categories']:
                print("\n🔴 HIGH-RISK CATEGORIES (exceeding threshold):")
                print("-" * 60)
                for risk in result['high_risk_categories']:
                    print(f"\n  Category: {risk['category']}")
                    print(f"  Recurrence Rate: {risk['recurrence_rate']} incidents/day")
                    print(f"  Total Incidents: {risk['incident_count']}")
                    print(f"  Trend: {risk['trend'].upper()}")

            if result['increasing_trends']:
                print("\n\n⚠️  INCREASING TRENDS:")
                print("-" * 60)
                for trend in result['increasing_trends']:
                    print(f"\n  Category: {trend['category']}")
                    print(f"  Recurrence Rate: {trend['recurrence_rate']} incidents/day")
                    print(f"  First Half: {trend['first_half']} incidents")
                    print(f"  Second Half: {trend['second_half']} incidents")
                    print(f"  Increase: {trend['increase_pct']}%")

            if result['recommendations']:
                print("\n\n📋 RECOMMENDATIONS:")
                print("-" * 60)
                for i, rec in enumerate(result['recommendations'], 1):
                    print(f"\n{i}. [{rec['priority']}] {rec['category']}")
                    print(f"   Reason: {rec['reason']}")
                    print(f"   Countermeasures:")
                    for measure in rec['countermeasures']:
                        print(f"     • {measure}")

            print("\n" + "="*60 + "\n")

    elif args.category:
        # Single category analysis
        if args.compare:
            result = IncidentPatternAnalyzer.compare_periods(
                category=args.category,
                current_days=args.days,
                previous_days=args.days,
                project_id=args.project_id
            )
        else:
            result = IncidentPatternAnalyzer.analyze_category_patterns(
                category=args.category,
                days=args.days,
                project_id=args.project_id
            )

        if args.output == 'json':
            print(json.dumps(result, indent=2, default=str))
        else:
            if args.compare:
                print("\n" + "="*60)
                print(f"PERIOD COMPARISON: {result['category']}")
                print("="*60)
                print(f"\nCurrent Period ({result['current_period']['days']} days):")
                print(f"  Count: {result['current_period']['count']}")
                print(f"  Rate: {result['current_period']['rate']} incidents/day")
                print(f"\nPrevious Period ({result['previous_period']['days']} days):")
                print(f"  Count: {result['previous_period']['count']}")
                print(f"  Rate: {result['previous_period']['rate']} incidents/day")
                print(f"\nChange: {result['change_pct']:+.1f}%")
                print(f"Status: {result['status']}")
                print("\n" + "="*60 + "\n")
            else:
                print("\n" + "="*60)
                print(f"INCIDENT PATTERN ANALYSIS: {result['category']}")
                print("="*60)
                print(f"\nAnalysis Period: {result['analysis_period_days']} days")
                print(f"Total Incidents: {result['incident_count']}")
                print(f"Recurrence Rate: {result['recurrence_stats']['recurrence_rate']} incidents/day")
                print(f"Trend: {result['recurrence_stats']['trend'].upper()}")
                print(f"Resolution Rate: {result['resolution_rate']}%")

                print(f"\nSeverity Distribution:")
                for severity, count in result['severity_distribution'].items():
                    print(f"  {severity}: {count}")

                print(f"\nRecommended Countermeasures:")
                for i, measure in enumerate(result['countermeasures'], 1):
                    print(f"  {i}. {measure}")

                print("\n" + "="*60 + "\n")

    else:
        # All categories analysis
        results = IncidentPatternAnalyzer.analyze_all_categories(
            days=args.days,
            project_id=args.project_id
        )

        if args.output == 'json':
            print(json.dumps(results, indent=2, default=str))
        else:
            print("\n" + "="*60)
            print("INCIDENT PATTERN ANALYSIS - ALL CATEGORIES")
            print("="*60)
            print(f"\nAnalysis Period: {args.days} days\n")

            if not results:
                print("No incidents found in the specified period.")
            else:
                for result in results:
                    print(f"\n{result['category']}")
                    print("-" * 60)
                    print(f"  Incidents: {result['incident_count']}")
                    print(f"  Recurrence Rate: {result['recurrence_stats']['recurrence_rate']} incidents/day")
                    print(f"  Trend: {result['recurrence_stats']['trend'].upper()}")
                    print(f"  Resolution Rate: {result['resolution_rate']}%")

            print("\n" + "="*60 + "\n")


if __name__ == '__main__':
    main()
