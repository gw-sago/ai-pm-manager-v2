"""
AI PM Framework - Permission Resolver

タスク情報（title, description）からキーワードマッチングで
最適な権限プロファイルを自動判定するモジュール。

Usage:
    from worker.permission_resolver import PermissionResolver

    resolver = PermissionResolver()
    profile_name = resolver.resolve(task_info)
    tools = resolver.resolve_tools(task_info, explicit_tools=None)
"""

import logging
import sys
from pathlib import Path
from typing import Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

# Set up logging
logger = logging.getLogger(__name__)

# Import permission profile utilities
try:
    from config.permission_profiles import get_profile_tools, get_default_profile
except ImportError as e:
    logger.error(f"Failed to import config.permission_profiles: {e}")
    raise


class PermissionResolver:
    """タスク情報から権限プロファイルを自動判定"""

    # キーワードマッチングルール
    # キーワードが見つかったらそのプロファイルを使用
    KEYWORD_RULES = {
        "research": [
            # 日本語キーワード
            "調査", "分析", "リサーチ", "検索", "比較", "評価",
            # 英語キーワード
            "search", "research", "analyze", "analyse", "investigate", "evaluation",
        ],
        "development": [
            # 日本語キーワード
            "実装", "開発", "修正", "追加", "作成", "コード",
            # 英語キーワード
            "fix", "add", "implement", "develop", "create", "build", "refactor", "code",
        ],
        "document": [
            # 日本語キーワード
            "ドキュメント", "文書", "記録", "レポート", "設計書",
            # 英語キーワード
            "document", "docs", "readme", "report", "spec", "specification",
        ],
    }

    # 特殊ロジック用キーワード（ツール追加・プロファイル昇格）
    WEB_KEYWORDS = [
        "web", "api", "url", "外部", "http", "https", "fetch", "リクエスト",
    ]

    TEST_KEYWORDS = [
        "テスト", "test", "lint", "検証", "verify", "validation",
    ]

    MIGRATION_KEYWORDS = [
        "マイグレーション", "migration", "schema", "スキーマ", "データベース", "database",
        "migrate", "db", "alter table",
    ]

    def __init__(self):
        """初期化"""
        self.logger = logger

    def resolve(self, task_info: dict) -> str:
        """
        タスク情報から推奨プロファイル名を返す

        Args:
            task_info: タスク情報辞書（title, descriptionを含む）

        Returns:
            プロファイル名（"research", "development", "document", "full"）
        """
        # タスク情報からテキストを抽出
        text = self._extract_text(task_info)

        # マイグレーション系タスクは常に "full" にする
        if self._contains_keywords(text, self.MIGRATION_KEYWORDS):
            self.logger.info(f"Migration keywords detected -> profile: full")
            return "full"

        # キーワードマッチングで判定
        for profile_name, keywords in self.KEYWORD_RULES.items():
            if self._contains_keywords(text, keywords):
                self.logger.info(f"Keyword match for '{profile_name}' profile")
                return profile_name

        # どれにもマッチしない場合はデフォルト
        default = get_default_profile()
        self.logger.info(f"No keyword match, using default profile: {default}")
        return default

    def resolve_tools(
        self, task_info: dict, explicit_tools: Optional[list] = None
    ) -> list[str]:
        """
        タスク情報から最終的な許可ツールリストを返す

        優先度:
        1. explicit_tools が指定されている場合はそれをそのまま返す（CLI明示指定）
        2. 自動判定（キーワードマッチング + 追加ロジック）

        Args:
            task_info: タスク情報辞書
            explicit_tools: CLIで明示指定された場合（こちらを優先して返す）

        Returns:
            許可ツールリスト
        """
        # CLI明示指定がある場合は優先
        if explicit_tools is not None:
            self.logger.info(f"Using explicitly specified tools: {explicit_tools}")
            return explicit_tools

        # プロファイル自動判定
        profile_name = self.resolve(task_info)
        tools = get_profile_tools(profile_name)

        if not tools:
            self.logger.warning(
                f"Profile '{profile_name}' has no tools, using empty list"
            )
            return []

        # コピーして変更可能にする
        tools = tools.copy()

        # タスク情報テキスト抽出
        text = self._extract_text(task_info)

        # 追加ロジック: Web関連キーワードがあればWebSearch/WebFetchを追加
        if self._contains_keywords(text, self.WEB_KEYWORDS):
            if "WebSearch" not in tools:
                tools.append("WebSearch")
                self.logger.info("Web keywords detected -> added WebSearch")
            if "WebFetch" not in tools:
                tools.append("WebFetch")
                self.logger.info("Web keywords detected -> added WebFetch")

        # 追加ロジック: テスト関連キーワードがあればBashを追加
        if self._contains_keywords(text, self.TEST_KEYWORDS):
            if "Bash" not in tools:
                tools.append("Bash")
                self.logger.info("Test keywords detected -> added Bash")

        return tools

    def _extract_text(self, task_info: dict) -> str:
        """
        タスク情報から検索対象のテキストを抽出

        Args:
            task_info: タスク情報辞書

        Returns:
            結合されたテキスト（小文字化）
        """
        # title と description を取得
        # task_info は通常の dict なので .get() が使える
        title = task_info.get("title", "")
        description = task_info.get("description", "")

        # 両方を結合して小文字化
        combined = f"{title} {description}".lower()
        return combined

    def _contains_keywords(self, text: str, keywords: list[str]) -> bool:
        """
        テキストにキーワードが含まれているかチェック

        Args:
            text: 検索対象テキスト（小文字化済み）
            keywords: キーワードリスト

        Returns:
            True if any keyword found, False otherwise
        """
        # すべてのキーワードを小文字化してチェック
        for keyword in keywords:
            keyword_lower = keyword.lower()
            # 単語境界を考慮した検索（部分一致を避ける）
            # ただし日本語は単語境界が使えないので通常の in で検索
            if keyword_lower in text:
                return True

        return False


# Utility function for easy access
def resolve_permission_profile(task_info: dict) -> str:
    """
    タスク情報から推奨プロファイル名を返す（ユーティリティ関数）

    Args:
        task_info: タスク情報辞書

    Returns:
        プロファイル名
    """
    resolver = PermissionResolver()
    return resolver.resolve(task_info)


def resolve_permission_tools(
    task_info: dict, explicit_tools: Optional[list] = None
) -> list[str]:
    """
    タスク情報から最終的な許可ツールリストを返す（ユーティリティ関数）

    Args:
        task_info: タスク情報辞書
        explicit_tools: CLIで明示指定された場合

    Returns:
        許可ツールリスト
    """
    resolver = PermissionResolver()
    return resolver.resolve_tools(task_info, explicit_tools)


# CLI testing
if __name__ == "__main__":
    import json
    import sys

    # Set up logging for CLI
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # テストケース
    test_cases = [
        {
            "title": "パフォーマンス調査",
            "description": "データベースのクエリ性能を分析する",
        },
        {
            "title": "バグ修正",
            "description": "ログイン機能の実装を修正する",
        },
        {
            "title": "README更新",
            "description": "プロジェクトのドキュメントを作成",
        },
        {
            "title": "マイグレーション作成",
            "description": "データベーススキーマのマイグレーションファイルを追加",
        },
        {
            "title": "API調査",
            "description": "外部APIのWebリクエスト仕様を調査",
        },
        {
            "title": "テスト追加",
            "description": "ユニットテストを実装してlintで検証",
        },
    ]

    resolver = PermissionResolver()

    print("=== Permission Resolver Test ===\n")

    for i, task_info in enumerate(test_cases, 1):
        print(f"Test Case {i}:")
        print(f"  Title: {task_info['title']}")
        print(f"  Description: {task_info['description']}")

        profile = resolver.resolve(task_info)
        tools = resolver.resolve_tools(task_info)

        print(f"  -> Profile: {profile}")
        print(f"  -> Tools: {tools}")
        print()
