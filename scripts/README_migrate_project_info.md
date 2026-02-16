# PROJECT_INFO.md Migration Script

## 概要

旧AI_PMリポジトリの`PROJECT_INFO.md`を解析し、プロジェクト概要・目的・技術スタック等を抽出してV2内部DBに登録するPythonスクリプト。

## 前提条件

- V2アプリが一度起動済みで、内部DBが作成されている
  - DB パス: `%APPDATA%\ai-pm-manager-v2\.aipm\aipm.db`
- V2内部DBに対象プロジェクトが登録済み（`projects`テーブルに`name`が存在する）
- マイグレーション v2（description, purpose, tech_stack フィールド追加）が適用済み

## 使用方法

```bash
python scripts/migrate_project_info.py <project_name> <project_info_md_path>
```

### 引数

- `<project_name>`: V2内部DBに登録されているプロジェクト名（`projects.name`）
- `<project_info_md_path>`: 旧AI_PMリポジトリのPROJECT_INFO.mdへの絶対パス

### 実行例

```bash
# ai_pm_manager プロジェクトの情報を移行
python scripts/migrate_project_info.py ai_pm_manager "D:/your_workspace/AI_PM/PROJECTS/ai_pm_manager/PROJECT_INFO.md"

# 別のプロジェクトの場合
python scripts/migrate_project_info.py Pokemon_TCG_Info "D:/your_workspace/AI_PM/PROJECTS/Pokemon_TCG_Info/PROJECT_INFO.md"
```

## 動作内容

### 1. PROJECT_INFO.md 解析

以下の情報を抽出します：

#### プロジェクト名・説明

```markdown
### プロジェクト名

**ai_pm_manager** - AI PM Framework ビューワー/管理アプリケーション
```

- `projects.name`: `ai_pm_manager`
- `projects.description`: `AI PM Framework ビューワー/管理アプリケーション`

#### 目的・背景

```markdown
### 目的・背景

- AI PM Frameworkは優れたワークフロー管理を提供するが、全てがMarkdownファイルベース
- 複数プロジェクトの横断的な状態確認が煩雑
- ...
```

- `projects.purpose`: 箇条書き（`- `）を除去し、改行で連結したテキスト

#### 技術スタック

```markdown
## 技術スタック・環境

### 使用言語
- TypeScript (メイン)
- JavaScript (設定ファイル等)

### フレームワーク・ライブラリ
- **Electron**: デスクトップアプリケーション基盤
- ...
```

- `projects.tech_stack`: サブセクション（使用言語、フレームワーク・ライブラリ、データベース、開発環境）を結合したテキスト

### 2. V2内部DB 更新

抽出した情報で`projects`テーブルの該当レコードを更新：

```sql
UPDATE projects
SET description = ?,
    purpose = ?,
    tech_stack = ?,
    updated_at = ?
WHERE name = ?
```

## 出力例

```
=== PROJECT_INFO.md Migration ===
Project Name: ai_pm_manager
PROJECT_INFO.md: D:\your_workspace\AI_PM\PROJECTS\ai_pm_manager\PROJECT_INFO.md

[OK] V2 DB found: C:\Users\xxx\AppData\Roaming\ai-pm-manager-v2\.aipm\aipm.db
[OK] PROJECT_INFO.md parsed successfully.
     - Extracted name: ai_pm_manager
     - Description length: 46 chars
     - Purpose length: 142 chars
     - Tech stack length: 1040 chars

[OK] Project 'ai_pm_manager' (id=1) updated successfully.
     - description: 46 chars
     - purpose: 142 chars
     - tech_stack: 1040 chars

=== Migration completed ===
```

## エラーケース

### プロジェクトが見つからない場合

```
[WARN] Project 'ai_pm_manager' not found in V2 DB.
       Available projects:
         - Default
```

**対処法**: V2アプリでプロジェクトを先に作成するか、プロジェクト名を確認してください。

### V2 DB が見つからない場合

```
[ERROR] V2 DB not found: C:\Users\xxx\AppData\Roaming\ai-pm-manager-v2\.aipm\aipm.db
```

**対処法**: V2アプリを一度起動してDBを初期化してください。

### PROJECT_INFO.md が見つからない場合

```
[ERROR] Failed to parse PROJECT_INFO.md: PROJECT_INFO.md not found: D:\your_workspace\AI_PM\PROJECTS\xxx\PROJECT_INFO.md
```

**対処法**: ファイルパスを確認してください。

## 注意事項

- **ORDER/TASK履歴は移行しません**: このスクリプトは`projects`テーブルの概要情報のみを移行します
- **既存データは上書きされます**: 同じプロジェクトに対して複数回実行すると、前回の値が上書きされます
- **DB バックアップ推奨**: 実行前にV2内部DBのバックアップを取ることを推奨します

## テスト方法

抽出データのプレビュー（DB更新なし）:

```python
# tmp/test_migrate_project_info.py を作成
from migrate_project_info import parse_project_info
from pathlib import Path

info = parse_project_info(Path('D:/your_workspace/AI_PM/PROJECTS/ai_pm_manager/PROJECT_INFO.md'))
print(info)
```

## 関連ファイル

- `src/main/database/schema.ts` - V2内部DBスキーマ定義
- `src/main/database/migrations.ts` - マイグレーション v2 定義
- `PROJECTS/*/PROJECT_INFO.md` - 旧AI_PMリポジトリのプロジェクト情報
