# REQUIREMENTS - ORDER_001: AppData DB廃止・DB一元化

## 機能要件

### REQ-001: ConfigService改修
- frameworkPathをコンストラクタ時に固定値で算出（`app.getAppPath()` or `process.resourcesPath`）
- `getActiveFrameworkPath()` → `string`（nullなし）
- AppData DB関連メソッドを全て削除
  - `addFrameworkPath()`, `removeFrameworkPath()`, `setActiveFrameworkIndex()`
  - `getFrameworkPathsFromDB()`, `getProjectRepo()`, `initializeDefaultFrameworkPath()`
- `ensureProjectsDirectory()` メソッド追加
- `AppConfig`インターフェースから`frameworkPaths`, `activeFrameworkIndex`を削除

### REQ-002: database/index.ts改修
- DB接続先を`ConfigService.getAipmDbPath()`（= `data/aipm.db`）から取得
- DBファイルが存在しない場合はエラー（backendがスキーマ管理）
- schema.ts / migrations.ts のインポート・実行を除去

### REQ-003: main.ts初期化フロー整理
- `initializeDefaultFrameworkPath()` 呼び出し削除
- `configService.ensureProjectsDirectory()` 呼び出し追加

### REQ-004: config.ts IPCハンドラ整理
- `config:remove-path` ハンドラ削除
- `config:save` ハンドラの簡素化（window設定のみ）
- `config:get-active-path` の戻り値を`string`に

### REQ-005: preload.ts API整理
- `FrameworkPath`インターフェース削除
- `removeFrameworkPath` API定義・実装の削除
- `getActiveFrameworkPath` 戻り値型を`string`に
- `SaveConfigRequest`から`frameworkPath`, `frameworkName`, `activeIndex`削除

## 非機能要件

- ビルドが通ること（`npm start`で正常起動）
- 既存のプロジェクト一覧表示が動作すること
