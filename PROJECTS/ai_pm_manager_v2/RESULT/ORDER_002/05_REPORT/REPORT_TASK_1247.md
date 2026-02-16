# REPORT - TASK_1247: ConfigService パス解決統一

## 実行結果

### 変更内容

| ファイル | 変更箇所 | 内容 |
|---------|---------|------|
| src/main/services/ConfigService.ts | constructor() L75-78 | パッケージ時frameworkPathを`path.dirname(process.execPath)`に変更 |
| src/main/services/ConfigService.ts | getAipmDbPath() L198-199 | `app.isPackaged`分岐を削除、常に`frameworkPath/data/aipm.db`を返す |
| src/main/services/ConfigService.ts | JSDoc/コメント | AppData参照記述を全て削除、新パス設計を反映 |

### 変更前後の比較

**constructor() - frameworkPath**:
- Before: `this._frameworkPath = userDataPath;` (= %APPDATA%/ai-pm-manager-v2/)
- After: `this._frameworkPath = path.dirname(process.execPath);` (= exeフォルダ)

**getAipmDbPath()**:
- Before: パッケージ時は`%APPDATA%/.aipm/aipm.db`、開発時は`リポジトリ/data/aipm.db`
- After: 常に`frameworkPath/data/aipm.db`（分岐なし）

### 影響範囲

- getAipmDbPath()を呼び出す全サービス（AipmDbService, XBacklogService, SupervisorService, database/index.ts）は変更不要（ConfigServiceの返値が変わるだけ）
- getActiveFrameworkPath()を呼び出す全サービス（ProjectService, ScriptExecutionService等）も変更不要
- config.jsonの保存先（AppData/.aipm/config.json）は変更なし

## 結論

ConfigService.tsの3箇所を修正し、AppData DB参照を完全に除去した。
