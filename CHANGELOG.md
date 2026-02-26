# Changelog

All notable changes to AI PM Manager V2 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-snapshot] - 2026-02-26

### Fixed
- Workerボタン非表示バグの根本原因を修正（ORDER_097）
  - DashboardService.tsのrelatedOrderIdマッピングを`item.backlog_id`→`item.id`に修正
  - backlog経由でないORDER（直接作成）でWorkerボタンが表示されない問題を解消
- order/create.pyの--statusオプションがDBに反映されないバグを修正（ORDER_100）
- docs/ディレクトリ未作成時にdocs_list.pyがexit code 1で異常終了する不具合を修正（ORDER_094）
  - docs/が存在しない場合は空リスト（success: true, files: [], categories: []）を正常に返すように変更
- PMボタン押下後にWorkerボタンが表示されないバグを修正（ORDER_093）
- UIのPMボタンでDRAFT ORDERを処理する際、DRAFT→IN_PROGRESSの不正な遷移エラーを修正（ORDER_092）
  - ScriptExecutionService.tsのStep 1でDRAFT→PLANNINGに遷移するよう修正
  - IN_PROGRESSへの遷移はprocess_order.pyのStep 6に委譲
- ORDER一覧画面がbacklog/list.py（非推奨）を使用しており全ORDERが表示されない不具合を修正（ORDER_088）
  - DashboardService.getAllBacklogs()のスクリプトをorder/list.pyに切り替え
  - レスポンスパースをorder/list.pyの直接配列形式に対応
  - BacklogFilterBarのステータス定数をORDER用に更新（PLANNING,REVIEW,COMPLETED等）
- バックグラウンドログタブが7000件超のログで重い・読み込み停止する不具合を修正（ORDER_090）
  - ステータス判定キャッシュ導入、表示件数を最新100件に制限
  - リフレッシュ間隔を10秒→30秒に延長、非表示時はリフレッシュ停止
- PMボタンがDB駆動ORDERで動作しない不具合を修正（ORDER_091）
- ドキュメントタブのファイルツリーにファイル名が表示されないバグ修正（ORDER_087）

### Changed
- ORDER詳細パネルのWorker実行・フルオートボタンを廃止し、ORDER一覧に統合（ORDER_099）
- ORDER一覧のCANCELLEDステータスにグレーアイコン・色を適用し、DRAFTと差別化（ORDER_101）
- 非推奨backlog関連コードを削除しORDER命名に統一（ORDER_089）
- 「バックログ」タブを「ORDER一覧」に統一

### Added
- /aipmコマンドの状態取得を統合スクリプト化（ORDER_096）
  - 複数Pythonスクリプト呼び出し（最大5回）を1回のPython起動・1回のDB接続に集約
  - N+1クエリ問題を解消しクエリ数をO(1)定数に最適化
- ドキュメントタブでユーザー指定のプロジェクトフォルダを参照可能に（ORDER_103）
  - プロジェクト設定のdev_workspace_pathからdocs/フォルダを自動検出
  - 未指定時は従来のPROJECTS/{project}/docs/をフォールバック表示
- 本番DBへのテストORDER作成防止バリデーション追加（ORDER_104）
  - db_config.pyにRoaming環境検出・テスト実行検出ロジック追加
  - Worker/フルオート実行時にテストデータ混入を防止
- ドキュメントタブで.html/.txtファイルも表示可能に（ORDER_095）
  - docs_list.pyを複数拡張子（.md/.html/.txt）対応に拡張
  - docs_get.pyの拡張子なし時の.md自動付与ロジックを修正
  - DocsPanel.tsxでHTML/テキストファイルの表示に対応
- ordersテーブルにDRAFTステータス追加、DRAFT ORDER CRUD API実装（ORDER_065）
- tasksテーブルにparent_task_id/depth/is_leader/decomposition_strategy/aggregation_task_id/task_phaseカラム追加（ORDER_065）
- task/create.pyに循環参照防止バリデーション・depth自動計算（最大4階層）実装（ORDER_065）
- order/create.pyに--status/--description/--sort-order/--category/--backlog-idオプション追加（ORDER_065）
- order/list.pyに--draftフィルタオプション追加（ORDER_065）
- orders.backlog_id逆引き補完マイグレーション新規作成（ORDER_065）
- /aipm-pmに--draftオプション追加（DRAFT ORDER作成・PLANNING昇格）（ORDER_065）
- /aipm-full-autoにDRAFT状態のハンドリング追加（ORDER_065）
- フロントエンドにDRAFTステータス対応（色定義・ラベル・フィルタ・PM処理開始ボタン）（ORDER_065）
- projectsテーブルにdev_workspace_pathカラム追加（ORDER_071）
- execute_task.pyがDBからdev_workspace_pathを取得しWorkerプロンプトに開発環境パスを注入
- project CRUD (create.py, list.py) がdev_workspace_pathカラムに対応
- db_config.pyのget_project_paths()にdev_workspace返却を追加
- backend/order/retry_order.py 新規作成 - ORDER再実行機能（ORDER_074）
- backend/pm/update_project_info.py 新規作成 - PROJECT_INFO自動深化（ORDER_073）
- backend/base/base_script.py, backend/utils/base_script.py - 共通基盤クラス（ORDER_083）
- backend/render/md_to_html.py - Worker実行フローへのHTML変換自動組込み（ORDER_076）
- git_release.pyに成果物0件時のREPORTフォールバック収集ロジック追加（ORDER_075）
- process_order.py/execute_task.pyにPROJECT_INFO自動読込・反映機能追加（ORDER_073）
- OrderCompleteReport.tsxに成果物ディレクトリアクセスボタン追加（ORDER_085）
- ProjectInfo.tsxにAI直接実行による最新化ボタン追加（ORDER_084）
- aipm-pm.mdに--scriptモード推奨警告追加（ORDER_081）
- CLAUDE.mdにビルドルール・環境分離ルール追記

### Changed
- backend/backlog/全11モジュールに非推奨警告追加、add.pyをorder/create.pyラッパーに変換（ORDER_065）
- /aipm-backlog-add、/aipm-backlog-to-orderコマンドを非推奨化（ORDER_065）
- BacklogList/BacklogAddForm等のフロントエンドUIをDRAFT ORDER対応に更新（ORDER_065）
- spec_generator.py/process_order.pyのデフォルトモデルをSonnet→Opusに統一（ORDER_078）
- process_review.pyの直接SQL 3箇所をupdate_task_status()経由に統一（ORDER_080）
- process_review.pyにBaseScript共通基盤クラス導入（ORDER_083）
- aipm-worker.md/aipm-full-auto.mdから旧aipm-dbパス・直接DB操作指示を除去（ORDER_081）
- リリースボタンをバックログ一覧に統一、ORDER詳細パネルのOrderReleaseSectionを削除（ORDER_079）
- ReleaseDetailSection.tsx削除（不要コンポーネント除去、ORDER_082）

### Fixed
- Workerサブエージェントがソースコード変更をRoaming側で行いデグレする根本原因を解消
- 過去ORDER成果物の実装消失6件を再実装（ORDER_018/027/039/052/054/061）
- 過去ORDER部分実装7件を修正（ORDER_019/032/034/035/041/045/051）

## [0.1.0] - 2026-02-24

### Added
- 初回リリース: AI PM Manager V2 Electron アプリケーション
- プロジェクト管理機能（作成・編集・削除）
- ORDER管理機能（バックログ・ORDER・タスクの管理）
- SQLite データベースによるデータ永続化
- Squirrel インストーラーによる Windows インストール対応
- AppData\Roaming への永続データ配置（アップデート時のデータ保護）
- Worker サブエージェントによるタスク自動実行
- Claude Code スラッシュコマンド連携（16コマンド）
- リアルタイムファイル監視（chokidar）
- タスク依存関係管理
- バックログからORDERへの自動変換
- Supervisorによるマルチプロジェクト横断管理
- リリースノート表示機能（本バージョンで追加）

### Changed
- データ保存先をAppData\LocalからAppData\Roaming（%APPDATA%）に変更
- DBモードに一本化（MDモード廃止）

### Fixed
- Squirrelインストーラー更新時の永続データ消失問題を修正
- better-sqlite3のnativeモジュール対応

[0.1.0]: https://github.com/example/ai-pm-manager-v2/releases/tag/v0.1.0
