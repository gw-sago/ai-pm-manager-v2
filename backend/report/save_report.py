#!/usr/bin/env python3
"""
AI PM Framework - レポート保存ユーティリティ（HTML同時生成）

MDファイル保存と同時にHTMLファイルを同ディレクトリに生成する。
TASK_127 (utils/md_to_html.py) の変換機能と
TASK_128 (templates/report_template.html) のテンプレートを利用する。

主要API:
    save_report_with_html(md_content, md_output_path, project_name, order_id, title)
        - MDファイルを保存し、同時にHTMLファイルを同ディレクトリに生成

    convert_existing_report_to_html(md_path, project_name, order_id)
        - 既存のMDファイルを読み込んでHTML変換、同ディレクトリに .html で保存

    batch_convert_reports_to_html(report_dir, project_name, order_id)
        - 指定ディレクトリ内の全MDファイルを一括HTML変換

Usage:
    # モジュールとして使用
    from report.save_report import save_report_with_html

    save_report_with_html(
        md_content="# レポート\\n\\n内容",
        md_output_path=Path("/path/to/REPORT_001.md"),
        project_name="my_project",
        order_id="ORDER_001",
        title="TASK_001 完了報告",
    )

    # CLI として使用（既存MDファイルのHTML変換）
    python backend/report/save_report.py /path/to/REPORT_001.md --project my_project --order ORDER_001
    python backend/report/save_report.py /path/to/05_REPORT/ --batch --project my_project --order ORDER_001
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

logger = logging.getLogger(__name__)

# テンプレートファイルパス
_TEMPLATE_PATH = _package_root / "templates" / "report_template.html"


def _load_report_template() -> Optional[str]:
    """
    report_template.html を読み込む。

    Returns:
        テンプレート文字列。読み込めない場合はNone。
    """
    if _TEMPLATE_PATH.exists():
        try:
            return _TEMPLATE_PATH.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("レポートテンプレートの読み込みに失敗しました: %s", e)
    else:
        logger.debug("レポートテンプレートが見つかりません: %s", _TEMPLATE_PATH)
    return None


def _convert_md_to_html_body(md_content: str) -> str:
    """
    MDコンテンツをHTML本文に変換する。
    md_to_html.py が利用できない場合は安全なフォールバックを使用。

    Args:
        md_content: Markdownテキスト

    Returns:
        HTML本文文字列
    """
    try:
        from utils.md_to_html import convert_md_to_html_safe
        return convert_md_to_html_safe(md_content)
    except ImportError:
        logger.warning("utils.md_to_html が利用できません。プレーンテキストにフォールバックします。")
        escaped = (
            md_content
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return f"<pre>{escaped}</pre>"


def _build_html_document(
    html_body: str,
    title: str,
    project_name: str,
    order_id: str,
    generated_at: Optional[str] = None,
) -> str:
    """
    HTML本文を完全なHTMLドキュメントに変換する。

    report_template.html が利用可能な場合はテンプレートを使用し、
    利用できない場合は md_to_html.py の wrap_html_document() にフォールバックする。

    Args:
        html_body: HTMLの本文部分
        title: ドキュメントタイトル
        project_name: プロジェクト名
        order_id: ORDER ID
        generated_at: 生成日時文字列（Noneの場合は現在時刻）

    Returns:
        完全なHTMLドキュメント文字列
    """
    if generated_at is None:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # テンプレートベースの生成を試行
    template_str = _load_report_template()
    if template_str is not None:
        try:
            return template_str.format(
                title=title,
                content=html_body,
                project_name=project_name,
                order_id=order_id,
                generated_at=generated_at,
            )
        except (KeyError, ValueError) as e:
            logger.warning("テンプレート適用に失敗しました: %s (wrap_html_documentにフォールバック)", e)

    # フォールバック: wrap_html_document
    try:
        from utils.md_to_html import wrap_html_document
        return wrap_html_document(html_body, title=title)
    except ImportError:
        logger.warning("wrap_html_document が利用できません。最小HTMLを生成します。")
        escaped_title = (
            title
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="utf-8">
    <title>{escaped_title}</title>
</head>
<body>
{html_body}
</body>
</html>"""


def save_report_with_html(
    md_content: str,
    md_output_path: Path,
    project_name: str,
    order_id: str,
    title: Optional[str] = None,
    *,
    encoding: str = "utf-8",
) -> Dict[str, Any]:
    """
    MDファイルを保存し、同時にHTMLファイルを同ディレクトリに生成する。

    Args:
        md_content: Markdownテキスト
        md_output_path: MDファイルの出力パス（Path オブジェクト）
        project_name: プロジェクト名
        order_id: ORDER ID
        title: HTMLドキュメントのタイトル（Noneの場合はファイル名から自動推定）
        encoding: ファイルエンコーディング

    Returns:
        {
            "success": bool,
            "md_path": str,        - 保存したMDファイルのパス
            "html_path": str,      - 生成したHTMLファイルのパス（エラー時はNone）
            "html_size": int,      - HTMLファイルのサイズ（バイト）
            "error": str,          - HTML生成エラー時のエラーメッセージ
        }

    Note:
        MDファイルの保存が主目的であり、HTML変換はベストエフォートで行う。
        HTML変換に失敗してもMDファイルは保存される（既存フローを壊さない）。
    """
    md_output_path = Path(md_output_path)
    result: Dict[str, Any] = {
        "success": True,
        "md_path": str(md_output_path),
        "html_path": None,
        "html_size": 0,
        "error": None,
    }

    # 1. MDファイル保存（既存フローと同等）
    md_output_path.parent.mkdir(parents=True, exist_ok=True)
    md_output_path.write_text(md_content, encoding=encoding)

    # 2. HTML変換・保存（ベストエフォート）
    try:
        # タイトル自動推定
        if title is None:
            title = md_output_path.stem  # e.g., "REPORT_129"

        # MD→HTML変換
        html_body = _convert_md_to_html_body(md_content)

        # HTMLドキュメント生成
        html_doc = _build_html_document(
            html_body=html_body,
            title=title,
            project_name=project_name,
            order_id=order_id,
        )

        # HTMLファイル保存（同ディレクトリ、拡張子のみ変更）
        html_path = md_output_path.with_suffix(".html")
        html_path.write_text(html_doc, encoding=encoding)

        result["html_path"] = str(html_path)
        result["html_size"] = html_path.stat().st_size

        logger.info("HTMLレポート生成完了: %s (%dバイト)", html_path, result["html_size"])

    except Exception as e:
        # HTML変換失敗はMDファイル保存を妨げない
        result["error"] = f"HTML変換エラー: {e}"
        logger.warning("HTMLレポート生成に失敗しました（MDファイルは保存済み）: %s", e)

    return result


def convert_existing_report_to_html(
    md_path: Path,
    project_name: str,
    order_id: str,
    title: Optional[str] = None,
    *,
    encoding: str = "utf-8",
) -> Dict[str, Any]:
    """
    既存のMDファイルを読み込んでHTML変換し、同ディレクトリに .html で保存する。

    Args:
        md_path: 変換対象のMDファイルパス
        project_name: プロジェクト名
        order_id: ORDER ID
        title: HTMLドキュメントのタイトル（Noneの場合はファイル名から自動推定）
        encoding: ファイルエンコーディング

    Returns:
        {
            "success": bool,
            "md_path": str,
            "html_path": str,
            "html_size": int,
            "error": str,          - エラー時のメッセージ
        }
    """
    md_path = Path(md_path)
    result: Dict[str, Any] = {
        "success": False,
        "md_path": str(md_path),
        "html_path": None,
        "html_size": 0,
        "error": None,
    }

    # MDファイル存在チェック
    if not md_path.exists():
        result["error"] = f"MDファイルが見つかりません: {md_path}"
        return result

    if not md_path.is_file():
        result["error"] = f"パスがファイルではありません: {md_path}"
        return result

    try:
        # MDファイル読み込み
        md_content = md_path.read_text(encoding=encoding)

        if not md_content.strip():
            result["error"] = f"MDファイルが空です: {md_path}"
            return result

        # タイトル自動推定
        if title is None:
            title = md_path.stem

        # MD→HTML変換
        html_body = _convert_md_to_html_body(md_content)

        # HTMLドキュメント生成
        html_doc = _build_html_document(
            html_body=html_body,
            title=title,
            project_name=project_name,
            order_id=order_id,
        )

        # HTMLファイル保存
        html_path = md_path.with_suffix(".html")
        html_path.write_text(html_doc, encoding=encoding)

        result["success"] = True
        result["html_path"] = str(html_path)
        result["html_size"] = html_path.stat().st_size

        logger.info("既存MDファイルをHTML変換: %s -> %s (%dバイト)", md_path, html_path, result["html_size"])

    except Exception as e:
        result["error"] = f"HTML変換エラー: {e}"
        logger.error("HTML変換に失敗しました: %s", e)

    return result


def batch_convert_reports_to_html(
    report_dir: Path,
    project_name: str,
    order_id: str,
    *,
    pattern: str = "*.md",
    encoding: str = "utf-8",
) -> Dict[str, Any]:
    """
    指定ディレクトリ内の全MDファイルを一括HTML変換する。

    Args:
        report_dir: MDファイルが格納されたディレクトリ
        project_name: プロジェクト名
        order_id: ORDER ID
        pattern: ファイルパターン（デフォルト: "*.md"）
        encoding: ファイルエンコーディング

    Returns:
        {
            "success": bool,
            "total": int,          - 対象MDファイル数
            "converted": int,      - 変換成功数
            "failed": int,         - 変換失敗数
            "results": [...],      - 各ファイルの変換結果リスト
            "errors": [...],       - エラーメッセージリスト
        }
    """
    report_dir = Path(report_dir)
    result: Dict[str, Any] = {
        "success": True,
        "total": 0,
        "converted": 0,
        "failed": 0,
        "results": [],
        "errors": [],
    }

    # ディレクトリ存在チェック
    if not report_dir.exists():
        result["success"] = False
        result["errors"].append(f"ディレクトリが見つかりません: {report_dir}")
        return result

    if not report_dir.is_dir():
        result["success"] = False
        result["errors"].append(f"パスがディレクトリではありません: {report_dir}")
        return result

    # MDファイル一覧取得
    md_files = sorted(report_dir.glob(pattern))
    result["total"] = len(md_files)

    if not md_files:
        logger.info("変換対象のMDファイルがありません: %s", report_dir)
        return result

    # 一括変換
    for md_file in md_files:
        file_result = convert_existing_report_to_html(
            md_path=md_file,
            project_name=project_name,
            order_id=order_id,
            encoding=encoding,
        )
        result["results"].append(file_result)

        if file_result["success"]:
            result["converted"] += 1
        else:
            result["failed"] += 1
            result["errors"].append(f"{md_file.name}: {file_result.get('error', '不明なエラー')}")

    if result["failed"] > 0:
        result["success"] = result["converted"] > 0  # 1件でも成功すれば部分成功

    logger.info(
        "一括HTML変換完了: %d/%d件成功 (失敗: %d件) in %s",
        result["converted"], result["total"], result["failed"], report_dir,
    )

    return result


# ============================================================================
# CLI エントリーポイント
# ============================================================================

def main():
    """CLI エントリーポイント: 既存MDファイルのHTML変換"""
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="MDレポートファイルをHTMLに変換",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("path", help="MDファイルまたはディレクトリのパス")
    parser.add_argument("--project", "-p", required=True, help="プロジェクト名")
    parser.add_argument("--order", "-o", required=True, help="ORDER ID")
    parser.add_argument("--batch", "-b", action="store_true",
                        help="ディレクトリ内の全MDファイルを一括変換")
    parser.add_argument("--pattern", default="*.md",
                        help="一括変換時のファイルパターン（デフォルト: *.md）")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    target_path = Path(args.path)

    if args.batch:
        # 一括変換
        result = batch_convert_reports_to_html(
            report_dir=target_path,
            project_name=args.project,
            order_id=args.order,
            pattern=args.pattern,
        )
    else:
        # 単一ファイル変換
        result = convert_existing_report_to_html(
            md_path=target_path,
            project_name=args.project,
            order_id=args.order,
        )

    if args.json:
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        if result.get("success"):
            if args.batch:
                print(f"一括変換完了: {result['converted']}/{result['total']}件成功")
                if result["failed"] > 0:
                    print(f"  失敗: {result['failed']}件")
                    for err in result.get("errors", []):
                        print(f"  - {err}")
            else:
                print(f"HTML変換完了: {result.get('html_path')}")
                print(f"  サイズ: {result.get('html_size', 0)}バイト")
        else:
            errors = result.get("errors", [result.get("error", "不明なエラー")])
            for err in (errors if isinstance(errors, list) else [errors]):
                print(f"エラー: {err}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
