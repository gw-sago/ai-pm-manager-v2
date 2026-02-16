---
description: ORDER完了→BACKLOG完了→リリースログ→コミットを一括実行
argument-hint: PROJECT_NAME ORDER_ID [ORDER_ID2 ...]
---

# ORDER リリース完了処理

ORDER指定でリリース完了処理をワンコマンドで実行します。
BACKLOG完了・リリースログ記録・git commitまでを一気通貫で自動実行。

**引数**:
- 第1引数: プロジェクト名（必須）
- 第2引数以降: ORDER ID（1つ以上必須、スペース区切りで複数指定可）

**使用例**:
```
/aipm-release ai_pm_manager ORDER_087
/aipm-release ai_pm_manager ORDER_087 ORDER_088
```

---

## Step 1: 引数解析・ORDER状態検証

### 1.1 引数パース

コマンド引数 `$ARGUMENTS` をスペース区切りで解析:
- 1番目: `$PROJECT_NAME`
- 2番目以降: `$ORDER_IDS` （ORDER_XXX形式のリスト）

引数不足の場合はエラー表示:
```
エラー: 引数が不足しています。

使用方法: /aipm-release PROJECT_NAME ORDER_ID [ORDER_ID2 ...]
例: /aipm-release ai_pm_manager ORDER_087 ORDER_088
```

### 1.2 各ORDERの状態検証

各ORDER_IDに対して以下を実行:

```bash
python backend/task/list.py $PROJECT_NAME --order $ORDER_ID --json
```

**検証条件**:
- 全タスクのstatusが `COMPLETED` または `DONE` であること
- 未完了タスク（QUEUED/IN_PROGRESS/BLOCKED/REWORK）がある場合はエラー:

```
エラー: ORDER_087 に未完了タスクがあります。

| タスク | タイトル | ステータス |
|--------|---------|----------|
| TASK_907 | 統合テストと動作確認 | QUEUED |

リリース前に全タスクを完了させてください。
```

**全ORDER検証OK → Step 2 へ**

---

## Step 2: 成果物収集（各ORDERごと）

### 2.1 REPORT読み込みによる成果物パス抽出

各ORDERのREPORTファイルを読み込み、成果物（作成・変更ファイル）を抽出:

```
PROJECTS/$PROJECT_NAME/RESULT/$ORDER_ID/05_REPORT/REPORT_*.md
```

各REPORTから以下のパターンで成果物パスを抽出:
- 「成果物」「変更ファイル」「作成ファイル」セクション内のファイルパス
- テーブル内の `NEW` / `MODIFIED` / `CREATED` 種別とファイルパス
- コードブロック内のファイルパス参照

### 2.2 git statusによる未コミット変更の検出

```bash
git status --short
```

未コミットファイルのうち、以下を対象に含める:
- `PROJECTS/$PROJECT_NAME/RESULT/$ORDER_ID/` 配下のファイル（REPORT/REVIEW）
- `PROJECTS/$PROJECT_NAME/RELEASE_LOG.md`
- REPORTで言及されている成果物ファイル
- `backend/` 配下の変更ファイル
- `docs/` 配下の変更ファイル
- `.claude/commands/` 配下の変更ファイル

### 2.3 成果物リストの構築

各ORDERごとにリリースファイルリストを構築:
```json
[
  {"target": "backend/incident/analyze_patterns.py", "change_type": "NEW"},
  {"target": "backend/pm/process_order.py", "change_type": "MODIFIED"}
]
```

---

## Step 3: 関連BACKLOG検出・完了処理

### 3.1 各ORDERに紐づくBACKLOGを取得

```bash
python backend/backlog/list.py $PROJECT_NAME --json
```

結果から `related_order_id` が対象ORDER_IDと一致するBACKLOGを抽出。

### 3.2 BACKLOG完了処理

抽出したBACKLOGのうち、statusが `IN_PROGRESS` のものをDONEに更新:

```bash
python backend/backlog/update.py $PROJECT_NAME $BACKLOG_ID --status DONE
```

**スキップ条件**（エラーにしない）:
- 関連BACKLOGがない → スキップ
- 既にDONE → スキップ
- CANCELED → スキップ

### 3.3 結果を記録

更新したBACKLOG情報を後続ステップで使用するために保持:
- BACKLOG_ID
- タイトル
- 旧ステータス → DONE

### 3.4 バックログ再整理

BACKLOG完了処理後、優先順位・依存関係・ステータスに基づいてsort_orderを再計算:

```bash
python backend/backlog/reorder.py $PROJECT_NAME --json
```

**再整理ルール**:
- IN_PROGRESSは最上位固定（sort_order: 0〜）
- 優先度順: High → Medium → Low
- 同一priority内は依存関係順（前提未達は後ろ）
- DONEは最下位

**スキップ条件**（エラーにしない）:
- バックログが存在しない → スキップ
- reorder.py実行エラー → 警告表示して続行

---

## Step 4: リリースログ自動生成

### 4.1 各ORDERごとにリリースエントリを生成

各ORDER_IDに対して `release/log.py` を実行:

```bash
python backend/release/log.py $PROJECT_NAME --order $ORDER_ID --files '$FILES_JSON' --executor "PM (Claude Opus 4.6)" --notes "$NOTES"
```

**パラメータ**:
- `$FILES_JSON`: Step 2で構築したファイルリスト（JSON形式）
- `$NOTES`: `$ORDER_TITLE` + 関連BACKLOGがあれば `(BACKLOG_XXX)` を付記

### 4.2 BACKLOG情報のリリースログ追記

`release/log.py` の出力後、RELEASE_LOG.mdを読み込み、生成されたエントリに
BACKLOGフィールドを追記（`- **ORDER**:` の直後に挿入）:

```markdown
- **ORDER**: ORDER_087
- **BACKLOG**: BACKLOG_132
```

※ 関連BACKLOGがない場合はBACKLOG行を追記しない

---

## Step 5: 統合リリース（git_release.py）

### 5.1 統合リリーススクリプト実行

Step 1〜4の処理を `git_release.py` で一括実行（ORDER完了済みの場合は `--skip-complete` 自動判定）:

**単一ORDER**:
```bash
python backend/release/git_release.py $PROJECT_NAME $ORDER_ID --json
```

**複数ORDER**:
```bash
python backend/release/git_release.py $PROJECT_NAME $ORDER_ID1 --multi $ORDER_ID1,$ORDER_ID2 --json
```

git_release.py が自動的に以下を実行:
1. ORDER状態検証（全タスクCOMPLETED/DONE確認）
2. **マイグレーション実行（破壊的DB変更を含む場合のみ）**
   - is_destructive_db_change = 1 のタスクを検出
   - ARTIFACTS配下のマイグレーションスクリプト（migrate/*.py）を実行
   - MigrationRunnerを使用した安全なマイグレーション
3. ORDER完了処理（complete_order）
4. 関連BACKLOG → DONE更新
5. RELEASE_LOG.md記録
6. ステージング対象ファイル自動検出（INCLUDE/EXCLUDEパターン）
7. git add → git commit
8. **ビルド実行（Electronアプリ等、ビルド設定がある場合のみ）**
   - build_manager.py を使用したビルド
   - 成果物（.exe等）の存在確認

**コミットメッセージ**: `release(ORDER_XXX): {タイトル}`

**マイグレーションスキップオプション**:
```bash
--skip-migration  # マイグレーション実行をスキップ
--skip-build      # ビルド実行をスキップ
```

### 5.2 ドライラン確認

事前にドライランで対象ファイルを確認可能:
```bash
python backend/release/git_release.py $PROJECT_NAME $ORDER_ID --dry-run --json
```

### 5.3 コミット失敗時

pre-commit hookでエラーが出た場合:
1. エラー内容を表示
2. 修正可能なら自動修正して再コミット
3. 修正不可能ならユーザーに報告して中断

### 5.4 マイグレーション→ビルド→デプロイ一括実行（execute_release.py）

破壊的DB変更を含むORDERのリリース時に、`execute_release.py` が以下のフローを一括実行:

**実行順序**:
1. **マイグレーション検出**: `is_destructive_db_change = 1` のタスクを検出
2. **マイグレーション実行**: `PROJECTS/$PROJECT_NAME/RESULT/$ORDER_ID/06_ARTIFACTS/migrate/*.py` を自動実行
   - MigrationRunnerによる安全機構（自動バックアップ・PRAGMA foreign_keys制御・トランザクション管理）
   - Worker実行中のタスクを検出し、安全でない場合は中断
   - 失敗時はリリース全体を中断
3. **ビルド実行**: `BUILD_CONFIGS` にプロジェクトが登録されている場合のみ
   - Pre-build（型チェック）→ Build → Artifact確認
   - ビルド履歴はDBに記録（builds テーブル）
   - 失敗しても警告のみでリリースは継続
4. **デプロイ検証**: 成果物の存在・サイズを確認

**個別実行（execute_release.py CLI）**:
```bash
# マイグレーション→ビルド→デプロイ一括実行
python backend/release/execute_release.py $PROJECT_NAME $ORDER_ID --verbose

# マイグレーションのみ実行
python backend/release/execute_release.py $PROJECT_NAME $ORDER_ID --migration-only

# ビルドのみ実行
python backend/release/execute_release.py $PROJECT_NAME $ORDER_ID --build-only

# ドライラン
python backend/release/execute_release.py $PROJECT_NAME $ORDER_ID --dry-run --verbose

# Worker実行中でも強制実行
python backend/release/execute_release.py $PROJECT_NAME $ORDER_ID --force
```

**ビルド個別実行**:
```bash
# ビルドのみ実行
python backend/release/build_manager.py $PROJECT_NAME --order $ORDER_ID --json

# ビルド履歴確認
python backend/release/build_manager.py $PROJECT_NAME --status --json
```

---

## Step 6: 完了サマリ表示

全処理完了後、以下のサマリを表示:

```
## リリース完了

### リリース情報

| ORDER | タイトル | リリースID | ファイル数 |
|-------|---------|-----------|-----------|
| ORDER_087 | TodoWriteチェックリスト標準化 | RELEASE_2026-02-06_018 | 4件 |
| ORDER_088 | INCIDENTSテーブル追加 | RELEASE_2026-02-06_019 | 13件 |

### BACKLOG更新

| BACKLOG | タイトル | 更新 |
|---------|---------|------|
| BACKLOG_132 | ORDER実行時のTodoWriteチェックリスト標準化 | IN_PROGRESS → DONE |
| BACKLOG_136 | INCIDENTSテーブル追加 | IN_PROGRESS → DONE |

### コミット

- ハッシュ: `4537df1`
- メッセージ: `feat(ORDER_087,088): TodoWriteチェックリスト標準化 & INCIDENTSテーブル追加`
- ファイル数: 14 files changed
```

---

## エラーハンドリング

| エラー | 対応 |
|--------|------|
| プロジェクト不存在 | エラーメッセージ表示して終了 |
| ORDER不存在 | エラーメッセージ表示して終了 |
| 未完了タスクあり | 未完了タスク一覧を表示して終了 |
| マイグレーション失敗 | リリース全体を中断（バックアップから復元案内） |
| Worker実行中 | 中断（--force で強制実行可） |
| ビルド失敗 | 警告表示して続行（リリースは中断しない） |
| デプロイ検証失敗 | 警告表示して続行 |
| BACKLOG更新失敗 | 警告表示して続行（リリースは中断しない） |
| リリースログ記録失敗 | エラー表示して終了（コミットしない） |
| git commit失敗 | エラー内容表示、手動対応を案内 |
