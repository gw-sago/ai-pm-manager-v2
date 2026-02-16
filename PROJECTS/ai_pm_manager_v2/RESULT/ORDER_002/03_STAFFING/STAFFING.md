# STAFFING - ORDER_002: getAipmDbPath()パッケージ時パス統一

## タスク分解

### TASK_007: ConfigService パス解決統一
- **担当**: Worker (Opus)
- **内容**: ConfigService.tsのconstructor()とgetAipmDbPath()を修正
  - パッケージ時frameworkPathをexe実行ディレクトリに変更
  - getAipmDbPath()のパッケージ時分岐を除去
  - JSDoc/コメント更新
- **依存**: なし
- **優先度**: P0

### TASK_008: ビルド確認・動作検証
- **担当**: Worker (Opus)
- **内容**:
  - TypeScript型チェック（tsc --noEmit）
  - Webpackビルド
  - 変更後のパス解決ロジック確認
- **依存**: TASK_007
- **優先度**: P0

## スケジュール
1. TASK_007 → TASK_008（逐次実行）
2. レビュー → ORDER完了
