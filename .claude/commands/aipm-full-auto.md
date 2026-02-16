---
description: ORDER完全自動実行 - PM処理→Worker→レビューを自動ループ
argument-hint: PROJECT_NAME ORDER_ID [--dry-run] [--pause-on-error] [--skip-release] [--force] [--max-rework N] [--verbose] [--parallel N] [--background]
---

> **完全自動実行コマンド**: 指定ORDERの全タスクをPM→Worker→レビューの順に自動実行します。

ORDER完全自動実行を開始します。

**引数**: `$ARGUMENTS` → PROJECT_NAME ORDER_ID [OPTIONS]

---

## 基本構文

```bash
/aipm-full-auto PROJECT_NAME ORDER_ID [OPTIONS]
```

**引数**:
| 引数 | 必須 | 説明 |
|------|------|------|
| PROJECT_NAME | Yes | プロジェクト名（例: AI_PM_PJ） |
| ORDER_ID | Yes | ORDER番号（例: 056）、`new`、または `BACKLOG_XXX` |

**オプション**:
| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--dry-run` | false | 実行計画のみ表示（実行しない） |
| `--pause-on-error` | false | エラー時にユーザー確認を求める |
| `--skip-release` | false | リリース処理をスキップ |
| `--auto-release` | false | 確認なしでリリース実行 |
| `--force` | false | アクティブORDER衝突・重複ORDER検出を無視して強制実行 |
| `--max-rework N` | 3 | 差し戻し回数上限 |
| `--verbose` | false | 詳細ログ出力 |
| `--parallel N` | 1 | 同時実行タスク数（最大5） |
| `--background` | false | バックグラウンド実行モード |

---

## Step 0: 引数解析・バリデーション

```
引数解析ロジック:
1. 引数が0個の場合:
   → エラー: 「使い方: /aipm-full-auto PROJECT_NAME ORDER_ID [OPTIONS]」
2. 引数が1個の場合:
   → エラー: 「ORDER_IDを指定してください」
3. 引数が2個以上の場合:
   → PROJECT_NAME = 第1引数
   → ORDER_ID = 第2引数
   → 残りをオプションとして解析
```

**オプション解析**:
```
オプション解析ロジック:
- --dry-run → DRY_RUN = true
- --pause-on-error → PAUSE_ON_ERROR = true
- --skip-release → SKIP_RELEASE = true
- --auto-release → AUTO_RELEASE = true
- --force → FORCE = true（アクティブORDER衝突・重複ORDER検出を無視）
- --max-rework N → MAX_REWORK = N（デフォルト: 3）
- --verbose → VERBOSE = true
- --parallel N → PARALLEL = N（デフォルト: 1、最大: 5）
- --background → BACKGROUND = true
```

---

## Step 1: データソース判定・初期化

### 1.1 DBモード判定

```bash
# DB利用可能判定
test -d scripts/aipm-db && test -f data/aipm.db && echo "DBモード" || echo "従来方式"
```

### 1.2 プロジェクト存在確認

```bash
# DBモード
python backend/project/list.py --json | grep -q "$PROJECT_NAME"

# フォールバック
ls PROJECTS/$PROJECT_NAME/PROJECT_INFO.md
```

→ 存在しない場合: エラー「プロジェクト '$PROJECT_NAME' が見つかりません」

### 1.3 ORDER状態確認

```bash
# DBモード
python backend/order/list.py $PROJECT_NAME --order-id ORDER_$ORDER_ID --json
```

| ORDER状態 | 動作 |
|-----------|------|
| 存在しない | ORDER_ID = `new` または `BACKLOG_XXX` なら新規作成、それ以外はエラー |
| PLANNING | PM処理から開始（Step 3へ） |
| IN_PROGRESS | タスク実行から継続（Step 4へ） |
| COMPLETED | 「ORDER_${ORDER_ID}は既に完了しています」と表示して終了 |
| ON_HOLD | 警告表示、実行中止（再開するには `/aipm-pm --resume`） |

### 1.4 重複ORDER検出（新規作成時のみ）

ORDER新規作成時（ORDER_ID = `new` または `BACKLOG_XXX`）、同一内容のアクティブORDERが存在しないかチェックします。

```bash
# 重複チェック実行
python backend/order/create.py $PROJECT_NAME --title "{タイトル}" --check-dup --backlog-id BACKLOG_XXX --json
```

**重複検出時の表示**:
```
【重複検出】同一内容のアクティブORDERが存在します。

■ 検出ORDER
| ORDER ID | タイトル | ステータス | 進捗 |
|----------|---------|----------|------|
| ORDER_XXX | {タイトル} | IN_PROGRESS | 60% |

■ 推奨アクション
- 既存ORDERを継続: /aipm-full-auto $PROJECT_NAME ORDER_XXX
- 強制的に新規作成: /aipm-full-auto $PROJECT_NAME BACKLOG_XXX --force

処理を中止しました。
```

**--force 指定時**:
- 重複警告を表示するが、処理を継続
- ログに「強制作成」を記録

**重複検出ロジック**:
1. BACKLOG_ID指定時: 同一BACKLOG_IDを含むアクティブORDERを検索
2. タイトル完全一致: 同一タイトルのアクティブORDERを検索
3. タイトル類似（90%以上）: 類似タイトルのアクティブORDERを警告表示（処理は継続可能）

### 1.5 アクティブORDER衝突検知（並行実行防止）

同一プロジェクト内でアクティブなORDER（IN_PROGRESS/PLANNING状態）が存在する場合、意図しない並行実行を防止するために警告を表示します。

```bash
# アクティブORDER一覧取得
python backend/order/list.py $PROJECT_NAME --active --json
```

**検出ロジック**:
1. アクティブORDER（ステータスがIN_PROGRESSまたはPLANNING）を取得
2. active_count > 0 の場合、衝突警告を表示
3. `--force` オプション指定時は警告のみで処理を継続

**衝突検出時の表示（--force なし）**:
```
【アクティブORDER検出】同一プロジェクトで実行中のORDERがあります。

■ 現在アクティブなORDER
| ORDER ID | タイトル | ステータス | 進捗 |
|----------|---------|----------|------|
| ORDER_XXX | {タイトル} | IN_PROGRESS | 60% |

■ 推奨アクション
- 既存ORDERを継続: /aipm-full-auto $PROJECT_NAME ORDER_XXX
- 強制的に新規実行: /aipm-full-auto $PROJECT_NAME BACKLOG_XXX --force
- 既存ORDERの状態確認: /aipm-status $PROJECT_NAME

処理を中止しました。
```

**--force 指定時**:
```
【警告】アクティブORDERが存在しますが、--forceオプションにより強制実行します。

■ 現在アクティブなORDER
| ORDER ID | タイトル | ステータス | 進捗 |
|----------|---------|----------|------|
| ORDER_XXX | {タイトル} | IN_PROGRESS | 60% |

処理を継続します...
```

**処理順序**:
1. Step 1.5（アクティブORDER衝突検知）を先に実行
2. --forceなしで衝突検出 → 処理中断
3. --forceありで衝突検出 → 警告表示後、Step 1.4（重複ORDER検出）へ進む
4. Step 1.4でも重複検出 → --forceなしなら処理中断

---

## Step 2: ドライラン処理（--dry-run 指定時）

`--dry-run` が指定された場合、実行計画を表示して終了します。

### 2.1 実行計画生成

```bash
# 発行予定タスク取得
python backend/task/list.py $PROJECT_NAME --order ORDER_$ORDER_ID --json

# 依存関係解析
# 各タスクの依存関係から実行順序を決定
```

### 2.2 ドライラン表示

```
【ドライラン】ORDER_$ORDER_ID 実行計画

■ 現在状態
- ORDER: ORDER_$ORDER_ID ({ステータス})
- タイトル: {ORDERタイトル}

■ 実行計画
{ステータスに応じた実行内容}

1. PM処理: GOAL/REQUIREMENTS/STAFFING作成（PLANNINGの場合）
2. タスク発行: {タスク数}件

3. タスク実行順序:
   [1] TASK_XXX: {タスク名}
       依存: なし
       推奨モデル: {Opus/Sonnet/Haiku}
   [2] TASK_YYY: {タスク名}
       依存: TASK_XXX
       推奨モデル: {モデル}
   ...

4. リリース: {必要/不要}（成果物パスに基づく判定）

■ 推定情報
- 総タスク数: {N}
- 差し戻し上限: {MAX_REWORK}回/タスク

実行しますか？ [Y/n]
```

→ `n` 選択時: 「実行を中止しました」と表示して終了
→ `Y` 選択時 または `--dry-run` なしの場合: Step 3へ進む

---

## Step 3: PM処理（ORDER状態がPLANNING/新規の場合）

ORDER状態がPLANNINGまたは新規作成の場合、PM処理を実行します。

### 3.1 PM処理開始表示

```
【PM処理開始】ORDER_$ORDER_ID

フェーズ: PM処理（GOAL/REQUIREMENTS/STAFFING作成）
```

### 3.2 aipm-pmコマンド相当の処理実行

以下の処理を実行します（/aipm-pm と同等）:

1. **アクティブORDER上限チェック**
   ```bash
   python backend/order/list.py $PROJECT_NAME --active --summary --json
   ```
   - active_count >= 5 → エラー終了
   - active_count >= 3 → 警告（--pause-on-error時は確認）

2. **ORDER読み込み**
   - `PROJECTS/$PROJECT_NAME/ORDERS/ORDER_$ORDER_ID.md` を読み込み

3. **要件定義作成（AI判断）**
   - `RESULT/ORDER_$ORDER_ID/01_GOAL.md` - ゴール明文化
   - `RESULT/ORDER_$ORDER_ID/02_REQUIREMENTS.md` - 要件整理
   - `RESULT/ORDER_$ORDER_ID/03_STAFFING.md` - タスク分解・計画

4. **ORDER作成・DB登録**
   ```bash
   python backend/order/create.py $PROJECT_NAME --order-id ORDER_$ORDER_ID \
     --title "{ORDERタイトル}" --priority P1 --json
   ```

5. **タスク発行（AI判断）**
   ```bash
   python backend/task/create.py $PROJECT_NAME ORDER_$ORDER_ID \
     --title "{タスク名}" --priority P1 --model Opus --depends "TASK_XXX" --json
   ```
   - 各タスクについてループ実行

### 3.3 PM処理完了チェックポイント

```
【PM処理完了】ORDER_$ORDER_ID

- GOAL/REQUIREMENTS/STAFFING: 作成完了
- 発行タスク: {N}件
- ORDERステータス: IN_PROGRESS

次フェーズ: タスク実行ループ
```

---

## Step 4: タスク実行ループ（メインループ）

全タスクを依存関係順に実行します。`--parallel N` 指定時は並列実行モードになります。

### 4.1 初期化

```python
# 変数初期化
completed_tasks = []
failed_tasks = []
running_tasks = []  # 並列実行中のタスク
rework_counters = {}  # {task_id: rework_count}
PARALLEL = options.get('parallel', 1)  # 同時実行数（デフォルト: 1）
BACKGROUND = options.get('background', False)  # バックグラウンドモード
```

### 4.2 進捗表示（ループ開始時）

```
【実行中】ORDER_$ORDER_ID - {ORDERタイトル}
実行モード: {逐次実行 | 並列実行（N並列）}

進捗: ░░░░░░░░░░ 0% (0/{N}タスク完了)

| # | Task ID | タイトル | ステータス | 試行 |
|---|---------|---------|----------|------|
| 1 | TASK_XXX | {名前} | QUEUED | 0/{MAX_REWORK} |
| 2 | TASK_YYY | {名前} | BLOCKED | 0/{MAX_REWORK} |
...
```

### 4.3 依存関係解析・並列実行グループ作成

```bash
# 全タスクの依存関係を解析
python backend/task/list.py $PROJECT_NAME --order ORDER_$ORDER_ID --with-deps --json
```

**依存関係解析ロジック**:
1. 各タスクの依存関係を取得
2. トポロジカルソートで実行順序を決定
3. 同一レベル（依存解決済み）のタスクをグループ化
4. 循環依存を検出した場合は警告・エスカレーション

**並列実行グループ例**:
```
Group 1: [TASK_001, TASK_002, TASK_003]  # 依存なし、並列実行可能
Group 2: [TASK_004, TASK_005]            # Group 1に依存
Group 3: [TASK_006]                      # Group 2に依存
```

### 4.4 次タスク取得（逐次実行モード: PARALLEL=1）

```bash
# 実行可能タスク取得（QUEUED + 依存解決済み）
python backend/task/list.py $PROJECT_NAME --order ORDER_$ORDER_ID \
  --status QUEUED --resolved-deps --limit 1 --json
```

**取得ロジック**:
1. ステータスがQUEUEDのタスクを抽出
2. 依存タスクが全てCOMPLETEDのものをフィルタ
3. 優先度順（P0 > P1 > P2 > P3）でソート
4. 最初の1件を選択

→ 該当なし（全タスク完了 or 全てブロック中）: Step 6へ

### 4.5 並列タスク取得（並列実行モード: PARALLEL>1）

```bash
# 実行可能タスクを最大N件取得
python backend/task/list.py $PROJECT_NAME --order ORDER_$ORDER_ID \
  --status QUEUED --resolved-deps --limit $PARALLEL --json
```

**並列実行ロジック**:
1. 依存解決済みのQUEUEDタスクを最大N件取得
2. 各タスクを並列に起動（Task tool + run_in_background）
3. 完了待機とステータス監視

**並列起動例**:
```
【並列実行開始】3タスクを同時起動

| Task ID | タスク名 | ステータス | 出力先 |
|---------|---------|----------|--------|
| TASK_001 | {名前1} | RUNNING | LOGS/TASK_001.log |
| TASK_002 | {名前2} | RUNNING | LOGS/TASK_002.log |
| TASK_003 | {名前3} | RUNNING | LOGS/TASK_003.log |
```

### 4.6 Worker実行（実行コンテキスト分岐方式）

**実行方式の判定ロジック**:
- **直接実行（run_in_background=false）**: PARALLEL=1 かつ --backgroundなし（CLI逐次実行時）
- **バックグラウンド実行（run_in_background=true）**: PARALLEL>1 または --background指定時

```python
# 実行方式判定
USE_BACKGROUND = (PARALLEL > 1) or BACKGROUND
```

直接実行はCLI実行時に進捗をリアルタイムで確認でき、バックグラウンド実行はElectronアプリやparallel実行時にUIへ即座に制御を返す用途に適している。

#### 4.6.1 直接実行モード（PARALLEL=1 かつ 非バックグラウンド）

```
【Worker実行】TASK_{TASK_ID}: {タスク名}
試行: {rework_count + 1}/{MAX_REWORK}
実行方式: 直接実行（フォアグラウンド）
```

**Worker起動処理（直接実行）**:

1. **ステータス更新（IN_PROGRESS）**
   ```bash
   python backend/task/update.py $PROJECT_NAME TASK_{TASK_ID} \
     --status IN_PROGRESS --assignee "Auto" --role Worker
   ```

2. **Task toolでWorkerを直接実行**
   ```
   Task tool呼び出し:
     subagent_type: "worker"
     run_in_background: false
     prompt: "/aipm-worker $PROJECT_NAME TASK_{TASK_ID}"
   → Worker完了まで待機（進捗がリアルタイムで表示される）
   → 完了後、結果を直接取得
   ```

3. **完了後の処理**
   - Worker実行結果を確認
   - 即座にStep 4.8（レビュー実行）へ移行
   - **Step 4.7（完了検出ループ）はスキップ**

→ Step 4.8（レビュー実行）へ直接進む

#### 4.6.2 バックグラウンド実行モード（PARALLEL>1 または --background）

```
【Worker実行】TASK_{TASK_ID}: {タスク名}
試行: {rework_count + 1}/{MAX_REWORK}
実行方式: バックグラウンド（run_in_background）
```

**Worker起動処理（バックグラウンド）**:

1. **ステータス更新（IN_PROGRESS）**
   ```bash
   python backend/task/update.py $PROJECT_NAME TASK_{TASK_ID} \
     --status IN_PROGRESS --assignee "Auto" --role Worker
   ```

2. **Task toolでWorkerをバックグラウンド起動**
   ```
   Task tool呼び出し:
     subagent_type: "worker"
     run_in_background: true
     prompt: "/aipm-worker $PROJECT_NAME TASK_{TASK_ID}"
   → output_file パスを取得・保持
   ```

3. **起動確認表示**
   ```
   【Worker起動完了】TASK_{TASK_ID}
   バックグラウンドで実行中...
   出力先: {output_file}
   ```

→ Step 4.7（完了検出・レビュー接続）へ進む

#### 並列実行時のWorker起動（PARALLEL > 1）

並列実行モードの場合、依存解決済みタスクを最大N件同時起動:

```python
# 依存解決済みのQUEUEDタスクを最大N件取得して起動
for task in parallel_tasks:
    # ステータス更新
    task/update.py → IN_PROGRESS

    # Task toolでバックグラウンド起動
    agent = Task(
        subagent_type="worker",
        run_in_background=True,
        prompt=f"/aipm-worker {PROJECT_NAME} {task.id}"
    )
    running_tasks.append({
        "task_id": task.id,
        "output_file": agent.output_file,
        "status": "RUNNING"
    })
```

### 4.7 Worker完了検出・レビュー接続（バックグラウンド実行時のみ）

**注意**: このステップはバックグラウンド実行モード（PARALLEL>1 または --background）の場合のみ実行します。直接実行モード（Step 4.6.1）ではWorker完了後に即座にStep 4.8へ移行するため、このステップはスキップされます。

Worker起動後、完了を検出してレビューフローに自動移行します。並列実行モードで使用します。

**ポーリング設定**:
- チェック間隔: 5秒（TaskOutput tool の block=true, timeout=30000 を使用）
- 最大待機時間: 3600秒（1時間）。超過時はタイムアウトエラー

#### 4.7.1 完了検出ループ

```python
# 完了検出ループ（逐次実行: 1タスク、並列実行: N タスク）
POLL_INTERVAL = 5  # 秒
MAX_POLL_TIME = 3600  # 秒
elapsed = 0

while running_tasks and elapsed < MAX_POLL_TIME:
    for task in running_tasks:
        # 方法1: TaskOutput toolで完了チェック（推奨）
        result = TaskOutput(task_id=task["agent_id"], block=False, timeout=5000)
        if result.status == "completed":
            → 完了処理へ（4.7.2）

        # 方法2: DB状態チェック（フォールバック）
        task_status = task/get.py → status
        if task_status == "DONE":
            → 完了処理へ（4.7.2）

        # 方法3: REPORTファイル存在チェック（フォールバック）
        if exists(RESULT/ORDER_$ORDER_ID/05_REPORT/REPORT_{TASK_ID}.md):
            → 完了処理へ（4.7.2）

    # エラー検出
    if result contains "Error" or "FAILED" or "ESCALATED":
        → エラー処理へ（Step 5）

    elapsed += POLL_INTERVAL
    wait(POLL_INTERVAL)

# タイムアウト処理
if elapsed >= MAX_POLL_TIME:
    → エラー: 「Worker実行がタイムアウト（{MAX_POLL_TIME}秒）しました」
    → Step 5（エラーハンドリング）へ
```

#### 4.7.2 完了検出後のレビュー自動実行

Worker完了を検出したら、即座にレビューフロー（Step 4.8）に移行:

```python
def execute_review_flow(task_id):
    # 1. タスクステータス確認（DONEであること）
    status = task/get.py → status
    if status != "DONE":
        # IN_PROGRESSのままならDONEに更新
        task/update.py → DONE

    # 2. REPORTファイル存在確認
    report_path = RESULT/ORDER_$ORDER_ID/05_REPORT/REPORT_{TASK_ID}.md
    if not exists(report_path):
        → エラー: 「REPORTファイルが見つかりません」

    # 3. Step 4.8 レビュー実行へ移行
    → execute_review(task_id)  # Step 4.8

    # 4. レビュー結果に応じた分岐
    if review_result == "APPROVED":
        → completed_tasks に追加
        → Step 4.3へ（次タスク取得）
    elif review_result == "REJECTED":
        → rework_counters[task_id] += 1
        if rework_counters[task_id] < MAX_REWORK:
            → Step 4.6へ戻る（再実行）
        else:
            → エスカレーション（Step 5へ）
    elif review_result == "ESCALATED":
        → failed_tasks に追加
        → Step 5へ
```

#### 4.7.3 並列実行時の進捗監視

```
【並列実行監視】ORDER_$ORDER_ID

進捗: ██████░░░░ 60% (6/10タスク完了)

■ 実行中タスク (2/3並列)
| Task ID | タスク名 | 経過時間 | ステータス |
|---------|---------|---------|----------|
| TASK_007 | {名前} | 00:02:30 | RUNNING |
| TASK_008 | {名前} | 00:01:15 | RUNNING |

■ 待機中タスク (2件)
| Task ID | 依存先 | 解決待ち |
|---------|--------|---------|
| TASK_009 | TASK_007 | 実行中 |
| TASK_010 | TASK_008, TASK_009 | 2件待ち |
```

並列実行時は完了したタスクから順次レビュー→次タスク起動を行い、常にPARALLEL数を維持:

```python
# 並列監視ループ
while running_tasks or has_queued_tasks():
    for task in running_tasks[:]:  # コピーでイテレート
        if is_completed(task):
            running_tasks.remove(task)
            execute_review_flow(task["task_id"])  # 4.7.2

    # スロットが空いたら次タスク起動
    while len(running_tasks) < PARALLEL:
        next_task = get_next_runnable_task()
        if next_task is None:
            break
        launch_worker_in_background(next_task)  # 4.6
        running_tasks.append(next_task)
```

### 4.8 レビュー実行（aipm-review相当）

```
【レビュー実行】TASK_{TASK_ID}
```

以下の処理を実行します（/aipm-review と同等）:

1. **REPORT/TASK読み込み**

2. **レビューステータス更新**
   ```bash
   python backend/queue/update.py $PROJECT_NAME TASK_{TASK_ID} IN_REVIEW --reviewer PM
   ```

3. **レビュー実施（AI判断）**
   - 完了条件達成確認
   - 成果物品質確認

4. **レビュー結果判定**
   | 判定 | 条件 |
   |------|------|
   | APPROVED | 完了条件達成、品質問題なし |
   | REJECTED | 完了条件未達または品質問題 |
   | ESCALATED | 判断困難、ユーザー確認が必要 |

5. **REVIEW作成**
   - `RESULT/ORDER_$ORDER_ID/07_REVIEW/REVIEW_{TASK_ID}.md` を作成

### 4.9 結果分岐

#### APPROVED（承認）の場合

```bash
# DB更新
python backend/queue/update.py $PROJECT_NAME TASK_{TASK_ID} APPROVED --reviewer PM

# タスクステータス更新
python backend/task/update.py $PROJECT_NAME TASK_{TASK_ID} --status COMPLETED
```

```
【タスク完了】TASK_{TASK_ID}: {タスク名}
結果: APPROVED
```

→ completed_tasks に追加
→ Step 4.3へ（次タスク取得）

#### REJECTED（差し戻し）の場合

```python
rework_counters[task_id] = rework_counters.get(task_id, 0) + 1

if rework_counters[task_id] < MAX_REWORK:
    # 再実行
    ...
else:
    # エスカレーション
    ...
```

**再実行（カウンタ < MAX_REWORK）**:
```
【差し戻し対応】TASK_{TASK_ID} (試行 {count}/{MAX_REWORK})

差し戻し理由:
- {reason}

修正を実行中...
```

```bash
# タスクステータスをREWORKに更新
python backend/task/update.py $PROJECT_NAME TASK_{TASK_ID} --status REWORK

# レビューキューをREJECTEDに更新
python backend/queue/update.py $PROJECT_NAME TASK_{TASK_ID} REJECTED --comment "{reason}"
```

→ Step 4.4へ戻る（差し戻し理由を含めて再実行）

**エスカレーション（カウンタ >= MAX_REWORK）**:
```
【エスカレーション】TASK_{TASK_ID}

差し戻し回数が上限（{MAX_REWORK}回）に達しました。

差し戻し履歴:
1. {理由1}
2. {理由2}
3. {理由3}

ユーザーによる判断が必要です。
```

```bash
# タスクステータスをESCALATEDに更新
python backend/task/update.py $PROJECT_NAME TASK_{TASK_ID} --status ESCALATED
```

→ failed_tasks に追加
→ Step 5へ（エラーハンドリング）

#### ESCALATED（判断困難）の場合

```
【エスカレーション】TASK_{TASK_ID}

レビュー時に判断困難な問題が検出されました。

問題内容:
- {issue}

ユーザーによる判断が必要です。
```

→ failed_tasks に追加
→ Step 5へ（エラーハンドリング）

### 4.10 進捗表示（各タスク完了時）

```
【実行中】ORDER_$ORDER_ID - {ORDERタイトル}

進捗: ████████░░ 80% (4/5タスク完了)

| # | Task ID | タイトル | ステータス | 試行 |
|---|---------|---------|----------|------|
| 1 | TASK_XXX | {名前} | COMPLETED | 1/{MAX_REWORK} |
| 2 | TASK_YYY | {名前} | COMPLETED | 2/{MAX_REWORK} |
| 3 | TASK_ZZZ | {名前} | IN_PROGRESS | 1/{MAX_REWORK} |
| 4 | TASK_AAA | {名前} | QUEUED | 0/{MAX_REWORK} |
...

現在: TASK_ZZZ ({タスク名})
```

---

## Step 5: エラーハンドリング

### 5.1 エラー種別判定

| 種別 | 条件 | 動作 |
|------|------|------|
| RECOVERABLE | 差し戻し上限未達、一時的エラー | リトライまたは継続 |
| FATAL | エスカレーション、クリティカルエラー | 中断 |

### 5.2 チェックポイント記録

エラー発生時、以下を記録:

```bash
# エラー情報をDBに記録
python backend/task/update.py $PROJECT_NAME TASK_{task_id} \
  --status INTERRUPTED
```

### 5.3 エラー表示

```
【エラー】TASK_{TASK_ID} の実行中にエラーが発生しました。

種別: {RECOVERABLE|FATAL}
内容: {error_message}

チェックポイントを記録しました。
```

### 5.4 --pause-on-error 時の確認

```
【選択肢】
A. リトライ（同じタスクを再実行）
B. スキップ（次のタスクへ進む）
C. 中断（自動実行を停止）

選択してください [A/B/C]:
```

### 5.5 リカバリ案内

```
リカバリ方法:
- 状態確認: /aipm-status $PROJECT_NAME
- 手動再開: /aipm-recover $PROJECT_NAME {TASK_ID}
- 継続実行: /aipm-full-auto $PROJECT_NAME $ORDER_ID
```

---

## Step 6: ORDER完了処理

全タスクが完了した場合、ORDER完了処理を実行します。

### 6.1 完了判定

```bash
# 全タスクステータス取得
python backend/task/list.py $PROJECT_NAME --order ORDER_$ORDER_ID --json
```

| 条件 | 判定 |
|------|------|
| 全タスクCOMPLETED | ORDER完了 |
| ESCALATEDあり | 部分完了（エスカレーション情報表示） |
| QUEUED/BLOCKEDあり | 未完了（ブロック状況表示） |

### 6.2 ORDER完了メッセージ

```
【ORDER完了】ORDER_$ORDER_ID

全タスクが完了しました。

■ 実行結果
- 完了タスク: {N}件
- 差し戻し再実行: {M}件
- エスカレーション: {E}件

■ 成果物一覧
{成果物パスのリスト}
```

### 6.3 統合リリース・git自動コミット

`--skip-release` が指定されていない場合、統合リリーススクリプトで一括実行:

1. **リリース対象検出**（DEV→本番差分）:
   ```bash
   python backend/release/detect.py $PROJECT_NAME --order ORDER_$ORDER_ID --json
   ```

2. **確認**（`--auto-release` でなければ）:
   ```
   リリースを実行しますか？ [Y/n]
   ```

3. **統合リリース実行**（ORDER完了→BACKLOG更新→RELEASE_LOG記録→git add/commit）:
   ```bash
   python backend/release/git_release.py $PROJECT_NAME ORDER_$ORDER_ID --json
   ```

   git_release.py が自動的に以下を実行:
   - ORDER完了処理（complete_order）
   - 関連BACKLOG → DONE更新
   - RELEASE_LOG.md記録
   - ステージング対象ファイル自動検出 → git add → git commit

   **コミットメッセージ**: `release(ORDER_XXX): {タイトル}`

4. **Electronアプリプロジェクトの場合、ビルド確認**:
   ```
   ビルドを実行しますか？ [Y/n/later]
   ```
   → 実行する場合:
   ```bash
   python backend/release/build_manager.py $PROJECT_NAME --order ORDER_$ORDER_ID --json
   ```
   → ビルド結果はbuildsテーブルでDB管理（PENDING→BUILDING→SUCCESS/FAILED）

**--auto-release 指定時**:
→ 確認なしでリリース実行（ビルドは手動確認）

**--skip-release 指定時 または リリース対象なし**:
```
リリース処理: スキップ
```

### 6.4 BACKLOG自動更新

ORDER完了時、関連BACKLOGをDONEに更新:

```bash
# 関連BACKLOG取得
python backend/backlog/list.py $PROJECT_NAME --order-id ORDER_$ORDER_ID --json

# BACKLOG更新
python backend/backlog/update.py $PROJECT_NAME {BACKLOG_ID} --status DONE
```

---

## Step 7: 最終回答

### 7.1 成功時

```
【自動実行完了】ORDER_$ORDER_ID

■ 実行結果サマリ
- プロジェクト: $PROJECT_NAME
- ORDER: ORDER_$ORDER_ID ({ORDERタイトル})
- 完了タスク: {N}件
- 差し戻し対応: {M}件
- エスカレーション: {E}件
- リリース: {実行済み/保留/スキップ}

■ 成果物
{成果物一覧}

■ 次のアクション
- プロジェクト状態確認: /aipm $PROJECT_NAME
- 次のORDER確認: /aipm-pm $PROJECT_NAME list
```

### 7.2 部分完了時（エスカレーションあり）

```
【自動実行一時停止】ORDER_$ORDER_ID

■ 実行結果サマリ
- 完了タスク: {N}件
- エスカレーション: {E}件（要ユーザー判断）

■ エスカレーション対象
| Task ID | タスク名 | 理由 |
|---------|---------|------|
| TASK_XXX | {名前} | {理由} |

■ 次のアクション
- エスカレーション確認: /aipm-status $PROJECT_NAME
- 手動対応後、継続: /aipm-full-auto $PROJECT_NAME $ORDER_ID
```

### 7.3 エラー終了時

```
【自動実行エラー】ORDER_$ORDER_ID

■ エラー情報
- 発生箇所: {PM処理/Worker実行/レビュー}
- タスク: TASK_{TASK_ID}
- 内容: {error_message}

■ チェックポイント
- 最終完了タスク: TASK_{LAST_COMPLETED}
- 保存済み進捗: {進捗情報}

■ リカバリ方法
- 状態確認: /aipm-recover $PROJECT_NAME
- 手動対応後、継続: /aipm-full-auto $PROJECT_NAME $ORDER_ID
```

---

## 状態遷移図

```
                    ┌─────────────┐
                    │   START     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Step 1:     │
                    │ 初期化      │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐      │      ┌─────▼─────┐
        │ PLANNING  │      │      │ IN_PROGRESS│
        └─────┬─────┘      │      └─────┬─────┘
              │            │            │
        ┌─────▼─────┐      │            │
        │ Step 3:   │      │            │
        │ PM処理    │      │            │
        └─────┬─────┘      │            │
              │            │            │
              └────────────┼────────────┘
                           │
                    ┌──────▼──────┐
                    │ Step 4:     │◄──────────┐
                    │ タスク取得  │           │
                    └──────┬──────┘           │
                           │                  │
              ┌────────────┼────────────┐     │
              │            │            │     │
        ┌─────▼─────┐ ┌────▼────┐ ┌────▼────┐│
        │ タスクあり ││ なし    ││ブロック ││
        └─────┬─────┘└────┬────┘└────┬────┘│
              │           │          │      │
        ┌─────▼─────┐     │          │      │
        │ Worker    │     │          │      │
        │ 実行      │     │          │      │
        └─────┬─────┘     │          │      │
              │           │          │      │
        ┌─────▼─────┐     │          │      │
        │ レビュー  │     │          │      │
        └─────┬─────┘     │          │      │
              │           │          │      │
     ┌────────┼────────┐  │          │      │
     │        │        │  │          │      │
┌────▼───┐┌───▼───┐┌───▼───┐        │      │
│APPROVED││REJECTED││ESCALATED       │      │
└────┬───┘└───┬───┘└───┬───┘        │      │
     │        │        │             │      │
     │   ┌────▼────┐   │             │      │
     │   │カウンタ │   │             │      │
     │   │チェック │   │             │      │
     │   └────┬────┘   │             │      │
     │   ┌────┴────┐   │             │      │
     │   │         │   │             │      │
     │ ┌─▼──┐   ┌──▼─┐ │             │      │
     │ │<MAX│   │>=MAX│ │             │      │
     │ └─┬──┘   └──┬─┘ │             │      │
     │   │         │   │             │      │
     │   │    ┌────▼───┴─────────────┘      │
     │   │    │                             │
     │   │    │ Step 5: エラーハンドリング   │
     │   │    │                             │
     │   └────┼─────────────────────────────┘
     │        │
     └────────┼──────────────────┐
              │                  │
        ┌─────▼─────┐      ┌─────▼─────┐
        │ Step 6:   │      │ 中断      │
        │ ORDER完了 │      └───────────┘
        └─────┬─────┘
              │
        ┌─────▼─────┐
        │ Step 7:   │
        │ 最終回答  │
        └─────┬─────┘
              │
        ┌─────▼─────┐
        │   END     │
        └───────────┘
```

---

## 実行例

### 1. 通常実行

```bash
/aipm-full-auto AI_PM_PJ 056
```
→ ORDER_056を自動実行
→ PM処理（必要な場合）→ 全タスク実行 → レビュー → 完了

### 2. ドライラン

```bash
/aipm-full-auto AI_PM_PJ 056 --dry-run
```
→ 実行計画のみ表示、実際の実行はしない

### 3. エラー時確認付き実行

```bash
/aipm-full-auto AI_PM_PJ 056 --pause-on-error
```
→ エラー発生時にユーザー確認を求める

### 4. リリーススキップ

```bash
/aipm-full-auto AI_PM_PJ 056 --skip-release
```
→ ORDER完了後のリリース確認をスキップ

### 5. 差し戻し上限変更

```bash
/aipm-full-auto AI_PM_PJ 056 --max-rework 5
```
→ 差し戻し上限を5回に変更

### 6. 詳細ログ出力

```bash
/aipm-full-auto AI_PM_PJ 056 --verbose
```
→ 各ステップの詳細ログを出力

### 7. 複合オプション

```bash
/aipm-full-auto AI_PM_PJ 056 --pause-on-error --max-rework 5 --verbose
```

### 8. 並列実行（3タスク同時）

```bash
/aipm-full-auto AI_PM_PJ 056 --parallel 3
```
→ 依存関係のない最大3タスクを同時実行
→ 各タスクの出力はLOGSディレクトリに保存

### 9. バックグラウンド並列実行

```bash
/aipm-full-auto AI_PM_PJ 056 --parallel 3 --background
```
→ バックグラウンドで実行開始し、即座に制御を返す
→ 進捗は `/aipm-status AI_PM_PJ` で確認

### 10. 並列実行 + 自動リリース

```bash
/aipm-full-auto AI_PM_PJ 056 --parallel 5 --auto-release
```
→ 最大5並列で実行、完了後は確認なしでリリース

---

## DBスクリプト一覧

| スクリプト | 用途 |
|-----------|------|
| `project/list.py` | プロジェクト一覧取得 |
| `order/list.py` | ORDER一覧・状態取得 |
| `order/create.py` | ORDER作成 |
| `order/update.py` | ORDER状態更新 |
| `task/list.py` | タスク一覧取得 |
| `task/get.py` | タスク詳細取得 |
| `task/create.py` | タスク作成 |
| `task/update.py` | タスク状態更新 |
| `queue/add.py` | レビューキュー追加 |
| `queue/update.py` | レビューキュー更新 |
| `task/update.py` | タスクステータス更新 |
| `backlog/list.py` | BACKLOG一覧取得 |
| `backlog/update.py` | BACKLOG状態更新 |
| `render/state.py` | プロジェクト状態のレンダリング |
| `release/detect.py` | リリース対象検出 |
| `release/log.py` | リリース履歴記録 |
| `release/git_release.py` | 統合リリース（ORDER完了→BACKLOG→ログ→git commit） |
| `release/build_manager.py` | ビルドステータスDB管理 |

**フォールバック**: DBスクリプト利用不可時は従来のGlob/Read/Edit操作を使用

---

## 後方互換性

| 条件 | 動作 |
|------|------|
| DBあり + スクリプトあり | DBモード（推奨） |
| DBなし or スクリプトなし | 従来方式（Markdown直接操作） |
| DBスクリプトエラー時 | 従来方式にフォールバック |
| 途中終了後の再実行 | チェックポイントから継続 |

---

## 制約事項

- 1回の実行で1 ORDERのみ処理
- 並列実行（`--parallel N`）は最大5タスクまで同時実行可能
- 並列実行はDBモードでのみ対応（Markdown直接操作モードは逐次実行のみ）
- エスカレーション発生時はユーザー判断が必要
- ターミナル自動実行時は `--dangerously-skip-permissions` が必要
- バックグラウンドモード（`--background`）実行時は `/aipm-status` で進捗確認

---

## 関連コマンド

| コマンド | 用途 |
|---------|------|
| `/aipm` | プロジェクト状態確認 |
| `/aipm-pm` | PM処理（個別実行） |
| `/aipm-worker` | Worker実行（個別実行） |
| `/aipm-review` | レビュー（個別実行） |
| `/aipm-recover` | 中断タスクのリカバリ |
| `/aipm-release-review` | リリース承認フロー |
| `/aipm-status` | 詳細状態確認 |

---

**Version**: 1.4.0
**作成日**: 2026-02-03
**最終更新**: 2026-02-10（リリースフロー自動化: git_release.py + build_manager.py統合）
**対応要件**: ORDER_056, ORDER_060, ORDER_068, ORDER_083

