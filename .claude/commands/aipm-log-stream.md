---
description: 実行中タスクのログをリアルタイム表示します
---

実行中タスクのログをリアルタイムでストリーミング表示します。

**引数**:
- 第1引数（任意）: プロジェクト名（例: ai_pm_manager）
  - 省略時はPROJECTS配下から自動検出
- 第2引数（任意）: タスクID（例: TASK_906）
  - 省略時は実行中タスクを自動検出

**オプション**:
- `--lines N`: 初期表示行数（デフォルト: 10）
- `--all`: 全ての実行中タスクを表示
- `--no-follow`: ファイル終端で終了（監視しない）

**使用例**:
```
/aipm-log-stream                           # 実行中タスクを自動検出してログ表示
/aipm-log-stream ai_pm_manager             # プロジェクト指定
/aipm-log-stream ai_pm_manager TASK_906    # タスクID指定
/aipm-log-stream --all                     # 全実行中タスクのログ表示
```

---

以下の手順で実行してください：

## Step 1: 実行中タスクの検出

### 1.1 タスクID指定あり

タスクIDが引数で指定されている場合、そのタスクの情報を取得：

```bash
python backend/utils/get_active_task.py --task-id $TASK_ID --json
```

プロジェクトも指定されている場合：

```bash
python backend/utils/get_active_task.py --task-id $TASK_ID --project $PROJECT_NAME --json
```

### 1.2 タスクID指定なし（自動検出）

プロジェクト指定ありの場合：

```bash
python backend/utils/get_active_task.py --project $PROJECT_NAME --json
```

全プロジェクト検索（引数なし）：

```bash
python backend/utils/get_active_task.py --json
```

全実行中タスクを表示する場合（`--all`オプション）：

```bash
python backend/utils/get_active_task.py --all --json
```

### 1.3 結果の確認

取得したJSONから以下を確認：
- `id`: タスクID
- `project_id`: プロジェクトID
- `order_id`: ORDER ID
- `status`: ステータス（IN_PROGRESSであること）
- `log_path`: ログファイルパス
- `log_exists`: ログファイルの存在有無

**タスクが見つからない場合**:
```
実行中のタスクはありません。

タスクIDを指定して直接確認できます：
/aipm-log-stream PROJECT_NAME TASK_XXX
```

**ログファイルが見つからない場合**:
```
タスク $TASK_ID は実行中ですが、ログファイルが見つかりません。

タスク情報:
- プロジェクト: $PROJECT_ID
- ORDER: $ORDER_ID
- ステータス: $STATUS
- 開始時刻: $STARTED_AT

ログファイルは実行開始後に生成されます。少し待ってから再度お試しください。
```

## Step 2: ログストリーミング表示

### 2.1 ログファイルが見つかった場合

取得した `log_path` を使用してストリーミング表示を開始：

```bash
python backend/utils/log_stream.py "$LOG_PATH" --lines $INITIAL_LINES
```

`--no-follow` オプション指定時：

```bash
python backend/utils/log_stream.py "$LOG_PATH" --lines $INITIAL_LINES --no-follow
```

### 2.2 表示開始メッセージ

ストリーミング開始前に以下を表示：

```
【ログストリーミング開始】
タスク: $TASK_ID ($TASK_TITLE)
プロジェクト: $PROJECT_ID
ログファイル: $LOG_PATH

--- ログ出力 ---
```

### 2.3 複数タスク表示（--all指定時）

`--all` オプション指定時、検出された全タスクの情報を表示：

```
【実行中タスク一覧】

1. $TASK_ID_1 ($PROJECT_ID_1)
   タイトル: $TITLE_1
   ログ: $LOG_PATH_1

2. $TASK_ID_2 ($PROJECT_ID_2)
   タイトル: $TITLE_2
   ログ: $LOG_PATH_2

表示するタスクを選択してください（番号）:
```

ユーザーが選択したタスクのログをストリーミング表示します。

## Step 3: エラーハンドリング

### 3.1 DBスクリプト利用不可

```
【エラー】DBスクリプトが利用できません。

以下を確認してください：
- backend/ ディレクトリが存在すること
- data/aipm.db ファイルが存在すること
```

### 3.2 Pythonスクリプトエラー

スクリプト実行でエラーが発生した場合、エラー内容を表示：

```
【エラー】ログ取得中にエラーが発生しました。

エラー内容: $ERROR_MESSAGE

手動でログファイルを確認する場合：
1. タスク情報を確認: python backend/utils/get_active_task.py --all
2. ログファイルを直接表示: python backend/utils/log_stream.py LOG_PATH
```
