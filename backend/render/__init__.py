"""
AI PM Framework - Render Module

DBからMarkdownファイルを生成するレンダリングモジュール。
Jinja2テンプレートを使用してDASHBOARD.md等を生成する。

Note:
    BACKLOG.md関連機能はORDER_090で廃止されました。
    DB駆動化に伴い、BACKLOG.mdの自動生成は不要になりました。
"""

__version__ = "1.1.0"

# 遅延インポート（循環インポート回避）


def render_dashboard(*args, **kwargs):
    """DASHBOARD.mdをレンダリング"""
    from .dashboard import render_dashboard as _render_dashboard
    return _render_dashboard(*args, **kwargs)


def render_dashboard_to_file(*args, **kwargs):
    """DASHBOARD.mdをファイルに出力"""
    from .dashboard import render_dashboard_to_file as _render_dashboard_to_file
    return _render_dashboard_to_file(*args, **kwargs)


def load_dashboard_context(*args, **kwargs):
    """DBからダッシュボードコンテキストを読み込む"""
    from .dashboard import load_dashboard_context as _load_dashboard_context
    return _load_dashboard_context(*args, **kwargs)


__all__ = [
    "render_dashboard",
    "render_dashboard_to_file",
    "load_dashboard_context",
]
