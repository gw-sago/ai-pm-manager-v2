# SQL Safety Checker

破壊的SQL操作を検出し、警告を出すユーティリティ。
Worker実行中に危険なDB変更が行われないよう監視します。

## 概要

このモジュールは、PythonコードやSQLスクリプト内の破壊的なデータベース操作を自動検出します。
以下のような操作を検出対象としています:

### 検出対象の破壊的SQL操作

| 操作 | 重要度 | 説明 | 例 |
|------|--------|------|-----|
| DROP TABLE | CRITICAL | テーブル削除 | `DROP TABLE users` |
| ALTER TABLE DROP COLUMN | CRITICAL | カラム削除 | `ALTER TABLE tasks DROP COLUMN status` |
| TRUNCATE TABLE | CRITICAL | テーブルデータ全削除 | `TRUNCATE TABLE logs` |
| DROP DATABASE | CRITICAL | データベース削除 | `DROP DATABASE aipm` |
| ALTER TABLE RENAME | HIGH | テーブル名変更 | `ALTER TABLE tasks RENAME TO tasks_old` |
| DELETE (WHERE句なし) | HIGH | 全行削除 | `DELETE FROM tasks` |
| PRAGMA foreign_keys=OFF | MEDIUM | 外部キー制約無効化 | `PRAGMA foreign_keys = OFF` |
| UPDATE (WHERE句なし) | MEDIUM | 全行更新 | `UPDATE users SET active = 1` |

## 使用方法

### 1. 基本的な使用方法

```python
from utils.sql_safety import check_code_for_destructive_sql

code = """
cursor.execute("DROP TABLE old_users")
cursor.execute("ALTER TABLE tasks DROP COLUMN deprecated_field")
"""

result = check_code_for_destructive_sql(code)

if result["has_destructive_sql"]:
    print(f"警告: {result['count']}件の破壊的SQL操作が検出されました")
    for op in result["operations"]:
        print(f"  - {op}")
```

### 2. ファイルのスキャン

```python
from utils.sql_safety import check_file_for_destructive_sql

result = check_file_for_destructive_sql("migrations/drop_old_tables.py")

if result["has_destructive_sql"]:
    print(f"警告: {result['file_path']} に破壊的SQL検出")
    print(f"  CRITICAL: {result['critical_count']}件")
    print(f"  HIGH: {result['high_count']}件")
    print(f"  MEDIUM: {result['medium_count']}件")
```

### 3. 詳細なスキャン

```python
from utils.sql_safety import DestructiveSqlDetector

detector = DestructiveSqlDetector()
result = detector.scan_file("path/to/script.py")

for match in result.matches:
    print(f"[{match.pattern.severity}] Line {match.line_number}:")
    print(f"  {match.pattern.description}")
    print(f"  → {match.line_content}")
```

### 4. ディレクトリのスキャン

```python
from utils.sql_safety import DestructiveSqlDetector

detector = DestructiveSqlDetector()
results = detector.scan_directory(
    "migrations/",
    extensions={".py", ".sql"},
    recursive=True
)

for result in results:
    print(f"\n{result.file_path}:")
    print(f"  破壊的操作: {len(result.matches)}件")
```

## Worker実行時の自動検出

`execute_task.py` では、Worker実行完了後に自動的に破壊的SQL検出が行われます。

### 実行フロー

1. Worker実行完了
2. 成果物ファイルリストを取得
3. 各ファイルをDestructiveSqlDetectorでスキャン
4. 検出結果をREPORTに追記
5. PMレビュー時に確認可能

### REPORT出力例

```markdown
## 破壊的SQL検出結果

⚠️ **破壊的SQL操作が検出されました** (4件)

- CRITICAL: 2件
- HIGH: 1件
- MEDIUM: 1件

### 検出詳細

| ファイル | 行 | 重要度 | 説明 | コード |
|---------|-------|--------|------|--------|
| `migrations/001_drop_old.py` | 15 | 🔴 CRITICAL | テーブル削除 | `DROP TABLE old_users` |
| `migrations/001_drop_old.py` | 18 | 🔴 CRITICAL | カラム削除 | `ALTER TABLE tasks DROP COLUMN deprecated` |
| `migrations/001_drop_old.py` | 21 | 🟡 MEDIUM | 外部キー制約の無効化 | `PRAGMA foreign_keys = OFF` |
| `migrations/001_drop_old.py` | 24 | 🟠 HIGH | テーブル名変更 | `ALTER TABLE tasks RENAME TO tasks_old` |

⚠️ **PM確認事項**: このタスクには破壊的なDB変更が含まれます。
マイグレーション実行タイミングと影響範囲を確認してください。
```

## 安全なマイグレーションの実装方法

破壊的SQL操作が必要な場合は、必ず `MigrationRunner` を使用してください。

### 正しい実装例

```python
from utils.migration_base import MigrationRunner

def migrate(conn):
    cursor = conn.cursor()

    # 破壊的操作を含むマイグレーション
    cursor.execute("DROP TABLE IF EXISTS old_table")
    cursor.execute("ALTER TABLE users DROP COLUMN deprecated")

    return True

# MigrationRunnerを使用
runner = MigrationRunner("drop_old_table", verbose=True)
success = runner.run(migrate)
```

### MigrationRunnerの安全機能

- ✅ 自動バックアップ作成
- ✅ PRAGMA foreign_keys 制御（CASCADE削除防止）
- ✅ 他Worker実行中の検出と警告
- ✅ トランザクション管理（自動rollback）
- ✅ ドライランモード対応

## カスタマイズ

### カスタムパターンの追加

```python
from utils.sql_safety import DestructiveSqlDetector, DestructiveSqlPattern

custom_patterns = [
    DestructiveSqlPattern(
        pattern=r'\bREINDEX\b',
        severity="MEDIUM",
        description="インデックス再構築（ロック発生リスク）",
        examples=["REINDEX users"]
    ),
]

detector = DestructiveSqlDetector(patterns=custom_patterns)
```

### コメント無視の無効化

```python
detector = DestructiveSqlDetector(ignore_comments=False)
```

## 制限事項

- 正規表現ベースの検出のため、動的SQL（文字列連結など）は検出できません
- SQLインジェクション対策とは異なる目的のツールです
- 複雑なSQL文は誤検出の可能性があります

## テスト

```bash
# ユニットテスト実行
cd D:/your_workspace/AI_PM
python tmp/test_sql_safety.py
```

## 関連ドキュメント

- `utils/migration_base.py` - マイグレーション実行基盤
- `worker/execute_task.py` - Worker実行スクリプト
- `data/schema_v2.sql` - データベーススキーマ

## バージョン履歴

- 1.0.0 (2026-02-16): 初版リリース
  - 破壊的SQL操作の自動検出機能
  - Worker実行時の自動スキャン
  - REPORT出力機能
