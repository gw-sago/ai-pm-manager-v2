# REVIEW - ORDER_001: AppData DB廃止・DB一元化

## レビュー日時
2026-02-16

## レビュー結果: APPROVED

## 受け入れ条件チェック

| # | 条件 | 結果 | 根拠 |
|---|------|------|------|
| 1 | Electron起動時にAppData内DBを参照しない | PASS | database/index.tsはConfigService.getAipmDbPath()（= data/aipm.db）のみ参照 |
| 2 | ConfigServiceがframeworkPathを固定値で返す | PASS | getActiveFrameworkPath()はstring型を返す。ProjectRepository/AppData DB依存なし |
| 3 | config:remove-path IPCハンドラ廃止 | PASS | config.tsに該当ハンドラなし |
| 4 | preload.tsからremoveFrameworkPath API削除 | PASS | ElectronAPIインターフェース・実装両方から削除済み |
| 5 | npm startでビルド通過 | PASS | webpack main/renderer両バンドル正常生成 |

## 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| src/main/services/ConfigService.ts | 改修 | AppData DB依存全削除、frameworkPath固定化 |
| src/main/database/index.ts | 改修 | DB接続先をdata/aipm.dbに変更 |
| src/main.ts | 改修 | initializeDefaultFrameworkPath()削除 |
| src/main/config.ts | 改修 | config:remove-pathハンドラ削除 |
| src/preload.ts | 改修 | FrameworkPath/removeFrameworkPath削除、型修正 |
| src/main/services/index.ts | 改修 | FrameworkPath/AipmDbConfigエクスポート削除 |
| src/components/DirectorySelector.tsx | 改修 | frameworkPath保存処理削除 |
| src/components/Settings.tsx | 改修 | frameworkPath保存処理削除 |
| data/schema_v2.sql | 改修 | target_filesカラム追加 |

## 備考

- schema.ts / migrations.ts / repositories/ は他サービスが型定義・リポジトリとして依存中のため、本ORDERでは残存。将来的な別ORDERで対応予定。
- file_locksテーブル未作成の警告あり（タスク更新時の無害な警告）。スキーマ追加で対応可能だが本ORDER範囲外。
