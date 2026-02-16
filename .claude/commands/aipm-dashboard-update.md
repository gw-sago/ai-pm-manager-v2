# aipm-dashboard-update

プロジェクトの設計書ダッシュボードを作成・更新します。

**機能**:
- 初回: DASHBOARDフォルダ作成、HTMLテンプレート配置、ランチャーバッチ配置
- 更新: JSONデータ再生成

## 使い方

```
/aipm-dashboard-update PROJECT_NAME
```

## 引数

- `PROJECT_NAME`: プロジェクト名（例: AI_PM_PJ, ai_pm_manager）

$ARGUMENTS

---

## 実行手順

### 1. プロジェクト名の確認

引数が指定されていない場合は、利用可能なプロジェクト一覧を表示してください。

```bash
ls -d PROJECTS/*/
```

### 2. ダッシュボード生成（初回セットアップ含む）

以下のコマンドでダッシュボードを生成（初回は自動でセットアップも実施）:

```bash
python -m scripts.dashboard.generate {PROJECT_NAME}
```

このコマンドで以下が自動実行されます:
- DASHBOARDフォルダ作成
- HTMLテンプレート配置
- ランチャーバッチ配置（初回のみ）
- JSONデータ生成

### 3. 結果報告

生成完了後、以下を報告:

- 生成されたファイル
- ダッシュボードの開き方
- プロジェクトの現在の状態サマリ

---

## 出力例

**初回作成時:**
```
設計書ダッシュボードを作成しました: PROJECTS/AI_PM_PJ/DASHBOARD/

作成ファイル:
- DASHBOARD/index.html
- DASHBOARD/data/dashboard.json
- 設計書ダッシュボード.bat（ランチャー）

開き方:
  プロジェクトフォルダの「設計書ダッシュボード.bat」をダブルクリック
  → ブラウザが自動で開きます
```

**更新時:**
```
設計書ダッシュボードを更新しました: PROJECTS/AI_PM_PJ/DASHBOARD/

更新ファイル:
- data/dashboard.json

プロジェクト状態:
- Current ORDER: ORDER_063 (COMPLETED)
```

---

## 表示される情報

| タブ | 内容 |
|------|------|
| プロジェクト概要 | 目的・背景、技術スタック、成果物 |
| システム構成図 | ER図、アーキテクチャ図 |
| 処理フロー | フローチャート、シーケンス図 |
| 状態遷移 | タスク・ORDER状態遷移図 |
| 仕様書 | PROJECT_INFO/02_SPECS/ 配下 |
| ADR | PROJECT_INFO/04_ADR/ 配下 |

---

## 更新推奨タイミング

- ORDER完了時
- 仕様書・アーキテクチャ図を追加・変更した時
- プロジェクト状況を誰かに共有する前
