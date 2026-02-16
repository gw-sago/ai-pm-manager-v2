# Fault Detection Module

障害検出モジュール - 自己修復パイプラインの一部

## 概要

AI PM Frameworkの実行中に発生する4種類の障害を自動検出します。

## 検出可能な障害タイプ

### 1. スタックタスク (STUCK_TASK)

**説明**: IN_PROGRESS状態が10分以上継続しているタスクを検出

**検出方法**:
- `tasks`テーブルから`status='IN_PROGRESS'`かつ`started_at`が閾値時間を超えているレコードを抽出

**重要度**: HIGH

**対策**: 自動ロールバック＋リトライ

### 2. 無効な状態遷移 (INVALID_TRANSITION)

**説明**: `status_transitions`テーブルで定義されていない状態遷移を検出

**検出方法**:
- `change_history`から最近24時間の状態遷移を取得
- `status_transitions`テーブルで許可されているか照合

**重要度**: MEDIUM

**対策**: 手動確認＋データ修正

### 3. サブエージェントクラッシュ (SUBAGENT_CRASH)

**説明**: ログファイルからPython例外・エラーメッセージを検出

**検出パターン**:
- Python traceback
- Error/Exception メッセージ
- Fatal/Crash キーワード
- Non-zero exit code
- Subprocess failure

**検出対象**:
- `logs/**/*.log`
- `PROJECTS/**/RESULT/**/*.log`
- `PROJECTS/**/RESULT/**/worker_output.txt`

**重要度**: HIGH

**対策**: 自動ロールバック＋リトライ（エラー内容をWorkerに注入）

### 4. ファイル書き込み失敗 (FILE_WRITE_FAILURE)

**説明**: ファイル書き込み処理の失敗を検出

**検出パターン**:
- 空のREPORTファイル（0バイト）
- 1時間以上残存している`.tmp`ファイル
- 不正なJSON形式のファイル

**重要度**: MEDIUM/LOW

**対策**: ファイル削除＋タスク再実行

## 使い方

### Python APIとして使用

```python
from fault_detection import detect_all_faults, FaultType

# 全種類の障害を検出
faults = detect_all_faults(stuck_threshold_minutes=10, verbose=True)

for fault in faults:
    print(f"{fault.fault_type}: {fault.description}")
    print(f"  Severity: {fault.severity}")
    print(f"  Task: {fault.task_id}")
    print(f"  Root Cause: {fault.root_cause}")
```

### 個別検出

```python
from fault_detection import (
    detect_stuck_tasks,
    detect_invalid_transitions,
    detect_subagent_crashes,
    detect_file_write_failures
)

# スタックタスクのみ検出
stuck_tasks = detect_stuck_tasks(stuck_threshold_minutes=10)

# 無効遷移のみ検出
invalid_transitions = detect_invalid_transitions()

# クラッシュのみ検出
crashes = detect_subagent_crashes()

# ファイル書き込み失敗のみ検出
file_failures = detect_file_write_failures()
```

### CLIとして使用

```bash
# 全種類の障害を検出
python backend/fault_detection/detector.py --type all

# スタックタスクのみ検出（閾値15分）
python backend/fault_detection/detector.py --type stuck --threshold 15

# JSON形式で出力
python backend/fault_detection/detector.py --type all --json

# 詳細ログ出力
python backend/fault_detection/detector.py --type all --verbose
```

## データ構造

### FaultReport

```python
@dataclass
class FaultReport:
    fault_type: FaultType          # 障害タイプ
    severity: str                  # HIGH, MEDIUM, LOW
    project_id: Optional[str]      # プロジェクトID
    order_id: Optional[str]        # ORDER ID
    task_id: Optional[str]         # タスクID
    description: str               # 障害の説明
    root_cause: Optional[str]      # 根本原因
    affected_records: Optional[str] # 影響を受けたレコード（JSON）
    detected_at: datetime          # 検出日時
    metadata: Dict[str, Any]       # 追加メタデータ
```

## 統合方法

### process_order.pyへの統合例

```python
from fault_detection import detect_all_faults
from utils.incident_logger import log_incident

# 定期チェック（1分ごと）
import time
import threading

def periodic_fault_check(interval_seconds=60):
    """定期的な障害チェック"""
    while True:
        try:
            faults = detect_all_faults()
            for fault in faults:
                # INCIDENTSテーブルに記録
                log_incident(
                    category=fault.fault_type.value,
                    description=fault.description,
                    severity=fault.severity,
                    project_id=fault.project_id,
                    order_id=fault.order_id,
                    task_id=fault.task_id,
                    root_cause=fault.root_cause,
                    affected_records=fault.affected_records
                )

                # 自動リカバリ処理をトリガー
                if fault.severity == "HIGH":
                    trigger_auto_recovery(fault)

        except Exception as e:
            logger.error(f"障害チェックエラー: {e}")

        time.sleep(interval_seconds)

# バックグラウンドで実行
fault_check_thread = threading.Thread(
    target=periodic_fault_check,
    args=(60,),  # 1分ごと
    daemon=True
)
fault_check_thread.start()
```

## テスト

```bash
# 基本テスト
python -m pytest tests/test_fault_detection.py

# 統合テスト
python backend/fault_detection/detector.py --type all --verbose
```

## 関連ファイル

- `backend/fault_detection/detector.py` - 検出ロジック本体
- `backend/fault_detection/__init__.py` - モジュールインターフェース
- `backend/checkpoint/create.py` - チェックポイント作成
- `backend/rollback/auto_rollback.py` - 自動ロールバック
- `backend/retry/retry_handler.py` - リトライ機構

## ログ出力例

```
2026-02-09 10:30:00 [INFO] 障害検出完了: 合計3件
2026-02-09 10:30:00 [WARNING] ⚠ 3件の障害を検出しました:

1. [HIGH] STUCK_TASK
   タスクが12.5分間IN_PROGRESSのままスタック
   タスク: TASK_932
   原因: Worker 'Worker A' がタスク実行中にスタックまたはクラッシュした可能性

2. [MEDIUM] INVALID_TRANSITION
   無効な状態遷移: task DONE → REJECTED
   タスク: TASK_931
   原因: status_transitionsテーブルで許可されていない遷移が実行された

3. [HIGH] SUBAGENT_CRASH
   サブエージェントクラッシュ検出: Python traceback detected
   タスク: TASK_930
   原因: ログファイル worker_output.txt でエラーパターン検出
```
