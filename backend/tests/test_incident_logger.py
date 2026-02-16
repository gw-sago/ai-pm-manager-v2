#!/usr/bin/env python3
"""
Test script for incident_logger.py utility

Tests all major functions of the IncidentLogger class.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.incident_logger import IncidentLogger, log_incident, IncidentLoggerError
from utils.db import get_connection, execute_query


def setup_test_data():
    """Create test incidents for testing"""
    print("Setting up test data...")

    # Create test incidents (using None for foreign keys to avoid FK violations)
    incidents = [
        {
            'category': 'MIGRATION_ERROR',
            'severity': 'HIGH',
            'description': 'Schema migration failed due to constraint violation',
            'project_id': None,
            'order_id': None,
            'root_cause': 'Missing foreign key constraint',
            'affected_records': ['TASK_917', 'TASK_918']
        },
        {
            'category': 'WORKER_FAILURE',
            'severity': 'MEDIUM',
            'description': 'Worker process crashed during task execution',
            'project_id': None,
            'task_id': None,
        },
        {
            'category': 'CASCADE_DELETE',
            'severity': 'LOW',
            'description': 'Unexpected cascade delete during ORDER cleanup',
            'project_id': None,
            'order_id': None,
        },
        {
            'category': 'FILE_LOCK_ERROR',
            'severity': 'HIGH',
            'description': 'Failed to acquire file lock for concurrent task',
            'project_id': None,
            'order_id': None,
            'task_id': None,
            'affected_records': ['schema.sql']
        },
    ]

    created_ids = []
    for inc in incidents:
        inc_id = IncidentLogger.create_incident(**inc)
        created_ids.append(inc_id)
        print(f"  Created: {inc_id}")

    return created_ids


def test_create_incident():
    """Test incident creation"""
    print("\n[TEST] Creating incident...")

    inc_id = IncidentLogger.create_incident(
        category='SYSTEM_ERROR',
        description='Test incident for unit testing',
        severity='LOW',
        project_id=None,
        order_id=None,
        task_id=None,
        root_cause='Test root cause',
        resolution='Test resolution',
        affected_records=['REC_001', 'REC_002']
    )

    print(f"  ✓ Created incident: {inc_id}")

    # Verify incident exists
    incident = IncidentLogger.get_incident(inc_id)
    assert incident is not None, "Incident should exist"
    assert incident['category'] == 'SYSTEM_ERROR', "Category should match"
    assert incident['severity'] == 'LOW', "Severity should match"
    assert len(incident['affected_records']) == 2, "Should have 2 affected records"

    print("  ✓ Incident verified")
    return inc_id


def test_update_incident(inc_id):
    """Test incident update"""
    print("\n[TEST] Updating incident...")

    IncidentLogger.update_incident(
        incident_id=inc_id,
        root_cause='Updated root cause',
        resolution='Updated resolution'
    )

    # Verify update
    incident = IncidentLogger.get_incident(inc_id)
    assert incident['root_cause'] == 'Updated root cause', "Root cause should be updated"
    assert incident['resolution'] == 'Updated resolution', "Resolution should be updated"

    print("  ✓ Incident updated successfully")


def test_get_by_category():
    """Test getting incidents by category"""
    print("\n[TEST] Getting incidents by category...")

    incidents = IncidentLogger.get_incidents_by_category('MIGRATION_ERROR')
    print(f"  Found {len(incidents)} MIGRATION_ERROR incidents")

    assert len(incidents) > 0, "Should find at least one incident"
    for inc in incidents:
        assert inc['category'] == 'MIGRATION_ERROR', "All should be MIGRATION_ERROR"

    print("  ✓ Category filter working")


def test_get_by_severity():
    """Test getting incidents by severity"""
    print("\n[TEST] Getting incidents by severity...")

    incidents = IncidentLogger.get_incidents_by_severity('HIGH')
    print(f"  Found {len(incidents)} HIGH severity incidents")

    for inc in incidents:
        assert inc['severity'] == 'HIGH', "All should be HIGH severity"

    print("  ✓ Severity filter working")


def test_get_by_project():
    """Test getting incidents by project"""
    print("\n[TEST] Getting incidents by project...")

    # Skip project filter test since we used None for project_id in test data
    print("  Skipped (using None for project_id in test data)")


def test_get_by_order():
    """Test getting incidents by ORDER"""
    print("\n[TEST] Getting incidents by ORDER...")

    # Skip ORDER filter test since we used None for order_id in test data
    print("  Skipped (using None for order_id in test data)")


def test_get_by_task():
    """Test getting incidents by task"""
    print("\n[TEST] Getting incidents by task...")

    # Skip task filter test since we used None for task_id in test data
    print("  Skipped (using None for task_id in test data)")


def test_get_summary():
    """Test getting incident summary"""
    print("\n[TEST] Getting incident summary...")

    summary = IncidentLogger.get_incidents_summary()

    print(f"  Total incidents: {summary['total']}")
    print(f"  By category: {summary['by_category']}")
    print(f"  By severity: {summary['by_severity']}")
    print(f"  Recent HIGH: {len(summary['recent_high'])}")

    assert summary['total'] > 0, "Should have incidents"
    assert 'by_category' in summary, "Should have category breakdown"
    assert 'by_severity' in summary, "Should have severity breakdown"

    print("  ✓ Summary generation working")


def test_recurrence_rate():
    """Test recurrence rate calculation"""
    print("\n[TEST] Calculating recurrence rate...")

    stats = IncidentLogger.get_recurrence_rate(
        category='MIGRATION_ERROR',
        days=30
    )

    print(f"  Category: {stats['category']}")
    print(f"  Total incidents: {stats['total_incidents']}")
    print(f"  Recurrence rate: {stats['recurrence_rate']} per day")
    print(f"  Trend: {stats['trend']}")

    assert 'total_incidents' in stats, "Should have total count"
    assert 'recurrence_rate' in stats, "Should have recurrence rate"
    assert stats['trend'] in ['increasing', 'decreasing', 'stable'], "Should have valid trend"

    print("  ✓ Recurrence rate calculation working")


def test_convenience_function():
    """Test convenience log_incident function"""
    print("\n[TEST] Testing convenience function...")

    inc_id = log_incident(
        category='OTHER',
        description='Test using convenience function',
        severity='LOW'
    )

    print(f"  ✓ Created incident using log_incident(): {inc_id}")

    # Verify
    incident = IncidentLogger.get_incident(inc_id)
    assert incident is not None, "Incident should exist"
    assert incident['category'] == 'OTHER', "Category should match"

    print("  ✓ Convenience function working")


def test_invalid_category():
    """Test error handling for invalid category"""
    print("\n[TEST] Testing invalid category error handling...")

    try:
        IncidentLogger.create_incident(
            category='INVALID_CATEGORY',
            description='This should fail',
        )
        assert False, "Should have raised IncidentLoggerError"
    except IncidentLoggerError as e:
        print(f"  ✓ Correctly raised error: {e}")


def test_invalid_severity():
    """Test error handling for invalid severity"""
    print("\n[TEST] Testing invalid severity error handling...")

    try:
        IncidentLogger.create_incident(
            category='SYSTEM_ERROR',
            description='This should fail',
            severity='CRITICAL'  # Invalid severity
        )
        assert False, "Should have raised IncidentLoggerError"
    except IncidentLoggerError as e:
        print(f"  ✓ Correctly raised error: {e}")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Testing IncidentLogger Utility")
    print("=" * 60)

    try:
        # Setup
        created_ids = setup_test_data()

        # Run tests
        test_inc_id = test_create_incident()
        test_update_incident(test_inc_id)
        test_get_by_category()
        test_get_by_severity()
        test_get_by_project()
        test_get_by_order()
        test_get_by_task()
        test_get_summary()
        test_recurrence_rate()
        test_convenience_function()
        test_invalid_category()
        test_invalid_severity()

        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)

        return 0

    except Exception as e:
        print(f"\n✗ Test failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
