---
description: 承認フロー実行 - 修正内容をレビューし承認判定
argument-hint: なし
---

PMまたはWorkerとして承認・リリースフローを実行します。

---

## Step 1: 状態確認

RELEASE_STATUS.mdを読み込み、現在のステータスを確認:
```bash
python scripts/release/update_status.py --release-status RELEASE_STATUS.md --dry-run --json
```

ファイルが存在しない場合はテンプレートから作成して続行。

---

## Step 2: ステータスに応じた処理分岐

### Case A: DRAFT（Worker実行）

1. **変更ファイル検出** - スクリプト実行:
```bash
python scripts/release/detect_changes.py --dev "PROJECTS/AI_PM_PJ/DEV" --prod "." --pattern "**/*.md" --since 7 --json
```

2. **バックアップ作成** - スクリプト実行（変更ファイルをカンマ区切りで渡す）:
```bash
python scripts/release/create_backup.py --version {VERSION} --files "{FILE1},{FILE2}" --source "."
```

3. **ステータス更新** - スクリプト実行:
```bash
python scripts/release/update_status.py --status REVIEW --version {VERSION} --add-history "DRAFT→REVIEW | Worker | PMレビュー依頼"
```

4. **出力**: レビュー依頼メッセージを表示し、`/aipm-release-review`再実行を促す

---

### Case B: REVIEW（PM実行 - AI判断）

**承認基準チェック**（AIが判断）:
- [ ] 変更内容がORDER要件を満たしている
- [ ] コマンド定義のフォーマットが正しい
- [ ] 既存のコマンドとの整合性がある
- [ ] ドキュメントが更新されている
- [ ] テストが実施されている

**判定実施**:
- 変更ファイルを確認し、承認基準を満たしているか判定

**⚠️ 承認前バージョン更新チェック（必須）**:

承認前に以下のファイルのバージョン表記が新バージョンに更新されているか確認:

| ファイル | 確認箇所 | 更新内容 |
|---------|---------|---------|
| `README.md` | 末尾の `**Version**:` | 新バージョン番号 |
| `README.md` | 末尾の `**最終更新**:` | 本日日付 |

**未更新の場合**:
1. 上記ファイルを編集してバージョン番号を更新
2. 更新完了後、承認処理を続行

**承認の場合** - スクリプト実行:
```bash
python scripts/release/update_status.py --status APPROVED --add-history "REVIEW→APPROVED | PM | 承認"
```
→ DB自動更新（対象ORDER→COMPLETED）、リリース完了メッセージ表示

**差し戻しの場合** - スクリプト実行:
```bash
python scripts/release/update_status.py --status DRAFT --add-history "REVIEW→DRAFT | PM | 差し戻し: {理由}"
```
→ 差し戻し理由を記載、Worker修正を促す

---

### Case C: APPROVED

```
既にAPPROVED状態です。新規修正はDRAFT状態から開始してください。
問題がある場合は `/aipm-rollback` でロールバック可能です。
```

---

## エラーハンドリング

| コード | エラー | 対処 |
|--------|--------|------|
| E01 | RELEASE_STATUS.mdフォーマットエラー | フォーマットを確認・修正 |
| E02 | 不正なステータス値 | DRAFT/REVIEW/APPROVEDのいずれかに修正 |
| E03 | CHANGELOG.md取得エラー | RELEASE_STATUS.mdのバージョン値を使用 |

---

## 関連コマンド

- `/aipm-rollback`: 前バージョンに戻す
- `/aipm-pm`: ORDER処理
- `/aipm-worker`: TASK実行

---

**作成日**: 2026-01-13
**最終更新**: 2026-01-29（バージョン更新チェック必須化）
