# AI PM Manager V2 - フレームワーク設定

## 概要
AI PM Manager V2は、UI操作とCLI操作（Claude Code）の両方をサポートする統合プロジェクト管理システムです。

## ディレクトリ構成

```
ai-pm-manager-v2/
├── src/                    # Electron + React フロントエンド
├── backend/                # Pythonバックエンド（= 旧 scripts/aipm-db/）
├── data/
│   ├── aipm.db             # SQLite メインDB
│   └── schema_v2.sql       # DBスキーマ定義
├── PROJECTS/               # プロジェクトデータ
│   └── {project_id}/
│       ├── PROJECT_INFO.md
│       ├── ORDERS/
│       └── RESULT/
├── templates/              # プロジェクトテンプレート
├── .claude/commands/       # スラッシュコマンド定義（16本）
└── CLAUDE.md               # このファイル
```

## Pythonスクリプトのパス

全てのPythonスクリプトは `backend/` 配下にあります:

```bash
# 例: プロジェクト一覧取得
python backend/project/list.py --json

# 例: ORDER一覧取得
python backend/order/list.py {PROJECT_NAME} --json

# 例: タスク一覧取得
python backend/task/list.py {PROJECT_NAME} --order ORDER_XXX --json
```

## DB設定

- **DBパス**: `data/aipm.db`（リポジトリルートからの相対パス）
- **スキーマ**: `data/schema_v2.sql`
- **パス解決**: `backend/config/db_config.py` がリポジトリルートを自動検出

## スラッシュコマンド

CLI操作で使用可能なコマンド:

| コマンド | 用途 |
|---------|------|
| `/aipm` | プロジェクト状態確認 |
| `/aipm-pm` | PM処理（ORDER作成・タスク発行） |
| `/aipm-worker` | Worker実行（タスク実装） |
| `/aipm-review` | レビュー（タスク承認/差し戻し） |
| `/aipm-full-auto` | 完全自動実行（PM→Worker→レビュー） |
| `/aipm-status` | 詳細状態確認 |
| `/aipm-backlog-add` | バックログ追加 |
| `/aipm-backlog-to-order` | バックログからORDER作成 |
| `/aipm-release` | リリース処理 |
| `/aipm-release-review` | リリース承認フロー |
| `/aipm-recover` | 中断タスクのリカバリ |
| `/aipm-rollback` | ロールバック |
| `/aipm-log-stream` | ログストリーム |
| `/aipm-dashboard-update` | ダッシュボード更新 |
| `/aipm-supervisor` | マルチプロジェクト監視 |
| `/aipm-restore` | 緊急リカバリ |

## 開発環境

### ソースコードとデプロイ先
- **ソースコード**: `d:\your_workspace\ai-pm-manager-v2\`
- **デプロイ先（実行環境）**: `c:\Users\s_sago.G-WISE\AppData\Local\ai_pm_manager_v2\`

### 「ビルドお願いします」ルール
ユーザーが「ビルド」「ビルドお願いします」と言った場合、以下を**すべて自動実行**する:
1. ソースリポジトリでインストーラービルド: `cd /d/your_workspace/ai-pm-manager-v2 && npx electron-forge make`
2. 生成されたSetup.exeを実行してインストール

**補足**: Squirrelインストーラーはバージョンディレクトリ（app-X.X.X/）のみ差し替え、data/aipm.db と PROJECTS/ には触れない。deployResources()（main.ts）がbackend/等のリソースのみ展開し、永続データを保護する。バックアップ&リストアは不要。

### その他コマンド
```bash
# 開発モード
npm start

# 型チェック
npm run typecheck
```

### 出力
```
out/make/squirrel.windows/x64/ai-pm-manager-v2-0.1.0 Setup.exe
```

## 制約事項

1. **Claude API直接利用禁止**: AI機能はPythonスクリプト（backend/）として実装し、ElectronからspawnまたはClaude Codeのスキル経由で実行する
2. **better-sqlite3**: webpack.main.config.js で `externals: { 'better-sqlite3': 'commonjs better-sqlite3' }` が必要
3. **preload.ts**: forge.config.js の entryPoints に preload 設定が必要
4. **DB駆動のみ**: MDモードは廃止済み。全データはSQLite DBで管理

## 永続データのパスルール（Roaming必須）

**重要**: PROJECTS/配下のファイルおよびdata/aipm.dbは、必ず`%APPDATA%`（Roaming）パスで操作すること。

### 背景
- SquirrelインストーラーがAppData\Localを上書きするため、Localに永続データを置くとインストール時に消失する
- `backend/config/db_config.py` の `_get_user_data_path()` が `%APPDATA%`(Roaming) を返す設計

### ルール
1. **ファイルパス構築時は必ず `get_project_paths()` を使う**
   ```python
   from config.db_config import get_project_paths
   paths = get_project_paths(project_id)  # Roaming絶対パスを返す
   ```
2. **相対パス `PROJECTS/{...}` の直接使用は禁止**
   - cwdがLocalのため、相対パスはLocalに解決される
3. **Workerサブエージェントのパス解決**
   - `execute_task.py` がWorkerプロンプトにRoaming絶対パスを注入する
   - CLIでの取得: `python backend/config/resolve_path.py PROJECT_NAME --json`

## 既知のバグパターン

- **BUG_003**: `sqlite3.Row` は `.get()` メソッド非対応。直接インデックスまたは `row_to_dict()` を使用
- **BUG_004**: DONE→REJECTED は禁止。必ず DONE→REWORK→REJECTED の遷移を経る
- **BUG_009**: preload.ts の型定義とバックエンド実装の乖離に注意
- **BUG_010**: export済みフック/コンポーネントの未import に注意
- **BUG_011**: WorkerがPROJECTS/配下を相対パスで参照するとLocalに書き込まれRoamingと不整合になる。必ず`get_project_paths()`のRoaming絶対パスを使用すること
