"""
AI PM Framework - BaseScript 共通基盤クラス

引数パース・ロギング・エラーハンドリング・JSON出力の共通機能を提供する基底クラス。

ORDER_044設計書に基づく実装。
"""

import argparse
import json
import logging
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional


class ScriptResult:
    """スクリプト実行結果を保持するクラス"""

    def __init__(
        self,
        success: bool = True,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        exit_code: int = 0,
    ):
        self.success = success
        self.data = data or {}
        self.error = error
        self.exit_code = exit_code if not success else 0

    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換"""
        result = {"success": self.success}
        result.update(self.data)
        if self.error:
            result["error"] = self.error
        return result

    @classmethod
    def ok(cls, **kwargs) -> "ScriptResult":
        """成功結果を生成"""
        return cls(success=True, data=kwargs)

    @classmethod
    def fail(cls, error: str, exit_code: int = 1, **kwargs) -> "ScriptResult":
        """失敗結果を生成"""
        return cls(success=False, data=kwargs, error=error, exit_code=exit_code)


class BaseScript(ABC):
    """
    AI PM Framework スクリプト共通基盤クラス

    サブクラスで実装すべきメソッド:
        - build_parser(parser): argparse引数の追加
        - execute(args): 実際の処理実装

    提供する機能:
        - 引数パース（--json, --verbose 共通フラグ含む）
        - ロギング設定
        - エラーハンドリング
        - JSON出力
        - UTF-8出力設定（Windows対応）
    """

    # サブクラスで上書き可能
    description: str = "AI PM Framework スクリプト"
    epilog: str = ""

    def __init__(self):
        self._logger: Optional[logging.Logger] = None
        self._args: Optional[argparse.Namespace] = None

    @property
    def logger(self) -> logging.Logger:
        """ロガーを取得（遅延初期化）"""
        if self._logger is None:
            self._logger = logging.getLogger(self.__class__.__module__)
        return self._logger

    def build_parser(self, parser: argparse.ArgumentParser) -> None:
        """
        引数パーサーにサブクラス固有の引数を追加する。

        サブクラスでオーバーライドして使用する。
        共通引数（--json, --verbose）は BaseScript が追加済み。

        Args:
            parser: argparse.ArgumentParser インスタンス
        """
        pass

    @abstractmethod
    def execute(self, args: argparse.Namespace) -> ScriptResult:
        """
        スクリプトのメイン処理を実装する。

        Args:
            args: パース済み引数

        Returns:
            ScriptResult: 実行結果
        """

    def _create_parser(self) -> argparse.ArgumentParser:
        """引数パーサーを生成（共通引数付き）"""
        parser = argparse.ArgumentParser(
            description=self.description,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=self.epilog,
        )

        # 共通フラグ
        parser.add_argument(
            "--json",
            action="store_true",
            help="JSON形式で出力",
        )
        parser.add_argument(
            "--verbose", "-v",
            action="store_true",
            help="詳細ログ出力",
        )

        # サブクラス固有の引数を追加
        self.build_parser(parser)

        return parser

    def _setup_logging(self, verbose: bool) -> None:
        """ロギングを設定する"""
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        logging.getLogger().setLevel(level)

    def _setup_utf8(self) -> None:
        """Windows環境でUTF-8出力を設定する"""
        try:
            from config import setup_utf8_output
            setup_utf8_output()
        except ImportError:
            pass

    def _output_result(self, result: ScriptResult, use_json: bool) -> None:
        """
        実行結果を出力する。

        Args:
            result: 実行結果
            use_json: True の場合JSON形式で出力
        """
        if use_json:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
        else:
            self._print_human_readable(result)

    def _print_human_readable(self, result: ScriptResult) -> None:
        """人間向けの出力（サブクラスでオーバーライド可能）"""
        if result.success:
            print("完了")
        else:
            print(f"エラー: {result.error}", file=sys.stderr)

    def run(self, argv: Optional[List[str]] = None) -> int:
        """
        スクリプトのエントリーポイント。

        Args:
            argv: コマンドライン引数（None の場合は sys.argv[1:] を使用）

        Returns:
            int: 終了コード（0=成功, 1以上=失敗）
        """
        self._setup_utf8()

        parser = self._create_parser()
        args = self._create_parser().parse_args(argv)
        self._args = args

        self._setup_logging(getattr(args, "verbose", False))

        try:
            result = self.execute(args)
        except KeyboardInterrupt:
            print("\n中断されました", file=sys.stderr)
            return 130
        except Exception as e:
            self.logger.exception(f"予期しないエラー: {e}")
            result = ScriptResult.fail(f"予期しないエラー: {e}")

        use_json = getattr(args, "json", False)
        self._output_result(result, use_json)

        return result.exit_code

    @classmethod
    def main(cls, argv: Optional[List[str]] = None) -> None:
        """
        クラスメソッドとしてのエントリーポイント。

        Usage:
            if __name__ == "__main__":
                MyScript.main()
        """
        script = cls()
        exit_code = script.run(argv)
        sys.exit(exit_code)
