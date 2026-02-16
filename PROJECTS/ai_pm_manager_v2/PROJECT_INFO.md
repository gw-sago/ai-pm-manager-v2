# AI PM Manager V2

## 概要

AI PM Manager V2は、UI操作（Electron + React）とCLI操作（Claude Code スキル）の両方をサポートする統合プロジェクト管理システムです。AIによるプロジェクト管理の自動化を実現します。

## 目的・背景

- AI PM フレームワーク（CLI）とElectron GUIの統合
- DB駆動のプロジェクト管理（SQLite）
- マルチORDER同時進行のサポート
- スラッシュコマンドによる効率的なCLI操作

## 技術スタック

| レイヤー | 技術 |
|---------|------|
| フロントエンド | Electron + TypeScript + React |
| バックエンド | Python 3.11+ |
| データベース | SQLite (better-sqlite3 / sqlite3) |
| CLI統合 | Claude Code スキル (.claude/commands/) |
| ビルド | Electron Forge + Webpack |

## ディレクトリ構成

```
ai-pm-manager-v2/
├── src/                    # Electron + React フロントエンド
├── backend/                # Pythonバックエンド
├── data/
│   ├── aipm.db             # SQLite メインDB
│   └── schema_v2.sql       # DBスキーマ定義
├── PROJECTS/               # プロジェクトデータ
├── templates/              # プロジェクトテンプレート
└── .claude/commands/       # スラッシュコマンド定義
```

## 成果物

- Electron デスクトップアプリ（Windows）
- Python CLI ツール群（backend/）
- Claude Code スキル定義（16本）

## ステータス

- 作成日: 2026-02-16
- 現在のステータス: INITIAL
