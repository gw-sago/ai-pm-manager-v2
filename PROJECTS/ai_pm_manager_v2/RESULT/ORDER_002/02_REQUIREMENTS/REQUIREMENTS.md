# REQUIREMENTS - ORDER_002: getAipmDbPath()パッケージ時パス統一

## 要件一覧

### R1: ConfigService パス解決の統一
- getAipmDbPath(): 常に `{exeの実行ディレクトリ}/data/aipm.db` を返す
- パッケージ時: `process.execPath`の親ディレクトリ（= exeが置かれたフォルダ）を基準とする
- 開発時: `app.getAppPath()`（= リポジトリルート）を基準とする

### R2: frameworkPath の統一
- パッケージ時: exeの実行ディレクトリ（PROJECTS/やdata/が存在する場所）
- 開発時: リポジトリルート（現行通り）

### R3: config.json の保存先維持
- config.json（ウィンドウサイズ等）はAppData/.aipm/に保存（変更なし）
- これはユーザー固有の設定であり、リポジトリに含めるべきでない

### R4: backendPath の維持
- パッケージ時: resources/backend/（変更なし）
- 開発時: リポジトリ/backend/（変更なし）

### R5: ビルド通過
- TypeScript型チェックエラー0件
- Webpackビルド成功

## 影響範囲
- ConfigService.ts: constructor(), getAipmDbPath(), getActiveFrameworkPath()
- コメント/JSDoc更新
- 他ファイル: ConfigServiceの返値に依存するため、コード変更なし（パス解決がConfigServiceに集約済み）

## 非スコープ
- AppData上のconfig.jsonの移動
- forge.config.jsの変更（extraResourceは現行のまま）
- テストファイルの変更（モックは既存のまま動作）
