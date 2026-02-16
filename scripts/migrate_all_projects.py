#!/usr/bin/env python3
"""
Batch Migration Script for PROJECT_INFO.md

全プロジェクトのPROJECT_INFO.mdを一括で移行する。

Usage:
    python migrate_all_projects.py [--dry-run]

Options:
    --dry-run: 実際の更新は行わず、プレビューのみ表示
"""

import sys
import os
from pathlib import Path
from typing import List, Tuple

# migrate_project_info.py をインポート
sys.path.insert(0, str(Path(__file__).parent))
from migrate_project_info import parse_project_info, update_project_info, get_v2_db_path


def find_all_project_info_files(base_path: Path) -> List[Tuple[str, Path]]:
    """
    PROJECTS/ 配下の全PROJECT_INFO.mdを検索

    Returns:
        List of (project_name, project_info_path) tuples
    """
    if not base_path.exists():
        raise FileNotFoundError(f"Base path not found: {base_path}")

    projects = []
    for project_dir in base_path.iterdir():
        if not project_dir.is_dir():
            continue

        project_info = project_dir / "PROJECT_INFO.md"
        if project_info.exists():
            projects.append((project_dir.name, project_info))

    return projects


def main():
    dry_run = '--dry-run' in sys.argv

    # 旧AI_PMのPROJECTSディレクトリ
    base_path = Path("D:/your_workspace/AI_PM/PROJECTS")

    print("=== Batch PROJECT_INFO.md Migration ===")
    print(f"Base Path: {base_path}")
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'LIVE (will update DB)'}")
    print()

    # 1. V2 DB パス取得
    try:
        db_path = get_v2_db_path()
        print(f"[OK] V2 DB found: {db_path}")
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # 2. PROJECT_INFO.md 一覧取得
    try:
        projects = find_all_project_info_files(base_path)
        print(f"[OK] Found {len(projects)} projects with PROJECT_INFO.md")
        print()
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # 3. 各プロジェクトを処理
    success_count = 0
    error_count = 0
    skip_count = 0

    for project_name, project_info_path in projects:
        print(f"--- Processing: {project_name} ---")

        try:
            # 解析
            info = parse_project_info(project_info_path)
            print(f"  [OK] Parsed successfully")
            print(f"       - Name: {info['name']}")
            print(f"       - Description: {len(info.get('description') or '')} chars")
            print(f"       - Purpose: {len(info.get('purpose') or '')} chars")
            print(f"       - Tech Stack: {len(info.get('tech_stack') or '')} chars")

            if dry_run:
                print(f"  [DRY RUN] Would update project '{project_name}' in V2 DB")
                success_count += 1
            else:
                # DB更新
                update_project_info(db_path, project_name, info)
                success_count += 1

        except FileNotFoundError as e:
            print(f"  [SKIP] {e}")
            skip_count += 1
        except ValueError as e:
            print(f"  [ERROR] Parse error: {e}")
            error_count += 1
        except Exception as e:
            print(f"  [ERROR] Unexpected error: {e}")
            error_count += 1

        print()

    # 4. サマリー
    print("=== Migration Summary ===")
    print(f"Success: {success_count}")
    print(f"Error: {error_count}")
    print(f"Skipped: {skip_count}")
    print(f"Total: {len(projects)}")

    if dry_run:
        print()
        print("This was a DRY RUN. To actually migrate, run without --dry-run:")
        print("  python migrate_all_projects.py")


if __name__ == '__main__':
    main()
