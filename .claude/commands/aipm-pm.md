---
description: PM役としてORDERを処理
argument-hint: PROJECT_NAME ORDER_NUMBER [--script] [--new-order] [--priority P1] [--pause] [--resume] [--set-priority P0] [--interrupt TASK_NUMBER "追加要件"]
---

PMとして指定されたプロジェクトの ORDER を処理します。

**引数**:
- 第1引数: プロジェクト名（例: AI_PM_PJ）
- 第2引数: ORDER番号（例: 014）または `new`（新規ORDER作成時）
- オプション:
  - `--script` - スクリプトモード（1コマンドで全処理を実行）
  - `--new-order` - 新規ORDER作成
  - `--priority P1` - 優先度指定（P0/P1/P2/P3）
  - `--pause` - ORDER一時停止
  - `--resume` - ORDER再開
  - `--set-priority P0` - 優先度変更
  - `--interrupt TASK_NUMBER "追加要件"` - 割り込みタスクを発行

---

## スクリプトモード（--script）: 1コマンドで全処理を実行

`--script` オプションを指定すると、親スクリプトを使用して1コマンドでPM処理全体を実行します。

**使用方法**:
```bash
# 通常のスクリプトモード
python backend/pm/process_order.py $PROJECT_NAME $ORDER_NUMBER

# ドライラン（実行計画のみ表示）
python backend/pm/process_order.py $PROJECT_NAME $ORDER_NUMBER --dry-run

# 詳細ログ出力
python backend/pm/process_order.py $PROJECT_NAME $ORDER_NUMBER --verbose
```

**スクリプトモードの内部処理**:
1. ORDER.md 読み込み
2. claude -p で要件定義生成（GOAL/REQUIREMENTS/STAFFING）
3. claude -p でタスク分割生成
4. order/create.py でDB登録
5. task/create.py でタスク作成
6. Markdown成果物生成

**メリット**:
- ツール呼び出し回数: 5-10回/処理 → 1回
- フロー漏れリスク: なし（Python保証）
- トークン消費: 50-70%削減

**--script 指定時の実行フロー**:
```
IF --script オプションあり THEN
    python backend/pm/process_order.py $PROJECT_NAME $ORDER_NUMBER を実行
    スクリプト出力を表示
    処理終了
ELSE
    従来のステップ別処理を実行（下記参照）
END IF
```

---

引数解析ルール：
- `$ARGUMENTS` をスペースで分割
- 第1引数を `PROJECT_NAME`、第2引数を `ORDER_NUMBER` として使用
- オプションフラグに応じてモードを切り替え
- 引数が1つのみの場合: エラーメッセージ「エラー: プロジェクト名とORDER番号を指定してください。使い方: /aipm-pm PROJECT_NAME ORDER_NUMBER」を表示
- 引数が0の場合: 同上

**実行モード**:

---

## スクリプト利用ガイド（DB中心アーキテクチャ）

### 利用可能なスクリプト

| カテゴリ | スクリプト | 用途 |
|---------|-----------|------|
| ORDER管理 | `python backend/order/create.py` | ORDER作成 |
| ORDER管理 | `python backend/order/update.py` | ORDER状態更新 |
| ORDER管理 | `python backend/order/list.py` | ORDER一覧取得 |
| タスク管理 | `python backend/task/create.py` | タスク作成 |
| タスク管理 | `python backend/task/update.py` | タスク状態更新 |
| タスク管理 | `python backend/task/list.py` | タスク一覧取得 |

### スクリプト実行パス

```
# 本番環境スクリプトを実行
python backend/order/create.py $PROJECT_NAME --title "ORDER名"
```

### 後方互換性

スクリプトが利用できない場合（エラー発生時）は、従来のEdit/Write直接操作にフォールバックしてください。

---

## モード1: 通常のORDER処理（--interruptなし、単一OR複数ORDER対応）

以下の手順を実行してください：

---

### Step 0: データソース判定（DB中心アーキテクチャ対応）

データ取得先を判定し、DB優先でプロジェクト状態を取得します。

#### 0.1 DB利用可能判定

以下の条件を順に確認：

```
DB利用可能判定:
1. backend/ ディレクトリが存在するか確認
2. data/aipm.db ファイルが存在するか確認
3. 両方存在 → DBモード
4. いずれか存在しない → 従来方式（Markdown直接読み込み）
```

#### 0.2 データソースインジケータ表示（オプション）

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

#### 0.3 フォールバック条件

以下の場合は従来方式にフォールバック：

```
フォールバック条件:
1. backend/ が存在しない
2. data/aipm.db が存在しない
3. DBスクリプトがエラーで終了（exit code != 0）
4. DBスクリプトの出力が空またはパースエラー

フォールバック時の動作:
→ エラーメッセージを表示しDBスクリプトの修復を促す
→ DBスクリプトが利用できない場合、処理を中断
```

---

### Step 1: アクティブORDER上限チェック（マルチORDER対応）

複数ORDERを同時に管理する場合、以下のチェックを実行：

#### 1.1 DBモードでの上限チェック

DBが利用可能な場合（Step 0でDBモードと判定された場合）:

**スクリプト呼び出し**:
```bash
# ORDER一覧からアクティブ件数を確認
python backend/order/list.py $PROJECT_NAME --active --summary --json
```

**取得できる情報**:
- active_count: アクティブORDER数
- recommended_max_active: 推奨上限（デフォルト3）
- hard_max_active: 絶対上限（デフォルト5）
- active_orders: アクティブORDERの詳細リスト

**出力例**:
```json
{
  "active_count": 2,
  "recommended_max_active": 3,
  "hard_max_active": 5,
  "active_orders": [
    {"id": "ORDER_041", "title": "各コマンドのDB優先化", "status": "IN_PROGRESS", "progress_percent": 25}
  ],
  "total_count": 41,
  "completed_count": 40,
  "on_hold_count": 0
}
```

**DBスクリプト成功時**:
- JSONから `active_count`、`recommended_max_active`、`hard_max_active` を取得
- 判定ロジック（1.3参照）に従って処理

**DBスクリプト失敗時**:
- フォールバック処理（1.2参照）へ

#### 1.2 フォールバック処理（従来方式）

DBスクリプトが利用できない場合、または失敗した場合：

- エラーメッセージを表示:「DBスクリプトが利用できません。DBを修復してください。」
- DBスクリプトが必須のため、処理を中断

#### 1.3 判定ロジック

```
上限チェックロジック:
1. active_count を取得（DBモードまたはフォールバック）
2. recommended_max_active = 3（デフォルト）
3. hard_max_active = 5（デフォルト）

4. IF active_count >= hard_max_active(5) THEN
     エラー: 「【エラー】アクティブORDER上限(5)に達しています。追加できません。
     既存ORDERを完了またはON_HOLDにしてください。」
     → 処理を中断

5. IF active_count >= recommended_max_active(3) THEN
     警告表示:
     「【警告】アクティブORDERが推奨上限(3)に達しています。

     現在のアクティブORDER:
     | ORDER ID | タイトル | ステータス |
     |----------|---------|----------|
     | ORDER_XXX | ... | IN_PROGRESS |
     ...

     選択肢:
     A. それでも追加する（上限5件まで）
     B. 既存ORDERを完了/ON_HOLDにする
     C. ORDER追加をキャンセル」

6. ELSE
     ORDER追加を許可、次のステップへ
```

#### 1.4 DBモードでの処理フロー例

```
DBモードでの上限チェックフロー:
1. python backend/order/list.py $PROJECT_NAME --active --summary --json を実行
2. 成功時:
   a. JSONから active_count, recommended_max_active, hard_max_active を取得
   b. active_orders から現在のアクティブORDER一覧も取得
   c. 判定ロジック（1.3）を実行
3. 失敗時:
   a. エラーメッセージを表示
   b. DBスクリプトの修復を促す
   c. 処理を中断
```

### 2. ORDER読み込み

- `PROJECTS/$PROJECT_NAME/ORDERS/ORDER_$ORDER_NUMBER.md` を読み込む
- ファイルが存在しない場合: 「エラー: ORDER_$ORDER_NUMBER.md が見つかりません。パス: PROJECTS/$PROJECT_NAME/ORDERS/ORDER_$ORDER_NUMBER.md」を表示
- 発注内容を理解する

### 3. 要件定義作成

- `PROJECTS/$PROJECT_NAME/RESULT/ORDER_$ORDER_NUMBER/01_GOAL.md` にプロジェクトゴールを明文化
- `PROJECTS/$PROJECT_NAME/RESULT/ORDER_$ORDER_NUMBER/02_REQUIREMENTS.md` に要件を整理・構造化
- `PROJECTS/$PROJECT_NAME/RESULT/ORDER_$ORDER_NUMBER/03_STAFFING.md` にタスク分解・計画を定義

### 4. ORDER作成・DB更新（マルチORDER対応）

**スクリプト利用時**:
```bash
# ORDER作成（DBに登録）
python backend/order/create.py $PROJECT_NAME --title "ORDERタイトル" --priority P1 --json
```

出力例:
```json
{
  "id": "ORDER_037",
  "title": "ORDERタイトル",
  "priority": "P1",
  "status": "PLANNING"
}
```

**フォールバック（スクリプト利用不可時）**:
DBスクリプトが利用できない場合はエラー終了。DBスクリプトの修復が必要です。

### 5. タスク発行（マルチORDER対応採番ルール）

**スクリプト利用時（ループで複数タスク作成）**:
```bash
# タスク作成（DBに登録）
python backend/task/create.py $PROJECT_NAME ORDER_$ORDER_NUMBER \
  --title "タスク名" \
  --priority P1 \
  --model Opus \
  --depends "TASK_188,TASK_189" \
  --json
```

出力例:
```json
{
  "id": "TASK_200",
  "title": "タスク名",
  "status": "BLOCKED",
  "priority": "P1",
  "recommended_model": "Opus",
  "depends_on": ["TASK_188", "TASK_189"]
}
```

**タスクID自動採番**:
- スクリプトはDB内の最大Task ID番号を取得し、自動で次の番号を採番
- ORDER間でTask IDは重複しない（グローバルユニーク）
- 依存タスクがあれば自動でBLOCKEDステータス、なければQUEUED

**フォールバック（スクリプト利用不可時）**:
`PROJECTS/$PROJECT_NAME/RESULT/ORDER_$ORDER_NUMBER/04_QUEUE/TASK_XXX.md` を作成。

#### タスクID採番ルール（ORDER間で重複しない）

```
タスクID採番ロジック:
1. 全アクティブORDERのタスク一覧からTask IDを収集
   - 各ORDER詳細セクションのタスク一覧を走査
   - 単一ORDERモードの場合は従来のタスク一覧を走査
2. 最大のTask ID番号を取得（例: TASK_156 → 156）
3. 新規タスクID = 最大番号 + 1
4. 連番で発行（例: TASK_157, TASK_158, ...）

注意:
- ORDER間でTask IDは重複しない（グローバルユニーク）
- 割り込みタスクは `TASK_XXX_INT` 形式で別採番
```

#### タスク発行時の処理

- 各タスクの完了条件を明確化
- DBの該当ORDERのタスク一覧を更新
- **推奨モデルの設定**: タスク複雑度に応じて推奨モデルを設定

#### モデル選択ガイダンス

タスク発行時に、以下の基準に従って推奨モデルを設定してください：

| モデル | 推奨用途 | コスト |
|--------|----------|--------|
| **Haiku** | ファイル探索、進捗確認、単純な検索・監視 | 低 |
| **Sonnet** | 設計レビュー、比較分析、調査タスク | 中 |
| **Opus** | コード作成、複雑な実装、重要な判断 | 高 |

**選択基準**:
- **Haiku**: 単純な読取・探索タスク。例：ファイル一覧取得、パターン検索、ステータス監視
- **Sonnet**: 分析・調査を伴うタスク。例：設計書レビュー、比較分析、技術調査
- **Opus**: 実装・判断を伴うタスク。例：コード実装、バグ修正、アーキテクチャ設計

**デフォルト**: 不明な場合は `Opus` を設定（安全側に倒す）

#### タスク粒度ガイドライン

**重要**: 各タスクは**10分以内で完了できる粒度**に分割してください。これはfull-auto実行時のタイムアウト防止に不可欠です。

| 粒度 | 目安時間 | 例 |
|------|---------|-----|
| 適切 | 5-10分 | 単一ファイルの機能追加、1機能のテスト作成、1コンポーネントの修正 |
| 大きすぎ | 15分以上 | 複数ファイルにまたがる大規模実装、全画面のリファクタリング |

**分割の基準**:
- 1タスク = 1ファイル（または密接に関連する2-3ファイル）の変更
- Electron TSX変更など重い実装は、コンポーネント単位で分割
- 「実装」と「テスト」は別タスクに分ける
- 迷ったら小さく分割する（結合より分割のほうが安全）

**Worker環境制約（必須遵守）**:
Workerはターミナル（CLI）操作のみ可能です。以下のGUI操作はWorkerでは**実行不可能**です:
- アプリケーション起動・画面操作
- スクリーンショット撮影・目視確認
- ブラウザ起動・Web画面操作
- GUIテスト（E2Eテスト等の画面操作を伴うもの）

**品質確認の代替手段**: GUI操作による確認が必要な場合は、以下のターミナル操作で代替してください:
- `npm run build` （ビルド成功確認）
- `tsc --noEmit` （型チェック）
- `npm test` （ユニットテスト実行）
- `eslint` / `prettier --check` （コード品質チェック）

**悪い例**:
- 「認証システムを実装する」→ 大きすぎ。ログイン画面/API/セッション管理/テストに分割
- 「全画面にダークモード対応を追加」→ 大きすぎ。画面単位で分割
- 「アプリを起動して画面を確認する」→ GUI操作不可。`npm run build && tsc --noEmit` で代替
- 「スクリーンショットを撮って比較する」→ GUI操作不可。ビルド成功+型チェックで代替

### 5.5 ORDER完了前 全タスクCOMPLETED確認（**必須**）

ORDER完了を宣言する前に、**必ず**全タスクがCOMPLETED状態であることを確認します。
このステップは**スキップ不可**です。

#### 5.5.1 全タスク状態確認

以下のスクリプトでORDER内の全タスク状態を取得：

```bash
python backend/task/list.py $PROJECT_NAME --order ORDER_$ORDER_NUMBER --json
```

#### 5.5.2 確認ロジック

```
ORDER完了前チェック:
1. ORDER_$ORDER_NUMBER に紐づく全タスクを取得
2. 各タスクのstatusを確認
3. IF 全タスクが COMPLETED THEN
     → ORDER完了処理に進む（Step 6へ）
4. ELSE
     → 【エラー】未完了タスクあり、ORDER完了を阻止
```

#### 5.5.3 未完了タスク検出時の処理

未完了タスク（status != COMPLETED）が存在する場合、以下を表示して**ORDER完了を阻止**：

```
【ORDER完了ブロック】ORDER_$ORDER_NUMBER

以下のタスクが未完了のため、ORDERを完了できません：

| Task ID | タスク名 | ステータス | 問題点 |
|---------|---------|----------|-------|
| TASK_XXX | {名前} | DONE | レビュー未完了 |
| TASK_YYY | {名前} | QUEUED | 未着手 |
| TASK_ZZZ | {名前} | REWORK | 差し戻し対応中 |

【必要なアクション】
- DONEタスク: レビューを実施してCOMPLETEDに → /aipm-review $PROJECT_NAME XXX
- QUEUED/IN_PROGRESSタスク: Worker実行を完了 → /aipm-worker $PROJECT_NAME YYY
- REWORKタスク: 修正を完了して再提出

全タスクがCOMPLETEDになるまでORDERは完了できません。
```

#### 5.5.4 ステータス別の問題点

| ステータス | 意味 | 必要なアクション |
|-----------|------|----------------|
| QUEUED | 未着手 | Worker実行が必要 |
| IN_PROGRESS | 実行中 | Worker完了待ち |
| DONE | Worker完了、レビュー待ち | PMレビューが必要 |
| REWORK | 差し戻し対応中 | Worker修正が必要 |
| BLOCKED | 依存待ち | 依存タスク完了待ち |
| ESCALATED | エスカレーション中 | User判断待ち |
| COMPLETED | 完了 | OK（問題なし） |

### 6. ORDER確認欄更新

- `PROJECTS/$PROJECT_NAME/ORDERS/ORDER_$ORDER_NUMBER.md` のPM記入欄にチェックを入れる

---

## モード2: 割り込みタスク発行（--interruptあり）

以下の手順を実行してください：

### 1. 割り込みタスクID採番

**スクリプト利用時**:
```bash
# 既存の割り込みタスクを確認
python backend/task/list.py $PROJECT_NAME --order ORDER_$ORDER_NUMBER --json | grep "TASK_${TASK_NUMBER}_INT"
```

**採番ロジック**:
- 0件 → `TASK_${TASK_NUMBER}_INT`
- 1件 → `TASK_${TASK_NUMBER}_INT_02`
- N件 → `TASK_${TASK_NUMBER}_INT_${N+1:02d}`

### 2. REQUIREMENTS.md更新

- `PROJECTS/$PROJECT_NAME/RESULT/ORDER_$ORDER_NUMBER/02_REQUIREMENTS.md` を読み込む
- 追加機能セクションを挿入:
  ```markdown
  ### 追加機能（割り込みタスク）
  - **F-INT-XXX**: {追加要件の内容}
  ```

### 3. GOAL.md更新

- `PROJECTS/$PROJECT_NAME/RESULT/ORDER_$ORDER_NUMBER/01_GOAL.md` を読み込む
- 成功基準に追加:
  ```markdown
  - [ ] {追加要件に対応する成功基準}
  ```

### 4. TASK_{TASK_NUMBER}_INT.md作成

**スクリプト利用時**:
```bash
python backend/task/create.py $PROJECT_NAME ORDER_$ORDER_NUMBER --task-id "TASK_${INTERRUPT_TASK_ID}" --title "{追加要件のタイトル}" --priority P0 --json
```

**フォールバック（スクリプト利用不可時）**:
`PROJECTS/$PROJECT_NAME/RESULT/ORDER_$ORDER_NUMBER/04_QUEUE/TASK_${INTERRUPT_TASK_ID}.md` を作成:

```markdown
# TASK_{INTERRUPT_TASK_ID}.md

## 基本情報
- **Task ID**: TASK_{INTERRUPT_TASK_ID}
- **タスク名**: {追加要件のタイトル}
- **担当**: Worker
- **ステータス**: QUEUED
- **優先度**: P0
- **割り込み元**: TASK_{TASK_NUMBER}

---

## タスク定義

### 実施内容
{追加要件の詳細}

### 完了条件
- [ ] {追加要件に対応する完了条件}
- [ ] REPORT_{INTERRUPT_TASK_ID}.mdを作成した

---

## 作業ノート（Worker記入・随時更新）

（作業開始時に記入）

---

## 完了報告（完了時のみ記入）

### 成果物
（完了時に記入）

### 完了条件チェック
（完了時に記入）

---

**作成日**: {今日の日付}
**作成者**: PM
**完了日**: -
```

### 5. DB更新

スクリプト利用時は自動更新。フォールバック時は:
- エラーメッセージを表示してDBスクリプトの修復を促す
- DBスクリプトが利用できない場合、処理を中断

### 6. 完了メッセージ表示

```
【割り込みタスク発行完了】
TASK_{INTERRUPT_TASK_ID}を発行しました。

タスク名: {追加要件のタイトル}
優先度: P0
ステータス: QUEUED
割り込み元: TASK_{TASK_NUMBER}

パス: PROJECTS/$PROJECT_NAME/RESULT/ORDER_$ORDER_NUMBER/04_QUEUE/TASK_{INTERRUPT_TASK_ID}.md

次のアクション:
/aipm-worker $PROJECT_NAME {INTERRUPT_TASK_ID（数字部分のみ、例: 075_INT）}
```

---

## モード3: ORDER一時停止（--pauseあり）

以下の手順を実行してください：

### 1. 対象ORDER確認

**スクリプト利用時**:
```bash
python backend/order/list.py $PROJECT_NAME --status IN_PROGRESS --json | grep "ORDER_$ORDER_NUMBER"
```

**フォールバック**:
- エラーメッセージを表示してDBスクリプトの修復を促す
- DBスクリプトが利用できない場合、処理を中断

### 2. 確認プロンプト表示

```
【ORDER一時停止確認】ORDER_$ORDER_NUMBER を一時停止しますか？

現在の状態:
- ステータス: IN_PROGRESS
- 進捗: XX%
- 実行中タスク: TASK_XXX (Worker A)

一時停止すると:
- 実行中タスクはQUEUEDに戻ります
- 担当Workerは解放されます
- ON_HOLD状態になり、--resumeで再開できます

[Y/n]:
```

### 3. DB更新

**スクリプト利用時**:
```bash
# ORDER状態をON_HOLDに更新
python backend/order/update.py $PROJECT_NAME ORDER_$ORDER_NUMBER --status ON_HOLD --reason "一時停止"

# 実行中タスクをQUEUEDに戻す
python backend/task/update.py $PROJECT_NAME TASK_XXX --status QUEUED --assignee "" --role PM
```

**フォールバック**:
DBスクリプトが利用できない場合はエラー終了。DBスクリプトの修復が必要です。

### 4. 完了メッセージ表示

```
【ORDER一時停止完了】
ORDER_$ORDER_NUMBER を一時停止しました。

再開するには:
/aipm-pm $PROJECT_NAME $ORDER_NUMBER --resume
```

---

## モード4: ORDER再開（--resumeあり）

以下の手順を実行してください：

### 1. アクティブORDER上限チェック

モード1と同様の上限チェックを実行。

### 2. 対象ORDER確認

**スクリプト利用時**:
```bash
python backend/order/list.py $PROJECT_NAME --on-hold --json | grep "ORDER_$ORDER_NUMBER"
```

**フォールバック**:
- エラーメッセージを表示してDBスクリプトの修復を促す
- DBスクリプトが利用できない場合、処理を中断

### 3. DB更新

**スクリプト利用時**:
```bash
python backend/order/update.py $PROJECT_NAME ORDER_$ORDER_NUMBER --status IN_PROGRESS --reason "再開"
```

**フォールバック**:
DBスクリプトが利用できない場合はエラー終了。DBスクリプトの修復が必要です。

### 4. 完了メッセージ表示

```
【ORDER再開完了】
ORDER_$ORDER_NUMBER を再開しました。

次のアクション:
/aipm-status $PROJECT_NAME でタスク状況を確認してください。
```

---

## モード5: 優先度変更（--set-priority あり）

以下の手順を実行してください：

### 1. 対象ORDER確認

**スクリプト利用時**:
```bash
python backend/order/list.py $PROJECT_NAME --json | grep "ORDER_$ORDER_NUMBER"
```

**フォールバック**:
- エラーメッセージを表示してDBスクリプトの修復を促す
- DBスクリプトが利用できない場合、処理を中断

### 2. 優先度検証

- 指定された優先度が P0/P1/P2/P3 のいずれかであることを確認
- 不正な値の場合はエラー表示

### 3. P0設定時の特別処理

P0（緊急）が設定された場合:
```
【緊急ORDER設定】
ORDER_$ORDER_NUMBER の優先度をP0（緊急）に設定しました。

現在のWorker配置:
- Worker A: ORDER_YYY / TASK_ZZZ

推奨アクション:
A. Worker AをORDER_$ORDER_NUMBER に再配置
   → 現在のタスクは中断、QUEUEDに戻ります
B. 現在のタスク完了後に再配置
   → 完了次第、自動的にP0 ORDERに配置
C. 再配置しない（手動管理）
   → 現在の配置を維持

どれを選択しますか？
```

### 4. DB更新

**スクリプト利用時**:
```bash
python backend/order/update.py $PROJECT_NAME ORDER_$ORDER_NUMBER --priority P0
```

**フォールバック**:
DBスクリプトが利用できない場合はエラー終了。DBスクリプトの修復が必要です。

### 5. 完了メッセージ表示

```
【優先度変更完了】
ORDER_$ORDER_NUMBER の優先度を {旧優先度} → {新優先度} に変更しました。
```

---

## モード6: ORDER一覧表示（特殊: ORDER_NUMBER に `list` を指定）

引数: `/aipm-pm PROJECT_NAME list`

**スクリプト利用時**:
```bash
# アクティブORDER
python backend/order/list.py $PROJECT_NAME --active --table

# 一時停止中ORDER
python backend/order/list.py $PROJECT_NAME --on-hold --table

# 完了済みORDER（直近5件）
python backend/order/list.py $PROJECT_NAME --completed --limit 5 --table

# サマリ
python backend/order/list.py $PROJECT_NAME --summary
```

**表示形式**:

```
【ORDER一覧】$PROJECT_NAME

【アクティブORDER】
| ORDER ID | タイトル | ステータス | 優先度 | 進捗 | 担当Worker |
|----------|---------|----------|--------|------|-----------|
| ORDER_019 | 複数ORDER同時進行 | IN_PROGRESS | P1 | 22% | Worker A |
| ORDER_020 | ドキュメント整備 | IN_PROGRESS | P2 | 83% | Worker B |

【一時停止中（ON_HOLD）】
| ORDER ID | タイトル | 停止日 | 理由 |
|----------|---------|--------|------|
| ORDER_018 | 機能改善 | 2026-01-15 | リソース調整 |

【完了済み（直近5件）】
| ORDER ID | タイトル | 完了日 |
|----------|---------|--------|
| ORDER_017 | Phase 1並行実行 | 2026-01-19 |
| ORDER_016 | バグ修正 | 2026-01-10 |
...

アクティブORDER: 2 / 3（推奨上限）
```

---

## 実行例

### 1. 通常のORDER処理:
```
/aipm-pm AI_PM_PJ 014
```
→ AI_PM_PJ プロジェクトの ORDER_014.md を処理し、GOAL/REQUIREMENTS/STAFFING を作成してタスクを発行

**DBモードでの内部処理フロー**:
```bash
# Step 0: データソース判定
# → backend/ と data/aipm.db の存在確認 → DBモード

# Step 1: アクティブORDER上限チェック
python backend/order/list.py AI_PM_PJ --active --summary --json
# → active_count: 1, recommended_max_active: 3 → 追加許可

# Step 4: ORDER作成
python backend/order/create.py AI_PM_PJ --title "ORDER名" --priority P1

# Step 5: タスク発行（ループ）
python backend/task/create.py AI_PM_PJ ORDER_014 --title "タスク1" --model Opus
python backend/task/create.py AI_PM_PJ ORDER_014 --title "タスク2" --depends "TASK_001" --model Opus
```

### 2. 割り込みタスク発行:
```
/aipm-pm AI_PM_PJ 015 --interrupt 075 "バックログにカテゴリ分類機能を追加"
```
→ TASK_075実行中に追加要件が発生。TASK_075_INTを発行し、REQUIREMENTS.md/GOAL.mdを更新

**スクリプト利用時の内部処理**:
```bash
python backend/task/create.py AI_PM_PJ ORDER_015 \
  --task-id "TASK_075_INT" \
  --title "バックログにカテゴリ分類機能を追加" \
  --priority P0
```

### 3. ORDER一時停止:
```
/aipm-pm AI_PM_PJ 019 --pause
```
→ ORDER_019を一時停止。実行中タスクはQUEUEDに戻る

**スクリプト利用時の内部処理**:
```bash
python backend/order/update.py AI_PM_PJ ORDER_019 --status ON_HOLD --reason "一時停止"
```

### 4. ORDER再開:
```
/aipm-pm AI_PM_PJ 019 --resume
```
→ 一時停止中のORDER_019を再開

**スクリプト利用時の内部処理**:
```bash
python backend/order/update.py AI_PM_PJ ORDER_019 --status IN_PROGRESS --reason "再開"
```

### 5. 優先度変更:
```
/aipm-pm AI_PM_PJ 021 --set-priority P0
```
→ ORDER_021の優先度をP0（緊急）に変更。Worker再配置の選択肢を表示

**スクリプト利用時の内部処理**:
```bash
python backend/order/update.py AI_PM_PJ ORDER_021 --priority P0
```

### 6. ORDER一覧表示:
```
/aipm-pm AI_PM_PJ list
```
→ AI_PM_PJの全ORDER一覧を表示

**スクリプト利用時の内部処理**:
```bash
python backend/order/list.py AI_PM_PJ --summary
python backend/order/list.py AI_PM_PJ --active --table
```

### 7. マルチORDER環境での新規ORDER追加:
```
/aipm-pm AI_PM_PJ 022 --priority P1
```
→ アクティブORDER上限をチェックし、ORDER_022を優先度P1で追加

---

## 後方互換性

| 条件 | 動作 |
|------|------|
| DBあり + スクリプトあり | DBモード（Step 0でDB利用可能と判定） |
| DBなし or スクリプトなし | エラー終了（DB必須） |
| DBスクリプトエラー時 | エラー終了（DBスクリプト修復が必要） |

- DBスクリプトが利用できない場合はエラー終了
- DBスクリプトの修復が必要です
