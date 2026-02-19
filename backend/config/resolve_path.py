#!/usr/bin/env python3
"""
AI PM Framework - プロジェクトパス解決スクリプト

WorkerがRoaming絶対パスを取得するためのCLIユーティリティ。
PROJECTS/配下のファイルは必ずRoaming（%APPDATA%）配下に配置する設計のため、
このスクリプトで正しいパスを取得してからファイル操作を行う。

Usage:
    python backend/config/resolve_path.py PROJECT_NAME [--json]
    python backend/config/resolve_path.py PROJECT_NAME --validate PATH

Options:
    --json      JSON形式で出力
    --validate  指定パスがRoaming配下か検証（Localパス検出時は終了コード1）

Examples:
    python backend/config/resolve_path.py ai_pm_manager_v2 --json
    python backend/config/resolve_path.py ai_pm_manager_v2 --validate "C:\\Users\\...\\AppData\\Local\\..."
"""

import argparse
import json
import sys
from pathlib import Path

# パス設定
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.db_config import get_project_paths, USER_DATA_PATH
from utils.path_validation import is_roaming_path, is_local_path, convert_local_to_roaming


def main():
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except (ImportError, AttributeError):
        pass

    parser = argparse.ArgumentParser(
        description="プロジェクトパス解決（Roaming絶対パス取得）"
    )
    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--validate", help="指定パスがRoaming配下か検証")

    args = parser.parse_args()

    paths = get_project_paths(args.project_id)

    if args.validate:
        target = args.validate
        result = {
            "path": target,
            "is_roaming": is_roaming_path(target),
            "is_local": is_local_path(target),
            "warning": None,
            "corrected_path": None,
        }
        if is_local_path(target):
            result["warning"] = (
                "Localパスが検出されました。Roamingパスを使用してください。"
            )
            result["corrected_path"] = convert_local_to_roaming(target)

        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["is_roaming"] else 1)

    output = {k: str(v) for k, v in paths.items()}
    output["user_data_path"] = str(USER_DATA_PATH)

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print("プロジェクトパス（Roaming）:")
        for key, val in output.items():
            print(f"  {key}: {val}")


if __name__ == "__main__":
    main()
