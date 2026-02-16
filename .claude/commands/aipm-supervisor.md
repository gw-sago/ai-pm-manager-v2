---
description: Supervisor（統括）機能 - 複数プロジェクトの横断管理
argument-hint: <subcommand> [args] (list|create|assign|unassign|xbacklog|dispatch|dashboard)
---

複数プロジェクトを横断管理するSupervisor機能を操作します。

**サブコマンド一覧**:
| サブコマンド | 説明 |
|------------|------|
| `list` | Supervisor一覧表示 |
| `create NAME` | Supervisor作成 |
| `assign PROJECT_ID SUPERVISOR_ID` | プロジェクトをSupervisorに割当 |
| `unassign PROJECT_ID` | プロジェクトの割当解除 |
| `xbacklog add SUPERVISOR_ID TITLE` | 横断バックログ追加 |
| `xbacklog list SUPERVISOR_ID` | 横断バックログ一覧 |
| `xbacklog analyze XBACKLOG_ID` | 振り分け分析実行 |
| `dispatch XBACKLOG_ID [PROJECT_ID\|--auto]` | 振り分け実行 |
| `dashboard SUPERVISOR_ID` | ダッシュボード表示 |

---

## 引数解析

`$ARGUMENTS` を解析：
- 第1引数: サブコマンド（必須）
- 残りの引数: サブコマンド固有のパラメータ

サブコマンドが不明な場合：
```
エラー: 不明なサブコマンド: {subcommand}
使い方: /aipm-supervisor <list|create|assign|unassign|xbacklog|dispatch|dashboard> [args]
```

---

## サブコマンド詳細

### 1. list - Supervisor一覧

```bash
python backend/supervisor/list.py --with-projects --json
```

**出力形式**:
```
=== Supervisor一覧 ===

● SUPERVISOR_001: フロントエンド統括 (ACTIVE)
  配下プロジェクト: 2件
  - AI_PM_PJ: AI PM Project
  - ai_pm_manager: AI PM Manager

○ SUPERVISOR_002: バックエンド統括 (INACTIVE)
  配下プロジェクト: 0件
```

---

### 2. create NAME - Supervisor作成

```bash
python backend/supervisor/create.py --name "$NAME" [--desc "$DESC"] --json
```

**引数**:
- NAME: Supervisor名（必須）
- --desc: 説明（オプション）

**成功時の出力**:
```
Supervisor 'SUPERVISOR_001' を作成しました。
  名前: フロントエンド統括
  ステータス: ACTIVE
```

---

### 3. assign PROJECT_ID SUPERVISOR_ID - プロジェクト割当

```bash
python backend/supervisor/assign.py $PROJECT_ID $SUPERVISOR_ID --json
```

**成功時の出力**:
```
プロジェクト 'AI_PM_PJ' を Supervisor 'SUPERVISOR_001' に割り当てました。
```

---

### 4. unassign PROJECT_ID - 割当解除

```bash
python backend/supervisor/unassign.py $PROJECT_ID --json
```

**成功時の出力**:
```
プロジェクト 'AI_PM_PJ' の Supervisor 割り当てを解除しました。
  (解除したSupervisor: フロントエンド統括)
```

---

### 5. xbacklog add SUPERVISOR_ID TITLE - 横断バックログ追加

```bash
python backend/xbacklog/add.py $SUPERVISOR_ID --title "$TITLE" [--priority High|Medium|Low] [--desc "$DESC"] --json
```

**引数**:
- SUPERVISOR_ID: Supervisor ID（必須）
- TITLE: タイトル（必須）
- --priority: 優先度（オプション、デフォルト: Medium）
- --desc: 説明（オプション）

**成功時の出力**:
```
横断バックログ 'XBACKLOG_001' を追加しました。
  Supervisor: SUPERVISOR_001
  タイトル: データエクスポート機能
  優先度: High
  ステータス: PENDING
```

---

### 6. xbacklog list SUPERVISOR_ID - 横断バックログ一覧

```bash
python backend/xbacklog/list.py $SUPERVISOR_ID [--status PENDING|ANALYZING|ASSIGNED|DONE] --json
```

**出力形式**:
```
=== 横断バックログ一覧 ===
Supervisor: SUPERVISOR_001

--- 📋 未処理 ---
  🔴 XBACKLOG_001: データエクスポート機能
     優先度: High

--- 🔍 分析中 ---
  🟡 XBACKLOG_002: パフォーマンス改善
     優先度: Medium

--- ✅ 振り分け済 ---
  🟢 XBACKLOG_003: ドキュメント整備
     振り分け先: AI_PM_PJ → BACKLOG_045
```

---

### 7. xbacklog analyze XBACKLOG_ID - 振り分け分析

```bash
python backend/xbacklog/analyze.py $XBACKLOG_ID --save --json
```

**出力形式**:
```
=== 振り分け分析結果: XBACKLOG_001 ===
タイトル: データエクスポート機能

抽出キーワード: エクスポート, データ, 機能

--- 推奨プロジェクト ---
  1. AI_PM_PJ: AI PM Project
     スコア: 45 ★★★★★
     マッチファイル例: scripts/export.py

  2. ai_pm_manager: AI PM Manager
     スコア: 23 ★★★
     マッチファイル例: src/utils/data.ts

【推奨】AI_PM_PJ (AI PM Project)
```

---

### 8. dispatch XBACKLOG_ID [PROJECT_ID|--auto] - 振り分け実行

**手動振り分け**:
```bash
python backend/xbacklog/dispatch.py $XBACKLOG_ID $PROJECT_ID --json
```

**自動振り分け**（分析結果の推奨プロジェクトを使用）:
```bash
python backend/xbacklog/dispatch.py $XBACKLOG_ID --auto --json
```

**成功時の出力**:
```
=== 振り分け完了 ===
横断バックログ 'XBACKLOG_001' を AI_PM_PJ の BACKLOG_046 に振り分けました

  横断バックログ: XBACKLOG_001
  タイトル: データエクスポート機能
  振り分け先: AI_PM_PJ (AI PM Project)
  作成BACKLOG: BACKLOG_046
  優先度: High
  (分析結果に基づく自動選択)
```

---

### 9. dashboard SUPERVISOR_ID - ダッシュボード

```bash
python backend/supervisor/dashboard.py $SUPERVISOR_ID --json
```

**出力形式**:
```
=== Supervisor ダッシュボード ===
SUPERVISOR_001: フロントエンド統括

■ 配下プロジェクト (2件)
| プロジェクト | ステータス | ORDER進捗 | タスク進捗 |
|-------------|-----------|----------|-----------|
| AI_PM_PJ | IN_PROGRESS | 85/90 | 520/580 |
| ai_pm_manager | IN_PROGRESS | 35/40 | 120/150 |

■ 横断バックログ (5件)
| ステータス | 件数 |
|-----------|------|
| PENDING | 2 |
| ANALYZING | 1 |
| ASSIGNED | 2 |
| DONE | 0 |

■ 集計
- 総ORDER数: 130
- 総タスク数: 730
- 完了率: 87%
```

---

## エラーハンドリング

スクリプトがエラーを返した場合：
```json
{
  "error": "エラーメッセージ"
}
```

エラー内容をユーザーに表示して処理を終了。

---

## 使用例

```bash
# Supervisor作成
/aipm-supervisor create "フロントエンド統括"

# プロジェクト割当
/aipm-supervisor assign AI_PM_PJ SUPERVISOR_001

# 横断バックログ追加
/aipm-supervisor xbacklog add SUPERVISOR_001 "新機能要望"

# 分析実行
/aipm-supervisor xbacklog analyze XBACKLOG_001

# 自動振り分け
/aipm-supervisor dispatch XBACKLOG_001 --auto

# ダッシュボード表示
/aipm-supervisor dashboard SUPERVISOR_001
```

---

**Version**: 1.0.0
**作成日**: 2026-02-05
