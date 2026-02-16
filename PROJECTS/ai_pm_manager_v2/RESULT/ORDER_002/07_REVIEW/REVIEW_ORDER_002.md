# REVIEW - ORDER_002: getAipmDbPath()パッケージ時パス統一

## レビュー日時
2026-02-16

## レビュー結果: APPROVED

## 受け入れ条件チェック

| # | 条件 | 結果 | 根拠 |
|---|------|------|------|
| 1 | getAipmDbPath()が常にdata/aipm.dbを返す | PASS | `app.isPackaged`分岐を完全除去、常に`frameworkPath/data/aipm.db`を返す |
| 2 | frameworkPathがパッケージ時にexe実行ディレクトリを返す | PASS | `path.dirname(process.execPath)`に変更 |
| 3 | AppData DBへの依存コードが除去されている | PASS | getAipmDbPath()内のAppDataパス参照完全除去 |
| 4 | npm startでビルド通過 | PASS | webpack main/renderer両バンドル正常生成、DB接続成功 |

## 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| src/main/services/ConfigService.ts | 改修 | constructor: パッケージ時frameworkPathをexe実行ディレクトリに変更 |
| src/main/services/ConfigService.ts | 改修 | getAipmDbPath(): app.isPackaged分岐削除、統一パス返却 |
| src/main/services/ConfigService.ts | 改修 | JSDoc/コメント: AppData参照記述を全て削除 |

## 備考

- config.jsonの保存先（%APPDATA%/.aipm/config.json）は変更なし（ユーザー固有設定）
- supervisorsテーブル未作成の警告あり（ORDER_002範囲外）
- パッケージ時のexe配布時は、exeと同階層にdata/, PROJECTS/ディレクトリを配置する運用が必要
