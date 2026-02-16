"""
AI PM Framework - Interaction Module

対話（AI質問・ユーザー回答）管理モジュール
"""

from pathlib import Path
import sys

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))
