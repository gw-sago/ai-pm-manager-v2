# ORDER_001.md

## 発注情報
- **発注ID**: ORDER_001
- **発注日**: 2026-02-16
- **発注者**: User
- **優先度**: P0
- **由来**: BACKLOG_010

---

## 発注内容

### 概要
AppData DB廃止・DB一元化（data/aipm.dbに統合）

### 詳細
カテゴリ: リファクタリング

V1設計の名残であるAppData内DB（%APPDATA%/.aipm/aipm.db）を廃止し、リポジトリルートのdata/aipm.dbに一元化する。現状: AppData DBのprojectsテーブルがframeworkPathリストとして使われており、プロジェクトDBのprojectsテーブルと同名で紛らわしい。frameworkPath設定はconfig.jsonのみで管理する形に変更。Electron側のDB接続(src/main/database/)、ConfigService、AipmDbService、ProjectServiceを改修。

### 受け入れ条件
（BACKLOGから引き継ぎ）

---

## PM記入欄

### 要件理解チェック
- [x] 発注内容を理解した
- [x] GOAL.mdを作成した
- [x] REQUIREMENTS.mdを作成した
- [x] STAFFING.mdを作成した
- [x] タスクを発行した

### 備考
全6タスク完了。レビューAPPROVED。2026-02-16 完了。

---

**作成日**: 2026-02-16
**作成者**: System（BACKLOG→ORDER変換）
**変換元**: PROJECTS/ai_pm_manager_v2/BACKLOG.md#BACKLOG_010
