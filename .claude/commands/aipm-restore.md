# AI PM Framework 緊急復旧

フレームワークが壊れた場合に、フレームワーク本体のみを安全なバージョンに即時復旧します。
**PROJECTS/配下のプロジェクトデータは保護され、一切変更されません。**

---

## 復旧対象と保護対象

### 復旧対象（フレームワーク本体のみ）

| パス | 内容 |
|------|------|
| `.claude/commands/` | スラッシュコマンド |
| `.claude/agents/` | エージェント定義 |
| `.claude/settings.json` | 共通設定 |
| `.framework/` | フレームワーク設定 |
| `TEMPLATE/` | プロジェクトテンプレート |
| `scripts/` | ユーティリティスクリプト |
| `README.md` | READMEファイル |
| `CLAUDE.md` | Claude設定 |
| `CHANGELOG.md` | 変更履歴 |

### 保護対象（絶対に復旧しない）

| パス | 理由 |
|------|------|
| `PROJECTS/` | 全プロジェクトデータ |
| `data/` | データベース等 |
| `.claude/settings.local.json` | ローカル設定 |

---

## 使用方法

**引数なし**: デフォルトタグ（v1.22.0-pre-db-migration）に復旧

**タグ指定**: 指定したタグに復旧

---

## 実行手順

### Step 1: 引数の確認

- 引数なしの場合: `$TAG = v1.22.0-pre-db-migration`（デフォルト）
- 引数ありの場合: `$TAG = 指定されたタグ`

### Step 2: 現在の状態を確認

以下のコマンドを実行して現在の状態を把握:

```bash
git status
git log --oneline -3
git tag -l
```

### Step 3: 復旧実行（フレームワーク本体のみ）

**方法A: スクリプト使用（推奨）**

```bash
python scripts/emergency_restore.py $TAG
```

**方法B: 手動でgit checkout（選択的）**

```bash
# フレームワーク本体のみを指定タグから復旧
git checkout $TAG -- .claude/commands/
git checkout $TAG -- .claude/agents/
git checkout $TAG -- .claude/settings.json
git checkout $TAG -- .framework/
git checkout $TAG -- TEMPLATE/
git checkout $TAG -- scripts/
git checkout $TAG -- README.md
git checkout $TAG -- CLAUDE.md
git checkout $TAG -- CHANGELOG.md
```

### Step 4: 復旧確認

```bash
# フレームワークの動作確認
ls -la .claude/commands/
cat README.md | head -20

# PROJECTS/配下が保護されていることを確認
git status PROJECTS/
# → 変更なしであるべき
```

### Step 5: 復旧完了報告

以下の情報をユーザーに報告:

```
## 緊急復旧完了

- 復旧先タグ: $TAG
- 復旧対象: フレームワーク本体のみ
- 保護: PROJECTS/配下は変更なし

### 次のステップ

1. フレームワークの動作を確認してください
2. 問題なければコミット:
   ```
   git add -A && git commit -m "fix: restore framework from $TAG"
   ```
```

---

## 利用可能な復旧ポイント

主要な安全なタグ:

| タグ | 説明 |
|------|------|
| `v1.22.0-pre-db-migration` | DB移行前の安全ポイント（ORDER_036設計完了時点） |
| `v1.22.0` | 公式リリースバージョン |
| `v1.21.0` | 初回GitHub連携バージョン |

タグ一覧の確認:
```bash
git tag -l --sort=-creatordate
```

---

## スクリプト版（推奨）

対話式でより安全に復旧:

```bash
python scripts/emergency_restore.py
```

タグ一覧を確認:
```bash
python scripts/emergency_restore.py --list
```

スクリプトの特徴:
- 復旧前に対象ファイルを明示
- PROJECTS/配下は絶対に触らない
- 確認プロンプトあり
