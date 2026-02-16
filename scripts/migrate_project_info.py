#!/usr/bin/env python3
"""
PROJECT_INFO.md Migration Script

旧AI_PMリポジトリのPROJECT_INFO.mdを解析し、
プロジェクト概要・目的・技術スタック等を抽出してV2内部DBに登録する。

Usage:
    python migrate_project_info.py <project_name> <project_info_md_path>

Example:
    python migrate_project_info.py ai_pm_manager D:/your_workspace/AI_PM/PROJECTS/ai_pm_manager/PROJECT_INFO.md
"""

import sys
import os
import re
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional


def get_v2_db_path() -> Path:
    """V2内部DBのパスを取得"""
    appdata = os.environ.get('APPDATA')
    if not appdata:
        raise RuntimeError("APPDATA environment variable not found")

    db_path = Path(appdata) / "ai-pm-manager-v2" / ".aipm" / "aipm.db"
    if not db_path.exists():
        raise FileNotFoundError(f"V2 DB not found: {db_path}")

    return db_path


def parse_project_info(md_path: Path) -> dict:
    """
    PROJECT_INFO.mdを解析してプロジェクト情報を抽出

    Returns:
        dict with keys: name, description, purpose, tech_stack

    Raises:
        FileNotFoundError: PROJECT_INFO.mdが存在しない場合
        ValueError: 必須フィールド（プロジェクト名）が抽出できない場合
    """
    if not md_path.exists():
        raise FileNotFoundError(f"PROJECT_INFO.md not found: {md_path}")

    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError as e:
        raise ValueError(f"Failed to decode {md_path}: {e}")

    result = {
        'name': None,
        'description': None,
        'purpose': None,
        'tech_stack': None,
    }

    # プロジェクト名を抽出（## プロジェクト概要 → ### プロジェクト名 の次の行）
    # パターン1: **ai_pm_manager** - AI PM Framework ビューワー/管理アプリケーション
    name_match = re.search(r'### プロジェクト名\s*\n\s*\*\*([^\*]+)\*\*\s*-\s*(.+)', content)
    if name_match:
        result['name'] = name_match.group(1).strip()
        result['description'] = name_match.group(2).strip()
    else:
        # パターン2: **name** のみ（ボールド）
        name_only_match = re.search(r'### プロジェクト名\s*\n\s*\*\*([^\*]+)\*\*', content)
        if name_only_match:
            result['name'] = name_only_match.group(1).strip()
            result['description'] = result['name']
        else:
            # パターン3: プレーンテキスト（AI_PMフレームワーク（AIプロジェクト管理フレームワーク）など）
            plain_match = re.search(r'### プロジェクト名\s*\n\s*([^\n]+)', content)
            if plain_match:
                line = plain_match.group(1).strip()
                # 「name（description）」形式を分割
                if '（' in line:
                    parts = line.split('（', 1)
                    result['name'] = parts[0].strip()
                    result['description'] = parts[1].rstrip('）').strip()
                else:
                    result['name'] = line
                    result['description'] = line

    # 目的・背景を抽出（### 目的・背景 の後、次の ### まで）
    purpose_match = re.search(
        r'### 目的・背景\s*\n(.*?)(?=\n###|\Z)',
        content,
        re.DOTALL
    )
    if purpose_match:
        purpose_text = purpose_match.group(1).strip()
        # 箇条書きの - を除去し、改行で連結
        purpose_lines = [
            line.strip().lstrip('- ').strip()
            for line in purpose_text.split('\n')
            if line.strip() and not line.strip().startswith('---')
        ]
        result['purpose'] = '\n'.join(purpose_lines)

    # 技術スタックを抽出（## 技術スタック・環境 セクション全体）
    tech_match = re.search(
        r'## 技術スタック・環境(.*?)(?=\n## |\Z)',
        content,
        re.DOTALL
    )
    if tech_match:
        tech_section = tech_match.group(1).strip()

        # 各サブセクションを抽出
        sections = {
            '使用言語': extract_subsection(tech_section, '### 使用言語'),
            'フレームワーク・ライブラリ': extract_subsection(tech_section, '### フレームワーク・ライブラリ'),
            'データベース': extract_subsection(tech_section, '### データベース'),
            '開発環境': extract_subsection(tech_section, '### 開発環境'),
        }

        # 結合（セクション名付き）
        tech_parts = []
        for key, value in sections.items():
            if value:
                tech_parts.append(f"### {key}\n{value}")

        result['tech_stack'] = '\n\n'.join(tech_parts) if tech_parts else None

    # 必須フィールドのバリデーション
    if not result['name']:
        raise ValueError(f"Project name not found in {md_path}. Expected format: ### プロジェクト名\\n**name** - description")

    return result


def extract_subsection(text: str, header: str) -> Optional[str]:
    """
    技術スタックセクション内のサブセクションを抽出

    Args:
        text: 親セクションのテキスト
        header: サブセクションのヘッダー（例: "### 使用言語"）

    Returns:
        サブセクションの内容（箇条書きのリスト・ブロック）
    """
    pattern = re.escape(header) + r'\s*\n(.*?)(?=\n### |\Z)'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return None

    subsection = match.group(1).strip()

    # --- 区切り線を除去
    subsection = re.sub(r'^\s*---\s*$', '', subsection, flags=re.MULTILINE).strip()

    # 箇条書きの行と、ネストされたサブ項目を保持
    lines = []
    for line in subsection.split('\n'):
        stripped = line.strip()
        # 箇条書き（-）、サブ項目（  -）、または説明文（  > **）を含む行を保持
        if stripped and (
            stripped.startswith('-') or
            stripped.startswith('>') or
            (line.startswith('  ') and (stripped.startswith('-') or '**' in stripped or '`' in stripped))
        ):
            lines.append(line.rstrip())

    return '\n'.join(lines) if lines else None


def update_project_info(db_path: Path, project_name: str, info: dict) -> None:
    """
    V2内部DBのprojectsテーブルを更新

    Args:
        db_path: V2内部DBのパス
        project_name: プロジェクト名（projects.name）
        info: parse_project_info() の返り値
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        # プロジェクトが存在するか確認
        cur.execute('SELECT id, name FROM projects WHERE name = ?', (project_name,))
        row = cur.fetchone()

        if not row:
            print(f"[WARN] Project '{project_name}' not found in V2 DB.")
            print(f"       Available projects:")
            cur.execute('SELECT name FROM projects')
            for p in cur.fetchall():
                print(f"         - {p['name']}")
            conn.close()
            return

        project_id = row['id']

        # description, purpose, tech_stack を更新
        now = datetime.now().isoformat()
        cur.execute('''
            UPDATE projects
            SET description = ?,
                purpose = ?,
                tech_stack = ?,
                updated_at = ?
            WHERE id = ?
        ''', (
            info.get('description'),
            info.get('purpose'),
            info.get('tech_stack'),
            now,
            project_id
        ))

        conn.commit()
        print(f"[OK] Project '{project_name}' (id={project_id}) updated successfully.")
        print(f"     - description: {len(info.get('description') or '')} chars")
        print(f"     - purpose: {len(info.get('purpose') or '')} chars")
        print(f"     - tech_stack: {len(info.get('tech_stack') or '')} chars")

    except sqlite3.Error as e:
        print(f"[ERROR] Database error: {e}")
        conn.rollback()
    finally:
        conn.close()


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    project_name = sys.argv[1]
    project_info_path = Path(sys.argv[2])

    print(f"=== PROJECT_INFO.md Migration ===")
    print(f"Project Name: {project_name}")
    print(f"PROJECT_INFO.md: {project_info_path}")
    print()

    # 1. V2 DB パス取得
    try:
        db_path = get_v2_db_path()
        print(f"[OK] V2 DB found: {db_path}")
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # 2. PROJECT_INFO.md 解析
    try:
        info = parse_project_info(project_info_path)
        print(f"[OK] PROJECT_INFO.md parsed successfully.")
        print(f"     - Extracted name: {info['name']}")
        print(f"     - Description length: {len(info.get('description') or '')} chars")
        print(f"     - Purpose length: {len(info.get('purpose') or '')} chars")
        print(f"     - Tech stack length: {len(info.get('tech_stack') or '')} chars")
        print()
    except Exception as e:
        print(f"[ERROR] Failed to parse PROJECT_INFO.md: {e}")
        sys.exit(1)

    # 3. V2 DB 更新
    update_project_info(db_path, project_name, info)
    print()
    print("=== Migration completed ===")


if __name__ == '__main__':
    main()
