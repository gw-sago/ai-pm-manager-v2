# Fault Detection Module - Integration Guide

このガイドでは、障害検出モジュールをprocess_order.pyに統合する方法を説明します。

## 統合オプション

### オプション1: 定期バックグラウンドチェック（推奨）

process_order.pyの開始時にバックグラウンドスレッドを起動し、定期的に障害をチェックします。

#### 実装例

```python
# backend/pm/process_order.py の冒頭に追加

from fault_detection.periodic_checker import PeriodicFaultChecker

# グローバル変数（モジュールレベル）
_fault_checker: Optional[PeriodicFaultChecker] = None

def start_fault_checker():
    """障害チェッカーを起動"""
    global _fault_checker

    if _fault_checker is None or not _fault_checker.is_running():
        _fault_checker = PeriodicFaultChecker(
            check_interval_seconds=60,  # 1分ごと
            stuck_threshold_minutes=10,
            auto_recovery=True,
            verbose=False
        )
        _fault_checker.start()
        logger.info("Fault checker started in background")

def stop_fault_checker():
    """障害チェッカーを停止"""
    global _fault_checker

    if _fault_checker and _fault_checker.is_running():
        _fault_checker.stop()
        logger.info("Fault checker stopped")

# main()関数内で起動
def main():
    """CLI エントリーポイント"""
    # ... 既存のコード ...

    # 障害チェッカー起動
    start_fault_checker()

    try:
        # PM処理実行
        processor = PMProcessor(...)
        results = processor.process()
        # ...

    finally:
        # 終了時に停止
        stop_fault_checker()
```

### オプション2: 同期的な定期チェック

PMProcessorクラス内で定期的にチェックを実行します。

#### 実装例

```python
# backend/pm/process_order.py の PMProcessor クラス内

from fault_detection import detect_all_faults
from utils.incident_logger import log_incident
from datetime import datetime

class PMProcessor:
    def __init__(self, ...):
        # ... 既存のコード ...
        self.last_fault_check = datetime.now()
        self.fault_check_interval_seconds = 60

    def _check_faults_periodically(self):
        """定期的な障害チェック"""
        now = datetime.now()
        elapsed = (now - self.last_fault_check).total_seconds()

        if elapsed < self.fault_check_interval_seconds:
            return  # まだチェック時刻ではない

        self.last_fault_check = now

        try:
            faults = detect_all_faults(stuck_threshold_minutes=10)

            for fault in faults:
                logger.warning(f"Fault detected: {fault.fault_type.value} - {fault.description}")

                # INCIDENTSテーブルに記録
                log_incident(
                    category=fault.fault_type.value,
                    description=fault.description,
                    severity=fault.severity,
                    project_id=fault.project_id,
                    order_id=fault.order_id,
                    task_id=fault.task_id,
                    root_cause=fault.root_cause
                )

        except Exception as e:
            logger.warning(f"Fault check error: {e}")

    def process(self):
        """PM処理を実行"""
        try:
            # ... 既存の処理 ...

            # 各ステップの間に障害チェック
            self._step_read_order()
            self._check_faults_periodically()

            self._step_validate_project()
            self._check_faults_periodically()

            # ...

        except PMProcessError as e:
            # ... エラー処理 ...
```

### オプション3: イベントドリブン型チェック

特定のイベント（タスク開始、完了など）時にのみチェックを実行します。

#### 実装例

```python
# backend/worker/execute_task.py の WorkerExecutor クラス内

from fault_detection import detect_stuck_tasks, FaultType

class WorkerExecutor:
    def _step_assign_worker(self):
        """Step 2: Worker割当・ステータス更新"""
        # ... 既存のコード ...

        # タスク開始前にスタックタスクをチェック
        stuck_tasks = detect_stuck_tasks(stuck_threshold_minutes=10)

        if stuck_tasks:
            logger.warning(f"Found {len(stuck_tasks)} stuck tasks before starting new task")

            for fault in stuck_tasks:
                # INCIDENTSテーブルに記録
                log_incident(
                    category="WORKER_FAILURE",
                    description=fault.description,
                    severity=fault.severity,
                    task_id=fault.task_id,
                    root_cause=fault.root_cause
                )

        # ... 既存のコード続き ...
```

## カスタムコールバックの使用

障害検出時にカスタム処理を実行できます。

```python
from fault_detection.periodic_checker import PeriodicFaultChecker
from fault_detection import FaultReport, FaultType

def on_fault_detected(fault: FaultReport):
    """障害検出時のコールバック"""
    if fault.fault_type == FaultType.STUCK_TASK:
        # スタックタスクの場合、自動リカバリをトリガー
        logger.error(f"Stuck task detected: {fault.task_id}")
        # trigger_auto_recovery(fault)

    elif fault.fault_type == FaultType.INVALID_TRANSITION:
        # 無効遷移の場合、管理者に通知
        send_admin_notification(fault)

    elif fault.severity == "HIGH":
        # HIGH重要度の場合、Slackに通知
        send_slack_alert(fault)

# コールバック付きでチェッカー起動
checker = PeriodicFaultChecker(
    check_interval_seconds=60,
    on_fault_detected=on_fault_detected,
    auto_recovery=True
)
checker.start()
```

## ログ出力例

```
2026-02-09 10:30:00 [INFO] Fault checker started in background
2026-02-09 10:31:00 [WARNING] Fault detected: STUCK_TASK [HIGH] - タスクが12.5分間IN_PROGRESSのままスタック
2026-02-09 10:31:00 [INFO] Logged fault to INCIDENTS table: TASK_932
2026-02-09 10:31:00 [INFO] Triggering auto recovery for fault: TASK_932 - STUCK_TASK
2026-02-09 10:32:00 [DEBUG] No faults detected
```

## 推奨設定

### 本番環境

```python
checker = PeriodicFaultChecker(
    check_interval_seconds=60,      # 1分ごとにチェック
    stuck_threshold_minutes=10,     # 10分でスタック判定
    auto_recovery=True,             # 自動リカバリ有効
    verbose=False                   # 詳細ログ無効
)
```

### 開発環境

```python
checker = PeriodicFaultChecker(
    check_interval_seconds=30,      # 30秒ごとにチェック（頻繁）
    stuck_threshold_minutes=5,      # 5分でスタック判定（早期）
    auto_recovery=False,            # 自動リカバリ無効（手動確認）
    verbose=True                    # 詳細ログ有効
)
```

## パフォーマンス考慮事項

### チェック間隔

- **推奨**: 60秒（1分）
- 短すぎる（< 30秒）: CPU負荷増加、ログ肥大化
- 長すぎる（> 300秒）: 障害検出遅延、リカバリ遅延

### スタック判定時間

- **推奨**: 10分
- 短すぎる（< 5分）: 正常動作を誤検出
- 長すぎる（> 30分）: リカバリ遅延、リソース無駄

### バックグラウンドスレッド

- デーモンスレッド使用（メインプロセス終了時に自動終了）
- DBアクセスは read-only 操作のみ
- 例外キャッチでスレッド継続を保証

## トラブルシューティング

### Q: バックグラウンドチェッカーが起動しない

A: ロギング設定を確認してください。

```python
import logging
logging.basicConfig(level=logging.DEBUG)
checker.start()
```

### Q: 誤検出が多い

A: 閾値を調整してください。

```python
checker = PeriodicFaultChecker(
    stuck_threshold_minutes=15,  # 10 → 15分に変更
)
```

### Q: ログファイルチェックが遅い

A: サブエージェントログチェックを無効化できます。

```python
from fault_detection import FaultDetector

detector = FaultDetector(
    check_subagent_logs=False  # ログチェック無効
)
```

## 次のステップ

- [x] 障害検出モジュール実装完了
- [ ] 自動ロールバック機構実装（TASK_935）
- [ ] リトライハンドラー実装（TASK_935）
- [ ] 統合テスト実装（TASK_937）

## 関連ドキュメント

- [README.md](./README.md) - 障害検出モジュール概要
- [detector.py](./detector.py) - 検出ロジック実装
- [periodic_checker.py](./periodic_checker.py) - 定期チェッカー実装
