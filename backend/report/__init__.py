"""
AI PM Framework - Report Module

レポート生成時のMD保存とHTML変換を統合するユーティリティ。
TASK_127 (md_to_html.py) と TASK_128 (report_template.html) の成果物を利用して、
MDファイル保存と同時にHTMLファイルを生成する。

主要API:
    save_report_with_html()       - MDファイル保存 + HTML同時生成
    convert_existing_report_to_html() - 既存MDファイルをHTML変換
    batch_convert_reports_to_html()   - ディレクトリ内の全MDファイルを一括HTML変換
"""

from report.save_report import (
    save_report_with_html,
    convert_existing_report_to_html,
    batch_convert_reports_to_html,
)

__all__ = [
    "save_report_with_html",
    "convert_existing_report_to_html",
    "batch_convert_reports_to_html",
]
