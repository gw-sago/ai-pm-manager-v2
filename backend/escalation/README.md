# Escalation Logging Module

エスカレーション発生時（モデル昇格、PM差し戻し、判定基準緩和など）のログをDB/ファイルに記録する機能を提供します。

## 機能概要

### 記録されるエスカレーション種別

1. **モデル昇格 (model_upgrade)**
   - REWORK 2回目以降でモデルが自動昇格した場合
   - 例: Sonnet → Opus

2. **PM差し戻し (review_rejection)**
   - PMレビューで差し戻された場合
   - REWORK回数、指摘内容、修正指針を記録

3. **判定基準緩和 (criteria_relaxation)**
   - REWORK回数に応じてレビュー判定基準が緩和された場合
   - REWORK 2回目: 致命的でない差異を許容
   - REWORK 3回目以降: 最低限の要件充足でAPPROVED

4. **リワーク回数上限超過 (rework_limit_exceeded)**
   - リワーク回数が上限を超えてREJECTED遷移した場合

## 保存先

### データベース
- **escalationsテーブル**: エスカレーション基本情報
  - id, task_id, project_id, title, description, status, created_at, resolved_at
- **change_historyテーブル**: 詳細メタデータ
  - エスカレーション種別、メタデータ（JSON）

### ファイル
- `PROJECTS/{PROJECT_ID}/RESULT/{ORDER_ID}/08_ESCALATIONS/{TASK_ID}_ESCALATIONS.md`
- タスクごとにエスカレーション履歴を集約

## 使用方法

### エスカレーションログ記録

```python
from escalation.log_escalation import log_escalation, EscalationType

# モデル昇格を記録
log_escalation(
    project_id="ai_pm_manager",
    task_id="TASK_123",
    escalation_type=EscalationType.MODEL_UPGRADE,
    description="REWORK 2回目: モデル自動昇格を実施",
    order_id="ORDER_102",
    metadata={
        "from_model": "sonnet",
        "to_model": "opus",
        "rework_count": 2,
    }
)

# PM差し戻しを記録
log_escalation(
    project_id="ai_pm_manager",
    task_id="TASK_123",
    escalation_type=EscalationType.REVIEW_REJECTION,
    description="PMレビュー差し戻し (REWORK #1)",
    order_id="ORDER_102",
    metadata={
        "rework_count": 1,
        "issues": ["テストが不足", "エラーハンドリングが不十分"],
        "recommendations": ["テストケース追加", "try-except追加"],
    }
)
```

### エスカレーション履歴取得

```python
from escalation.log_escalation import get_escalation_history, get_escalation_statistics

# 特定タスクのエスカレーション履歴
history = get_escalation_history(
    project_id="ai_pm_manager",
    task_id="TASK_123"
)

# 統計情報取得
stats = get_escalation_statistics(
    project_id="ai_pm_manager",
    task_id="TASK_123"  # オプション
)
# 返却値: {"total": 3, "by_type": {...}, "by_status": {...}}
```

### コマンドラインツール

```bash
# エスカレーション履歴を表示
python backend/escalation/view_escalations.py ai_pm_manager

# 特定タスクのエスカレーション履歴
python backend/escalation/view_escalations.py ai_pm_manager --task-id TASK_975

# 統計情報表示
python backend/escalation/view_escalations.py ai_pm_manager --stats

# 特定種別のみ表示
python backend/escalation/view_escalations.py ai_pm_manager --type model_upgrade
```

## 自動記録タイミング

以下の処理で自動的にエスカレーションログが記録されます:

1. **Worker実行時** (`worker/execute_task.py`)
   - REWORK 2回目以降でモデル昇格時

2. **Review処理時** (`review/process_review.py`)
   - PM差し戻し時
   - 判定基準緩和適用時（REWORK 2回目以降）
   - リワーク回数上限超過時

## データ構造

### escalationsテーブル
| カラム | 型 | 説明 |
|--------|-----|------|
| id | TEXT | エスカレーションID（例: TASK_975_ESC_1） |
| task_id | TEXT | 対象タスクID |
| project_id | TEXT | プロジェクトID |
| title | TEXT | エスカレーションタイトル |
| description | TEXT | 説明 |
| status | TEXT | ステータス（OPEN/RESOLVED/CANCELED） |
| resolution | TEXT | 解決内容（オプション） |
| created_at | DATETIME | 作成日時 |
| resolved_at | DATETIME | 解決日時（オプション） |

### change_historyテーブルへの記録
- entity_type = "escalation"
- field_name = "escalation_type" または "metadata"
- new_value = エスカレーション種別 または JSON化されたメタデータ

## 将来の活用

エスカレーションログは以下の分析に活用可能:
- どのタスクがREWORKループに陥りやすいか
- どの段階でエスカレーションが多発するか
- モデル昇格の効果測定
- 判定基準緩和の妥当性検証
