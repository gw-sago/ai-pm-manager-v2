# ORDER_002.md

## 発注情報
- **発注ID**: ORDER_002
- **発注日**: 2026-02-16
- **発注者**: User
- **優先度**: P0
- **由来**: BACKLOG_212

---

## 発注内容

### 概要
getAipmDbPath()パッケージ時パス統一（AppData DB完全廃止）

### 詳細
カテゴリ: リファクタリング

getAipmDbPath()がパッケージ時（exe起動）にAppData側のDB（%APPDATA%/.aipm/aipm.db）を参照する設計が残っている。開発時・パッケージ時ともにリポジトリルートのdata/aipm.dbを参照するように統一し、AppData DBへのコピー運用を不要にする。

現状の問題:
- ConfigService.getAipmDbPath()がapp.isPackaged時にAppDataパスを返す
- Pythonバックエンドは常にdata/aipm.dbに書き込む
- exe起動時とCLI操作でDB参照先が異なりデータ不整合が発生

### 受け入れ条件
1. getAipmDbPath()が開発時・パッケージ時ともにdata/aipm.dbを返すこと
2. frameworkPathもパッケージ時にリポジトリルートを返すこと
3. AppData DBへの依存コードが全て除去されていること
4. npm startでビルド通過すること

---

## PM記入欄

### 要件理解チェック
- [x] 発注内容を理解した
- [x] GOAL.mdを作成した
- [x] REQUIREMENTS.mdを作成した
- [x] STAFFING.mdを作成した
- [x] タスクを発行した

### 備考
全2タスク完了。レビューAPPROVED。2026-02-16 完了。

---

**作成日**: 2026-02-16
**作成者**: System（BACKLOG→ORDER変換）
**変換元**: BACKLOG_212
