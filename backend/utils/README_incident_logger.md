# Incident Logger Utility

## Overview

The `incident_logger.py` utility module provides functions for tracking and analyzing system incidents and failure patterns in the AI PM Framework.

## Features

- **Create incidents**: Record new incidents with detailed information
- **Query incidents**: Filter by category, severity, project, order, or task
- **Update incidents**: Add root cause and resolution details
- **Generate summaries**: Get statistics and trends across incidents
- **Calculate recurrence rates**: Analyze failure patterns over time

## Usage

### Basic Usage

```python
from utils.incident_logger import IncidentLogger, log_incident

# Create an incident (simple)
incident_id = log_incident(
    category='WORKER_FAILURE',
    description='Worker process crashed during task execution',
    severity='HIGH',
    project_id='ai_pm_manager',
    task_id='TASK_917'
)

# Create an incident (detailed)
incident_id = IncidentLogger.create_incident(
    category='MIGRATION_ERROR',
    description='Schema migration failed due to constraint violation',
    severity='HIGH',
    project_id='ai_pm_manager',
    order_id='ORDER_088',
    root_cause='Missing foreign key constraint',
    resolution='Added proper FK constraint in migration script',
    affected_records=['TASK_917', 'TASK_918']
)
```

### Update Incidents

```python
# Add root cause and resolution after analysis
IncidentLogger.update_incident(
    incident_id='INC_001',
    root_cause='Database lock timeout due to concurrent access',
    resolution='Implemented retry logic with exponential backoff'
)
```

### Query Incidents

```python
# Get incident by ID
incident = IncidentLogger.get_incident('INC_001')

# Get incidents by category
incidents = IncidentLogger.get_incidents_by_category('MIGRATION_ERROR', limit=10)

# Get incidents by severity
high_incidents = IncidentLogger.get_incidents_by_severity('HIGH')

# Get incidents by project/order/task
project_incidents = IncidentLogger.get_incidents_by_project('ai_pm_manager')
order_incidents = IncidentLogger.get_incidents_by_order('ORDER_088')
task_incidents = IncidentLogger.get_incidents_by_task('TASK_917')
```

### Generate Summaries

```python
# Get incident summary with statistics
summary = IncidentLogger.get_incidents_summary(
    start_date='2026-01-01T00:00:00',
    end_date='2026-02-01T00:00:00',
    project_id='ai_pm_manager'
)

print(f"Total incidents: {summary['total']}")
print(f"By category: {summary['by_category']}")
print(f"By severity: {summary['by_severity']}")
print(f"Recent high severity: {len(summary['recent_high'])}")
```

### Calculate Recurrence Rates

```python
# Analyze failure patterns
stats = IncidentLogger.get_recurrence_rate(
    category='WORKER_FAILURE',
    days=30,
    project_id='ai_pm_manager'
)

print(f"Total incidents: {stats['total_incidents']}")
print(f"Recurrence rate: {stats['recurrence_rate']} per day")
print(f"Trend: {stats['trend']}")  # 'increasing', 'decreasing', or 'stable'
```

## Incident Categories

The following incident categories are supported:

- `MIGRATION_ERROR`: Database schema migration failures
- `CASCADE_DELETE`: Unexpected cascade delete operations
- `CONSTRAINT_VIOLATION`: Database constraint violations
- `DATA_INTEGRITY`: Data consistency issues
- `CONCURRENCY_ERROR`: Race conditions and concurrent access issues
- `FILE_LOCK_ERROR`: File locking failures
- `WORKER_FAILURE`: Worker process crashes or failures
- `REVIEW_ERROR`: Review process failures
- `SYSTEM_ERROR`: General system errors
- `OTHER`: Other unclassified incidents

## Severity Levels

- `HIGH`: Critical incidents requiring immediate attention
- `MEDIUM`: Moderate incidents that should be addressed soon
- `LOW`: Minor incidents for tracking and analysis

## Database Schema

The `incidents` table includes:

- `incident_id`: Primary key (e.g., INC_001)
- `timestamp`: When the incident occurred
- `project_id`, `order_id`, `task_id`: Related entities (optional)
- `category`: Incident category
- `severity`: Severity level
- `description`: Incident description
- `root_cause`: Root cause analysis (optional)
- `resolution`: How it was resolved (optional)
- `affected_records`: JSON array of affected record IDs (optional)

## Integration Examples

### In Exception Handlers

```python
try:
    # Execute migration
    run_migration()
except Exception as e:
    # Log incident
    log_incident(
        category='MIGRATION_ERROR',
        description=f'Migration failed: {str(e)}',
        severity='HIGH',
        project_id=project_id,
        order_id=order_id,
        root_cause='Database lock timeout',
        affected_records=['schema.sql']
    )
    raise
```

### In Pipeline Scripts

```python
from utils.incident_logger import log_incident

def process_order(order_id):
    try:
        # Process order
        execute_tasks(order_id)
    except WorkerFailure as e:
        # Record incident
        incident_id = log_incident(
            category='WORKER_FAILURE',
            description=f'Worker failed: {e.worker_id}',
            severity='MEDIUM',
            order_id=order_id,
            task_id=e.task_id
        )
        # Handle failure...
```

## Testing

Run the test suite:

```bash
python backend/tests/test_incident_logger.py
```

## Migration

To create the `incidents` table:

```bash
python backend/migrations/add_incidents_table.py
```

## Notes

- Foreign key fields (`project_id`, `order_id`, `task_id`) are nullable for flexibility
- No foreign key constraints are enforced (due to composite PK issues in related tables)
- The fields are for tracking and analysis purposes only
- Incident IDs are auto-generated in INC_XXX format
- `affected_records` stores JSON array of affected entity IDs
