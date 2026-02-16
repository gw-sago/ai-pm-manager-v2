---
description: プロジェクト状態を確認します（マルチORDER対応）
---

現在のプロジェクト状態を確認します。

**引数**:
- 第1引数（任意）: プロジェクト名（例: AI_PM_PJ）
  - 省略時はカレントディレクトリまたはPROJECTS配下から自動検出
- 第2引数（任意）: オプション
  - `--sync`: ステータス表示前にMarkdown→DB同期を実行

**使用例**:
```
/aipm-status AI_PM_PJ                  # 通常の状態確認（整合性チェック含む）
/aipm-status AI_PM_PJ --sync           # 同期実行後に状態確認
/aipm-status AI_PM_PJ --fix-integrity  # 整合性の不整合を自動修復
```

以下の情報を取得して要約表示してください：

---

## Step 0: データソース判定（DB中心アーキテクチャ対応）

ステータス表示の前に、データ取得先を判定しDB優先でプロジェクト状態を取得します。

### 0.1 DB利用可能判定

以下の条件を順に確認：

```
DB利用可能判定:
1. backend/ ディレクトリが存在するか確認
2. data/aipm.db ファイルが存在するか確認
3. 両方存在 → DBモード
4. いずれか存在しない → 従来方式（Markdown直接読み込み）
```

### 0.2 DBモードでのデータ取得

DBが利用可能な場合、以下のスクリプトでプロジェクト状態を取得：

```bash
# 状態サマリ取得（ORDER概要統計）
python backend/order/list.py $PROJECT_NAME --summary --json

# アクティブORDER一覧取得
python backend/order/list.py $PROJECT_NAME --active --json

# タスク一覧取得（特定ORDER）
python backend/task/list.py $PROJECT_NAME --order ORDER_XXX --json

# レビューキュー取得
python backend/queue/list.py $PROJECT_NAME --json

# Worker配置状況（実行中タスク）
python backend/task/list.py $PROJECT_NAME --status IN_PROGRESS --json

# 中断タスク一覧
python backend/task/list.py $PROJECT_NAME --status INTERRUPTED --json
```

### 0.3 フォールバック処理

DBスクリプト実行に失敗した場合、または DB が存在しない場合は従来方式にフォールバック：

```
フォールバック条件:
1. backend/ が存在しない
2. data/aipm.db が存在しない
3. DBスクリプトがエラーで終了（exit code != 0）
4. DBスクリプトの出力が空またはパースエラー

フォールバック時の動作:
→ DBが利用できない場合はエラーを表示
→ 「DB未初期化」として最小限の情報のみ表示
```

### 0.4 データソースインジケータ表示（オプション）

データ取得元を表示する場合のフォーマット：

```
【データソース】
- モード: DB優先
- DB: ✓ (data/aipm.db)
- スクリプト: ✓ (backend/)
```

または（フォールバック時）:

```
【データソース】
- モード: Markdown直接読み込み
- 理由: DBスクリプトが利用不可
```

### 0.5 後方互換性対応表

| セクション | DBモード（必須） | フォールバック時 |
|-----------|-----------------|-----------------|
| 状態サマリ | `order/list.py --summary` | エラー表示 |
| ORDER一覧 | `order/list.py --active` | エラー表示 |
| タスク一覧 | `task/list.py --order` | エラー表示 |
| レビューキュー | `queue/list.py` | エラー表示 |
| Worker配置 | `task/list.py --status IN_PROGRESS` | エラー表示 |
| 中断タスク | `task/list.py --status INTERRUPTED` | エラー表示 |

---

## Step 0.6: --sync オプション処理（事前同期）

`--sync` オプションが指定された場合、ステータス表示前にMarkdown→DB同期を実行します。

### 0.6.1 同期実行

```bash
# 同期スクリプト実行
python scripts/sync/sync_md_to_db.py {PROJECT_NAME} --source aipm-status
```

### 0.6.2 同期結果表示

```
【同期状態】
同期実行: 2026-01-27 10:15:30
結果: success | partial | failed
変更件数: {changes_count}件
警告: {warnings_count}件（あれば表示）
```

### 0.6.3 エラー時の処理

同期エラーが発生した場合も、ステータス表示は継続します：

```
【同期警告】
同期中にエラーが発生しました: {error_message}
最終成功同期: {last_sync_at}
ステータス表示を続行します...
```

---

## Step 0.7: DB同期状態セクション（常時表示）

ステータス表示時に、DB同期の状態を確認して表示します。

### 0.7.1 同期状態の取得

```bash
# 同期状態を取得（CLIから）
python scripts/sync/sync_status.py get {PROJECT_NAME}
```

または、Python経由：
```python
from scripts.sync.sync_status import SyncStatusManager
manager = SyncStatusManager()
status = manager.get_status(project_name)
```

### 0.7.2 同期状態の表示形式

状態サマリ（セクション2）の直後に以下を表示：

```
【DB同期状態】
最終同期: 2026-01-27 10:15:30
ソース: hooks | manual | aipm-status
結果: success | partial | failed
```

**stale（古い同期）の場合**:
```
【DB同期状態】⚠️
最終同期: 2026-01-27 09:00:00（30分前）
状態が古い可能性があります。
再同期: /aipm-status {PROJECT_NAME} --sync
```

### 0.7.3 表示条件

| 条件 | 表示内容 |
|------|----------|
| 同期成功 & 5分以内 | 通常表示（アイコンなし） |
| 同期成功 & 5分以上 | 警告表示（⚠️アイコン + 再同期案内） |
| 同期部分成功（partial） | 警告表示 + 警告件数 |
| 同期失敗 | エラー表示 + 再同期案内 |
| 同期状態なし | 「同期状態: 未同期」と表示 |

### 0.7.4 後方互換性

- `scripts/sync/sync_status.py` が存在しない場合：同期状態セクションをスキップ
- `data/sync_status.json` が存在しない場合：「同期状態: 未同期」と表示

---

## Step 0.8: 整合性チェック（DB-Markdown同期ズレ検出）

ステータス表示時に、DBとMarkdownの整合性をチェックし、ズレがあれば警告を表示します。

### 0.8.1 整合性チェック実行

```bash
# 整合性チェックスクリプト実行
python scripts/sync/check_integrity.py {PROJECT_NAME} --json
```

### 0.8.2 チェック対象

| チェック項目 | 説明 | 重要度 |
|-------------|------|--------|
| ステータス不整合 | Markdown vs DB のステータスが異なる | critical |
| REPORT存在ズレ | REPORTあるがDBがQUEUED/IN_PROGRESS | critical |
| REVIEW存在ズレ | REVIEWあるがDBがCOMPLETED以外 | critical |
| DB未登録 | MarkdownにあるがDBに存在しない | critical |
| レビューキュー欠落 | DONE/COMPLETEDだがレビューキューなし | warning |
| 担当者不整合 | 担当者情報がMarkdownにあるがDBにない | warning |

### 0.8.3 結果表示

**不整合が検出された場合**:

```
【整合性チェック】⚠️ 不整合検出

| Task ID | 項目 | Markdown | DB | 重要度 |
|---------|------|----------|-------|--------|
| TASK_297 | status | DONE | QUEUED | critical |
| TASK_298 | status | COMPLETED | QUEUED | critical |

自動修復するには:
python scripts/sync/check_integrity.py {PROJECT_NAME} --fix

または手動同期:
/aipm-status {PROJECT_NAME} --sync
```

**不整合がない場合**:

```
【整合性チェック】✓ 正常
チェック済み: {N}件のタスク
```

### 0.8.4 自動修復オプション（--fix-integrity）

`--fix-integrity` オプション指定時、検出された不整合を自動修復：

```bash
/aipm-status PROJECT_NAME --fix-integrity
```

**修復処理**:
1. MarkdownのステータスをDBに反映
2. 欠落しているレビューキューエントリを追加
3. 担当者情報を同期

**修復結果表示**:
```
【整合性修復】
修復済み: 3件
- TASK_297: status QUEUED → DONE
- TASK_298: status QUEUED → COMPLETED
- TASK_298: review_queue 追加
```

### 0.8.5 表示条件とスキップ

| 条件 | 動作 |
|------|------|
| `scripts/sync/check_integrity.py` が存在しない | セクションをスキップ |
| チェック対象タスクが0件 | 「チェック対象なし」と表示 |
| 不整合が0件 | 正常表示（緑チェックマーク） |
| 不整合がcritical 1件以上 | 警告表示（⚠️アイコン）+ 修復案内 |
| 不整合がwarningのみ | 軽微な警告表示 |

### 0.8.6 チェック頻度の推奨

- `/aipm-status` 実行時: 毎回チェック（軽量）
- タスク完了時: Worker完了報告後に自動チェック推奨
- 定期チェック: 1日1回の手動確認を推奨

---

## スクリプト利用ガイド（DBモード詳細リファレンス）

> **Note**: このセクションはStep 0（データソース判定）でDBモードと判定された場合の詳細リファレンスです。
> 各セクションのDBモード対応はStep 0.5の後方互換性対応表も参照してください。

### データ取得方法

DB連携スクリプトが利用可能な場合、以下のコマンドで効率的にデータを取得できます。

#### ORDER一覧取得

```bash
# アクティブORDER一覧を取得
python backend/order/list.py PROJECT_NAME --status active --json

# 全ORDER一覧を取得
python backend/order/list.py PROJECT_NAME --json

# ORDER概要統計を取得
python backend/order/list.py PROJECT_NAME --summary --json
```

**出力形式（--json指定時）**:
```json
{
  "orders": [
    {
      "id": "ORDER_036",
      "title": "DB連携スクリプト基盤構築",
      "priority": "P1",
      "status": "IN_PROGRESS",
      "progress_pct": 45,
      "task_count": 8,
      "completed_count": 3,
      "created_at": "2026-01-20T10:00:00",
      "updated_at": "2026-01-22T15:30:00"
    }
  ],
  "summary": {
    "total": 36,
    "active": 1,
    "completed": 33,
    "on_hold": 2
  }
}
```

#### タスク一覧取得

```bash
# 全タスク一覧を取得
python backend/task/list.py PROJECT_NAME --json

# 特定ORDERのタスク一覧を取得
python backend/task/list.py PROJECT_NAME --order ORDER_036 --json

# ステータス別にフィルタ
python backend/task/list.py PROJECT_NAME --status IN_PROGRESS --json
python backend/task/list.py PROJECT_NAME --status QUEUED --json
python backend/task/list.py PROJECT_NAME --status INTERRUPTED --json
```

**出力形式（--json指定時）**:
```json
{
  "tasks": [
    {
      "id": "TASK_196",
      "order_id": "ORDER_036",
      "title": "aipm-pm/aipm-statusコマンド更新",
      "status": "IN_PROGRESS",
      "priority": "P1",
      "assigned_to": "Worker",
      "dependencies": ["TASK_192", "TASK_195"],
      "started_at": "2026-01-22T14:00:00"
    }
  ],
  "summary": {
    "total": 8,
    "queued": 2,
    "in_progress": 1,
    "completed": 4,
    "interrupted": 1
  }
}
```

#### キュー一覧取得

```bash
# 実行可能なタスク一覧を取得
python backend/queue/list.py PROJECT_NAME --json

# 特定ORDERのキューを取得
python backend/queue/list.py PROJECT_NAME --order ORDER_036 --json
```

**出力形式（--json指定時）**:
```json
{
  "queue": [
    {
      "id": "TASK_197",
      "order_id": "ORDER_036",
      "title": "テストスイート実装",
      "priority": "P1",
      "dependencies_met": true,
      "blocked_by": []
    }
  ],
  "blocked": [
    {
      "id": "TASK_199",
      "order_id": "ORDER_036",
      "title": "統合テスト",
      "blocked_by": ["TASK_197", "TASK_198"]
    }
  ]
}
```

### スクリプト実行の前提条件

> **Note**: Step 0 のDB利用可能判定を参照してください。

```
確認手順（Step 0 で自動実行）:
1. aipm-db パッケージの存在確認:
   - backend/ ディレクトリが存在すること

2. データベースの存在確認:
   - data/aipm.db ファイルが存在すること

3. スクリプトが利用できない場合:
   - DB未初期化エラーを表示し、初期化を促す
```

### フォールバック処理

スクリプトが利用できない場合、エラーメッセージを表示し初期化を促します：

```
フォールバック判定:
1. スクリプト実行を試行
2. IF エラー（ModuleNotFoundError, FileNotFoundError等）:
     「DB未初期化」エラーを表示
3. 初期化手順を案内
```

---

## 1. プロジェクト状態取得（DB経由）

- 引数でプロジェクト名が指定されている場合: DBから該当プロジェクトの状態を取得
- 指定がない場合: カレントディレクトリからプロジェクト名を推測し、DBから取得

### 1.1 マルチORDERモード判定

DB取得後、以下の条件でモードを判定する：

```
モード判定:
1. DBからアクティブORDER一覧を取得
2. IF アクティブORDERが2件以上:
     マルチORDERモードで表示
3. ELSE:
     単一ORDERモード（従来互換）で表示
```

---

## 2. 状態サマリ表示（共通ヘッダー）

### 2.1 単一ORDERモード

```
【プロジェクト状態】{PROJECT_NAME}
ORDER: {ORDER_ID}
プロジェクト名: {プロジェクト名}
ステータス: {現在ステータス}
進捗: {完了タスク数}/{全タスク数} タスク完了
中断中タスク: {中断タスク数}件
最終更新: {最終更新日時}
```

### 2.2 マルチORDERモード

```
【プロジェクト状態】{PROJECT_NAME}
現在ステータス: {現在ステータス}
アクティブORDER: {アクティブ数} / {推奨上限}（上限）
全体進捗: {全タスク完了率}% ({完了タスク}/{全タスク})
中断中タスク: {中断タスク数}件
最終更新: {最終更新日時}
```

**中断タスク数の集計ルール**:
- タスク一覧でステータスが `INTERRUPTED` のタスクを集計
- 中断タスクが0件の場合は表示をスキップ可能
- 中断タスクが1件以上の場合は必ず表示

---

## 3. アクティブORDER一覧表示（マルチORDERモード）

### 3.1 アクティブORDER一覧テーブル

DBの「アクティブORDER一覧」からデータを抽出し表示：

```
【アクティブORDER一覧】

| ORDER | タイトル | 優先度 | 進捗 | ステータス | 担当Worker |
|-------|---------|--------|------|----------|-----------|
| ORDER_019 | 複数ORDER同時進行 | P1 | 22% | IN_PROGRESS | Worker A |
| ORDER_020 | ドキュメント整備 | P2 | 83% | IN_PROGRESS | Worker B |
```

**表示ルール**:
- 優先度順（P0 > P1 > P2 > P3）でソート
- P0のORDERは行頭に「**」を付けて強調
- アクティブORDERがない場合：「アクティブORDERなし」と表示

### 3.2 待機ORDER一覧

ステータスがQUEUEDまたはON_HOLDのORDERを表示：

```
【待機ORDER】

| ORDER | タイトル | 優先度 | 理由 |
|-------|---------|--------|------|
| ORDER_021 | 緊急バグ修正 | P0 | 依存: ORDER_019 |
| ORDER_022 | 改善施策 | P3 | ON_HOLD |
```

**表示ルール**:
- 待機理由（依存、一時停止等）を表示
- 待機ORDERがない場合：このセクションをスキップ

---

## 4. ORDER別詳細表示（マルチORDERモード）

各アクティブORDERについて、以下の概要を表示：

```
【ORDER_019】複数ORDER同時進行 (P1)
- 進捗: 2/9 タスク完了 (22%)
- 実行中: TASK_148 (Worker A)
- 次タスク: TASK_152, TASK_153, TASK_154
- レビュー待ち: 0件

【ORDER_020】ドキュメント整備 (P2)
- 進捗: 5/6 タスク完了 (83%)
- 実行中: TASK_205 (Worker B)
- 次タスク: なし
- レビュー待ち: 1件
```

**抽出ロジック**:
1. 各「ORDER_XXX 詳細」セクションを読み込む
2. タスク一覧からステータス別に集計
3. IN_PROGRESSタスクを「実行中」に表示
4. QUEUEDタスクを「次タスク」に表示（最大3件）
5. レビューキューのPENDING件数を「レビュー待ち」に表示

---

## 5. Worker配置状況（マルチORDERモード）

全ORDERを横断したWorker配置状況を表示：

```
【Worker配置】

| Worker | 担当ORDER | 担当TASK | ステータス |
|--------|----------|---------|----------|
| Worker A | ORDER_019 | TASK_148 | IN_PROGRESS |
| Worker B | ORDER_020 | TASK_205 | IN_PROGRESS |
| Worker C | - | - | 待機中 |
```

**抽出ロジック**:
1. 各ORDER詳細セクションのタスク一覧を検索
2. IN_PROGRESSまたはREWORKステータスのタスクを抽出
3. 担当Worker列から識別子を取得
4. アクティブでないWorkerは「待機中」として表示

---

## 6. レビューキュー（全ORDER横断）

### 6.1 レビューキュー全体表示

全ORDERのレビューキューを統合して表示：

```
【レビューキュー（全ORDER）】

| ORDER | Task ID | 提出日時 | ステータス | 優先度 | 備考 |
|-------|---------|---------|----------|--------|------|
| ORDER_020 | TASK_203 | 2026-01-19 10:00 | PENDING | P1 | - |
| ORDER_019 | TASK_147 | 2026-01-19 09:30 | PENDING | P1 | - |
| ORDER_020 | TASK_201 | 2026-01-19 08:00 | IN_REVIEW | P0 | 再提出 |
```

**表示ルール**:
- 優先度順（P0 > P1 > P2）でソート、同優先度は提出日時順（FIFO）
- P0は「**」で強調
- レビューキューが空の場合：「レビューキュー: 空」と表示
- 単一ORDERモード時は従来の形式で表示（ORDERカラムなし）

### 6.2 PM状況サマリ

```
### PM
- レビュー中: {IN_REVIEWステータスのTask ID} または「なし」
- レビュー待ち: {全ORDERのPENDING件数}件
- 差し戻し対応待ち: {全ORDERのREJECTED件数}件
```

---

## 7. 単一ORDERモード表示（従来互換）

マルチORDERモードでない場合は、従来の表示形式を維持：

### 7.1 PM/Worker現在状況表示

```
### PM
- レビュー中: {IN_REVIEWステータスのTask ID} または「なし」
- レビュー待ち: {PENDINGステータスの件数}件
- 差し戻し対応待ち: {REJECTEDステータスの件数}件

### Worker
- 実行中: {IN_PROGRESSステータスのTask ID} ({担当Worker}) または「なし」
- 実行可能: {QUEUEDステータスのTask ID一覧} または「なし」
- 差し戻し修正中: {REWORKステータスのTask ID} または「なし」
```

### 7.2 レビューキュー概要表示

```
### レビューキュー

| Task ID | ステータス | 優先度 | 備考 |
|---------|----------|--------|------|
| TASK_001 | IN_REVIEW | P1 | - |
| TASK_002 | PENDING | P0 (差戻) | 再提出 |
```

### 7.3 並行実行状況表示

#### 進行中タスク一覧

```
【実行中タスク】（並行実行中）

| Task ID | タスク名 | 担当 | 開始日 |
|---------|---------|------|--------|
| TASK_001 | 現状分析・設計 | Worker A | 2026-01-15 |
| TASK_003 | 実装A | Worker B | 2026-01-15 |
```

- `IN_PROGRESS`のタスクが0件の場合：「実行中タスクなし」と表示
- `IN_PROGRESS`のタスクが1件の場合：「実行中タスク: TASK_XXX（タスク名）」と表示
- `IN_PROGRESS`のタスクが2件以上の場合：上記テーブル形式で一覧表示

#### 待機中タスク（依存ブロック中）

```
【待機中タスク】（依存ブロック中）

| Task ID | タスク名 | ブロック理由 |
|---------|---------|-------------|
| TASK_005 | 統合テスト | TASK_003, TASK_004 未完了 |
```

- BLOCKEDステータスのタスク、または依存タスクが未完了のQUEUEDタスクを表示
- ブロック理由には未完了の依存タスクIDを列挙

#### 次に開始可能なタスク

```
【次に開始可能なタスク】
- TASK_006: ドキュメント更新（依存なし）
- TASK_007: リリース準備（TASK_003完了済み）
```

---

## 8. 差し戻しタスク警告表示（共通）

レビューキューにREJECTEDステータスのタスク、またはタスク一覧にREWORKステータスのタスクがある場合、警告を表示：

```
【要対応】差し戻しタスクあり

| ORDER | Task ID | タスク名 | 差し戻し理由の参照先 |
|-------|---------|---------|---------------------|
| ORDER_019 | TASK_XXX | XXX機能実装 | REVIEW_XXX.md |

差し戻しタスクは優先的に対応してください：
/aipm-worker PROJECT_NAME XXX
```

**表示条件**:
- レビューキューにREJECTEDステータスのタスクがある
- またはタスク一覧にREWORKステータスのタスクがある
- 両方存在する場合は統合して表示
- マルチORDERモード時はORDERカラムを追加

---

## 8.5. 中断タスク表示（INTERRUPTEDステータス対応）

タスク一覧にINTERRUPTEDステータスのタスクがある場合、専用セクションで表示：

### 8.5.1 中断タスク一覧（単一ORDERモード）

```
【注意】中断中のタスクがあります

| Task ID | タスク名 | 中断日時 | 最終チェックポイント |
|---------|---------|---------|---------------------|
| TASK_XXX | XXX機能実装 | 2026-01-21 10:30 | Step 3完了 |

リカバリするには:
/aipm-recover PROJECT_NAME
```

### 8.5.2 中断タスク一覧（マルチORDERモード）

```
【注意】中断中のタスクがあります

| ORDER | Task ID | タスク名 | 中断日時 | 最終チェックポイント |
|-------|---------|---------|---------|---------------------|
| ORDER_019 | TASK_XXX | XXX機能実装 | 2026-01-21 10:30 | Step 3完了 |
| ORDER_020 | TASK_YYY | YYY調査 | 2026-01-21 09:00 | 調査開始 |

リカバリするには:
/aipm-recover PROJECT_NAME
```

### 8.5.3 表示内容詳細

| 項目 | 内容 | 取得元 |
|------|------|--------|
| ORDER | ORDER ID | DBのタスク一覧（マルチORDERモード時） |
| Task ID | タスク識別子 | DBのタスク一覧 |
| タスク名 | タスクのタイトル | DBのタスク一覧 |
| 中断日時 | INTERRUPTEDに遷移した日時 | DBの状態遷移履歴 |
| 最終チェックポイント | 最後に保存されたチェックポイント | DBのチェックポイント情報 |

### 8.5.4 チェックポイント情報の取得

```
チェックポイント取得ロジック:
1. DBからタスクのチェックポイント情報を検索
2. 「チェックポイント」セクションを検索
3. 最新のチェックポイント情報を取得:
   - checkpoint_id: チェックポイント識別子
   - timestamp: 保存日時
   - description: 進捗説明
4. チェックポイント情報がDBにない場合：「チェックポイントなし」と表示
```

### 8.5.5 表示条件

- タスク一覧にINTERRUPTEDステータスのタスクがある場合に表示
- INTERRUPTEDタスクが0件の場合：このセクションをスキップ
- 差し戻しタスク（セクション8）の後、次のアクション（セクション9）の前に表示

---

## 9. 次のアクション提示（共通）

ステータスに応じた次に必要なアクションを提示。

### 9.1 マルチORDERモードの優先順位

1. **緊急ORDER対応**（P0 ORDERが待機中の場合）
   ```
   【緊急】P0 ORDER (ORDER_021) が待機中です。
   依存解決または優先対応を検討してください。
   ```

2. **中断タスクリカバリ**（INTERRUPTEDタスクがある場合）
   ```
   【注意】中断中のタスクがあります。
   リカバリするには: /aipm-recover PROJECT_NAME
   ```

3. **差し戻しタスク対応**（REJECTEDまたはREWORKがある場合）
   ```
   差し戻しタスクがあります。優先的に対応してください：
   /aipm-worker PROJECT_NAME XXX
   ```

4. **PMレビュー実行**（レビュー待ちがある場合）
   ```
   レビュー待ちタスクがあります（{件数}件）：
   /aipm-review PROJECT_NAME --next
   ```

5. **次タスク実行**（実行可能タスクがある場合）
   - 優先度の高いORDERのタスクを優先提示
   ```
   次のタスクを開始できます：
   [ORDER_019 P1] /aipm-worker PROJECT_NAME 152
   [ORDER_020 P2] /aipm-worker PROJECT_NAME 206
   ```

6. **待機**（全タスクがブロック中または実行中）
   ```
   実行中のタスク完了をお待ちください。
   ```

### 9.2 単一ORDERモードの優先順位

1. **中断タスクリカバリ**（INTERRUPTEDタスクがある場合）
   ```
   【注意】中断中のタスクがあります。
   リカバリするには: /aipm-recover PROJECT_NAME
   ```

2. **差し戻しタスク対応**（REJECTEDまたはREWORKがある場合）
   ```
   差し戻しタスクがあります。優先的に対応してください：
   /aipm-worker PROJECT_NAME XXX
   ```

3. **PMレビュー実行**（レビュー待ちがある場合）
   ```
   レビュー待ちタスクがあります：
   /aipm-review PROJECT_NAME --next
   ```

4. **次タスク実行**（実行可能タスクがある場合）
   ```
   次のタスクを開始できます：
   /aipm-worker PROJECT_NAME XXX
   ```

5. **待機**（全タスクがブロック中または実行中）
   ```
   実行中のタスク完了をお待ちください。
   ```

---

## 表示例

### マルチORDERモード（複数ORDER同時進行）

```
【プロジェクト状態】AI_PM_PJ
現在ステータス: IN_PROGRESS
アクティブORDER: 2 / 3（上限）
全体進捗: 38% (7/18)
最終更新: 2026-01-19 15:00

【アクティブORDER一覧】

| ORDER | タイトル | 優先度 | 進捗 | ステータス | 担当Worker |
|-------|---------|--------|------|----------|-----------|
| ORDER_019 | 複数ORDER同時進行 | P1 | 22% | IN_PROGRESS | Worker A |
| ORDER_020 | ドキュメント整備 | P2 | 83% | IN_PROGRESS | Worker B |

【待機ORDER】

| ORDER | タイトル | 優先度 | 理由 |
|-------|---------|--------|------|
| ORDER_021 | 緊急バグ修正 | P0 | 依存: ORDER_019 |

【ORDER_019】複数ORDER同時進行 (P1)
- 進捗: 2/9 タスク完了 (22%)
- 実行中: TASK_148 (Worker A)
- 次タスク: TASK_152, TASK_153, TASK_154
- レビュー待ち: 0件

【ORDER_020】ドキュメント整備 (P2)
- 進捗: 5/6 タスク完了 (83%)
- 実行中: TASK_205 (Worker B)
- 次タスク: なし
- レビュー待ち: 1件

【Worker配置】

| Worker | 担当ORDER | 担当TASK | ステータス |
|--------|----------|---------|----------|
| Worker A | ORDER_019 | TASK_148 | IN_PROGRESS |
| Worker B | ORDER_020 | TASK_205 | IN_PROGRESS |

【レビューキュー（全ORDER）】

| ORDER | Task ID | 提出日時 | ステータス | 優先度 | 備考 |
|-------|---------|---------|----------|--------|------|
| ORDER_020 | TASK_203 | 2026-01-19 10:00 | PENDING | P1 | - |

### PM
- レビュー中: なし
- レビュー待ち: 1件
- 差し戻し対応待ち: 0件

【次の推奨アクション】
1. 【緊急】P0 ORDER (ORDER_021) の依存解決を検討
2. [PM] ORDER_020 のレビュー待ちタスクをレビュー：
   /aipm-review AI_PM_PJ --next
3. [Worker] 追加タスク開始可能：
   [ORDER_019 P1] /aipm-worker AI_PM_PJ 152
```

### 単一ORDERモード（従来互換）

```
【プロジェクト状態】AI_PM_PJ
ORDER: ORDER_018
プロジェクト名: 並行稼働対応 Phase 2（v1.16.0）
ステータス: IN_PROGRESS
進捗: 2/7 タスク完了
最終更新: 2026-01-15 14:00

### PM
- レビュー中: なし
- レビュー待ち: 0件
- 差し戻し対応待ち: 0件

### Worker
- 実行中: TASK_143 (Worker A)
- 実行可能: TASK_144, TASK_145
- 差し戻し修正中: なし

### レビューキュー
キューは空です

【待機中タスク】（依存ブロック中）
- TASK_146: WORKFLOW.md・README.md更新 → TASK_143, 144, 145 未完了
- TASK_147: 動作確認・受け入れ条件テスト → TASK_146 未完了

【次に開始可能なタスク】
- TASK_144: aipm-review.md更新（TASK_142完了済み）
- TASK_145: aipm-status.md更新（TASK_142完了済み）

【次のアクション】
並行実行で追加のWorkerを起動できます：
/aipm-worker AI_PM_PJ 144
または
/aipm-worker AI_PM_PJ 145
```

### P0 ORDER発生時の表示例

```
【プロジェクト状態】AI_PM_PJ
現在ステータス: IN_PROGRESS
アクティブORDER: 3 / 3（上限）
全体進捗: 45% (18/40)
最終更新: 2026-01-19 16:00

【アクティブORDER一覧】

| ORDER | タイトル | 優先度 | 進捗 | ステータス | 担当Worker |
|-------|---------|--------|------|----------|-----------|
| **ORDER_021** | **緊急バグ修正** | **P0** | 0% | **IN_PROGRESS** | **Worker A** |
| ORDER_019 | 複数ORDER同時進行 | P1 | 50% | IN_PROGRESS | - |
| ORDER_020 | ドキュメント整備 | P2 | 83% | IN_PROGRESS | Worker B |

【警告】緊急ORDER (P0) が進行中です！
ORDER_021（緊急バグ修正）への最優先対応をお願いします。

【ORDER_021】緊急バグ修正 (P0) ⚠️
- 進捗: 0/3 タスク完了 (0%)
- 実行中: TASK_301 (Worker A)
- 次タスク: TASK_302, TASK_303
- レビュー待ち: 0件

【次の推奨アクション】
1. 【最優先】ORDER_021 (P0) のタスク完了を優先：
   現在 Worker A が TASK_301 を実行中
2. [Worker] P0 ORDER への追加リソース投入を検討：
   /aipm-worker AI_PM_PJ 302
```

### INTERRUPTED発生時の表示例（単一ORDERモード）

```
【プロジェクト状態】AI_PM_PJ
ORDER: ORDER_034
プロジェクト名: エラーハンドリング・リカバリ強化
ステータス: INTERRUPTED
進捗: 2/6 タスク完了
中断中タスク: 1件
最終更新: 2026-01-21 15:30

### PM
- レビュー中: なし
- レビュー待ち: 0件
- 差し戻し対応待ち: 0件

### Worker
- 実行中: なし
- 実行可能: TASK_180
- 差し戻し修正中: なし

### レビューキュー
キューは空です

【注意】中断中のタスクがあります

| Task ID | タスク名 | 中断日時 | 最終チェックポイント |
|---------|---------|---------|---------------------|
| TASK_178 | aipm-worker.mdへのチェックポイント記録 | 2026-01-21 14:30 | Step 2: 設計完了 |

リカバリするには:
/aipm-recover AI_PM_PJ

【次の推奨アクション】
1. 【注意】中断中のタスクがあります。
   リカバリするには: /aipm-recover AI_PM_PJ
2. [Worker] 実行可能タスクあり：
   /aipm-worker AI_PM_PJ 180
```

### INTERRUPTED発生時の表示例（マルチORDERモード）

```
【プロジェクト状態】AI_PM_PJ
現在ステータス: INTERRUPTED
アクティブORDER: 2 / 3（上限）
全体進捗: 40% (8/20)
中断中タスク: 2件
最終更新: 2026-01-21 15:30

【アクティブORDER一覧】

| ORDER | タイトル | 優先度 | 進捗 | ステータス | 担当Worker |
|-------|---------|--------|------|----------|-----------|
| ORDER_034 | エラーハンドリング強化 | P1 | 33% | INTERRUPTED | - |
| ORDER_035 | ドキュメント整備 | P2 | 50% | IN_PROGRESS | Worker B |

【注意】中断中のタスクがあります

| ORDER | Task ID | タスク名 | 中断日時 | 最終チェックポイント |
|-------|---------|---------|---------|---------------------|
| ORDER_034 | TASK_178 | チェックポイント記録 | 2026-01-21 14:30 | Step 2完了 |
| ORDER_034 | TASK_179 | aipm-recover.md作成 | 2026-01-21 14:45 | 設計開始 |

リカバリするには:
/aipm-recover AI_PM_PJ

【次の推奨アクション】
1. 【注意】中断中のタスク（2件）があります。
   リカバリするには: /aipm-recover AI_PM_PJ
2. [Worker] ORDER_035 のタスクは継続可能：
   /aipm-worker AI_PM_PJ 301
```

---

## 後方互換性

- 「アクティブORDER一覧」セクションが存在しない場合：単一ORDERモードで動作
- レビューキューセクションが存在しない場合：PM状況セクションとレビューキュー概要をスキップ
- DONEステータスが存在しない場合：従来通りCOMPLETED扱いで動作
- DB未登録プロジェクトでは初期化を促すメッセージを表示
- ORDER詳細セクションがない場合：従来の「タスク一覧」セクションを使用
- INTERRUPTEDステータスが存在しない場合：中断タスクセクションをスキップ
- チェックポイント情報がDBにない場合：「チェックポイントなし」と表示

---

## 付録：抽出ロジック詳細

### A.1 マルチORDERモード判定ロジック

```
マルチORDER判定:
1. DBからプロジェクト状態を取得
2. 「アクティブORDER一覧」セクションを検索
3. IF セクションが存在しない:
     RETURN 単一ORDERモード
4. テーブル行を解析（ヘッダー・区切り行を除く）
5. IF 有効なORDERエントリが0-1件:
     RETURN 単一ORDERモード
6. IF 有効なORDERエントリが2件以上:
     RETURN マルチORDERモード
```

### A.2 全ORDER横断レビューキュー集計ロジック

```
レビューキュー集計:
1. アクティブORDER一覧を取得
2. 各ORDERについて:
   a. 「レビューキュー（ORDER_XXX）」セクションを検索
   b. テーブル行を解析
   c. 各エントリにORDER IDを付加
3. 全エントリを統合
4. 優先度順（P0 > P1 > P2）、提出日時順でソート
5. 結果を返す
```

### A.3 Worker配置状況集計ロジック

```
Worker配置集計:
1. 空のWorkerマップを作成
2. 各ORDER詳細セクションについて:
   a. タスク一覧を検索
   b. IN_PROGRESS/REWORKステータスのタスクを抽出
   c. 担当Worker列から識別子を取得
   d. WorkerマップにORDER ID、Task ID、ステータスを追加
3. 結果をWorker名順でソート
4. 結果を返す
```
