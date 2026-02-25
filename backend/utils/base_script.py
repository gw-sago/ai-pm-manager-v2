"""
AI PM Framework - スクリプト基底クラス

ORDER_044 DESIGN_class_structure.md に基づく共通基盤クラス群。

全スクリプトの重複コード（sys.path設定・argparse初期化・JSON出力・
エラーハンドリング・終了コード管理）を一元化する。

クラス階層:
    BaseScript
    ├── ReadScript          # 読み取り専用操作（list, get 系）
    │   ├── ListScript      # 一覧取得（フィルタ・ソート対応）
    │   └── GetScript       # 単一取得
    └── WriteScript         # 書き込み操作（create, update 系）
        ├── CreateScript    # 新規作成
        └── UpdateScript    # 更新・ステータス変更

AIScript                    # AI統合スクリプト専用（process_order, process_review 等）

配置: backend/utils/base_script.py
"""

import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# 終了コード定数
# ---------------------------------------------------------------------------

class ExitCode:
    """
    終了コード定数（DESIGN_parent_script_spec.md 3.1節準拠）

    EXIT_SUCCESS      = 0  正常終了
    EXIT_BUSINESS_ERROR = 1  ビジネスロジックエラー
    EXIT_SYSTEM_ERROR   = 2  システムエラー（予期しない例外）
    EXIT_CONFIG_ERROR   = 3  設定エラー（DBパス不正・環境変数未設定）
    """
    SUCCESS = 0
    BUSINESS_ERROR = 1
    SYSTEM_ERROR = 2
    CONFIG_ERROR = 3


# ---------------------------------------------------------------------------
# BaseScript
# ---------------------------------------------------------------------------

class BaseScript:
    """
    全親スクリプトの基底クラス。

    提供機能:
    - sys.path 自動設定（backend/ ルートを追加）
    - UTF-8 stdout/stderr 設定（Windows対応）
    - argparse 初期化（--json / --table 共通オプション付き）
    - JSON 出力（ensure_ascii=False、indent=2）
    - エラー出力（stderr へのメッセージ出力）
    - エラーハンドリング（ValidationError / DatabaseError / 予期しない例外）
    - 終了コード管理（ExitCode 定数を再エクスポート）

    使い方:
        class MyScript(BaseScript):
            def add_arguments(self, parser):
                parser.add_argument('project_name')

            def run(self, args):
                return {"result": "ok"}

        if __name__ == '__main__':
            MyScript("説明文").main()
    """

    # 終了コード定数（後方互換のためクラス属性としても公開）
    EXIT_SUCCESS = ExitCode.SUCCESS
    EXIT_BUSINESS_ERROR = ExitCode.BUSINESS_ERROR
    EXIT_SYSTEM_ERROR = ExitCode.SYSTEM_ERROR
    EXIT_CONFIG_ERROR = ExitCode.CONFIG_ERROR

    def __init__(self, description: str, epilog: str = ""):
        """
        Args:
            description: スクリプトの説明文（argparse --help に表示）
            epilog: ヘルプの末尾に表示するテキスト（使用例等）
        """
        self._setup_path()
        self._setup_encoding()
        self.parser = self._build_parser(description, epilog)

    # ------------------------------------------------------------------
    # セットアップメソッド
    # ------------------------------------------------------------------

    def _setup_path(self):
        """
        sys.path を backend/ ルートに設定する。

        __file__ から backend/ ディレクトリを検索し、
        sys.path に追加することで各モジュールを import 可能にする。
        """
        # backend/utils/base_script.py → backend/ を package_root とする
        current_file = Path(__file__).resolve()
        package_root = current_file.parent.parent  # backend/
        if str(package_root) not in sys.path:
            sys.path.insert(0, str(package_root))

    def _setup_encoding(self):
        """Windows 環境の UTF-8 stdout/stderr 設定。"""
        try:
            from config.db_config import setup_utf8_output
            setup_utf8_output()
        except ImportError:
            # フォールバック: 手動で設定
            import io
            if sys.platform == "win32":
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(encoding='utf-8')
                else:
                    sys.stdout = io.TextIOWrapper(
                        sys.stdout.buffer, encoding='utf-8'
                    )
                if hasattr(sys.stderr, 'reconfigure'):
                    sys.stderr.reconfigure(encoding='utf-8')
                else:
                    sys.stderr = io.TextIOWrapper(
                        sys.stderr.buffer, encoding='utf-8'
                    )

    def _build_parser(
        self, description: str, epilog: str
    ) -> argparse.ArgumentParser:
        """
        argparse パーサを構築する。

        共通オプション（--json / --table）を自動追加する。
        サブクラスは add_arguments() で固有の引数を追加する。
        """
        parser = argparse.ArgumentParser(
            description=description,
            epilog=epilog,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        # 共通出力形式オプション
        output_group = parser.add_mutually_exclusive_group()
        output_group.add_argument(
            '--json',
            action='store_true',
            default=True,
            help='JSON形式で出力（デフォルト）',
        )
        output_group.add_argument(
            '--table',
            action='store_true',
            help='テーブル形式で出力（デバッグ用）',
        )
        return parser

    # ------------------------------------------------------------------
    # オーバーライドポイント
    # ------------------------------------------------------------------

    def add_arguments(self, parser: argparse.ArgumentParser):
        """
        サブクラスでオーバーライドしてスクリプト固有の引数を追加する。

        super().add_arguments(parser) を呼び出すことで
        親クラスの共通引数も追加できる。
        """
        pass

    def run(self, args: argparse.Namespace) -> Dict[str, Any]:
        """
        サブクラスでオーバーライドして処理を実装する。

        Returns:
            JSON シリアライズ可能な dict。

        Raises:
            NotImplementedError: サブクラスで実装されていない場合。
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.run() を実装してください。"
        )

    def output_table(self, data: Dict[str, Any]):
        """
        テーブル形式出力。

        デフォルトは JSON フォールバック。
        サブクラスでオーバーライドしてカスタム表示を実装する。
        """
        print(json.dumps(data, ensure_ascii=False, indent=2))

    # ------------------------------------------------------------------
    # エントリポイント
    # ------------------------------------------------------------------

    def main(self):
        """
        スクリプトのエントリポイント。

        処理フロー:
        1. add_arguments() でパーサを完成
        2. args を parse_args() で解析
        3. run(args) を呼び出し
        4. 結果を _output() で出力（--json / --table に応じて切り替え）
        5. エラーを捕捉して適切な終了コードで sys.exit
        """
        self.add_arguments(self.parser)
        args = self.parser.parse_args()
        try:
            result = self.run(args)
            self._output(result, args)
            sys.exit(self.EXIT_SUCCESS)
        except Exception as e:
            self._handle_exception(e)

    def _handle_exception(self, e: Exception):
        """
        例外を種別に応じた終了コードでハンドリングする。

        ValidationError / DatabaseError → EXIT_BUSINESS_ERROR (1)
        その他の例外                    → EXIT_SYSTEM_ERROR   (2)
        """
        try:
            from utils.validation import ValidationError
        except ImportError:
            ValidationError = None

        try:
            from utils.db import DatabaseError
        except ImportError:
            DatabaseError = None

        if ValidationError and isinstance(e, ValidationError):
            self._output_error(str(e), exit_code=self.EXIT_BUSINESS_ERROR)
        elif DatabaseError and isinstance(e, DatabaseError):
            self._output_error(str(e), exit_code=self.EXIT_BUSINESS_ERROR)
        else:
            self._output_error(
                f"予期しないエラー: {e}", exit_code=self.EXIT_SYSTEM_ERROR
            )

    # ------------------------------------------------------------------
    # 出力ヘルパー
    # ------------------------------------------------------------------

    def _output(self, data: Dict[str, Any], args: argparse.Namespace):
        """
        結果を JSON または Table 形式で stdout に出力する。

        --table フラグが有効な場合は output_table() を呼び出す。
        それ以外は JSON 出力（ensure_ascii=False, indent=2）。
        """
        if getattr(args, 'table', False):
            self.output_table(data)
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))

    def _output_error(self, message: str, exit_code: int):
        """
        エラーメッセージを stderr に出力し、指定コードで終了する。

        Args:
            message: エラーメッセージ
            exit_code: プロセス終了コード（ExitCode 定数を使用）
        """
        print(message, file=sys.stderr)
        sys.exit(exit_code)

    def output_json(self, data: Dict[str, Any]):
        """
        JSON を stdout に出力するユーティリティ。

        run() 内から直接呼び出す場合に使用する。
        通常は run() の返り値として dict を返すことで自動出力される。
        """
        print(json.dumps(data, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# ReadScript
# ---------------------------------------------------------------------------

class ReadScript(BaseScript):
    """
    読み取り専用スクリプトの基底クラス。

    追加機能:
    - --status, --active, --completed, --on-hold フィルタの共通処理
    - --limit オプション
    - --summary オプション
    - get_db() によるDB接続の簡易取得
    """

    def add_arguments(self, parser: argparse.ArgumentParser):
        """共通フィルタオプションを追加する。"""
        super().add_arguments(parser)
        parser.add_argument('--status', help='ステータスフィルタ（カンマ区切りで複数指定可）')
        parser.add_argument('--active', action='store_true', help='アクティブなもののみ表示')
        parser.add_argument('--completed', action='store_true', help='完了済みのみ表示')
        parser.add_argument('--on-hold', action='store_true', help='保留中のみ表示')
        parser.add_argument('--limit', type=int, help='出力件数上限')
        parser.add_argument('--summary', action='store_true', help='サマリー情報のみ出力')

    @contextmanager
    def get_db(self):
        """
        DB接続をコンテキストマネージャとして取得する。

        使い方:
            with self.get_db() as conn:
                rows = fetch_all(conn, "SELECT * FROM projects")
        """
        from utils.db import get_connection
        conn = get_connection()
        try:
            yield conn
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# ListScript
# ---------------------------------------------------------------------------

class ListScript(ReadScript):
    """
    一覧取得スクリプトの基底クラス。

    ReadScript を継承し、リスト取得に特化した追加機能を提供する。
    """
    pass


# ---------------------------------------------------------------------------
# GetScript
# ---------------------------------------------------------------------------

class GetScript(ReadScript):
    """
    単一エンティティ取得スクリプトの基底クラス。
    """
    pass


# ---------------------------------------------------------------------------
# WriteScript
# ---------------------------------------------------------------------------

class WriteScript(BaseScript):
    """
    書き込みスクリプトの基底クラス。

    追加機能:
    - --dry-run オプション（DBへの書き込みをスキップ）
    - --force オプション（確認プロンプトをスキップ）
    - run_in_transaction() によるトランザクション管理
    """

    def add_arguments(self, parser: argparse.ArgumentParser):
        """--dry-run / --force オプションを追加する。"""
        super().add_arguments(parser)
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='DBへの書き込みを行わない（確認モード）',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='確認プロンプトをスキップ',
        )

    def run_in_transaction(self, conn, logic_fn):
        """
        トランザクション内で logic_fn(conn) を実行する。

        例外時は自動 rollback し、例外を再 raise する。

        Args:
            conn: DB接続オブジェクト
            logic_fn: conn を引数に取る callable

        Returns:
            logic_fn の返り値
        """
        try:
            result = logic_fn(conn)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# CreateScript
# ---------------------------------------------------------------------------

class CreateScript(WriteScript):
    """
    新規作成スクリプトの基底クラス。
    """
    pass


# ---------------------------------------------------------------------------
# UpdateScript
# ---------------------------------------------------------------------------

class UpdateScript(WriteScript):
    """
    更新・ステータス変更スクリプトの基底クラス。
    """
    pass


# ---------------------------------------------------------------------------
# AIScript
# ---------------------------------------------------------------------------

class AIScript(BaseScript):
    """
    AI（Claude API）を呼び出すスクリプトの基底クラス。

    対象スクリプト:
    - backend/pm/process_order.py
    - backend/review/process_review.py
    - backend/worker/execute_task.py

    追加機能:
    - --model オプション（haiku / sonnet / opus）
    - --timeout オプション（デフォルト: 300秒）
    - --batch オプション（複数対象の一括処理）
    - --dry-run オプション
    - --skip-ai オプション（AI処理をスキップして自動承認）
    - API 呼び出しエラーの一元ハンドリング
    """

    VALID_MODELS = ('haiku', 'sonnet', 'opus')
    DEFAULT_MODEL = 'sonnet'
    DEFAULT_TIMEOUT = 300  # 秒

    def add_arguments(self, parser: argparse.ArgumentParser):
        """AI処理共通オプションを追加する。"""
        super().add_arguments(parser)
        parser.add_argument(
            '--model',
            choices=self.VALID_MODELS,
            default=self.DEFAULT_MODEL,
            help=f'使用モデル（デフォルト: {self.DEFAULT_MODEL}）',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=self.DEFAULT_TIMEOUT,
            help=f'claude -p タイムアウト秒数（デフォルト: {self.DEFAULT_TIMEOUT}）',
        )
        parser.add_argument(
            '--batch',
            action='store_true',
            help='バッチモード（複数対象を逐次処理）',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='実行計画のみ表示（AI呼び出し・DB更新なし）',
        )
        parser.add_argument(
            '--skip-ai',
            action='store_true',
            help='AI処理をスキップ（自動承認）',
        )

    def call_claude(
        self,
        prompt: str,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """
        Claude API を呼び出す。

        タイムアウト・エラーハンドリングを内包する。
        失敗時は EXIT_SYSTEM_ERROR で終了する。

        Args:
            prompt: Claude に渡すプロンプト文字列
            model: 使用モデル（None の場合は DEFAULT_MODEL）
            timeout: タイムアウト秒数（None の場合は DEFAULT_TIMEOUT）

        Returns:
            Claude の応答テキスト

        Raises:
            SystemExit: API 呼び出し失敗時（EXIT_SYSTEM_ERROR）
        """
        _model = model or self.DEFAULT_MODEL
        _timeout = timeout or self.DEFAULT_TIMEOUT

        try:
            from utils.claude_cli import create_runner
            runner = create_runner(model=_model, timeout=_timeout)
            result = runner.run(prompt)
            if result.success:
                return result.output
            else:
                self._output_error(
                    f"[S001] AI API call failed: {result.error}",
                    exit_code=self.EXIT_SYSTEM_ERROR,
                )
        except ImportError:
            self._output_error(
                "[S001] AI API call failed: claude_cli モジュールが利用できません",
                exit_code=self.EXIT_SYSTEM_ERROR,
            )
