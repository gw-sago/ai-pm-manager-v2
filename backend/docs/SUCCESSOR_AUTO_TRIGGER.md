# Successor Task Auto-Trigger Implementation

## Overview

This document describes the successor task auto-trigger functionality implemented in TASK_738. This feature automatically identifies and triggers successor tasks when their dependencies are completed and approved.

## Implementation Details

### Location

**Primary Implementation:**
- `backend/worker/execute_task.py:816-866` - `_step_check_successor_tasks()` method
- `backend/utils/task_unblock.py:173-218` - `check_successor_dependencies()` method
- `backend/utils/task_unblock.py:132-171` - `find_successor_tasks()` method

**Test Suite:**
- `backend/tests/test_successor_auto_trigger.py` - Comprehensive test suite

### Trigger Point

The successor auto-trigger logic is executed after a task receives an APPROVE verdict from review:

```python
# execute_task.py:206-208
if verdict == "APPROVE":
    self._step_check_successor_tasks()
```

This ensures that successor tasks are only triggered when their dependencies are **fully completed** (not just DONE, but APPROVED and COMPLETED).

### Execution Flow

```
1. Task completes work (DONE status)
2. Review process executes (auto-review)
3. Review verdict: APPROVE
   └─> Task status: COMPLETED
   └─> _step_check_successor_tasks() called
       ├─> Find all successor tasks (tasks that depend on this task)
       ├─> Check each successor:
       │   ├─> All dependencies COMPLETED?
       │   └─> File locks available?
       └─> Update BLOCKED → QUEUED for ready tasks
           └─> Log kicked successor tasks
```

### Algorithm

#### Step 1: Find Successor Tasks

```python
successors = TaskUnblocker.find_successor_tasks(project_id, completed_task_id)
```

Finds all tasks that have `completed_task_id` as a dependency in the `task_dependencies` table.

**Query:**
```sql
SELECT DISTINCT t.id, t.title, t.status, t.priority, t.order_id, t.target_files
FROM task_dependencies td
JOIN tasks t ON td.task_id = t.id AND td.project_id = t.project_id
WHERE td.depends_on_task_id = ? AND td.project_id = ?
ORDER BY
    CASE t.priority
        WHEN 'P0' THEN 0
        WHEN 'P1' THEN 1
        WHEN 'P2' THEN 2
        ELSE 3
    END,
    t.created_at ASC
```

#### Step 2: Check Dependencies

```python
ready_tasks = TaskUnblocker.check_successor_dependencies(project_id, completed_task_id)
```

For each successor task, checks:

1. **All dependencies completed?**
   ```python
   TaskUnblocker._check_dependencies_completed(conn, project_id, task_id)
   ```
   Verifies all tasks in `task_dependencies.depends_on_task_id` have status = 'COMPLETED'

2. **File locks available?**
   ```python
   TaskUnblocker._check_file_locks_available(conn, project_id, task_id)
   ```
   Checks if target files are not locked by other IN_PROGRESS tasks

#### Step 3: Update Task Status

```python
for task in ready_tasks:
    updated, new_status = TaskUnblocker.update_task_status_if_unblocked(
        project_id,
        task_id
    )
```

Updates task status from BLOCKED → QUEUED if all conditions are met.

**Only BLOCKED tasks are updated:**
- COMPLETED tasks: no update
- IN_PROGRESS tasks: no update
- QUEUED tasks: no update
- BLOCKED tasks: → QUEUED

#### Step 4: Log Results

```python
if kicked_successors:
    self.results["kicked_successors"] = kicked_successors
    self._log_step(
        "check_successors",
        "success",
        f"{len(kicked_successors)}タスクを自動起動: {', '.join(kicked_successors)}"
    )
```

Logs all kicked successor tasks for audit and debugging.

### Priority Ordering

Successor tasks are evaluated and kicked in priority order:

1. **Priority Level**: P0 > P1 > P2 > P3
2. **Creation Time**: Earlier tasks first (created_at ASC)

This ensures high-priority tasks are triggered before lower-priority ones.

### Example Scenario

**Dependency Graph:**
```
TASK_723 (P0) → TASK_724 (P1), TASK_725 (P1)
```

**Execution:**
1. TASK_723 completes work
2. Review approves → TASK_723 status: COMPLETED
3. Successor check:
   - Find successors: TASK_724, TASK_725
   - TASK_724 dependencies: [TASK_723=COMPLETED] ✓
   - TASK_724 file locks: available ✓
   - TASK_725 dependencies: [TASK_723=COMPLETED] ✓
   - TASK_725 file locks: available ✓
4. Update status:
   - TASK_724: BLOCKED → QUEUED
   - TASK_725: BLOCKED → QUEUED
5. Log: "2タスクを自動起動: TASK_724, TASK_725"

**Result:**
Both TASK_724 and TASK_725 are now QUEUED and ready for Worker execution.

## Integration with Worker Loop

The successor auto-trigger works seamlessly with the Worker loop mode (`--loop`):

```bash
python backend/worker/execute_task.py ai_pm_manager TASK_723 --loop
```

**Flow:**
1. Execute TASK_723
2. Review → APPROVE
3. Kick successors (TASK_724, TASK_725 → QUEUED)
4. Loop finds next QUEUED task → TASK_724
5. Execute TASK_724
6. Loop finds next QUEUED task → TASK_725
7. Execute TASK_725
8. No more QUEUED tasks → loop ends

This enables **automatic cascade execution** of dependent tasks.

## Testing

### Run Tests

```bash
cd backend
python tests/test_successor_auto_trigger.py
```

### Test Coverage

The test suite verifies:
- Finding successor tasks via dependency graph
- Checking dependency completion status
- Checking file lock availability
- Priority-based ordering
- Status update logic (BLOCKED → QUEUED)
- Integration flow simulation

### Test Output

```
================================================================================
ALL TESTS PASSED ✓
================================================================================

CONCLUSION:
  The successor task auto-trigger logic (TASK_738) is fully implemented
  and working correctly. The system successfully:
    1. Identifies successor tasks based on dependencies
    2. Checks if all dependencies are COMPLETED
    3. Checks if file locks are available
    4. Updates BLOCKED → QUEUED for ready tasks
    5. Sorts tasks by priority (P0 > P1 > P2) and task ID
    6. Logs all auto-kick operations
================================================================================
```

## Configuration

### Max Kicks Limit

The successor auto-trigger has no explicit limit, but the file lock auto-kick has a default limit of 10:

```python
# execute_task.py:764
kicked_tasks = TaskUnblocker.auto_kick_unblocked_tasks(
    self.project_id,
    self.order_id,
    exclude_task_id=self.task_id,
    max_kicks=10  # File lock auto-kick limit
)
```

The successor auto-trigger processes all ready successors without limit.

### Logging

Enable verbose logging to see detailed successor check operations:

```bash
python backend/worker/execute_task.py ai_pm_manager TASK_XXX --verbose
```

**Log Output:**
```
[check_successors] start: task=TASK_723
[successor_kick] success: TASK_724: BLOCKED → QUEUED
[successor_kick] success: TASK_725: BLOCKED → QUEUED
[check_successors] success: 2タスクを自動起動: TASK_724, TASK_725
```

## Related Features

### File Lock Auto-Kick

The successor auto-trigger complements the file lock auto-kick feature:

- **Successor Auto-Kick**: Triggered after APPROVE verdict
  - Checks dependency graph
  - Kicks tasks that depend on the completed task

- **File Lock Auto-Kick**: Triggered after file lock release
  - Checks all QUEUED/BLOCKED tasks in same ORDER
  - Kicks tasks that were blocked by file locks

Both features work together to maximize parallel task execution.

### Task Dependency Management

Successor auto-trigger relies on the `task_dependencies` table:

```sql
CREATE TABLE task_dependencies (
    task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    created_at TEXT,
    PRIMARY KEY (task_id, depends_on_task_id, project_id)
);
```

**PM Responsibility:**
When creating tasks in STAFFING.md, specify dependencies using:
```markdown
**depends_on**: TASK_XXX
```

The PM processor will automatically populate the `task_dependencies` table.

## Troubleshooting

### Successors Not Getting Kicked

**Possible Causes:**

1. **Dependencies not completed**
   - Check all dependency tasks have status = 'COMPLETED'
   - Use `/aipm-status` to view dependency graph

2. **File locks held by other tasks**
   - Check `file_locks` table for conflicts
   - Use `FileLockManager.can_task_start()` to debug

3. **Task already QUEUED or IN_PROGRESS**
   - Only BLOCKED tasks are updated to QUEUED
   - Check task status before expecting auto-kick

4. **Review verdict not APPROVE**
   - Successor auto-kick only triggers on APPROVE verdict
   - REJECT or ERROR verdicts don't trigger successor check

### Debug Commands

**Check successor tasks:**
```python
from utils.task_unblock import TaskUnblocker
successors = TaskUnblocker.find_successor_tasks("ai_pm_manager", "TASK_723")
print([s['id'] for s in successors])
```

**Check if successor is ready:**
```python
ready = TaskUnblocker.check_successor_dependencies("ai_pm_manager", "TASK_723")
print([r['id'] for r in ready])
```

**Check dependency status:**
```python
from utils.db import get_connection
conn = get_connection()
is_ready = TaskUnblocker._check_dependencies_completed(conn, "ai_pm_manager", "TASK_724")
print(f"Dependencies completed: {is_ready}")
conn.close()
```

## Performance Considerations

- Successor checks use indexed queries on `task_dependencies` table
- Priority ordering is done in SQL for efficiency
- File lock checks use indexed queries on `file_locks` table
- No limit on number of successors checked (processes all)

For large dependency graphs (>50 successors), consider:
- Batching successor checks
- Async processing of successor updates
- Caching dependency graph

## Future Enhancements

Potential improvements:
1. **Parallel successor execution**: Launch multiple Workers in parallel
2. **Cascade depth limiting**: Prevent infinite dependency chains
3. **Conditional triggering**: Custom rules for when to trigger successors
4. **Cross-ORDER dependencies**: Support dependencies across multiple ORDERs
5. **Priority boost**: Increase priority of unblocked successors

---

**Implementation Date**: 2026-02-06
**Task**: TASK_738
**Developer**: Worker (Auto)
**Status**: ✅ Completed
