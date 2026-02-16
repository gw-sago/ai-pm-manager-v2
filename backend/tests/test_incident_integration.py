#!/usr/bin/env python3
"""
Test: Incident Logger Integration Test

Verify that incident logging is properly integrated into pipeline scripts.
"""

import sys
from pathlib import Path

# Add parent directory to path
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.incident_logger import IncidentLogger, log_incident
from utils.db import get_connection, execute_query


def test_incident_creation():
    """Test basic incident creation"""
    print("Testing incident creation...")

    incident_id = log_incident(
        category='WORKER_FAILURE',
        description='Test incident for integration testing',
        severity='LOW',
        project_id='test_project',
        order_id='ORDER_999',
        task_id='TASK_9999'
    )

    print(f"✓ Created incident: {incident_id}")

    # Verify it was created
    incident = IncidentLogger.get_incident(incident_id)
    assert incident is not None, "Incident not found"
    assert incident['category'] == 'WORKER_FAILURE'
    assert incident['description'] == 'Test incident for integration testing'
    print("✓ Incident verified in database")

    return incident_id


def test_incident_categories():
    """Test different incident categories"""
    print("\nTesting incident categories...")

    categories = [
        ('MIGRATION_ERROR', 'Migration test'),
        ('CASCADE_DELETE', 'Cascade delete test'),
        ('CONSTRAINT_VIOLATION', 'Constraint violation test'),
        ('DATA_INTEGRITY', 'Data integrity test'),
        ('CONCURRENCY_ERROR', 'Concurrency error test'),
        ('WORKER_FAILURE', 'Worker failure test'),
        ('SYSTEM_ERROR', 'System error test'),
    ]

    for category, description in categories:
        incident_id = log_incident(
            category=category,
            description=description,
            severity='LOW'
        )
        print(f"✓ Created {category}: {incident_id}")


def test_incident_query():
    """Test incident querying"""
    print("\nTesting incident queries...")

    # Get by category
    incidents = IncidentLogger.get_incidents_by_category('WORKER_FAILURE', limit=5)
    print(f"✓ Found {len(incidents)} WORKER_FAILURE incidents")

    # Get summary
    summary = IncidentLogger.get_incidents_summary()
    print(f"✓ Total incidents: {summary['total']}")
    print(f"✓ By category: {summary['by_category']}")
    print(f"✓ By severity: {summary['by_severity']}")


def test_cleanup():
    """Clean up test incidents"""
    print("\nCleaning up test incidents...")

    conn = get_connection()
    try:
        # Delete test incidents
        execute_query(
            conn,
            "DELETE FROM incidents WHERE project_id = 'test_project' OR description LIKE '%test%'"
        )
        print("✓ Test incidents cleaned up")
    finally:
        conn.close()


def main():
    """Run all tests"""
    print("=== Incident Logger Integration Test ===\n")

    try:
        test_incident_creation()
        test_incident_categories()
        test_incident_query()
        test_cleanup()

        print("\n=== All tests passed ===")
        return 0

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
