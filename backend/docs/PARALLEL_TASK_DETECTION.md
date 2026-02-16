# Parallel Task Detection Implementation (TASK_924)

## Overview

This document describes the parallel task detection logic implemented in TASK_924 (ORDER_090). This feature identifies QUEUED tasks within an ORDER that can be launched simultaneously based on:

1. **No dependency conflicts**: All dependencies are COMPLETED or DONE
2. **No file lock conflicts**: No overlapping target_files with other parallel tasks
3. **Task status is QUEUED**: Only QUEUED tasks are considered

This implementation integrates logic from:
- **ORDER_076**: File lock management system
- **ORDER_078**: Dependency-based auto-trigger logic

## Implementation Details

### Core Module

**Location**: `backend/worker/parallel_detector.py`

**Key Class**: `ParallelTaskDetector`

### Main Functions

#### 1. `find_parallel_launchable_tasks()`

Finds all QUEUED tasks in an ORDER that can be launched in parallel.

```python
from worker.parallel_detector import ParallelTaskDetector

tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
    project_id="ai_pm_manager",
    order_id="ORDER_090",
    max_tasks=10
)

# Returns: List of task dicts
# [
#   {
#     "id": "TASK_740",
#     "title": "タスクA",
#     "priority": "P0",
#     "status": "QUEUED",
#     "target_files": '["file_a.py"]',
#     "created_at": "2026-02-06 10:00:00"
#   },
#   ...
# ]
```

**Features**:
- Returns tasks sorted by priority (P0 > P1 > P2 > P3) and creation time
- Ensures no file conflicts among returned tasks
- Respects max_tasks limit
- Only returns tasks whose dependencies are COMPLETED or DONE

#### 2. `get_parallel_launch_summary()`

Provides a comprehensive summary of parallel launchable tasks with blocking reasons.

```python
summary = ParallelTaskDetector.get_parallel_launch_summary(
    project_id="ai_pm_manager",
    order_id="ORDER_090",
    max_tasks=10
)

# Returns: Summary dict
# {
#   "project_id": "ai_pm_manager",
#   "order_id": "ORDER_090",
#   "total_queued": 10,
#   "launchable_count": 5,
#   "launchable_tasks": ["TASK_740", "TASK_741", ...],
#   "blocked_by_dependencies": ["TASK_745"],
#   "blocked_by_locks": ["TASK_746", "TASK_747"],
#   "max_tasks": 10
# }
```

**Categories**:
- `launchable_tasks`: Tasks that can be launched immediately
- `blocked_by_dependencies`: Tasks waiting for dependencies to complete
- `blocked_by_locks`: Tasks blocked by file locks or file conflicts

### Detection Algorithm

The detection algorithm works as follows:

```
1. Query all QUEUED tasks in ORDER
   └─> Sorted by priority (P0 > P1 > P2) and created_at ASC

2. For each QUEUED task (in priority order):
   a. Check dependencies
      └─> All depends_on_task_id must have status IN ('COMPLETED', 'DONE')

   b. Check existing file locks
      └─> Query file_locks table for conflicts

   c. Check file conflicts with parallel tasks
      └─> Check target_files against already selected tasks

   d. If all checks pass:
      └─> Add to launchable list
      └─> Add task's target_files to locked files set

   e. If max_tasks reached:
      └─> Stop iteration

3. Return launchable tasks
```

### Integration Points

#### File Lock System (ORDER_076)

Uses `FileLockManager` from `utils/file_lock.py`:

```python
from utils.file_lock import FileLockManager

# Check if task can start (no existing file locks)
can_start, blocking_tasks = FileLockManager.can_task_start(project_id, task_id)

# Parse target_files JSON
target_files = FileLockManager.parse_target_files(target_files_json)
```

#### Dependency System (ORDER_078)

Uses dependency checking logic from `utils/task_unblock.py`:

```python
# Check if all dependencies are COMPLETED or DONE
pending_deps = fetch_one(
    conn,
    """
    SELECT COUNT(*) as count
    FROM task_dependencies td
    JOIN tasks t ON td.depends_on_task_id = t.id
    WHERE td.task_id = ? AND td.project_id = ?
    AND t.status NOT IN ('COMPLETED', 'DONE')
    """,
    (task_id, project_id)
)

is_ready = (pending_deps is None or pending_deps["count"] == 0)
```

## Command-Line Interface

### Basic Usage

```bash
# Detect parallel launchable tasks
python -m worker.parallel_launch ai_pm_manager ORDER_090

# With max tasks limit
python -m worker.parallel_launch ai_pm_manager ORDER_090 --max-tasks 5

# Show summary with blocking reasons
python -m worker.parallel_launch ai_pm_manager ORDER_090 --summary

# JSON output
python -m worker.parallel_launch ai_pm_manager ORDER_090 --json
```

### Example Output

**Table Format**:
```
================================================================================
Parallel Launchable Tasks (max: 10)
================================================================================

  5件のタスクが並列起動可能です:

  --------------------------------------------------------------------------------
  Task ID         Priority   Title
  --------------------------------------------------------------------------------
  TASK_740        P0         タスクA - ファイルA処理
  TASK_741        P0         タスクB - ファイルB処理
  TASK_742        P1         タスクC - ファイルC処理
  TASK_743        P1         タスクD - ファイルD処理
  TASK_744        P2         タスクE - 設定ファイル更新
  --------------------------------------------------------------------------------

【対象ファイル】(4ファイル)
  - file_a.py
  - file_b.py
  - file_c.py
  - config.json

================================================================================
```

**Summary Format**:
```
================================================================================
Parallel Launch Summary - ORDER_090
================================================================================

Project: ai_pm_manager
ORDER: ORDER_090
Max Tasks: 10

【タスク統計】
  Total QUEUED: 10
  Parallel Launchable: 5
  Blocked by Dependencies: 2
  Blocked by File Locks: 3

【並列起動可能タスク】(5件)
  - TASK_740
  - TASK_741
  - TASK_742
  - TASK_743
  - TASK_744

【依存関係でブロック】(2件)
  - TASK_745
  - TASK_746

【ファイルロックでブロック】(3件)
  - TASK_747
  - TASK_748
  - TASK_749

================================================================================
```

## Testing

### Test Suite

**Location**: `backend/tests/test_parallel_detector.py`

**Run Tests**:
```bash
cd backend
python tests/test_parallel_detector.py
```

**Test Coverage**:
1. Basic parallel task detection
2. File conflict detection
3. Dependency checking
4. Max tasks limit
5. Priority ordering
6. Summary generation
7. Blocking reason categorization

**Test Output**:
```
================================================================================
Parallel Task Detector Test Suite
================================================================================

[Test 1] Find parallel launchable tasks (max=10)
✓ Expected tasks found: {'TASK_P001', 'TASK_P002', 'TASK_P003', 'TASK_P004', 'TASK_P008'}
✓ No file conflicts among launchable tasks
✓ Max tasks limit respected
✓ Priority ordering correct (P0 > P1 > P2)

[Test 2] Parallel launch summary
✓ Total QUEUED (7) >= Launchable (5)

================================================================================
ALL TESTS COMPLETED
================================================================================
```

## Usage Examples

### Example 1: Detect Parallel Tasks

```python
from worker.parallel_detector import ParallelTaskDetector

# Find up to 10 parallel launchable tasks
tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
    project_id="ai_pm_manager",
    order_id="ORDER_090",
    max_tasks=10
)

print(f"Found {len(tasks)} launchable tasks")
for task in tasks:
    print(f"  {task['id']}: {task['title']} (priority={task['priority']})")
```

### Example 2: Get Summary

```python
from worker.parallel_detector import ParallelTaskDetector

# Get comprehensive summary
summary = ParallelTaskDetector.get_parallel_launch_summary(
    project_id="ai_pm_manager",
    order_id="ORDER_090",
    max_tasks=10
)

print(f"Total QUEUED: {summary['total_queued']}")
print(f"Launchable: {summary['launchable_count']}")
print(f"Blocked by deps: {len(summary['blocked_by_dependencies'])}")
print(f"Blocked by locks: {len(summary['blocked_by_locks'])}")
```

### Example 3: Integration with Worker Loop

```python
from worker.parallel_detector import ParallelTaskDetector
from worker.execute_task import WorkerExecutor

# Detect parallel tasks
tasks = ParallelTaskDetector.find_parallel_launchable_tasks(
    project_id="ai_pm_manager",
    order_id="ORDER_090",
    max_tasks=5
)

# Launch each task in parallel (conceptual - actual implementation in TASK_925)
for task in tasks:
    print(f"Launching {task['id']} in parallel...")
    # Future: Launch worker session here
```

## Key Features

### 1. Priority-Based Ordering

Tasks are always returned in priority order:
- P0 tasks before P1 tasks
- P1 tasks before P2 tasks
- Within same priority, earlier created tasks first

### 2. File Conflict Prevention

The detector ensures no file conflicts among returned tasks:
- Tracks files used by already-selected tasks
- Checks each candidate task's target_files against locked files
- Skips tasks with file conflicts

### 3. Dependency Awareness

Only tasks with all dependencies satisfied are returned:
- Checks task_dependencies table
- Requires all depends_on_task_id to have status IN ('COMPLETED', 'DONE')
- DONE tasks are considered complete for dependency purposes

### 4. Max Tasks Limit

Respects max_tasks parameter to prevent overwhelming parallel execution:
- Default: 10 tasks
- Stops iteration once limit reached
- Ensures highest priority tasks are selected first

## Architecture Decisions

### Why DONE Tasks Unblock Dependencies

DONE tasks have completed their work output, even if awaiting review approval. Dependent tasks can proceed with the completed work without waiting for review:

```python
# This allows parallel progress:
TASK_A (DONE) → TASK_B (can start)

# Instead of forcing sequential:
TASK_A (DONE) → [wait for review] → TASK_A (COMPLETED) → TASK_B (can start)
```

### Why File Conflicts Are Checked Twice

1. **Against existing IN_PROGRESS tasks**: Prevents conflicts with currently running tasks
2. **Against other parallel candidates**: Prevents conflicts among tasks being launched together

This two-level check ensures:
- No interference with running work
- No interference among parallel launches

### Why Priority Ordering Matters

Priority ordering ensures:
- Critical P0 tasks get resources first
- Less important P2 tasks don't block P0 tasks
- Consistent, predictable task selection

## Performance Considerations

### Query Optimization

- Uses indexed queries on task_dependencies
- Uses indexed queries on file_locks
- Sorts in SQL for efficiency
- Single pass through QUEUED tasks

### Scalability

For large ORDERs (>100 QUEUED tasks):
- Max tasks limit prevents excessive processing
- Early termination once limit reached
- File conflict check is O(n) per task

### Memory Usage

- Maintains set of locked files (grows with selected tasks)
- Task list size bounded by max_tasks parameter

## Future Enhancements

Potential improvements for TASK_925 and beyond:

1. **Parallel Worker Launch**: Actually launch multiple Worker sessions
2. **Dynamic Max Tasks**: Adjust based on system resources
3. **Priority Boost**: Increase priority of long-waiting tasks
4. **Cross-ORDER Detection**: Detect parallel tasks across multiple ORDERs
5. **Conflict Resolution**: Suggest task ordering to maximize parallelism

## Troubleshooting

### No Tasks Detected

**Symptoms**: `find_parallel_launchable_tasks()` returns empty list

**Possible Causes**:
1. No QUEUED tasks in ORDER
2. All QUEUED tasks have pending dependencies
3. All QUEUED tasks conflict with IN_PROGRESS file locks
4. All QUEUED tasks conflict with each other's files

**Debug**:
```python
# Get summary to see blocking reasons
summary = ParallelTaskDetector.get_parallel_launch_summary(
    project_id, order_id
)
print(f"Blocked by deps: {summary['blocked_by_dependencies']}")
print(f"Blocked by locks: {summary['blocked_by_locks']}")
```

### File Conflicts Not Detected

**Symptoms**: Tasks with same target_files both returned

**Check**:
```python
from utils.file_lock import FileLockManager

# Verify target_files format
target_files = FileLockManager.parse_target_files(task["target_files"])
print(f"Parsed files: {target_files}")

# Should be JSON array: '["file1.py", "file2.py"]'
```

### Dependencies Not Recognized

**Symptoms**: Tasks returned despite pending dependencies

**Check**:
```sql
-- Check task_dependencies table
SELECT * FROM task_dependencies WHERE task_id = 'TASK_XXX';

-- Check dependency status
SELECT t.id, t.status
FROM task_dependencies td
JOIN tasks t ON td.depends_on_task_id = t.id
WHERE td.task_id = 'TASK_XXX';
```

## Related Documentation

- [File Lock System (ORDER_076)](./FILE_LOCKS.md)
- [Successor Auto-Trigger (ORDER_078)](./SUCCESSOR_AUTO_TRIGGER.md)
- [Worker Parallel Launch (TASK_925)](./WORKER_PARALLEL_LAUNCH.md) *(future)*

---

**Implementation Date**: 2026-02-06
**Task**: TASK_924
**Developer**: Worker (AI)
**Status**: ✅ Completed
