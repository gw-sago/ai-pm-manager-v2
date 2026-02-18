# Worker実行ステップ取得機構

## 概要

`get_execution_steps.py` は、Worker実行中のタスクが現在どのステップにいるかを取得するAPIを提供します。

## 機能

### 1. Worker実行ステップの定義

execute_task.pyの実行フローを7つのステップに分類:

1. **get_task_info** - タスク情報取得
2. **assign_worker** - Worker割当
3. **file_lock** - ファイルロック取得
4. **execute_task** - AI実行（claude -p）
5. **create_report** - レポート作成
6. **update_status_done** - 完了処理（DONE遷移）
7. **auto_review** - 自動レビュー

### 2. API関数

#### get_task_execution_step()

単一タスクの現在の実行ステップを取得します。

```python
from worker.get_execution_steps import get_task_execution_step

step_info = get_task_execution_step("ai_pm_manager", "TASK_1034", verbose=True)

print(step_info["current_step"])         # "execute_task"
print(step_info["current_step_display"]) # "AI実行"
print(step_info["step_index"])           # 3
print(step_info["progress_percent"])     # 50
```

**戻り値**:
```python
{
    "current_step": str,              # ステップ名
    "current_step_display": str,      # ステップ表示名（日本語）
    "step_index": int,                # ステップインデックス（0-based）
    "total_steps": int,               # 総ステップ数（7）
    "progress_percent": int,          # 進捗率（0-100）
    "status": str,                    # タスクステータス
    "assignee": str,                  # 担当Worker
    "started_at": str,                # 実行開始日時（ISO形式）
    "last_updated": str,              # 最終更新日時
    "completed_steps": List[Dict],    # 完了ステップリスト（verbose時）
    "error": str,                     # エラー情報（あれば）
}
```

#### get_multiple_tasks_execution_steps()

複数タスクのステップを一括取得します。

```python
from worker.get_execution_steps import get_multiple_tasks_execution_steps

results = get_multiple_tasks_execution_steps(
    "ai_pm_manager",
    order_id="ORDER_119",
    status_filter=["IN_PROGRESS", "QUEUED"]
)

for task_id, step_info in results.items():
    print(f"{task_id}: {step_info['current_step_display']} ({step_info['progress_percent']}%)")
```

#### format_execution_step_display()

ステップ情報を表示用にフォーマットします。

```python
from worker.get_execution_steps import format_execution_step_display

display = format_execution_step_display(step_info)
print(display)  # "[4/7] AI実行中 (57%)"
```

## ステップ推定ロジック

現在のステップは以下の情報から推定されます:

1. **tasksテーブルのstatus**
   - `IN_PROGRESS` 以外の場合は実行中でないと判定

2. **change_historyテーブルの最新レコード**
   - `status_change` で DONE遷移 → `update_status_done`
   - `assignee_change` → `file_lock`
   - その他の場合 → `assign_worker` または `execute_task`

3. **tasksテーブルのmetadata**
   - `file_locked` フラグがあれば `execute_task` 中と判定

## 使用例

### コマンドライン実行

```bash
# 単一タスクのステップ取得
python backend/worker/get_execution_steps.py ai_pm_manager TASK_1034

# 出力例（JSON形式）
{
  "current_step": "execute_task",
  "current_step_display": "AI実行",
  "step_index": 3,
  "total_steps": 7,
  "progress_percent": 50,
  "status": "IN_PROGRESS",
  "assignee": "Worker-001",
  "started_at": "2026-02-10T10:30:00",
  "last_updated": "2026-02-10T10:35:00"
}
```

### Python スクリプトからの利用

```python
from worker.get_execution_steps import (
    get_task_execution_step,
    get_multiple_tasks_execution_steps,
    format_execution_step_display,
)

# 単一タスク
step_info = get_task_execution_step("ai_pm_manager", "TASK_1034")
if step_info["current_step"]:
    print(f"現在のステップ: {step_info['current_step_display']}")
    print(f"進捗: {step_info['progress_percent']}%")

# 複数タスク（ORDER単位）
results = get_multiple_tasks_execution_steps(
    "ai_pm_manager",
    order_id="ORDER_119",
    status_filter=["IN_PROGRESS"]
)

for task_id, info in results.items():
    display = format_execution_step_display(info)
    print(f"{task_id}: {display}")
```

### Electron アプリからの利用（ScriptExecutionService）

```typescript
// ScriptExecutionService.ts
import { spawn } from 'child_process';

async getTaskExecutionStep(projectId: string, taskId: string): Promise<ExecutionStepInfo> {
  const scriptPath = path.join(__dirname, '../../backend/worker/get_execution_steps.py');

  return new Promise((resolve, reject) => {
    const process = spawn('python', [scriptPath, projectId, taskId]);

    let stdout = '';
    process.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    process.on('close', (code) => {
      if (code === 0) {
        const stepInfo = JSON.parse(stdout);
        resolve(stepInfo);
      } else {
        reject(new Error(`Failed to get execution step: exit code ${code}`));
      }
    });
  });
}
```

## テスト

テストスクリプトを実行してモジュールの動作を確認できます。

```bash
# 存在するタスクでテスト
python backend/worker/get_execution_steps.py ai_pm_manager TASK_1034

# 存在しないタスクでテスト（エラーハンドリング確認）
python backend/worker/get_execution_steps.py ai_pm_manager TASK_999999
```

## 注意事項

1. **IN_PROGRESS以外のタスク**
   - QUEUED/BLOCKED: `progress_percent=0`, `current_step=None`
   - DONE/COMPLETED: `progress_percent=100`, `current_step=None`

2. **ステップ推定の精度**
   - change_historyレコードから推定するため、正確性は履歴の詳細度に依存
   - より正確な追跡が必要な場合は、execute_task.pyでworker_metadataに現在ステップを明示的に記録する拡張が推奨される

3. **パフォーマンス**
   - 複数タスク取得時は各タスクごとにchange_historyクエリを実行
   - 大量タスクの場合はクエリ最適化が必要

## 今後の拡張案

1. **execute_task.pyとの統合**
   - `_log_step()` で現在ステップをDBに記録
   - `tasks.metadata` に `current_step` フィールドを追加

2. **リアルタイム更新**
   - WebSocket経由でステップ変更を通知
   - Electron アプリでのポーリング間隔最適化

3. **エラーステップの追跡**
   - どのステップで失敗したかを記録
   - リトライ時の復旧ポイント特定

4. **ステップ実行時間の記録**
   - 各ステップの所要時間を測定
   - パフォーマンスボトルネック分析
