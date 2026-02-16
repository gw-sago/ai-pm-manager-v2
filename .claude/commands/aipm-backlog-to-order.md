---
description: BACKLOG項目をORDER化
argument-hint: PROJECT_NAME BACKLOG_ID
---

BACKLOG項目をORDERに変換し、新規プロジェクトとして開始します。

**引数**:
- 第1引数: プロジェクト名（例: AI_PM_PJ）
- 第2引数: BACKLOG_ID（例: BACKLOG_003）

引数が提供された場合、以下のように解析してください：
- `$ARGUMENTS` をスペースで分割し、第1引数を `PROJECT_NAME`、第2引数を `BACKLOG_ID` として使用
- 引数が不足している場合: エラーメッセージ「エラー: プロジェクト名とBACKLOG_IDを指定してください。使い方: /aipm-backlog-to-order PROJECT_NAME BACKLOG_ID」を表示
- BACKLOG_IDが `BACKLOG_` で始まらない場合: エラーメッセージ「エラー: BACKLOG_IDは "BACKLOG_XXX" 形式で指定してください。」を表示

以下の手順を実行してください：

---

## Step 1: DBからBACKLOG情報を取得

```bash
python backend/backlog/list.py $PROJECT_NAME --id $BACKLOG_ID --json
```

**成功時**:
- JSON出力から以下を抽出:
  - `title`: タイトル
  - `priority`: 優先度
  - `status`: ステータス
  - `description`: 説明

**エラー時**:
- 「エラー: BACKLOG_ID "{BACKLOG_ID}" が見つかりません。」を表示し、処理を終了

---

## Step 2: ステータス検証

- 取得した `status` を確認
- ステータスが `TODO` 以外の場合: 「エラー: ORDER化できるのはステータスが "TODO" の項目のみです。現在のステータス: {status}」を表示し、処理を終了

---

## Step 3: ORDER番号採番

- `PROJECTS/$PROJECT_NAME/ORDERS/` ディレクトリ内の既存ORDER_XXX.mdファイルを検索
- 最大のORDER番号を取得（例: ORDER_012.md, ORDER_015.md → 最大値は 15）
- 新規ORDER番号 = 最大値 + 1 を3桁ゼロ埋めで生成（例: `ORDER_016`）
- 既存ORDERが0件の場合: `ORDER_001` を使用

---

## Step 4: ORDER_XXX.md作成

`PROJECTS/$PROJECT_NAME/ORDERS/ORDER_{新規ORDER番号}.md` を作成:

```markdown
# ORDER_{新規ORDER番号}.md

## 発注情報
- **発注ID**: ORDER_{新規ORDER番号}
- **発注日**: {今日の日付 YYYY-MM-DD}
- **発注者**: User
- **優先度**: {BACKLOG項目の優先度}
- **由来**: {BACKLOG_ID}

---

## 発注内容

### 概要
{BACKLOG項目のタイトル}

### 詳細
{BACKLOG項目の説明}

### 受け入れ条件
{BACKLOG項目の受け入れ条件（説明に含まれる場合）}

---

## PM記入欄

### 要件理解チェック
- [ ] 発注内容を理解した
- [ ] GOAL.mdを作成した
- [ ] REQUIREMENTS.mdを作成した
- [ ] STAFFING.mdを作成した
- [ ] タスクを発行した

### 備考
（PM記入）

---

**作成日**: {今日の日付}
**作成者**: System（BACKLOG→ORDER変換）
**変換元**: DB:{BACKLOG_ID}
```

---

## Step 5: DBにORDER登録・BACKLOG更新

```bash
# ORDER作成
python backend/order/create.py $PROJECT_NAME \
  --order-id ORDER_{新規ORDER番号} \
  --title "{タイトル}" \
  --priority {優先度} \
  --backlog-id {BACKLOG_ID}

# BACKLOGステータス更新
python backend/backlog/update.py $PROJECT_NAME $BACKLOG_ID \
  --status IN_PROGRESS \
  --order ORDER_{新規ORDER番号}
```

**エラー時**: 「エラー: DB更新に失敗しました。DBスクリプトの修復が必要です。」を表示し、処理を終了

---

## Step 6: 完了メッセージ

```
【ORDER化完了】

プロジェクト: {PROJECT_NAME}
BACKLOG_ID: {BACKLOG_ID}
タイトル: {タイトル}

ORDER_{新規ORDER番号}.md を作成しました。
パス: PROJECTS/{PROJECT_NAME}/ORDERS/ORDER_{新規ORDER番号}.md

【DB更新】
- BACKLOGステータス: TODO → IN_PROGRESS
- 関連ORDER: ORDER_{新規ORDER番号}

【次のアクション】
PMとして要件定義とタスク発行を実施してください：
/aipm-pm {PROJECT_NAME} {新規ORDER番号}
```

---

## 実行例

```bash
# BACKLOG_003をORDER化
/aipm-backlog-to-order AI_PM_PJ BACKLOG_003
```
→ AI_PM_PJ プロジェクトの BACKLOG_003 を ORDER化し、DB更新を実行

---

## エラーケース

| 条件 | エラーメッセージ |
|------|-----------------|
| 引数不足 | 「エラー: プロジェクト名とBACKLOG_IDを指定してください。」 |
| BACKLOG_ID形式不正 | 「エラー: BACKLOG_IDは "BACKLOG_XXX" 形式で指定してください。」 |
| BACKLOG_IDがDBに存在しない | 「エラー: BACKLOG_ID "{BACKLOG_ID}" が見つかりません。」 |
| ステータスがTODO以外 | 「エラー: ORDER化できるのはステータスが "TODO" の項目のみです。」 |
| DB更新失敗 | 「エラー: DB更新に失敗しました。DBスクリプトの修復が必要です。」 |

---

**バージョン**: 2.0.0（DB駆動版）
**更新日**: 2026-02-04
