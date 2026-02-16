# Database Initialization & Migration Scripts

This directory contains scripts for initializing and migrating the AI PM Manager database.

## Scripts Overview

### 1. `db_init.py` - Database Initialization

Creates a new empty database from the schema template.

**Usage:**
```bash
# Create new database (default location: ../data/aipm.db)
python db_init.py

# Create database at custom location
python db_init.py --db-path /path/to/aipm.db

# Force re-initialization (WARNING: destroys existing data)
python db_init.py --force

# Create empty template file
python db_init.py --template /path/to/template.db
```

**Options:**
- `--db-path PATH`: Database file path (default: `../data/aipm.db`)
- `--schema-path PATH`: Schema file path (default: `../data/schema_v2.sql`)
- `--force`: Force re-initialization (destroys existing data)
- `--template PATH`: Create empty template file at specified path
- `--quiet`: Suppress output messages

**Exit Codes:**
- `0`: Success
- `1`: Error (database already exists, schema not found, or creation failed)

---

### 2. `db_migrate.py` - Database Migration

Migrates existing database from AI_PM project to ai-pm-manager-v2.

**Usage:**
```bash
# Migrate from existing database (with backup)
python db_migrate.py --source D:/your_workspace/AI_PM/data/aipm.db

# Migrate to custom location
python db_migrate.py --source SOURCE_DB --target TARGET_DB

# Dry-run (validation only, no migration)
python db_migrate.py --source SOURCE_DB --dry-run

# Skip backup creation (not recommended)
python db_migrate.py --source SOURCE_DB --skip-backup
```

**Migration Process:**
1. Validates source database schema compatibility
2. Creates backup of source database (default: `../data/backups/`)
3. Creates new database from `schema_v2.sql`
4. Copies data from source to target database
5. Validates data integrity after migration
6. Reports success/failure with detailed statistics

**Options:**
- `--source PATH`: Source database path (required)
- `--target PATH`: Target database path (default: `../data/aipm.db`)
- `--schema-path PATH`: Schema file path (default: `../data/schema_v2.sql`)
- `--backup-dir PATH`: Backup directory (default: `../data/backups`)
- `--skip-backup`: Skip backup creation (not recommended)
- `--dry-run`: Validate only, don't perform migration
- `--quiet`: Suppress output messages

**Exit Codes:**
- `0`: Migration successful
- `1`: Error (validation failed, migration failed, or integrity check failed)

---

### 3. `db_auto_init.py` - Auto Database Initialization

Automatically initializes database on first app startup if it doesn't exist.
Designed to be called from Electron app.

**Usage:**
```bash
# Auto-initialize if needed
python db_auto_init.py

# JSON output (for IPC integration)
python db_auto_init.py --json

# Custom paths
python db_auto_init.py --db-path /path/to/aipm.db --schema-path /path/to/schema.sql
```

**Behavior:**
- If database exists and is valid: Does nothing, returns success
- If database doesn't exist: Creates new database from schema
- If database is corrupted: Reports error

**JSON Output Example:**
```json
{
  "success": true,
  "message": "データベースを初期化しました: ../data/aipm.db",
  "db_path": "../data/aipm.db"
}
```

**Options:**
- `--db-path PATH`: Database file path (default: `../data/aipm.db`)
- `--schema-path PATH`: Schema file path (default: `../data/schema_v2.sql`)
- `--quiet`: Suppress output messages
- `--json`: Output result as JSON (for IPC integration)

**Exit Codes:**
- `0`: Database ready (existing or newly created)
- `1`: Error (initialization failed)

---

### 4. `db_check.py` - Database Health Check

Checks database integrity, schema version, and provides diagnostics.

**Usage:**
```bash
# Auto-initialize if needed
python db_auto_init.py

# JSON output (for IPC integration)
python db_auto_init.py --json

# Custom paths
python db_auto_init.py --db-path /path/to/aipm.db --schema-path /path/to/schema.sql
```

**Behavior:**
- If database exists and is valid: Does nothing, returns success
- If database doesn't exist: Creates new database from schema
- If database is corrupted: Reports error

**JSON Output Example:**
```json
{
  "success": true,
  "message": "データベースを初期化しました: ../data/aipm.db",
  "db_path": "../data/aipm.db"
}
```

**Options:**
- `--db-path PATH`: Database file path (default: `../data/aipm.db`)
- `--schema-path PATH`: Schema file path (default: `../data/schema_v2.sql`)
- `--quiet`: Suppress output messages
- `--json`: Output result as JSON (for IPC integration)

**Exit Codes:**
- `0`: Database ready (existing or newly created)
- `1`: Error (initialization failed)

---

### 4. `db_check.py` - Database Health Check

Checks database integrity, schema version, and provides diagnostics.

**Usage:**
```bash
# Check database health
python db_check.py

# Check custom database
python db_check.py --db-path /path/to/aipm.db

# JSON output (for automation/IPC)
python db_check.py --json
```

**Checks Performed:**
- File exists and is readable
- SQLite integrity check (PRAGMA integrity_check)
- Required tables present (projects, orders, tasks, etc.)
- Foreign keys enabled status
- Table row counts
- Indexes, views, and triggers count
- Schema version information

**JSON Output Example:**
```json
{
  "healthy": true,
  "diagnostics": {
    "exists": true,
    "readable": true,
    "file_size_mb": 2.35,
    "integrity_ok": true,
    "foreign_keys_enabled": true,
    "tables": ["projects", "orders", "tasks", ...],
    "row_counts": {"projects": 5, "orders": 120, "tasks": 450},
    "indexes": 28,
    "views": 4,
    "triggers": 4,
    "schema_version": {
      "version": "001",
      "description": "Initial schema",
      "applied_at": "2026-02-16 10:30:00"
    },
    "errors": []
  }
}
```

**Options:**
- `--db-path PATH`: Database file path (default: `../data/aipm.db`)
- `--json`: Output result as JSON
- `--quiet`: Suppress output messages

**Exit Codes:**
- `0`: Database is healthy
- `1`: Database has errors or is unhealthy

---

## Integration with Electron App

### First-Time Startup (Auto-Initialize)

In your Electron main process, call `db_auto_init.py` before any database operations:

```typescript
// src/main.ts
import { spawn } from 'child_process';
import path from 'path';

async function ensureDatabaseReady(): Promise<boolean> {
  return new Promise((resolve, reject) => {
    const pythonPath = 'python'; // or path to bundled Python
    const scriptPath = path.join(__dirname, '../backend/db_auto_init.py');

    const proc = spawn(pythonPath, [scriptPath, '--json']);

    let stdout = '';
    proc.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    proc.on('close', (code) => {
      if (code === 0) {
        try {
          const result = JSON.parse(stdout);
          console.log('Database ready:', result.message);
          resolve(result.success);
        } catch (e) {
          reject(new Error('Failed to parse JSON output'));
        }
      } else {
        reject(new Error(`Database initialization failed with code ${code}`));
      }
    });
  });
}

// Call on app startup
app.whenReady().then(async () => {
  try {
    await ensureDatabaseReady();
    // Continue with app initialization
    createWindow();
  } catch (error) {
    console.error('Database initialization error:', error);
    dialog.showErrorBox('Database Error', 'Failed to initialize database');
    app.quit();
  }
});
```

### Manual Migration (First-Time User Setup)

Provide a UI option for users to migrate their existing AI_PM database:

```typescript
// IPC handler for migration
ipcMain.handle('migrate-database', async (event, sourcePath: string) => {
  return new Promise((resolve, reject) => {
    const pythonPath = 'python';
    const scriptPath = path.join(__dirname, '../backend/db_migrate.py');

    const proc = spawn(pythonPath, [
      scriptPath,
      '--source', sourcePath,
      '--json'  // Optional: add JSON output to migration script if needed
    ]);

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => {
      stdout += data.toString();
      // Send progress updates to renderer
      event.sender.send('migration-progress', data.toString());
    });

    proc.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    proc.on('close', (code) => {
      if (code === 0) {
        resolve({ success: true, output: stdout });
      } else {
        reject(new Error(`Migration failed: ${stderr}`));
      }
    });
  });
});
```

---

## Testing

### Test Database Initialization

```bash
# Test initialization in tmp directory
cd D:/your_workspace/ai-pm-manager-v2
python backend/db_init.py --db-path tmp/test_aipm.db

# Verify tables were created
sqlite3 tmp/test_aipm.db "SELECT name FROM sqlite_master WHERE type='table';"
```

### Test Migration (Dry-Run)

```bash
# Test migration validation without actually migrating
python backend/db_migrate.py \
  --source D:/your_workspace/AI_PM/data/aipm.db \
  --target tmp/migrated_aipm.db \
  --dry-run
```

### Test Auto-Init

```bash
# Test auto-init with JSON output
python backend/db_auto_init.py --db-path tmp/auto_test.db --json

# Run again to test existing database detection
python backend/db_auto_init.py --db-path tmp/auto_test.db --json
```

---

## Error Handling

All scripts return appropriate exit codes:
- **Exit Code 0**: Success
- **Exit Code 1**: Error

Check exit codes in your integration:

```bash
if python backend/db_auto_init.py; then
  echo "Database ready"
else
  echo "Database initialization failed"
  exit 1
fi
```

---

## File Paths

### Default Paths (Relative to ai-pm-manager-v2/)
- Database: `data/aipm.db`
- Schema: `data/schema_v2.sql`
- Backups: `data/backups/`
- Migrations: `data/migrations/`

### Custom Paths
All scripts accept custom paths via command-line arguments.

---

## Migration Checklist

When migrating from AI_PM to ai-pm-manager-v2:

1. ✅ Verify source database exists and is accessible
2. ✅ Run dry-run migration to validate compatibility
3. ✅ Review validation output (table counts, row counts)
4. ✅ Run actual migration (backup is created automatically)
5. ✅ Verify migration success (integrity check runs automatically)
6. ✅ Test app functionality with migrated database
7. ✅ Keep backup for rollback if needed

---

## Troubleshooting

### "Database already exists" error
- Use `--force` flag to overwrite (WARNING: destroys data)
- Or manually delete existing database file

### "Schema file not found" error
- Verify `data/schema_v2.sql` exists
- Or specify custom path with `--schema-path`

### "Source database validation failed" error
- Check source database is not corrupted
- Verify source database has required tables (projects, orders, tasks, etc.)
- Check source database is not locked by another process

### Migration data integrity check fails
- Review migration output for specific table mismatches
- Check for foreign key constraint violations
- Verify source database consistency before migration

---

## Notes

- **Backup Strategy**: Migration script creates timestamped backups automatically
- **Idempotency**: `db_auto_init.py` is safe to call multiple times (skips if DB exists)
- **Transactions**: Migration uses transactions for data integrity
- **Foreign Keys**: Disabled during migration, re-enabled after completion
- **Schema Version**: `schema_version` table tracks applied migrations
