#!/usr/bin/env python3
"""
AI PM Framework - Markdown to HTML 変換ユーティリティのテスト

テスト対象: backend/utils/md_to_html.py

テスト項目:
- 見出し (h1, h2, h3) の変換
- リスト (ul, ol) の変換
- テーブルの変換
- コードブロック（インライン、フェンス）の変換
- 空文字列の処理
- safe変換（convert_md_to_html_safe）
- ファイル変換（convert_md_file_to_html）
- HTMLドキュメントラップ（wrap_html_document）
- エラーケース（不正入力）
"""

import sys
import os
import tempfile
import unittest
from pathlib import Path

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
sys.path.insert(0, str(_package_root))

from utils.md_to_html import (
    convert_md_to_html,
    convert_md_to_html_safe,
    convert_md_file_to_html,
    wrap_html_document,
)


class TestConvertMdToHtmlHeadings(unittest.TestCase):
    """見出し (h1, h2, h3) の変換テスト"""

    def test_h1_heading(self):
        """h1 見出しが正しく変換されること"""
        md = "# 見出し1"
        html = convert_md_to_html(md)
        self.assertIn("<h1", html)
        self.assertIn("見出し1", html)
        self.assertIn("</h1>", html)

    def test_h2_heading(self):
        """h2 見出しが正しく変換されること"""
        md = "## 見出し2"
        html = convert_md_to_html(md)
        self.assertIn("<h2", html)
        self.assertIn("見出し2", html)
        self.assertIn("</h2>", html)

    def test_h3_heading(self):
        """h3 見出しが正しく変換されること"""
        md = "### 見出し3"
        html = convert_md_to_html(md)
        self.assertIn("<h3", html)
        self.assertIn("見出し3", html)
        self.assertIn("</h3>", html)

    def test_multiple_headings(self):
        """複数の見出しレベルが正しく変換されること"""
        md = "# Title\n\n## Section\n\n### Subsection"
        html = convert_md_to_html(md)
        self.assertIn("<h1", html)
        self.assertIn("<h2", html)
        self.assertIn("<h3", html)


class TestConvertMdToHtmlLists(unittest.TestCase):
    """リスト (ul, ol) の変換テスト"""

    def test_unordered_list(self):
        """箇条書きリスト (ul) が正しく変換されること"""
        md = "- 項目1\n- 項目2\n- 項目3"
        html = convert_md_to_html(md)
        self.assertIn("<ul>", html)
        self.assertIn("<li>", html)
        self.assertIn("項目1", html)
        self.assertIn("項目2", html)
        self.assertIn("項目3", html)
        self.assertIn("</ul>", html)

    def test_ordered_list(self):
        """番号付きリスト (ol) が正しく変換されること"""
        md = "1. 最初\n2. 次\n3. 最後"
        html = convert_md_to_html(md)
        self.assertIn("<ol>", html)
        self.assertIn("<li>", html)
        self.assertIn("最初", html)
        self.assertIn("次", html)
        self.assertIn("最後", html)
        self.assertIn("</ol>", html)

    def test_nested_list(self):
        """ネストされたリストが正しく変換されること"""
        md = "- 親項目\n    - 子項目1\n    - 子項目2"
        html = convert_md_to_html(md)
        self.assertIn("<ul>", html)
        self.assertIn("親項目", html)
        self.assertIn("子項目1", html)
        self.assertIn("子項目2", html)


class TestConvertMdToHtmlTable(unittest.TestCase):
    """テーブルの変換テスト"""

    def test_simple_table(self):
        """シンプルなテーブルが正しく変換されること"""
        md = (
            "| 名前 | 年齢 |\n"
            "|------|------|\n"
            "| 太郎 | 25   |\n"
            "| 花子 | 30   |"
        )
        html = convert_md_to_html(md)
        self.assertIn("<table>", html)
        self.assertIn("<th>", html)
        self.assertIn("名前", html)
        self.assertIn("年齢", html)
        self.assertIn("<td>", html)
        self.assertIn("太郎", html)
        self.assertIn("25", html)
        self.assertIn("花子", html)
        self.assertIn("30", html)
        self.assertIn("</table>", html)

    def test_table_with_three_columns(self):
        """3列テーブルが正しく変換されること"""
        md = (
            "| Col1 | Col2 | Col3 |\n"
            "|------|------|------|\n"
            "| A    | B    | C    |"
        )
        html = convert_md_to_html(md)
        self.assertIn("<table>", html)
        self.assertIn("Col1", html)
        self.assertIn("Col2", html)
        self.assertIn("Col3", html)
        self.assertIn("A", html)


class TestConvertMdToHtmlCodeBlocks(unittest.TestCase):
    """コードブロック（インライン、フェンス）の変換テスト"""

    def test_inline_code(self):
        """インラインコードが正しく変換されること"""
        md = "これは `inline_code` です"
        html = convert_md_to_html(md)
        self.assertIn("<code>", html)
        self.assertIn("inline_code", html)
        self.assertIn("</code>", html)

    def test_fenced_code_block(self):
        """フェンスドコードブロックが正しく変換されること"""
        md = '```python\ndef hello():\n    print("Hello")\n```'
        html = convert_md_to_html(md)
        self.assertIn("<code", html)
        self.assertIn("def hello():", html)
        self.assertIn("</code>", html)

    def test_fenced_code_block_without_lang(self):
        """言語指定なしフェンスドコードブロックが変換されること"""
        md = "```\nplain text code\n```"
        html = convert_md_to_html(md)
        self.assertIn("<code", html)
        self.assertIn("plain text code", html)

    def test_code_block_preserves_content(self):
        """コードブロック内の内容が保持されること"""
        md = "```\nif x > 0:\n    return True\n```"
        html = convert_md_to_html(md)
        self.assertIn("if x", html)
        self.assertIn("return True", html)


class TestConvertMdToHtmlEmptyInput(unittest.TestCase):
    """空文字列の処理テスト"""

    def test_empty_string(self):
        """空文字列は空文字列を返すこと"""
        result = convert_md_to_html("")
        self.assertEqual(result, "")

    def test_whitespace_only(self):
        """空白のみの文字列は空文字列を返すこと"""
        result = convert_md_to_html("   ")
        self.assertEqual(result, "")

    def test_newline_only(self):
        """改行のみの文字列は空文字列を返すこと"""
        result = convert_md_to_html("\n\n\n")
        self.assertEqual(result, "")


class TestConvertMdToHtmlSafe(unittest.TestCase):
    """convert_md_to_html_safe のテスト"""

    def test_safe_normal_conversion(self):
        """正常なMarkdownが正しく変換されること"""
        md = "# Hello\n\nThis is a test."
        html = convert_md_to_html_safe(md)
        self.assertIn("<h1", html)
        self.assertIn("Hello", html)

    def test_safe_empty_string(self):
        """空文字列は空文字列を返すこと"""
        result = convert_md_to_html_safe("")
        self.assertEqual(result, "")

    def test_safe_non_string_input(self):
        """文字列以外の入力は空文字列を返すこと"""
        result = convert_md_to_html_safe(None)
        self.assertEqual(result, "")

        result = convert_md_to_html_safe(123)
        self.assertEqual(result, "")

        result = convert_md_to_html_safe([1, 2, 3])
        self.assertEqual(result, "")

    def test_safe_whitespace_only(self):
        """空白のみの場合は空文字列を返すこと"""
        result = convert_md_to_html_safe("   \n  ")
        self.assertEqual(result, "")


class TestConvertMdFileToHtml(unittest.TestCase):
    """convert_md_file_to_html のテスト（一時ファイル使用）"""

    def test_file_conversion(self):
        """ファイルベースの変換が正しく動作すること"""
        md_content = "# File Test\n\nHello from file."
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "test.md")
            output_path = os.path.join(tmpdir, "test.html")

            with open(input_path, "w", encoding="utf-8") as f:
                f.write(md_content)

            html = convert_md_file_to_html(input_path, output_path)

            # 戻り値の検証
            self.assertIn("<h1", html)
            self.assertIn("File Test", html)
            self.assertIn("Hello from file", html)

            # 出力ファイルの存在確認
            self.assertTrue(os.path.exists(output_path))

            # 出力ファイルの内容確認
            with open(output_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            self.assertIn("<h1", file_content)
            self.assertIn("File Test", file_content)

    def test_file_conversion_default_output(self):
        """出力パス未指定時に.html拡張子のファイルが作成されること"""
        md_content = "## Default Output\n\nContent here."
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "sample.md")

            with open(input_path, "w", encoding="utf-8") as f:
                f.write(md_content)

            html = convert_md_file_to_html(input_path)

            # .html ファイルが作成されていること
            expected_output = os.path.join(tmpdir, "sample.html")
            self.assertTrue(os.path.exists(expected_output))

            # 戻り値の検証
            self.assertIn("<h2", html)
            self.assertIn("Default Output", html)

    def test_file_not_found(self):
        """存在しないファイルでFileNotFoundErrorが発生すること"""
        with self.assertRaises(FileNotFoundError):
            convert_md_file_to_html("/nonexistent/path/file.md")

    def test_file_with_japanese(self):
        """日本語を含むMarkdownファイルが正しく変換されること"""
        md_content = "# 日本語テスト\n\nこんにちは世界。\n\n- りんご\n- みかん"
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "japanese.md")
            output_path = os.path.join(tmpdir, "japanese.html")

            with open(input_path, "w", encoding="utf-8") as f:
                f.write(md_content)

            html = convert_md_file_to_html(input_path, output_path)

            self.assertIn("日本語テスト", html)
            self.assertIn("こんにちは世界", html)
            self.assertIn("りんご", html)
            self.assertIn("みかん", html)


class TestWrapHtmlDocument(unittest.TestCase):
    """wrap_html_document のテスト"""

    def test_basic_wrap(self):
        """基本的なHTMLドキュメントラップが動作すること"""
        body = "<h1>Hello</h1><p>World</p>"
        doc = wrap_html_document(body)

        self.assertIn("<!DOCTYPE html>", doc)
        self.assertIn("<html", doc)
        self.assertIn("<head>", doc)
        self.assertIn("<meta charset=\"utf-8\">", doc)
        self.assertIn("<body>", doc)
        self.assertIn("<h1>Hello</h1>", doc)
        self.assertIn("<p>World</p>", doc)
        self.assertIn("</html>", doc)

    def test_custom_title(self):
        """カスタムタイトルが設定されること"""
        body = "<p>Test</p>"
        doc = wrap_html_document(body, title="My Custom Title")
        self.assertIn("<title>My Custom Title</title>", doc)

    def test_default_title(self):
        """デフォルトタイトルが 'Document' であること"""
        body = "<p>Test</p>"
        doc = wrap_html_document(body)
        self.assertIn("<title>Document</title>", doc)

    def test_custom_css(self):
        """カスタムCSSが挿入されること"""
        body = "<p>Test</p>"
        custom_css = "body { color: red; }"
        doc = wrap_html_document(body, css=custom_css)
        self.assertIn("body { color: red; }", doc)

    def test_default_css_included(self):
        """デフォルトCSSが含まれること"""
        body = "<p>Test</p>"
        doc = wrap_html_document(body)
        self.assertIn("<style>", doc)
        self.assertIn("font-family", doc)

    def test_title_html_escaped(self):
        """タイトルのHTMLエスケープが機能すること"""
        body = "<p>Test</p>"
        doc = wrap_html_document(body, title="<script>alert('xss')</script>")
        # <script> がエスケープされていること
        self.assertNotIn("<script>alert", doc)
        self.assertIn("&lt;script&gt;", doc)

    def test_content_div_present(self):
        """content div が存在すること"""
        body = "<p>Inner</p>"
        doc = wrap_html_document(body)
        self.assertIn('<div class="content">', doc)

    def test_lang_attribute(self):
        """html タグに lang='ja' が設定されていること"""
        body = "<p>Test</p>"
        doc = wrap_html_document(body)
        self.assertIn('lang="ja"', doc)


class TestConvertMdToHtmlErrorCases(unittest.TestCase):
    """エラーケース（不正入力）のテスト"""

    def test_none_input_raises_value_error(self):
        """None入力でValueErrorが発生すること"""
        with self.assertRaises(ValueError):
            convert_md_to_html(None)

    def test_integer_input_raises_value_error(self):
        """整数入力でValueErrorが発生すること"""
        with self.assertRaises(ValueError):
            convert_md_to_html(123)

    def test_list_input_raises_value_error(self):
        """リスト入力でValueErrorが発生すること"""
        with self.assertRaises(ValueError):
            convert_md_to_html(["not", "a", "string"])

    def test_dict_input_raises_value_error(self):
        """辞書入力でValueErrorが発生すること"""
        with self.assertRaises(ValueError):
            convert_md_to_html({"key": "value"})

    def test_custom_extensions(self):
        """カスタム拡張機能リストで動作すること"""
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = convert_md_to_html(md, extensions=["tables"])
        self.assertIn("<table>", html)

    def test_empty_extensions(self):
        """空の拡張機能リストで動作すること"""
        md = "# Heading\n\nParagraph."
        html = convert_md_to_html(md, extensions=[])
        self.assertIn("Heading", html)
        self.assertIn("Paragraph", html)


class TestConvertMdToHtmlMixed(unittest.TestCase):
    """複合的なMarkdownの変換テスト"""

    def test_mixed_content(self):
        """見出し・リスト・テーブル・コードが混在するMarkdownの変換"""
        md = """# プロジェクト概要

## 機能一覧

- 機能A
- 機能B
- 機能C

## スケジュール

| フェーズ | 期間 |
|---------|------|
| 設計    | 1週間 |
| 実装    | 2週間 |

## サンプルコード

```python
def main():
    print("Hello")
```

インラインコード: `variable_name` を使用する。
"""
        html = convert_md_to_html(md)

        # 見出し
        self.assertIn("<h1", html)
        self.assertIn("プロジェクト概要", html)
        self.assertIn("<h2", html)

        # リスト
        self.assertIn("<ul>", html)
        self.assertIn("機能A", html)

        # テーブル
        self.assertIn("<table>", html)
        self.assertIn("フェーズ", html)
        self.assertIn("設計", html)

        # コードブロック
        self.assertIn("<code", html)
        self.assertIn("def main():", html)

        # インラインコード
        self.assertIn("variable_name", html)


if __name__ == "__main__":
    unittest.main()
