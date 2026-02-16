"""
AI PM Framework - モジュールロック管理パッケージ

複数ORDER並行実行時のモジュール競合を防ぐためのロック管理機能を提供。

機能:
- acquire: ロック取得
- release: ロック解放
- check: 競合チェック
- list: ロック一覧表示
"""

__all__ = [
    'acquire_lock',
    'release_lock',
    'check_conflict',
    'list_locks',
]
