# Changelog

All notable changes to AI PM Manager V2 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-snapshot] - 2026-02-24

### Added
- projectsテーブルにdev_workspace_pathカラム追加（ORDER_071）
- execute_task.pyがDBからdev_workspace_pathを取得しWorkerプロンプトに開発環境パスを注入
- Workerプロンプトに開発環境/Roamingの使い分けルールを明示的に指示
- project CRUD (create.py, list.py) がdev_workspace_pathカラムに対応
- db_config.pyのget_project_paths()にdev_workspace返却を追加
- CLAUDE.mdにビルドルール・環境分離ルール追記

### Fixed
- Workerサブエージェントがソースコード変更をRoaming側で行いデグレする根本原因を解消

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
