---
description: AI PM フレームワーク自動起動 - プロジェクト状態を分析し、次のアクションをガイド（マルチORDER対応）
allowed-tools: Glob(**/*.md), Read(**/README.md), Read(**/.framework/BOOTSTRAP.md), Read(**/ORDER_*.md), Bash(python backend/*)
---

# AI PM フレームワーク自動起動

AI PM フレームワークを起動します。以下の手順を自動実行してください：

**引数**:
- 第1引数: プロジェクト名（オプション、例: AI_PM_PJ）
- `--all`: 非アクティブプロジェクトも含めて表示

引数が提供された場合、以下のように解析してください：
- `AI_PM_PJ` を `$PROJECT_NAME` として使用
- `--all` を含む場合: 非アクティブプロジェクトも表示
- 引数なしの場合: アクティブプロジェクトのみスキャン（デフォルト動作）

---

## Step 0: 引数チェック

引数の有無を確認し、動作モードを決定：

| 引数 | 動作モード | 処理内容 |
|------|-----------|---------|
| `PROJECT_NAME` | 単一プロジェクト | DBから指定プロジェクトの状態を取得 |
| なし | 全プロジェクト | アクティブプロジェクトのみ表示（デフォルト） |
| `--all` | 全プロジェクト（全件） | 非アクティブプロジェクトも含めて表示 |

### --all オプションについて

`--all` オプションは非アクティブプロジェクト（アーカイブ済み、一時停止中など）も含めて表示するためのオプションです。

**デフォルト動作（--all なし）**:
- `is_active = True` のプロジェクトのみ表示
- 過去に完了した非アクティブプロジェクトは非表示

**--all 指定時**:
- `is_active` に関係なく全プロジェクトを表示
- 非アクティブプロジェクトには `(inactive)` マークを付与

---

## Step 0.5: 統合ステータス取得（DB中心アーキテクチャ対応）

統合スクリプト `backend/status/aipm_status.py` を **1回だけ** 実行し、プロジェクト・ORDER・タスクの全データを一括取得します。

### 0.5.1 DB利用可能判定

以下の条件を順に確認：

```
DB利用可能判定:
1. backend/ ディレクトリが存在するか確認
2. data/aipm.db ファイルが存在するか確認
3. 両方存在 → DBモード（統合スクリプト実行）
4. いずれか存在しない → フォールバック（限定情報表示）
```

### 0.5.2 統合スクリプトによるデータ取得

DBが利用可能な場合、**1回のスクリプト呼び出し**で全データを取得：

**単一プロジェクトモード（引数あり）**:

```bash
python backend/status/aipm_status.py $PROJECT_NAME --json
```

**全プロジェクトモード（引数なし、デフォルト: アクティブのみ）**:

```bash
python backend/status/aipm_status.py --json
```

**全プロジェクトモード（--all: 非アクティブ含む）**:

```bash
python backend/status/aipm_status.py --all --json
```

> **重要**: 従来は `project/list.py`, `order/list.py`, `task/list.py` を個別に呼び出していたが、
> `aipm_status.py` に統合され **1回のPython起動・1回のDB接続** で全データを取得する。
> 上記3パターンのうち、引数に応じた **1つだけ** を実行すること。

### 0.5.3 統合JSON出力のデータ構造

統合スクリプトの `--json` 出力は以下の構造を持つ：

```json
{
  "projects": [
    {
      "id": "ai_pm_manager_v2",
      "name": "ai_pm_manager_v2",
      "status": "IN_PROGRESS",
      "is_active": true,
      "order_count": 10,
      "active_order_count": 2,
      "completed_order_count": 7,
      "draft_order_count": 1,
      "task_count": 50,
      "completed_task_count": 40,
      "in_progress_task_count": 2,
      "blocked_task_count": 0,
      "rework_task_count": 0,
      "queued_task_count": 3,
      "done_task_count": 1,
      "task_progress_percent": 80,
      "active_orders": [
        {
          "id": "ORDER_096",
          "title": "Python起動コスト削減",
          "priority": "P1",
          "status": "IN_PROGRESS",
          "task_count": 3,
          "completed_task_count": 1,
          "in_progress_task_count": 1,
          "progress_percent": 33,
          "tasks": [
            {
              "id": "TASK_337",
              "title": "統合スクリプト作成",
              "status": "COMPLETED",
              "priority": "P1",
              "assignee": "worker"
            },
            {
              "id": "TASK_338",
              "title": "スキル定義の変更",
              "status": "IN_PROGRESS",
              "priority": "P1",
              "assignee": "worker"
            }
          ]
        }
      ]
    }
  ],
  "draft_orders": [
    {
      "id": "ORDER_097",
      "project_id": "ai_pm_manager_v2",
      "title": "次の改善",
      "priority": "P2",
      "status": "DRAFT",
      "created_at": "2026-02-26T..."
    }
  ],
  "backlog_summary": {
    "total_items": 5,
    "todo_count": 3,
    "in_progress_count": 1,
    "high_priority_count": 1
  },
  "metadata": {
    "timestamp": "2026-02-26T...",
    "data_source": "sqlite",
    "mode": "single_project",
    "query_count": 8,
    "project_count": 1
  }
}
```

**データマッピング（従来の個別スクリプト → 統合JSON）**:

| 従来の呼び出し | 統合JSONでの対応箇所 |
|---------------|---------------------|
| `project/list.py --json` | `projects[]` （プロジェクト一覧） |
| `order/list.py --active --json` | `projects[].active_orders[]` （各プロジェクトのアクティブORDER） |
| `order/list.py --draft --json` | `draft_orders[]` （DRAFTステータスのORDER一覧） |
| `task/list.py --status IN_PROGRESS --json` | `projects[].in_progress_task_count` + `projects[].active_orders[].tasks[]` でstatus=IN_PROGRESSをフィルタ |
| `task/list.py --status QUEUED --limit 1 --json` | `projects[].active_orders[].tasks[]` でstatus=QUEUEDの先頭を使用 |

### 0.5.4 フォールバック処理

統合スクリプト実行に失敗した場合、または DB が存在しない場合はフォールバック：

```
フォールバック条件:
1. backend/ が存在しない
2. data/aipm.db が存在しない
3. 統合スクリプトがエラーで終了（exit code != 0）
4. 統合スクリプトの出力が空またはJSONパースエラー

フォールバック時の動作:
→ プロジェクトディレクトリの存在確認のみ実施
→ Step 1 の処理に進む（限定的な情報で表示）
```

### 0.5.5 データソースインジケータ表示（オプション）

データ取得元を表示する場合のフォーマット：

```
【データソース】
- モード: DB優先（統合スクリプト）
- DB: ✓ (data/aipm.db)
- スクリプト: ✓ (backend/status/aipm_status.py)
- クエリ数: {metadata.query_count}
```

または（フォールバック時）:

```
【データソース】
- モード: フォールバック（限定情報）
- 理由: 統合スクリプトが利用不可
```

### 0.5.6 統合JSONからの表示データ構築

統合JSONから取得したデータを表示フォーマットに変換：

| 統合JSON項目 | 表示項目 |
|-------------|---------|
| `projects[].active_orders[].id` | ORDER ID |
| `projects[].active_orders[].title` | ORDERタイトル |
| `projects[].active_orders[].status` | ステータス |
| `projects[].active_orders[].priority` | 優先度 |
| `projects[].active_orders[].progress_percent` | 進捗率 |
| `projects[].active_orders[].tasks[]` でstatus=IN_PROGRESS | 実行中タスク |
| `projects[].active_orders[].tasks[]` でstatus=QUEUED の先頭 | 次のタスク |

---

## Step 1: プロジェクト検索

### 統合スクリプト実行済みの場合（Step 0.5でデータ取得成功）

統合JSONの `projects` 配列からプロジェクト情報を取得済み。追加のスクリプト呼び出しは不要。

```
統合スクリプト成功時の処理フロー:
1. projects 配列の件数を確認
2. 件数 > 0: データを使用してStep 3へ進む
3. 件数 = 0:
   - 単一プロジェクトモードの場合 → プロジェクト未登録エラー
   - 全プロジェクトモードの場合 → プロジェクトなしメッセージ
```

### 引数ありの場合（単一プロジェクトモード）

1. 統合JSONの `projects` 配列を確認
2. **プロジェクトが見つかった場合（配列に1件以上）**:
   - 統合JSONのデータを使用してStep 3へ
3. **プロジェクトが見つからない場合（配列が空）**: 以下のエラーメッセージを表示して終了

```
エラー: プロジェクト '$PROJECT_NAME' が見つかりません。

利用可能なプロジェクト:
（python backend/status/aipm_status.py --json を実行して全プロジェクトを取得し、名前を列挙）

使用方法:
/aipm [PROJECT_NAME]

例:
/aipm AI_PM_PJ    # 指定プロジェクトのみ表示
/aipm             # 全プロジェクトを表示
```

### 引数なしの場合（全プロジェクトモード）

統合JSONの `projects` 配列がそのまま一覧として使用可能。

**フォールバック（統合スクリプト利用不可時）**:
1. `Glob PROJECTS/*/` でプロジェクトディレクトリを検索
2. 各プロジェクトのディレクトリ存在を確認
3. ※ フォールバック時は詳細情報が取得できないため、DBセットアップを推奨

---

## Step 2: フレームワーク README の読み込み
フレームワークREADMEを読み込み、自動起動トリガーを理解してください：
- パス: `README.md`

---

## Step 3: プロジェクト状態の判定・アクション提示

### 統合JSONからの状態判定

統合JSONの `projects[]` の情報から状態を判定：

```
統合JSONでの状態判定:
1. active_order_count == 0 → COMPLETED または INITIAL または DRAFT_ONLY
   - completed_order_count > 0 かつ status == 'COMPLETED' → COMPLETED
   - order_count == 0 → INITIAL
   - draft_order_count > 0 → DRAFT_ONLY（draft_ordersセクションを表示し昇格を提案）
2. active_order_count >= 1 → IN_PROGRESS
   - active_orders[] 内の各ORDERのstatusを確認
   - draft_orders[] も併せて表示
```

**次のタスク取得**（統合JSONから）:

統合JSONの `projects[].active_orders[].tasks[]` から、`status == "QUEUED"` のタスクを探す。
tasks配列はステータス順（IN_PROGRESS→REWORK→DONE→QUEUED→BLOCKED）でソート済みなので、
最初に見つかったQUEUEDタスクが次のタスクとなる。

> **注意**: 追加のスクリプト呼び出しは不要。統合JSONに全タスク情報が含まれている。

### フォールバック時の状態判定

DBが利用できない場合は、プロジェクトディレクトリ情報のみで状態を推定：

| 判定条件 | 推定ステータス | アクション |
|----------|---------------|-----------|
| `RESULT/ORDER_*/` が存在しない | `INITIAL` | ユーザーにORDER_001.mdの記入を促す |
| `RESULT/ORDER_*/` が存在 | `IN_PROGRESS` | DB登録を促す |

**推奨**: フォールバック時は正確な状態判定ができないため、DBのセットアップを推奨してください。

---

## Step 3.5: マルチORDERモード判定

統合JSONの `projects[].active_order_count` に基づいて、複数ORDER同時進行モードかどうかを判定：

### 判定ロジック

```
1. projects[].active_order_count を取得
2. active_order_count に基づく分岐:
   - 0件: 「アクティブORDERがありません」→ 新規ORDER作成を提案
   - 1件: 単一ORDERモードとして動作（従来動作）
   - 2件以上: マルチORDERナビゲーション（Step 3.6へ）
```

---

## Step 3.6: マルチORDERナビゲーション

複数のアクティブORDERがある場合、統合JSONのデータから以下の情報を表示：

### 3.6.1 ORDER状況の収集

統合JSONの `projects[].active_orders[]` から以下を取得（追加スクリプト呼び出し不要）：
- `active_orders[].id`: ORDER ID
- `active_orders[].title`: タイトル
- `active_orders[].priority`: 優先度（P0/P1/P2/P3）
- `active_orders[].progress_percent`: 進捗率
- `active_orders[].status`: ステータス
- `active_orders[].tasks[]` で `status == "DONE"` の件数: レビュー待ちタスク数

また、DRAFT ORDERは `draft_orders[]` から取得（該当プロジェクトの `project_id` でフィルタ）。

### 3.6.2 推奨アクションの決定

以下の優先順位で推奨アクションを決定：

| 優先度 | 条件 | 推奨アクション |
|--------|------|----------------|
| 1 | P0（緊急）のORDERあり | 緊急対応を最優先 |
| 2 | レビュー待ちタスクあり | レビュー実施を提案 |
| 3 | 完了間近（80%以上）のORDERあり | 完了を優先 |
| 4 | 優先度順 | P1 > P2 > P3 の順に提案 |

### 3.6.3 ORDER間依存関係の警告

DBから取得したORDER依存関係情報を確認し：
- **NOT_SATISFIED**の依存がある場合は警告表示
- 依存先ORDERの完了状況を表示
- ブロックされているORDERを明示

### 3.6.4 マルチORDERナビゲーション表示フォーマット

```
## AI PM Framework - マルチORDERモード

### アクティブORDER一覧

| ORDER | タイトル | 優先度 | 進捗 | ステータス |
|-------|---------|--------|------|----------|
| ORDER_019 | 複数ORDER同時進行 | P1 | 44% | IN_PROGRESS |
| ORDER_020 | ドキュメント整備 | P2 | 83% | IN_PROGRESS |

### 推奨アクション

1. **[P1] ORDER_019**: 複数ORDER同時進行（進行中）
   - 次のタスク: TASK_152（aipm-pm.md更新）
   - コマンド: `/aipm-worker AI_PM_PJ 152`

2. **[P2] ORDER_020**: ドキュメント整備（完了間近 83%）
   - 次のタスク: TASK_207（最終確認）
   - コマンド: `/aipm-worker AI_PM_PJ 207`

### 依存関係警告（該当がある場合のみ表示）

⚠️ 以下のORDERは依存関係により待機中です：
- ORDER_022 は ORDER_019 の完了を待機中（FINISH_TO_START）

### DRAFT ORDER（バックログ相当）

DRAFT ORDERが存在する場合、以下のセクションも表示：

```
### DRAFT ORDER（バックログ）

| ORDER | タイトル | 優先度 | 作成日 |
|-------|---------|--------|--------|
| ORDER_025 | パフォーマンス改善 | P2 | 2026-02-20 |
| ORDER_026 | ドキュメント自動生成 | P3 | 2026-02-22 |

DRAFT ORDERをPLANNINGに昇格するには:
/aipm-pm PROJECT_NAME ORDER_NUMBER
```

### 選択肢

どのORDERを対象にしますか？
- A. ORDER_019を続行（優先度高）
- B. ORDER_020を完了させる（完了間近）
- C. 全ORDER状況を確認 (`/aipm-status AI_PM_PJ`)
- D. 特定ORDERのタスクを直接指定
- E. DRAFT ORDERをPLANNINGに昇格（DRAFT ORDERがある場合のみ表示）
```

---

## Step 4: ユーザーをガイド
現在の状態に基づいて、明確で実行可能な次のステップを日本語で提示してください。

**出力形式例（単一プロジェクト指定時）**:
```
## AI PM Framework - 現在の状態

### プロジェクト: AI_PM_PJ
- ステータス: IN_PROGRESS
- ORDER: ORDER_014 (スラッシュコマンド改善 v1.12.0)
- 進捗: 1/6タスク完了

---

## 次のアクション

次のタスク: TASK_069（/aipmスキルの日本語化）

以下のコマンドで継続できます：
/aipm-worker AI_PM_PJ 069
```

**出力形式例（全プロジェクトスキャン時）**:
```
## AI PM Framework - 現在の状態

2つのアクティブなプロジェクトを検出しました：

### プロジェクト1: AI_PM_PJ
- ステータス: IN_PROGRESS
- ORDER: ORDER_014 (スラッシュコマンド改善 v1.12.0)
- 進捗: 1/6タスク完了

### プロジェクト2: SIS_batch_investigation
- ステータス: COMPLETED
- ORDER: ORDER_003 (PostgreSQLトランザクションエラー修正)

---

## 次のアクション

AI_PM_PJ プロジェクトでタスクが進行中です：
- 次のタスク: TASK_069（/aipmスキルの日本語化）

以下のコマンドで継続できます：
/aipm-worker AI_PM_PJ 069
```

**出力形式例（--all オプション指定時）**:
```
## AI PM Framework - 現在の状態

全プロジェクト一覧（アクティブ + 非アクティブ）：

### アクティブプロジェクト

| ID | 名前 | ステータス | 進捗 |
|----|------|------------|------|
| AI_PM_PJ | AI PM Framework | IN_PROGRESS | 75% |
| SIS_batch | バッチ調査 | REVIEW | 100% |

### 非アクティブプロジェクト

| ID | 名前 | ステータス | 理由 |
|----|------|------------|------|
| Old_Project | 旧プロジェクト (inactive) | COMPLETED | アーカイブ済み |
| Test_PJ | テストプロジェクト (inactive) | ON_HOLD | 一時停止中 |

---

## 補足

非アクティブプロジェクトはデフォルトでは非表示です。
`/aipm` でアクティブプロジェクトのみ表示されます。
```

**出力形式例（マルチORDERモード時）**:
```
## AI PM Framework - マルチORDERモード

### プロジェクト: AI_PM_PJ
- ステータス: IN_PROGRESS
- アクティブORDER: 3件

### アクティブORDER一覧

| ORDER | タイトル | 優先度 | 進捗 | ステータス |
|-------|---------|--------|------|----------|
| ORDER_021 | 緊急バグ修正 | P0 | 0% | QUEUED |
| ORDER_019 | 複数ORDER同時進行 | P1 | 44% | IN_PROGRESS |
| ORDER_020 | ドキュメント整備 | P2 | 83% | IN_PROGRESS |

### 推奨アクション

🚨 **緊急対応が必要です**

1. **[P0] ORDER_021**: 緊急バグ修正
   - 次のタスク: TASK_210（バグ調査）
   - コマンド: `/aipm-worker AI_PM_PJ 210`

2. **[P2] ORDER_020**: ドキュメント整備（完了間近 83%）
   - 次のタスク: TASK_207（最終確認）
   - コマンド: `/aipm-worker AI_PM_PJ 207`

### 依存関係警告

⚠️ 以下のORDERは依存関係により待機中です：
- ORDER_022 は ORDER_019 の完了を待機中（FINISH_TO_START）

---

どのORDERを対象にしますか？
- A. ORDER_021を開始（緊急P0）
- B. ORDER_020を完了させる（完了間近）
- C. ORDER_019を続行
- D. 全ORDER状況を確認 (`/aipm-status AI_PM_PJ`)
```

---

## 実行例

### 1. 特定プロジェクトを指定して起動
```
/aipm AI_PM_PJ
```
→ AI_PM_PJ プロジェクトの状態のみを表示

**内部処理**:
```bash
python backend/status/aipm_status.py AI_PM_PJ --json
```

### 2. アクティブプロジェクトをスキャンして起動（デフォルト動作）
```
/aipm
```
→ アクティブプロジェクトのみスキャンして状態を表示
→ `is_active = True` のプロジェクトのみ

**内部処理**:
```bash
python backend/status/aipm_status.py --json
```

### 2.1 全プロジェクトを表示（非アクティブ含む）
```
/aipm --all
```
→ PROJECTS/ 配下の全プロジェクトをスキャンして状態を表示
→ 非アクティブプロジェクトには `(inactive)` マークを付与

**内部処理**:
```bash
python backend/status/aipm_status.py --all --json
```

### 3. マルチORDERプロジェクトの起動
```
/aipm AI_PM_PJ
```
→ 複数のアクティブORDERがある場合、マルチORDERナビゲーションを表示
→ 優先度順、完了間近順で推奨アクションを提示
→ ORDER間依存関係の警告を表示

### 4. 統合スクリプトでの起動（v2.0.0+）
```
/aipm AI_PM_PJ
```
→ `backend/status/aipm_status.py` が **1回のPython起動・1回のDB接続** で全データを取得
→ 従来の3-4回のPython起動が不要になり、高速な状態表示を実現

### 5. フォールバック動作
```
/aipm AI_PM_PJ
```
→ 統合スクリプトが利用できない場合、プロジェクトディレクトリ情報のみで限定的に表示
→ 完全な情報表示にはDBセットアップが必要

---

## 後方互換性

### DB中心アーキテクチャとの互換性

| 条件 | データソース | 動作 |
|------|-------------|------|
| `backend/status/aipm_status.py` + `data/aipm.db` 存在 | 統合スクリプト | 1回のスクリプト呼び出しで全データ取得 |
| 統合スクリプト実行エラー | フォールバック | プロジェクトディレクトリ情報のみで限定表示 |
| DBなし（旧環境） | 限定情報 | DBセットアップを推奨（TEMPLATE/SETUP.md参照） |

### is_active フィルタリングについて

| オプション | 動作 | 用途 |
|-----------|------|------|
| なし | アクティブプロジェクトのみ表示（デフォルト） | 日常の作業時 |
| `--all` | 全プロジェクト表示（非アクティブ含む） | 過去プロジェクト確認時 |

**注意**: フォールバック時は `is_active` フィルタは適用されません。

### 単一ORDERモードとマルチORDERモードの自動判定

| 条件 | 動作モード |
|------|-----------|
| `projects[].active_order_count` が0件 | 新規ORDER作成を促す |
| `projects[].active_order_count` が1件 | 単一ORDERモード |
| `projects[].active_order_count` が2件以上 | マルチORDERナビゲーション |

既存プロジェクトは自動的に単一ORDERモードで動作し、破壊的変更なく利用可能です。
DB中心アーキテクチャは必須となり、DBがない環境ではセットアップを推奨します。

---

**注**: このコマンドはフレームワーク README.md を読み込みます。README には完全な自動起動ロジックが含まれており、起動プロセス全体をガイドします。
