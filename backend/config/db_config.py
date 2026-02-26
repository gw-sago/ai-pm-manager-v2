"""
AI PM Framework - データベース設定

データベースのパス設定と環境変数管理を提供。
"""

import os
import sys
import io
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


def setup_utf8_output():
    """
    Windows環境でUTF-8出力を設定

    Windowsのコンソール出力をUTF-8に設定し、
    日本語文字の文字化けを防ぐ。
    """
    if sys.platform == "win32":
        # 標準出力・エラー出力をUTF-8に設定
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        else:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
        else:
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

        # stdin
        if hasattr(sys.stdin, 'reconfigure'):
            sys.stdin.reconfigure(encoding='utf-8')
        elif hasattr(sys.stdin, 'buffer'):
            sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')

        # 子プロセス用の環境変数設定
        os.environ['PYTHONIOENCODING'] = 'utf-8'


def _get_ai_pm_root() -> Path:
    """
    AI_PM_ROOT パスを取得（アプリケーション本体のルート）

    環境変数 AI_PM_ROOT が設定されていればそれを使用、
    なければスクリプトの位置から自動検出。

    このパスはスキーマファイルやバックエンドスクリプトなど、
    アプリケーションと一緒にデプロイされるファイルの基準パス。

    新リポジトリ構成:
    - backend/config/db_config.py → ai-pm-manager-v2/ がルート
    """
    env_root = os.environ.get("AI_PM_ROOT")
    if env_root:
        return Path(env_root)

    # 新リポジトリ配置: backend/config/db_config.py から 2階層上がルート
    # config → backend → ai-pm-manager-v2
    current_file = Path(__file__).resolve()
    return current_file.parent.parent.parent


def _get_user_data_path() -> Path:
    """
    ユーザーデータ（DB, PROJECTS等）の保存先パスを取得

    永続データ（DB、プロジェクトファイル、バックアップ）の基準パス。
    アプリのアップデート時にも保持される場所に配置する。

    優先順位:
    1. 環境変数 AI_PM_USERDATA が設定されていればそれを使用
    2. Windows: %APPDATA%/ai-pm-manager-v2/
    3. フォールバック: AI_PM_ROOT（従来互換）
    """
    # 環境変数が明示指定されていれば最優先
    env_userdata = os.environ.get("AI_PM_USERDATA")
    if env_userdata:
        return Path(env_userdata)

    # Windows: %APPDATA% を使用
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "ai-pm-manager-v2"

    # フォールバック: AI_PM_ROOT（従来互換、非Windows環境等）
    return _get_ai_pm_root()


# グローバル定数
AI_PM_ROOT = _get_ai_pm_root()
USER_DATA_PATH = _get_user_data_path()


@dataclass
class DBConfig:
    """データベース設定を保持するクラス"""

    # データベースファイルパス（ユーザーデータ領域）
    db_path: Path = USER_DATA_PATH / "data" / "aipm.db"

    # スキーマファイルパス（アプリ本体と一緒にデプロイされる）
    schema_path: Path = AI_PM_ROOT / "data" / "schema_v2.sql"

    # データディレクトリ（ユーザーデータ領域）
    data_dir: Path = USER_DATA_PATH / "data"

    # バックアップディレクトリ（ユーザーデータ領域）
    backup_dir: Path = USER_DATA_PATH / "data" / "backup"

    def __post_init__(self):
        """パスをPathオブジェクトに変換し、必要なディレクトリを作成"""
        self.db_path = Path(self.db_path)
        self.schema_path = Path(self.schema_path)
        self.data_dir = Path(self.data_dir)
        self.backup_dir = Path(self.backup_dir)

        # データディレクトリが存在しない場合は自動作成
        if str(self.db_path) != ":memory:":
            self.data_dir.mkdir(parents=True, exist_ok=True)


# デフォルト設定インスタンス
_default_config: Optional[DBConfig] = None


def get_db_config() -> DBConfig:
    """
    データベース設定を取得

    Returns:
        DBConfig: 設定インスタンス
    """
    global _default_config

    if _default_config is None:
        _default_config = DBConfig()

    return _default_config


def set_db_config(config: DBConfig) -> None:
    """
    データベース設定を設定

    Args:
        config: 設定インスタンス
    """
    global _default_config
    _default_config = config


def get_db_path() -> Path:
    """データベースファイルパスを取得"""
    return get_db_config().db_path


def get_schema_path() -> Path:
    """スキーマファイルパスを取得"""
    return get_db_config().schema_path


def get_data_dir() -> Path:
    """データディレクトリパスを取得"""
    return get_db_config().data_dir


def get_backup_dir() -> Path:
    """バックアップディレクトリパスを取得"""
    return get_db_config().backup_dir


# === 環境別設定 ===

def get_test_db_config() -> DBConfig:
    """
    テスト用データベース設定を取得

    Returns:
        DBConfig: テスト用設定（メモリDBまたは一時ファイル）
    """
    import tempfile

    temp_dir = Path(tempfile.gettempdir())

    return DBConfig(
        db_path=temp_dir / "aipm_test.db",
        schema_path=get_db_config().schema_path,
        data_dir=temp_dir / "aipm_test_data",
        backup_dir=temp_dir / "aipm_test_backup",
    )


def get_memory_db_config() -> DBConfig:
    """
    インメモリデータベース設定を取得（テスト用）

    Returns:
        DBConfig: インメモリDB設定

    Note:
        db_path を ":memory:" にするとインメモリDBになる
    """
    return DBConfig(
        db_path=Path(":memory:"),
        schema_path=get_db_config().schema_path,
        data_dir=get_db_config().data_dir,
        backup_dir=get_db_config().backup_dir,
    )


# === ヘルパー関数 ===

def ensure_data_dir() -> Path:
    """
    データディレクトリが存在することを保証

    Returns:
        Path: データディレクトリパス
    """
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def ensure_backup_dir() -> Path:
    """
    バックアップディレクトリが存在することを保証

    Returns:
        Path: バックアップディレクトリパス
    """
    backup_dir = get_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def get_project_paths(project_id: str) -> dict:
    """
    プロジェクトの各種パスを取得

    Args:
        project_id: プロジェクトID（例: AI_PM_PJ）

    Returns:
        dict: 各種パスを含む辞書
            - base: プロジェクトベースパス（PROJECTS/{project_id}）
            - dev: DEVディレクトリパス
            - orders: ORDERSディレクトリパス
            - result: RESULTディレクトリパス
            - release_log: RELEASE_LOG.mdパス
            - dev_workspace: 開発環境パス（DBから取得、未設定時はNone）

    Note:
        backlogパスは廃止されました（ORDER_090）。
        バックログはDBで管理されています。
    """
    base = USER_DATA_PATH / "PROJECTS" / project_id

    # DBから dev_workspace_path を取得（利用可能な場合）
    dev_workspace = None
    try:
        import sqlite3
        db_path = USER_DATA_PATH / "data" / "aipm.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                cols = [row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()]
                if "dev_workspace_path" in cols:
                    row = conn.execute(
                        "SELECT dev_workspace_path FROM projects WHERE id = ?",
                        (project_id,),
                    ).fetchone()
                    if row and row["dev_workspace_path"]:
                        dev_workspace = Path(row["dev_workspace_path"])
            finally:
                conn.close()
    except Exception:
        pass

    return {
        "base": base,
        "dev": base / "DEV",
        "orders": base / "ORDERS",
        "result": base / "RESULT",
        "release_log": base / "RELEASE_LOG.md",
        "docs": base / "docs",
        "docs_index": base / "docs" / "INDEX.md",
        "dev_workspace": dev_workspace,
    }


# === 本番DB保護チェック ===

def is_production_db() -> bool:
    """
    現在使用中のDBが本番DBかどうかを判定する

    AIPM_DB_PATH 環境変数が未設定の場合、デフォルトの本番DB
    （%APPDATA%/ai-pm-manager-v2/data/aipm.db）が使用されるため
    本番DBと判定する。

    Returns:
        bool: 本番DBの場合True、テスト用DBの場合False
    """
    aipm_db_path = os.environ.get("AIPM_DB_PATH")
    if not aipm_db_path:
        # 環境変数未設定 = デフォルト本番DB使用
        return True

    # 環境変数が設定されている場合、本番DBパスと比較
    configured_path = Path(aipm_db_path).resolve()
    production_db_path = (USER_DATA_PATH / "data" / "aipm.db").resolve()
    return configured_path == production_db_path


def warn_if_production_db(command_name: str = "", stderr: bool = True) -> bool:
    """
    本番DBを使用している場合に警告を出力する

    フルオート実行やWorker実行の冒頭で呼び出し、
    AIPM_DB_PATH未設定（＝本番DB使用）の場合に警告を出力する。

    Args:
        command_name: 実行コマンド名（警告メッセージに使用）
        stderr: Trueの場合stderrに出力、Falseの場合stdoutに出力

    Returns:
        bool: 本番DBの場合True（警告を出力した場合）
    """
    if not is_production_db():
        return False

    output = sys.stderr if stderr else sys.stdout
    separator = "=" * 60
    cmd_info = f" ({command_name})" if command_name else ""
    print(separator, file=output)
    print(f"[WARNING] 本番DB使用中{cmd_info}", file=output)
    print("AIPM_DB_PATH が未設定のため、本番DB（aipm.db）に直接アクセスします。", file=output)
    print("テスト・開発目的の場合は以下のように環境変数を設定してください:", file=output)
    print("  export AIPM_DB_PATH=data/test_aipm.db", file=output)
    print("  または: AIPM_DB_PATH=data/test_aipm.db python backend/worker/...", file=output)
    print(separator, file=output)
    return True


def resolve_docs_path(project_id: str) -> dict:
    """
    ドキュメント参照パスを解決する

    dev_workspace_pathが設定されていればそのパス自体をドキュメントルートとして参照し、
    未設定またはパスが存在しない場合はPROJECTS/{project_id}/docs/にフォールバックする。

    Args:
        project_id: プロジェクトID

    Returns:
        dict: ドキュメントパス情報
            - docs_path: 実際に参照するディレクトリのPath
            - source: パスのソース ("dev_workspace" or "project_docs")
            - dev_workspace_path: 設定されているdev_workspace_path（未設定時はNone）
            - fallback_used: フォールバックが使用されたかどうか
    """
    paths = get_project_paths(project_id)
    dev_workspace = paths["dev_workspace"]
    default_docs = paths["docs"]

    # dev_workspace_pathが設定されている場合
    if dev_workspace is not None:
        if dev_workspace.exists() and dev_workspace.is_dir():
            return {
                "docs_path": dev_workspace,
                "source": "dev_workspace",
                "dev_workspace_path": dev_workspace,
                "fallback_used": False,
            }
        else:
            # dev_workspace_path設定あり、だがパスが存在しない→フォールバック
            return {
                "docs_path": default_docs,
                "source": "project_docs",
                "dev_workspace_path": dev_workspace,
                "fallback_used": True,
            }

    # dev_workspace_path未設定→デフォルトのdocs/
    return {
        "docs_path": default_docs,
        "source": "project_docs",
        "dev_workspace_path": None,
        "fallback_used": False,
    }
