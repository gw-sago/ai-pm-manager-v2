---
description: ロールバック実行 - 前バージョンに戻す
argument-hint: [VERSION]
---

承認済みリリース（APPROVED状態）を前バージョンにロールバックします。

**前提条件**: RELEASE_STATUS.mdのステータスが`APPROVED`であること
**引数**: `VERSION` (任意) - ロールバック先バージョン（省略時は直前のバージョン）

---

## 実行手順

### Step 1: バックアップ確認

```bash
python scripts/release/rollback.py --list
```

### Step 2: ロールバック実行

dry-runで事前確認（推奨）:
```bash
python scripts/release/rollback.py --version {VERSION} --dry-run
```

ロールバック実行:
```bash
python scripts/release/rollback.py --version {VERSION}
```

スクリプトが自動実行:
1. バックアップディレクトリ確認（.rollback/v{VERSION}/）
2. ファイル復元（.claude/commands/配下へコピー）
3. 復元結果を表示

### Step 3: ステータス更新

```bash
python scripts/release/update_status.py --add-history "ROLLBACK | PM | v{VERSION}へロールバック"
```

---

## 使用例

```bash
python scripts/release/rollback.py --list                          # 一覧
python scripts/release/rollback.py --version v1.19.0 --dry-run     # 確認
python scripts/release/rollback.py --version v1.19.0               # 実行
python scripts/release/rollback.py --version v1.19.0 --json        # JSON出力
```

---

## エラー時の対処

| エラー | 対処 |
|--------|------|
| バックアップが見つからない | `--list`で利用可能バージョンを確認 |
| 本番ディレクトリが見つからない | `--prod`オプションでパス指定 |

---

## 関連

- `/aipm-release-review`: 承認フロー
- `scripts/release/rollback.py --help`: スクリプトヘルプ

---

**作成日**: 2026-01-13 | **軽量化日**: 2026-01-21 | **v2.0**（スクリプト呼び出し版）
