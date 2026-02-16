---
description: バックログ項目を追加
argument-hint: PROJECT_NAME "タイトル" [--priority High|Medium|Low] [--category カテゴリ]
---

バックログに新しいアイデア・要望を追加します。

**引数**:
- 第1引数: プロジェクト名（例: AI_PM_PJ）
- 第2引数: バックログ項目のタイトル（引用符で囲む）
- オプション: `--priority High|Medium|Low` （デフォルト: Medium）
- オプション: `--category カテゴリ` （機能追加/改善/バグ修正/ドキュメント/リファクタリング/調査/その他）

引数が提供された場合、以下のように解析してください：
- `$ARGUMENTS` を解析し、第1引数を `PROJECT_NAME`、第2引数（引用符内）を `TITLE`、`--priority` オプションを `PRIORITY`、`--category` オプションを `CATEGORY` として使用
- 引数が不足している場合: エラーメッセージ「エラー: プロジェクト名とタイトルを指定してください。使い方: /aipm-backlog-add PROJECT_NAME "タイトル" [--priority High|Medium|Low]」を表示
- 優先度が指定されていない場合: `Medium` をデフォルトとして使用
- 優先度が `High`, `Medium`, `Low` 以外の場合: エラーメッセージ「エラー: 優先度は High, Medium, Low のいずれかを指定してください。」を表示

---

## 処理フロー

以下の手順を実行してください：

### Step 1: プロジェクト存在確認

プロジェクトが存在するか確認：
- `PROJECTS/$PROJECT_NAME/` ディレクトリが存在するか確認
- 存在しない場合: 「エラー: プロジェクトが見つかりません: $PROJECT_NAME」を表示

---

### Step 2: BACKLOG追加（スクリプト呼び出し）

以下のPythonスクリプトを実行してBACKLOGを追加：

```bash
python backend/backlog/add.py $PROJECT_NAME --title "$TITLE" --priority $PRIORITY [--category $CATEGORY] [--description "$DESCRIPTION"] --json
```

**パラメータ**:
- `$PROJECT_NAME`: プロジェクト名
- `--title`: BACKLOGタイトル（必須）
- `--priority`: 優先度（High/Medium/Low、デフォルト: Medium）
- `--category`: カテゴリ（オプション）
- `--description`: 説明（オプション）
- `--json`: JSON形式で出力

**成功時の出力例**:
```json
{
  "success": true,
  "backlog_id": "BACKLOG_032",
  "title": "ダッシュボードの性能改善",
  "priority": "Medium",
  "category": "改善",
  "message": "BACKLOGを作成しました: BACKLOG_032"
}
```

**スクリプトが自動実行する処理**:
1. BACKLOG_ID自動採番（最大番号+1）
2. DBへのINSERT
3. 状態遷移履歴の記録

---

### Step 3: エラーハンドリング

スクリプトがエラーを返した場合：

```json
{
  "success": false,
  "error": "エラーメッセージ"
}
```

エラー内容をユーザーに表示し、以下の案内を追加：
```
【リカバリ方法】
- DBスクリプトが正常に動作するか確認してください
- python backend/backlog/list.py $PROJECT_NAME でDB接続を確認
- 問題が解決しない場合は /aipm-restore を実行
```

---

### Step 4: 完了メッセージ

スクリプト成功時、以下のメッセージを表示：

```
【バックログ追加完了】

プロジェクト: {PROJECT_NAME}
BACKLOG_ID: {backlog_id}
タイトル: {title}
優先度: {priority}
カテゴリ: {category}（カテゴリ指定時のみ）
ステータス: TODO
登録日: {今日の日付}

【次のアクション】
- 詳細な説明はDBを直接更新: python backend/backlog/update.py {PROJECT_NAME} {backlog_id} --description "説明"
- ORDER化する場合: /aipm-backlog-to-order {PROJECT_NAME} {backlog_id}
- 完全自動実行: /aipm-full-auto {PROJECT_NAME} {backlog_id}
```

---

## 実行例

### 基本的な追加（Medium優先度）

```bash
/aipm-backlog-add AI_PM_PJ "ダッシュボードの性能改善"
```

スクリプト呼び出し:
```bash
python backend/backlog/add.py AI_PM_PJ --title "ダッシュボードの性能改善" --json
```

### High優先度で追加

```bash
/aipm-backlog-add AI_PM_PJ "セキュリティ脆弱性の修正" --priority High
```

スクリプト呼び出し:
```bash
python backend/backlog/add.py AI_PM_PJ --title "セキュリティ脆弱性の修正" --priority High --json
```

### カテゴリ指定で追加

```bash
/aipm-backlog-add AI_PM_PJ "UIの配色変更" --priority Low --category 改善
```

スクリプト呼び出し:
```bash
python backend/backlog/add.py AI_PM_PJ --title "UIの配色変更" --priority Low --category 改善 --json
```

---

## カテゴリ一覧

| カテゴリ | 説明 |
|---------|------|
| 機能追加 | 新規機能の追加 |
| 改善 | 既存機能の改善・強化 |
| バグ修正 | バグ・不具合の修正 |
| ドキュメント | ドキュメントの追加・更新 |
| リファクタリング | コードの整理・最適化 |
| 調査 | 技術調査・検証 |
| その他 | 上記に該当しないもの |

---

## エラーケース

| エラー | メッセージ |
|--------|----------|
| プロジェクト名なし | 「エラー: プロジェクト名とタイトルを指定してください。使い方: /aipm-backlog-add PROJECT_NAME "タイトル" [--priority High\|Medium\|Low]」 |
| プロジェクト未発見 | 「エラー: プロジェクトが見つかりません: $PROJECT_NAME」 |
| 不正な優先度 | 「エラー: 優先度は High, Medium, Low のいずれかを指定してください。」 |
| DBエラー | 「エラー: データベースエラー: {詳細}」＋リカバリ案内 |

---

## 注意事項

- バックログはDBで管理されています（BACKLOG.mdは廃止）
- バックログの一覧確認: `python backend/backlog/list.py $PROJECT_NAME`
- バックログの詳細な説明を追加する場合:
  ```bash
  python backend/backlog/update.py $PROJECT_NAME $BACKLOG_ID --description "詳細な説明"
  ```

---

**バージョン**: 2.1.0（BACKLOG.md廃止対応）
**更新日**: 2026-02-04
