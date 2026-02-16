# Incident Pattern Analysis Scripts

障害パターン分析スクリプト - 同カテゴリの過去障害を参照し、再発率を算出、推奨対策を提示します。

## 概要

このモジュールは、INCIDENTSテーブルに記録された障害情報を分析し、以下の機能を提供します：

- カテゴリ別の障害発生率の算出
- 再発パターンの検出
- トレンド分析（増加傾向、減少傾向、安定）
- 期間比較による改善・悪化の判定
- 推奨対策の提示
- 包括的なレポート生成

## ファイル構成

- `analyze_patterns.py` - 障害パターン分析スクリプト
- `generate_report.py` - レポート生成スクリプト
- `__init__.py` - モジュール初期化
- `README.md` - このファイル

## 使用方法

### 1. パターン分析スクリプト (`analyze_patterns.py`)

#### 全カテゴリの分析

```bash
# 過去30日間の全カテゴリを分析
python analyze_patterns.py

# 過去90日間の分析
python analyze_patterns.py --days 90

# 特定プロジェクトに絞り込み
python analyze_patterns.py --project-id ai_pm_manager
```

#### 特定カテゴリの詳細分析

```bash
# WORKER_FAILUREカテゴリの分析
python analyze_patterns.py --category WORKER_FAILURE --days 30

# 前期間との比較を含む
python analyze_patterns.py --category MIGRATION_ERROR --compare
```

#### ハイリスクパターンの検出

```bash
# 閾値0.5（1日あたり0.5件以上）を超えるカテゴリを検出
python analyze_patterns.py --high-risk --threshold 0.5

# 閾値を0.02に下げてより細かく検出
python analyze_patterns.py --high-risk --threshold 0.02
```

#### JSON出力

```bash
# JSON形式で出力
python analyze_patterns.py --category WORKER_FAILURE --output json

# ハイリスク分析をJSON形式で
python analyze_patterns.py --high-risk --output json
```

### 2. レポート生成スクリプト (`generate_report.py`)

#### サマリーレポート

```bash
# Markdown形式でサマリーレポートを生成
python generate_report.py --type summary --format markdown

# テキスト形式で出力
python generate_report.py --type summary --format text

# ファイルに保存
python generate_report.py --type summary --format markdown --output report.md
```

#### カテゴリ詳細レポート

```bash
# 特定カテゴリの詳細レポート
python generate_report.py --type category --category MIGRATION_ERROR --format markdown

# 複数の期間を比較
python generate_report.py --type category --category CASCADE_DELETE --days 60
```

#### JSON出力

```bash
# JSON形式でサマリーレポート
python generate_report.py --type summary --format json

# カテゴリ詳細をJSON形式で
python generate_report.py --type category --category SYSTEM_ERROR --format json
```

## コマンドラインオプション

### `analyze_patterns.py` オプション

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--category` | 分析対象のカテゴリ | 全カテゴリ |
| `--days` | 分析する日数 | 30 |
| `--project-id` | プロジェクトIDで絞り込み | 全プロジェクト |
| `--high-risk` | ハイリスクパターンのみ表示 | false |
| `--threshold` | ハイリスク判定の閾値（incidents/day） | 0.5 |
| `--compare` | 前期間との比較を実施 | false |
| `--output` | 出力形式（text/json） | text |

### `generate_report.py` オプション

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--type` | レポートタイプ（summary/category） | summary |
| `--category` | カテゴリ詳細レポートのカテゴリ | - |
| `--days` | 分析する日数 | 30 |
| `--project-id` | プロジェクトIDで絞り込み | 全プロジェクト |
| `--format` | 出力形式（markdown/text/json） | markdown |
| `--output` | 出力ファイルパス | stdout |

## 障害カテゴリ

以下のカテゴリが定義されています：

- `MIGRATION_ERROR` - マイグレーションエラー
- `CASCADE_DELETE` - カスケード削除
- `CONSTRAINT_VIOLATION` - 制約違反
- `DATA_INTEGRITY` - データ整合性エラー
- `CONCURRENCY_ERROR` - 同時実行エラー
- `FILE_LOCK_ERROR` - ファイルロックエラー
- `WORKER_FAILURE` - Workerの障害
- `REVIEW_ERROR` - レビューエラー
- `SYSTEM_ERROR` - システムエラー
- `OTHER` - その他

## 出力例

### パターン分析出力（テキスト形式）

```
============================================================
INCIDENT PATTERN ANALYSIS: WORKER_FAILURE
============================================================

Analysis Period: 30 days
Total Incidents: 3
Recurrence Rate: 0.1 incidents/day
Trend: INCREASING
Resolution Rate: 0.0%

Severity Distribution:
  HIGH: 0
  MEDIUM: 0
  LOW: 3

Recommended Countermeasures:
  1. Implement worker health checks
  2. Add automatic worker restart on failure
  3. Use circuit breaker pattern for external dependencies
  4. Implement comprehensive error logging

============================================================
```

### ハイリスクパターン分析

```
============================================================
HIGH-RISK INCIDENT PATTERN ANALYSIS
============================================================

Analysis Period: 30 days

🔴 HIGH-RISK CATEGORIES (exceeding threshold):
------------------------------------------------------------

  Category: WORKER_FAILURE
  Recurrence Rate: 0.1 incidents/day
  Total Incidents: 3
  Trend: INCREASING

📋 RECOMMENDATIONS:
------------------------------------------------------------

1. [HIGH] WORKER_FAILURE
   Reason: High recurrence rate: 0.1 incidents/day
   Countermeasures:
     • Implement worker health checks
     • Add automatic worker restart on failure
     • Use circuit breaker pattern for external dependencies
     • Implement comprehensive error logging

============================================================
```

### サマリーレポート（Markdown形式）

```markdown
# Incident Analysis Report

**Generated:** 2026-02-06 19:19:22
**Analysis Period:** 30 days

## Executive Summary

- **Total Incidents:** 14
- **High Severity:** 2
- **High-Risk Categories:** 0
- **Increasing Trends:** 9

## Category Distribution

| Category | Count | Rate (per day) | Trend | Resolution Rate |
|----------|-------|----------------|-------|-----------------|
| WORKER_FAILURE | 3 | 0.1 | 📈 increasing | 0.0% |
| MIGRATION_ERROR | 2 | 0.07 | 📈 increasing | 0.0% |
```

## Python APIとしての使用

スクリプトをPythonコードから直接使用することもできます：

```python
from incident.analyze_patterns import IncidentPatternAnalyzer

# カテゴリパターンを分析
analysis = IncidentPatternAnalyzer.analyze_category_patterns(
    category='WORKER_FAILURE',
    days=30
)

print(f"Recurrence Rate: {analysis['recurrence_stats']['recurrence_rate']}")
print(f"Trend: {analysis['recurrence_stats']['trend']}")

# ハイリスクパターンを識別
high_risk = IncidentPatternAnalyzer.identify_high_risk_patterns(
    days=30,
    recurrence_threshold=0.3
)

for category in high_risk['high_risk_categories']:
    print(f"{category['category']}: {category['recurrence_rate']} incidents/day")
```

```python
from incident.generate_report import IncidentReportGenerator

# サマリーレポートを生成
report = IncidentReportGenerator.generate_summary_report(
    days=30,
    output_format='markdown'
)
print(report)

# カテゴリ詳細レポートを生成
detail_report = IncidentReportGenerator.generate_category_detail_report(
    category='MIGRATION_ERROR',
    days=30,
    output_format='markdown'
)
print(detail_report)
```

## 推奨対策

各カテゴリに対して、以下のような推奨対策が自動的に提示されます：

### MIGRATION_ERROR
- Test migrations in development environment first
- Implement rollback procedures before migration
- Use migration version control
- Review schema changes with team before applying

### CASCADE_DELETE
- Review foreign key relationships before deletion
- Implement soft deletes for critical data
- Add confirmation steps for cascade operations
- Use database triggers to log cascade deletions

### WORKER_FAILURE
- Implement worker health checks
- Add automatic worker restart on failure
- Use circuit breaker pattern for external dependencies
- Implement comprehensive error logging

（その他のカテゴリについても同様に推奨対策が定義されています）

## トラブルシューティング

### データベース接続エラー

```bash
# 環境変数を確認
echo $AIPM_DB_PATH

# データベースファイルが存在するか確認
ls -la $AIPM_DB_PATH
```

### インポートエラー

```bash
# 正しいディレクトリから実行していることを確認
cd backend/incident
python analyze_patterns.py
```

## 関連ファイル

- `../utils/incident_logger.py` - インシデント記録用ユーティリティ
- `../utils/db.py` - データベース接続ユーティリティ
- `../../AI_PM_PJ/RESULT/ORDER_036/06_ARTIFACTS/schema.sql` - INCIDENTSテーブル定義

## ライセンス

AI PM Framework の一部として提供されています。
