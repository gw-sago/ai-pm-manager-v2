# Changelog

All notable changes to AI PM Manager V2 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-snapshot] - 2026-02-25

### Added
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
