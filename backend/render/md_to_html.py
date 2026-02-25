"""
AI PM Framework - Render: Markdown to HTML 変換モジュール

backend/utils/md_to_html.py の実装を render サブパッケージから提供するラッパー。
実際の変換ロジックは utils 版に集約されており、このモジュールはそれをインポートして
render パッケージの一部として公開する。

使用例:
    from render.md_to_html import convert_md_to_html, wrap_html_document

    html_body = convert_md_to_html(md_text)
    full_html = wrap_html_document(html_body, title="Report")
"""

# utils版から全ての公開APIを再エクスポートする
from utils.md_to_html import (
    convert_md_to_html,
    convert_md_to_html_safe,
    convert_md_file_to_html,
    wrap_html_document,
)

__all__ = [
    "convert_md_to_html",
    "convert_md_to_html_safe",
    "convert_md_file_to_html",
    "wrap_html_document",
]
