# Parallel Worker Launch - 並列Worker起動機能

## 概要

ORDER開始時に依存関係のない複数のQUEUEDタスクを同時にIN_PROGRESSへ遷移し、独立したWorkerセッションで並列実行する機能。

## 主要機能

### 1. 並列起動可能タスク検出 (`parallel_detector.py`)
- ORDER内のQUEUEDタスクから起動可能なタスクを検出
- 依存関係チェック（全依存タスクがCOMPLETED/DONE）
- ファイルロック競合チェック（既存IN_PROGRESSタスクとの競合）
- 並列候補間のファイル競合チェック

### 2. 並列Worker起動 (`parallel_launcher.py`)
- 検出されたタスクを同時にIN_PROGRESSへ遷移
- 各タスクでファイルロックを取得
- 独立したWorkerプロセスを起動（subprocess.Popen）
- 起動失敗時のロールバック処理

### 3. Worker統合 (`execute_task.py`)
- `--parallel`フラグで並列起動モードを有効化
- `--max-workers N`で最大並列数を制御

### 4. リソース管理 (`resource_monitor.py`, `worker_config.py`)
- CPU/メモリ使用率の監視
- リソース制約時の起動制限
- 動的Worker数調整（Auto-scaling）
- 実行数上限制御

## 使用方法

### 基本的な使い方

```bash
# ORDER内の並列起動可能タスクを検出
python -m worker.parallel_launch ai_pm_manager ORDER_090

# 並列起動可能タスクのサマリを表示
python -m worker.parallel_launch ai_pm_manager ORDER_090 --summary

# 最大3タスクまで並列起動
python -m worker.parallel_launch ai_pm_manager ORDER_090 --max-workers 3

# Dry-runモード（実際には起動しない）
python -m worker.parallel_launch ai_pm_manager ORDER_090 --dry-run

# JSON形式で出力
python -m worker.parallel_launch ai_pm_manager ORDER_090 --json
```

### Worker統合モード

```bash
# execute_taskから並列起動
python -m worker.execute_task ai_pm_manager TASK_925 --parallel

# 最大Worker数を指定
python -m worker.execute_task ai_pm_manager TASK_925 --parallel --max-workers 5

# 特定のモデルを使用
python -m worker.execute_task ai_pm_manager TASK_925 --parallel --model sonnet
```

### リソース管理オプション

```bash
# リソース監視を有効化して並列起動（デフォルト）
python -m worker.parallel_launcher ai_pm_manager ORDER_090

# CPU/メモリ閾値を指定
python -m worker.parallel_launcher ai_pm_manager ORDER_090 --max-cpu 90.0 --max-memory 80.0

# リソース監視を無効化
python -m worker.parallel_launcher ai_pm_manager ORDER_090 --no-resource-monitoring

# Auto-scalingを無効化（リソース制約時も最大Worker数を維持）
python -m worker.parallel_launcher ai_pm_manager ORDER_090 --no-auto-scaling

# 環境変数で設定
export AIPM_MAX_WORKERS=10
export AIPM_MAX_CPU_PERCENT=90.0
export AIPM_MAX_MEMORY_PERCENT=85.0
export AIPM_ENABLE_MONITORING=true
export AIPM_ENABLE_AUTO_SCALING=true
python -m worker.parallel_launcher ai_pm_manager ORDER_090
```

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│                     Parallel Worker Launch                   │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ Task Detector │    │    Launcher   │    │ Worker Exec   │
│               │───▶│               │───▶│               │
│ - Dependency  │    │ - Status      │    │ - Independent │
│ - File Lock   │    │ - Lock Acq    │    │   Process     │
│ - Parallel    │    │ - Rollback    │    │ - Auto Review │
└───────────────┘    └───────────────┘    └───────────────┘
```

### 処理フロー

1. **検出フェーズ** (parallel_detector.py)
   - ORDER内のQUEUEDタスクを取得
   - 各タスクの依存関係をチェック
   - 既存のIN_PROGRESSタスクのファイルロックをチェック
   - 並列候補間でファイル競合をチェック
   - 優先度順にソート（P0 > P1 > P2 > P3）

2. **準備フェーズ** (parallel_launcher.py)
   - 各タスクでファイルロックを取得
   - タスクステータスをIN_PROGRESSへ遷移
   - 失敗時はロールバック（ロック解放 & QUEUED復帰）

3. **起動フェーズ** (parallel_launcher.py)
   - 各タスクで独立したWorkerプロセスを起動
   - subprocess.Popenで非同期実行
   - PIDを記録してトラッキング可能に

4. **実行フェーズ** (execute_task.py)
   - 各Workerが独立して実行
   - タスク完了時にファイルロック解放
   - 自動レビュー実行（--no-reviewで無効化可能）
   - 後続タスクの自動キック

## 安全機構

### 1. ファイルロック管理
- タスクの`target_files`フィールドを使用
- IN_PROGRESS遷移前にロック取得
- 競合時は起動をスキップ
- 完了時に自動解放

### 2. ステータス遷移保護
- QUEUED → IN_PROGRESS のみ許可
- 遷移失敗時はロールバック
- トランザクション管理

### 3. エラーハンドリング
- 一部タスク失敗時も他のタスクは継続
- 起動失敗時は自動ロールバック
- 詳細なエラーログ記録

## 制約事項

### 並列起動の条件
1. タスクステータスがQUEUED
2. 全依存タスクがCOMPLETED/DONE
3. 既存IN_PROGRESSタスクとファイル競合なし
4. 並列候補タスク間でファイル競合なし

### リソース制限と管理

#### 実行数上限制御
- デフォルト最大5Worker（`--max-workers`で調整可能）
- 各Workerは独立プロセス（CPU/メモリ使用量に注意）
- 設定ファイルまたは環境変数で上限を設定可能

#### リソース監視（ORDER_090で実装）
- **CPU使用率監視**: デフォルト85%閾値
- **メモリ使用率監視**: デフォルト85%閾値
- リソース制約時は新規Worker起動を制限
- 既存Workerは継続実行（一部失敗でも他は続行）

#### Auto-scaling
- システムリソース状況に応じて動的にWorker数を調整
- CPU/メモリ使用率が高い場合、推奨Worker数を削減
  - 95%以上: 最大25%のWorker
  - 90-95%: 最大50%のWorker
  - 85-90%: 最大75%のWorker
- リソース回復時は元の最大数に戻る

#### エラーハンドリング
- リソース制約でスキップされたタスクはIN_PROGRESS状態を維持
- リソース回復時に自動的に実行可能
- 一部タスク失敗時も他のタスクは継続実行

## パフォーマンス

### 期待効果
- ORDER完了時間の短縮
- 依存関係のないタスクの並列実行
- リソース活用の最適化

### ベンチマーク例
```
順次実行: TASK_A(5分) → TASK_B(5分) → TASK_C(5分) = 15分
並列実行: TASK_A(5分) + TASK_B(5分) + TASK_C(5分) = 5分
```

## トラブルシューティング

### 並列起動できない場合

1. **依存関係ブロック**
   ```bash
   # 依存関係を確認
   python -m worker.parallel_launch PROJECT ORDER --summary
   ```

2. **ファイルロック競合**
   ```bash
   # 現在のロックを確認
   python -c "from utils.file_lock import FileLockManager; \
              locks = FileLockManager.get_all_locks('PROJECT'); \
              print(locks)"
   ```

3. **ステータス不整合**
   ```bash
   # タスクステータスを確認
   python -c "from utils.db import get_connection, fetch_all; \
              conn = get_connection(); \
              tasks = fetch_all(conn, 'SELECT id, status FROM tasks WHERE order_id=?', ('ORDER_ID',)); \
              print(tasks); conn.close()"
   ```

## 関連機能

- **ORDER_076**: ファイルロック方式（競合管理基盤）
- **ORDER_078**: 依存タスク完了時の自動発火（完了後の連鎖起動）
- **ORDER_090**: 並列タスク同時起動（本機能）

### リソース監視が利用できない場合

- `psutil`ライブラリが必須（リソース監視用）
- インストール: `pip install psutil`
- `psutil`がない場合、リソース監視は無効化され警告が表示されるが、並列起動は継続可能

### リソース状況の確認

```python
# システム情報の取得
from worker.resource_monitor import get_system_info
info = get_system_info()
print(info)

# リソース状況の確認
from worker.resource_monitor import ResourceMonitor
monitor = ResourceMonitor(max_cpu_percent=85.0, max_memory_percent=85.0)
status = monitor.get_status()
print(f"CPU: {status.cpu_percent}%, Memory: {status.memory_percent}%")
print(f"Healthy: {status.is_healthy}")

# Worker数の推奨値を取得
recommended = monitor.get_recommended_worker_count(
    current_workers=0,
    max_workers=10
)
print(f"Recommended workers: {recommended}")
```

## 今後の拡張

- [ ] 並列実行状況のリアルタイム監視UI
- [ ] Worker間の通信機能
- [ ] 優先度ベースのプリエンプション（P0タスクが低優先度タスクを中断）
- [ ] 並列実行ログの統合ビューア
- [x] 動的リソース配分（Auto-scaling） ← ORDER_090で実装
- [x] 実行数上限制御とリソース管理 ← ORDER_090で実装
