#!/usr/bin/env python3
"""
旧AI PM DB（D:/your_workspace/AI_PM/data/aipm.db）から
V2 DB（data/aipm.db）にプロジェクトデータを移行するスクリプト。

移行対象: ai_pm_manager, AI_PM_PJ
移行先: V2 DB（project_idはそのまま、非アクティブとして登録）
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime

OLD_DB = Path(r"D:/your_workspace/AI_PM/data/aipm.db")
V2_DB = Path(__file__).resolve().parent.parent.parent / "data" / "aipm.db"

PROJECTS_TO_MIGRATE = ["ai_pm_manager", "AI_PM_PJ"]


def dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def migrate():
    if not OLD_DB.exists():
        print(f"ERROR: Old DB not found: {OLD_DB}")
        sys.exit(1)
    if not V2_DB.exists():
        print(f"ERROR: V2 DB not found: {V2_DB}")
        sys.exit(1)

    old = sqlite3.connect(str(OLD_DB))
    old.row_factory = dict_factory

    v2 = sqlite3.connect(str(V2_DB))
    v2.row_factory = dict_factory
    v2.execute("PRAGMA foreign_keys = OFF")  # 移行中はFK無効

    now = datetime.now().isoformat()

    for project_id in PROJECTS_TO_MIGRATE:
        print(f"\n{'='*60}")
        print(f"Migrating: {project_id}")
        print(f"{'='*60}")

        # 1. projects
        proj = old.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not proj:
            print(f"  SKIP: project {project_id} not found in old DB")
            continue

        existing = v2.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if existing:
            print(f"  SKIP: project {project_id} already exists in V2 DB")
            continue

        v2.execute("""
            INSERT INTO projects (id, name, path, status, current_order_id, created_at, updated_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            proj["id"], proj["name"],
            f"PROJECTS/{proj['id']}",
            proj["status"], proj.get("current_order_id"),
            proj["created_at"], now
        ))
        print(f"  projects: 1 inserted (is_active=0)")

        # 2. orders
        orders = old.execute("SELECT * FROM orders WHERE project_id = ?", (project_id,)).fetchall()
        order_count = 0
        for o in orders:
            try:
                v2.execute("""
                    INSERT INTO orders (id, project_id, title, priority, status,
                        started_at, completed_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    o["id"], project_id, o["title"], o["priority"], o["status"],
                    o.get("started_at"), o.get("completed_at"),
                    o["created_at"], o["updated_at"]
                ))
                order_count += 1
            except sqlite3.IntegrityError as e:
                print(f"  SKIP order {o['id']}: {e}")
        print(f"  orders: {order_count} inserted")

        # 3. tasks
        tasks = old.execute("SELECT * FROM tasks WHERE project_id = ?", (project_id,)).fetchall()
        task_count = 0
        for t in tasks:
            try:
                v2.execute("""
                    INSERT INTO tasks (id, order_id, project_id, title, description,
                        status, assignee, priority, recommended_model,
                        reject_count, static_analysis_score, complexity_score,
                        estimated_tokens, actual_tokens, cost_usd,
                        is_destructive_db_change, target_files,
                        started_at, completed_at, reviewed_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    t["id"], t["order_id"], project_id, t["title"], t.get("description"),
                    t["status"], t.get("assignee"), t.get("priority", "P1"),
                    t.get("recommended_model"),
                    t.get("reject_count", 0),
                    t.get("static_analysis_score"),
                    t.get("complexity_score"),
                    t.get("estimated_tokens"),
                    t.get("actual_tokens"),
                    t.get("cost_usd"),
                    t.get("is_destructive_db_change", 0),
                    t.get("target_files"),
                    t.get("started_at"), t.get("completed_at"),
                    t.get("reviewed_at"),
                    t["created_at"], t["updated_at"]
                ))
                task_count += 1
            except sqlite3.IntegrityError as e:
                print(f"  SKIP task {t['id']}: {e}")
        print(f"  tasks: {task_count} inserted")

        # 4. task_dependencies
        deps = old.execute("SELECT * FROM task_dependencies WHERE project_id = ?", (project_id,)).fetchall()
        dep_count = 0
        for d in deps:
            try:
                v2.execute("""
                    INSERT INTO task_dependencies (task_id, depends_on_task_id, project_id, created_at)
                    VALUES (?, ?, ?, ?)
                """, (d["task_id"], d["depends_on_task_id"], project_id, d.get("created_at", now)))
                dep_count += 1
            except sqlite3.IntegrityError as e:
                pass  # skip duplicates silently
        print(f"  task_dependencies: {dep_count} inserted")

        # 5. backlog_items
        backlogs = old.execute("SELECT * FROM backlog_items WHERE project_id = ?", (project_id,)).fetchall()
        bl_count = 0
        for b in backlogs:
            try:
                v2.execute("""
                    INSERT INTO backlog_items (id, project_id, title, description,
                        priority, status, related_order_id, sort_order,
                        created_at, completed_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    b["id"], project_id, b["title"], b.get("description"),
                    b.get("priority", "Medium"), b.get("status", "TODO"),
                    b.get("related_order_id"),
                    b.get("sort_order", 0),
                    b["created_at"], b.get("completed_at"), b["updated_at"]
                ))
                bl_count += 1
            except sqlite3.IntegrityError as e:
                print(f"  SKIP backlog {b['id']}: {e}")
        print(f"  backlog_items: {bl_count} inserted")

        # 6. change_history
        history = old.execute("SELECT * FROM change_history WHERE project_id = ?", (project_id,)).fetchall()
        hist_count = 0
        for h in history:
            try:
                v2.execute("""
                    INSERT INTO change_history (entity_type, entity_id, project_id,
                        field_name, old_value, new_value, changed_by, change_reason, changed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    h["entity_type"], h["entity_id"], project_id,
                    h.get("field_name"), h.get("old_value"), h.get("new_value"),
                    h.get("changed_by"), h.get("change_reason"), h.get("changed_at")
                ))
                hist_count += 1
            except sqlite3.IntegrityError:
                pass
        print(f"  change_history: {hist_count} inserted")

        # 7. escalations
        escs = old.execute("SELECT * FROM escalations WHERE project_id = ?", (project_id,)).fetchall()
        esc_count = 0
        for e in escs:
            try:
                v2.execute("""
                    INSERT INTO escalations (task_id, project_id, title, description,
                        status, resolution, created_at, resolved_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    e["task_id"], project_id, e["title"], e.get("description"),
                    e["status"], e.get("resolution"), e["created_at"], e.get("resolved_at")
                ))
                esc_count += 1
            except sqlite3.IntegrityError:
                pass
        print(f"  escalations: {esc_count} inserted")

        # 8. bugs
        bugs = old.execute("SELECT * FROM bugs WHERE project_id = ?", (project_id,)).fetchall()
        bug_count = 0
        for b in bugs:
            try:
                v2.execute("""
                    INSERT INTO bugs (id, project_id, title, description, pattern_type,
                        severity, status, solution, related_files, tags,
                        occurrence_count, effectiveness_score, total_injections,
                        related_failures, last_occurred_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    b["id"], project_id, b["title"], b.get("description"),
                    b.get("pattern_type"), b.get("severity"), b.get("status"),
                    b.get("solution"), b.get("related_files"), b.get("tags"),
                    b.get("occurrence_count", 0),
                    b.get("effectiveness_score"),
                    b.get("total_injections"),
                    b.get("related_failures"),
                    b.get("last_occurred_at"),
                    b["created_at"], b["updated_at"]
                ))
                bug_count += 1
            except sqlite3.IntegrityError as e:
                print(f"  SKIP bug {b['id']}: {e}")
        print(f"  bugs: {bug_count} inserted")

    v2.commit()
    v2.execute("PRAGMA foreign_keys = ON")

    # 最終確認
    print(f"\n{'='*60}")
    print("Migration Summary")
    print(f"{'='*60}")
    for pid in PROJECTS_TO_MIGRATE:
        orders = v2.execute("SELECT COUNT(*) as c FROM orders WHERE project_id = ?", (pid,)).fetchone()
        tasks = v2.execute("SELECT COUNT(*) as c FROM tasks WHERE project_id = ?", (pid,)).fetchone()
        backlogs = v2.execute("SELECT COUNT(*) as c FROM backlog_items WHERE project_id = ?", (pid,)).fetchone()
        proj = v2.execute("SELECT is_active FROM projects WHERE id = ?", (pid,)).fetchone()
        print(f"  {pid}: orders={orders['c']}, tasks={tasks['c']}, backlogs={backlogs['c']}, is_active={proj['is_active'] if proj else 'N/A'}")

    v2_proj = v2.execute("SELECT id, is_active FROM projects ORDER BY id").fetchall()
    print(f"\nAll projects in V2 DB:")
    for p in v2_proj:
        status = "active" if p["is_active"] else "inactive"
        print(f"  {p['id']} ({status})")

    old.close()
    v2.close()
    print("\nDone!")


if __name__ == "__main__":
    migrate()
