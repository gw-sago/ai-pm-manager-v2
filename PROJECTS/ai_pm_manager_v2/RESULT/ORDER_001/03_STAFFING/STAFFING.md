# STAFFING - ORDER_001: AppData DB廃止・DB一元化

## タスク一覧

| Task ID | タイトル | 担当 | 優先度 | 依存 | モデル |
|---------|---------|------|--------|------|--------|
| TASK_001 | ConfigService改修 | Worker | P0 | なし | Opus |
| TASK_002 | database/index.ts DB接続先変更 | Worker | P0 | TASK_001 | Opus |
| TASK_003 | main.ts 初期化フロー整理 | Worker | P1 | TASK_001 | Sonnet |
| TASK_004 | config.ts IPCハンドラ整理 | Worker | P1 | TASK_001 | Sonnet |
| TASK_005 | preload.ts API整理・型定義クリーンアップ | Worker | P1 | TASK_004 | Sonnet |
| TASK_006 | ビルド確認・動作検証 | Worker | P0 | TASK_001-005 | Sonnet |

## タスク詳細

### TASK_001: ConfigService改修
- frameworkPathを固定パス化
- AppData DB依存（ProjectRepository, getDatabase）を全削除
- ensureProjectsDirectory() 追加

### TASK_002: database/index.ts DB接続先変更
- getDatabasePath() → ConfigService.getAipmDbPath()
- DB不在時はthrow（自動作成しない）
- schema/migrations参照の除去

### TASK_003: main.ts 初期化フロー整理
- initializeDefaultFrameworkPath() 呼び出し削除
- ensureProjectsDirectory() 追加

### TASK_004: config.ts IPCハンドラ整理
- config:remove-path 削除
- config:save 簡素化
- config:get-active-path 戻り値型変更

### TASK_005: preload.ts API整理
- FrameworkPath インターフェース削除
- removeFrameworkPath API削除
- getActiveFrameworkPath 型修正
- services/index.ts エクスポート整理

### TASK_006: ビルド確認・動作検証
- npm start でアプリ正常起動
- プロジェクト一覧表示確認
- エラーなしで動作することを確認

## 実行順序

```
TASK_001 ──┬── TASK_002
           ├── TASK_003
           ├── TASK_004 ── TASK_005
           └── (全完了) ── TASK_006
```
