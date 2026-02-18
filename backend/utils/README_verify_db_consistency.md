# DB整合性検証スクリプト

## 概要

`verify_db_consistency.py` は、AI PM Frameworkのデータベース整合性を包括的に検証するスクリプトです。
backend/配下のPythonスクリプト編集後に実行して、DB状態に問題がないか確認します。

## 使用方法

### 基本的な使い方

```bash
# 全プロジェクトのDB整合性をチェック
python -m scripts.aipm-db.utils.verify_db_consistency

# 詳細な出力（全ての問題を表示）
python -m scripts.aipm-db.utils.verify_db_consistency --verbose

# 特定プロジェクトのみチェック
python -m scripts.aipm-db.utils.verify_db_consistency --project ai_pm_manager

# JSON形式で出力（CI/CD統合用）
python -m scripts.aipm-db.utils.verify_db_consistency --json
```

### オプション

- `--verbose, -v`: 詳細なチェック結果を表示（全ての問題を出力）
- `--json`: JSON形式で結果を出力（スクリプト統合用）
- `--project PROJECT`: 特定プロジェクトのみチェック
- `--fix`: 検出した問題を自動修正（未実装）

### 終了コード

- `0`: エラーなし（警告・情報のみの場合も含む）
- `1`: エラー検出またはスクリプト実行失敗

## 検証項目

### 1. 外部キー整合性 (FK)

データベースの参照整合性を検証します。

- ORDERが存在しないプロジェクトIDを参照していないか
- TASKが存在しないプロジェクトIDまたはORDER IDを参照していないか
- task_dependenciesが存在しない依存タスクIDを参照していないか
- BACKLOGが存在しないプロジェクトIDを参照していないか

**検出例:**
```
❌ [FK] TASK TASK_301 が存在しないORDER ORDER_059 を参照
```

### 2. ステータス値の有効性 (STATUS)

現在のステータスが有効な値かを検証します。

- ORDERのステータスが `validation.py` の `VALID_STATUSES['order']` に含まれているか
- TASKのステータスが `VALID_STATUSES['task']` に含まれているか
- BACKLOGのステータスが `VALID_STATUSES['backlog']` に含まれているか

**検出例:**
```
❌ [STATUS] TASK TASK_006 が無効なステータス 'CANCELLED' を持つ
```

### 3. 状態遷移整合性 (STATUS)

change_historyテーブルの状態遷移履歴が、status_transitionsテーブルで定義されたルールに従っているかを検証します。

**検出例:**
```
⚠️ [STATUS] task TASK_123 に不正な状態遷移履歴: DONE → QUEUED
```

### 4. 複合キー整合性 (FK)

複合主キー (id, project_id) が一意であることを検証します。

- ORDERの (id, project_id) が重複していないか
- TASKの (id, project_id) が重複していないか
- BACKLOGの (id, project_id) が重複していないか

**検出例:**
```
❌ [FK] ORDER複合キー (id=ORDER_001, project_id=AI_PM_PJ) が重複
```

### 5. タスク依存関係整合性 (DEPENDENCY)

タスクのBLOCKEDステータスと依存関係の整合性を検証します。

- BLOCKEDステータスだが依存タスクが全て完了している → 警告
- BLOCKED以外（QUEUED除く）だが未完了の依存がある → 情報

**検出例:**
```
⚠️ [DEPENDENCY] TASK TASK_250 がBLOCKEDだが依存タスクは全て完了済み
ℹ️ [DEPENDENCY] TASK TASK_251 (status=IN_PROGRESS) に未完了の依存があるがBLOCKEDでない
```

### 6. バックログ整合性 (BACKLOG)

backlog_itemsとordersの連携の整合性を検証します。

- related_order_idが存在しないORDERを参照していないか → エラー
- 関連ORDERが完了しているのにBACKLOGがDONEでないか → 警告

**検出例:**
```
❌ [BACKLOG] BACKLOG BACKLOG_042 が存在しないORDER ORDER_053 を参照
⚠️ [BACKLOG] BACKLOG BACKLOG_075 に関連するORDER ORDER_032 が完了しているがBACKLOGはDONEでない
```

## 出力フォーマット

### 人間可読形式（デフォルト）

```
============================================================
DB整合性検証結果
============================================================
プロジェクト: ALL
チェック日時: 2026-02-06T18:30:00
総チェック数: 7

エラー: 5
警告: 2
情報: 1

❌ エラーが検出されました

❌ [FK] TASK TASK_301 が存在しないORDER ORDER_059 を参照
    task_id: TASK_301
    order_id: ORDER_059
    project_id: AI_PM_PJ
...
```

### JSON形式（--json）

```json
{
  "success": false,
  "timestamp": "2026-02-06T18:30:00",
  "project_id": "ALL",
  "stats": {
    "total_checks": 7,
    "errors": 5,
    "warnings": 2,
    "info": 1
  },
  "issues": [
    {
      "category": "FK",
      "severity": "ERROR",
      "message": "TASK TASK_301 が存在しないORDER ORDER_059 を参照",
      "details": {
        "task_id": "TASK_301",
        "order_id": "ORDER_059",
        "project_id": "AI_PM_PJ"
      },
      "timestamp": "2026-02-06T18:30:00"
    }
  ]
}
```

## プログラムからの使用

Pythonコードから直接呼び出すことも可能です。

```python
from utils.verify_db_consistency import DBConsistencyChecker

# チェッカー初期化
checker = DBConsistencyChecker(project_id="ai_pm_manager", verbose=True)

# 検証実行
result = checker.check_all()

# 結果確認
if result["success"]:
    print("✅ DB整合性に問題なし")
else:
    print(f"❌ {result['stats']['errors']} 件のエラーを検出")
    for issue in result["issues"]:
        if issue["severity"] == "ERROR":
            print(f"  - {issue['message']}")
```

## CI/CD統合例

GitHub ActionsやPre-commitフックに統合する例:

```yaml
# .github/workflows/db-check.yml
name: DB Consistency Check
on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run DB Consistency Check
        run: |
          python -m scripts.aipm-db.utils.verify_db_consistency --json > result.json
          exit_code=$?
          cat result.json
          exit $exit_code
```

## 問題の解決方法

### 外部キーエラー

```
❌ [FK] TASK TASK_301 が存在しないORDER ORDER_059 を参照
```

**原因:** ORDERが削除されたがTASKが残っている、または誤ったORDER_IDが設定されている

**対処:**
1. TASKを削除する
2. 正しいORDER_IDに更新する
3. 欠落しているORDERを復元する

### ステータスエラー

```
❌ [STATUS] TASK TASK_006 が無効なステータス 'CANCELLED' を持つ
```

**原因:** 古いステータス値が残っている、またはスキーマ変更時の移行漏れ

**対処:**
1. 有効なステータス値に更新する（例: CANCELLED → INTERRUPTED）
2. validation.pyのVALID_STATUSESに新しいステータスを追加する（非推奨）

### 依存関係エラー

```
⚠️ [DEPENDENCY] TASK TASK_250 がBLOCKEDだが依存タスクは全て完了済み
```

**原因:** 依存タスク完了後のBLOCKED解除処理が未実行

**対処:**
```python
# タスクをQUEUEDに更新
python -m scripts.aipm-db.task.update ai_pm_manager TASK_250 --status QUEUED
```

## Claude Code Hookとの統合

### Hookの設定方法

`backend/` 配下のPythonファイルを編集した際に自動的にDB整合性チェックを実行するhookを設定できます。

#### 手動設定手順（TASK_758）

1. `.claude/settings.local.json` を開く

2. `hooks.PostToolUse` 配列の末尾に以下を追加:

```json
{
  "matcher": "Edit(d:/your_workspace/AI_PM/backend/**/*.py)",
  "hooks": [
    {
      "type": "command",
      "command": "cd backend && python backend/utils/verify_db_consistency.py",
      "async": true
    }
  ]
},
{
  "matcher": "Write(d:/your_workspace/AI_PM/backend/**/*.py)",
  "hooks": [
    {
      "type": "command",
      "command": "cd backend && python backend/utils/verify_db_consistency.py",
      "async": true
    }
  ]
}
```

3. `permissions.allow` 配列の末尾に以下を追加:

```json
"Bash(cd backend && python backend/utils/verify_db_consistency.py:*)"
```

4. JSONの構文（特にカンマの位置）に注意してください
5. Claude Codeを再起動して設定を有効化

#### Hook動作

- `backend/` 配下の `.py` ファイルをEdit/Write操作した時に自動実行
- 非同期実行（`async: true`）のため編集操作をブロックしない
- バックグラウンドでDB整合性チェックを実行
- エラーがあればログに出力

#### 設定ファイル

- Hook設定ガイド: `PROJECTS/ai_pm_manager/RESULT/ORDER_083/06_ARTIFACTS/TASK_758_SETTINGS_GUIDE.md`
- Hook設定JSON: `PROJECTS/ai_pm_manager/RESULT/ORDER_083/06_ARTIFACTS/TASK_758_hook_config.json`

## 推奨される使用タイミング

1. **自動実行（Hook）:** Claude Codeのhook機能により、backend/配下のPython編集時に自動実行
2. **スクリプト編集後:** backend/配下のPythonスクリプトを編集したら必ず実行
3. **コミット前:** Gitコミット前のPre-commitフックで実行
4. **定期チェック:** CIで定期的に実行（日次など）
5. **デバッグ時:** 予期しない動作が発生した場合の原因調査

## 制限事項

- `--fix` オプションは未実装（検出のみ）
- プロジェクト指定時も全テーブルをスキャン（パフォーマンス最適化の余地あり）
- 大量の問題がある場合、出力が長くなる（--verbose使用時）

## 関連ファイル

- `utils/db.py`: データベース接続・クエリ実行
- `utils/validation.py`: ステータス定義・入力検証
- `utils/transition.py`: 状態遷移ルール定義
- `config.py`: データベースパス設定
