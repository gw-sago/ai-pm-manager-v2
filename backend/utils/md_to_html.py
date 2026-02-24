"""
AI PM Framework - Markdown to HTML 変換ユーティリティ

MarkdownテキストをHTMLに変換する。
見出し・リスト・テーブル・コードブロックを適切に変換する。

依存: markdown ライブラリ (pip install markdown)
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# markdown ライブラリの遅延インポート
_markdown_module = None
_markdown_available = None


def _get_markdown():
    """markdown ライブラリを遅延読み込みする。"""
    global _markdown_module, _markdown_available
    if _markdown_available is None:
        try:
            import markdown
            _markdown_module = markdown
            _markdown_available = True
            logger.debug("markdown ライブラリを読み込みました (version: %s)", markdown.__version__)
        except ImportError:
            _markdown_available = False
            logger.warning(
                "markdown ライブラリが見つかりません。pip install markdown でインストールしてください。"
            )
    return _markdown_module


# デフォルトで有効にする拡張機能
DEFAULT_EXTENSIONS = [
    "tables",          # テーブル (GFM互換)
    "fenced_code",     # フェンスドコードブロック (```)
    "codehilite",      # コードハイライト（pygmentsがあれば）
    "toc",             # 目次生成
    "nl2br",           # 改行を <br> に変換
    "sane_lists",      # リストの改善
    "smarty",          # スマート引用符
]

# 拡張機能設定のデフォルト
DEFAULT_EXTENSION_CONFIGS: Dict[str, Dict[str, Any]] = {
    "codehilite": {
        "css_class": "highlight",
        "guess_lang": False,        # 言語自動推測を無効化
        "use_pygments": False,      # pygments がなくてもエラーにしない
    },
    "toc": {
        "permalink": False,
    },
}


def convert_md_to_html(
    md_text: str,
    extensions: Optional[list] = None,
    extension_configs: Optional[Dict[str, Dict[str, Any]]] = None,
    safe_mode: bool = False,
) -> str:
    """
    MarkdownテキストをHTMLに変換する。

    Args:
        md_text: 変換対象のMarkdownテキスト
        extensions: 使用する拡張機能のリスト（Noneでデフォルト使用）
        extension_configs: 拡張機能の設定辞書（Noneでデフォルト使用）
        safe_mode: Trueの場合、HTMLタグをエスケープする

    Returns:
        変換後のHTML文字列

    Raises:
        RuntimeError: markdown ライブラリが利用できない場合
        ValueError: md_text が文字列でない場合
    """
    if not isinstance(md_text, str):
        raise ValueError(f"md_text は文字列である必要があります。受け取った型: {type(md_text).__name__}")

    if not md_text.strip():
        return ""

    md = _get_markdown()
    if md is None:
        raise RuntimeError(
            "markdown ライブラリが利用できません。"
            "pip install markdown でインストールしてください。"
        )

    # 拡張機能の決定（利用可能なもののみ使う）
    use_extensions = extensions if extensions is not None else _get_available_extensions()
    use_configs = extension_configs if extension_configs is not None else DEFAULT_EXTENSION_CONFIGS

    try:
        html = md.markdown(
            md_text,
            extensions=use_extensions,
            extension_configs=use_configs,
        )
        return html
    except Exception as e:
        logger.error("Markdown変換中にエラーが発生しました: %s", e)
        # 拡張機能を減らしてリトライ
        try:
            logger.info("拡張機能なしでリトライします")
            html = md.markdown(md_text)
            return html
        except Exception as e2:
            logger.error("拡張機能なしでも変換に失敗しました: %s", e2)
            raise RuntimeError(f"Markdown変換に失敗しました: {e2}") from e2


def _get_available_extensions() -> list:
    """
    利用可能なデフォルト拡張機能のリストを返す。
    インストールされていない拡張機能はスキップする。
    """
    md = _get_markdown()
    if md is None:
        return []

    available = []
    for ext_name in DEFAULT_EXTENSIONS:
        try:
            # 拡張機能がロード可能か確認
            md.markdown("", extensions=[ext_name])
            available.append(ext_name)
        except Exception:
            logger.debug("拡張機能 '%s' は利用できません。スキップします。", ext_name)
    return available


def convert_md_to_html_safe(md_text: str) -> str:
    """
    安全なMarkdown→HTML変換。エラー時は元テキストをプレーンテキストとして返す。

    markdown ライブラリが利用できない場合でも例外を投げず、
    <pre> タグで囲んだプレーンテキストを返す。

    Args:
        md_text: 変換対象のMarkdownテキスト

    Returns:
        変換後のHTML文字列（失敗時はプレーンテキストを <pre> で囲んだもの）
    """
    if not isinstance(md_text, str):
        return ""

    if not md_text.strip():
        return ""

    try:
        return convert_md_to_html(md_text)
    except (RuntimeError, Exception) as e:
        logger.warning("Markdown変換に失敗したため、プレーンテキストとして返します: %s", e)
        escaped = _escape_html(md_text)
        return f"<pre>{escaped}</pre>"


def _escape_html(text: str) -> str:
    """基本的なHTMLエスケープ処理。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def convert_md_file_to_html(
    input_path: str,
    output_path: Optional[str] = None,
    encoding: str = "utf-8",
) -> str:
    """
    MarkdownファイルをHTMLに変換する。

    Args:
        input_path: 入力Markdownファイルのパス
        output_path: 出力HTMLファイルのパス（Noneの場合は .html 拡張子に変換）
        encoding: ファイルエンコーディング

    Returns:
        変換後のHTML文字列

    Raises:
        FileNotFoundError: 入力ファイルが見つからない場合
        RuntimeError: 変換に失敗した場合
    """
    from pathlib import Path

    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {input_path}")

    md_text = input_file.read_text(encoding=encoding)
    html = convert_md_to_html(md_text)

    if output_path is not None:
        out_file = Path(output_path)
    else:
        out_file = input_file.with_suffix(".html")

    out_file.write_text(html, encoding=encoding)
    logger.info("HTML出力: %s", out_file)
    return html


def wrap_html_document(
    html_body: str,
    title: str = "Document",
    css: Optional[str] = None,
) -> str:
    """
    HTML本文を完全なHTMLドキュメントとしてラップする。

    Args:
        html_body: HTMLの本文部分
        title: ページタイトル
        css: カスタムCSSスタイル（Noneでデフォルト使用）

    Returns:
        完全なHTMLドキュメント文字列
    """
    if css is None:
        css = _get_default_css()

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_escape_html(title)}</title>
    <style>
{css}
    </style>
</head>
<body>
    <div class="content">
{html_body}
    </div>
</body>
</html>"""


def _get_default_css() -> str:
    """デフォルトのCSSスタイルを返す。"""
    return """
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            line-height: 1.6;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
            background-color: #fff;
        }
        .content {
            padding: 10px;
        }
        h1, h2, h3, h4, h5, h6 {
            margin-top: 1.5em;
            margin-bottom: 0.5em;
            font-weight: 600;
            line-height: 1.25;
        }
        h1 { font-size: 2em; border-bottom: 1px solid #eee; padding-bottom: 0.3em; }
        h2 { font-size: 1.5em; border-bottom: 1px solid #eee; padding-bottom: 0.3em; }
        h3 { font-size: 1.25em; }
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px 12px;
            text-align: left;
        }
        th {
            background-color: #f6f8fa;
            font-weight: 600;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        code {
            background-color: #f6f8fa;
            padding: 0.2em 0.4em;
            border-radius: 3px;
            font-size: 85%;
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
        }
        pre {
            background-color: #f6f8fa;
            padding: 16px;
            border-radius: 6px;
            overflow-x: auto;
            line-height: 1.45;
        }
        pre code {
            background-color: transparent;
            padding: 0;
        }
        ul, ol {
            padding-left: 2em;
        }
        li {
            margin: 0.25em 0;
        }
        blockquote {
            margin: 0;
            padding: 0 1em;
            border-left: 4px solid #ddd;
            color: #666;
        }
        a {
            color: #0366d6;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        hr {
            border: none;
            border-top: 1px solid #eee;
            margin: 2em 0;
        }
    """


# モジュール情報
__all__ = [
    "convert_md_to_html",
    "convert_md_to_html_safe",
    "convert_md_file_to_html",
    "wrap_html_document",
]
