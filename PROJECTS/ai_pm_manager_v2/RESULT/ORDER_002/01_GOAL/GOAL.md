# GOAL - ORDER_002: getAipmDbPath()パッケージ時パス統一

## ゴール
Electron exe（パッケージ版）起動時のDB参照先をAppData（%APPDATA%/.aipm/aipm.db）からリポジトリルート（data/aipm.db）に統一し、開発時とパッケージ時でDB参照先の不整合を完全に解消する。

## 背景
- ORDER_001でAppData DB廃止方針を決定したが、ConfigService.getAipmDbPath()のパッケージ時分岐が残存
- Pythonバックエンド（backend/）は常にdata/aipm.dbに書き込むが、Electron exe起動時はAppData DBを読む
- データ不整合が頻発し、手動でDBコピーが必要な状態

## 成功条件
1. getAipmDbPath()が常にdata/aipm.dbのパスを返す
2. frameworkPathがパッケージ時もリポジトリルートを返す
3. AppData内の.aipmディレクトリへのDB依存が完全に除去される
4. config.jsonの保存先はAppDataのまま維持（UI設定はユーザー固有）
5. webpackビルドが正常に通る
