# GOAL - ORDER_001: AppData DB廃止・DB一元化

## ゴール

V1設計の名残であるAppData内DB（`%APPDATA%/.aipm/aipm.db`）を廃止し、リポジトリルートの `data/aipm.db` に一元化する。

## 背景

- V1ではUI（Electron）とフレームワーク（AI PM）が別リポジトリで管理されていた
- AppData DBの`projects`テーブルが「frameworkPathリスト」として機能し、外部フレームワークの場所を記録していた
- V2では1リポジトリに統合されたため、frameworkPath = リポジトリルート（固定値）となり、AppData DBの存在意義がなくなった
- 2つのDBが同名テーブル（projects）を持ち、混乱の原因になっていた

## 完了条件

1. Electron起動時にAppData内のDBを作成・参照しないこと
2. ConfigServiceがframeworkPathを固定値で返すこと（AppData DB不要）
3. `config:remove-path` IPCハンドラが廃止されていること
4. preload.tsから`removeFrameworkPath`APIが削除されていること
5. `npm start`でアプリが正常起動し、プロジェクト一覧が表示されること

## スコープ外

- schema.ts / repositories/ の完全廃止（他サービスが型定義・リポジトリを利用中）
- AipmDbService / ProjectService の改修（既にdata/aipm.dbのみ参照）
- Python backendの変更（影響なし）
