#!/usr/bin/env python3
"""
AI PM Framework - 横断バックログ振り分け分析スクリプト

Usage:
    python backend/xbacklog/analyze.py XBACKLOG_ID [options]

Arguments:
    XBACKLOG_ID         横断バックログID（例: XBACKLOG_001）

Options:
    --save              分析結果をDBに保存
    --json              JSON形式で出力

Analysis Types:
    1. キーワード分析: タイトル・説明からキーワード抽出、プロジェクト内ファイルとのマッチング
    2. 影響範囲分析: 変更対象ファイルの推定、既存コードとの関連性
    3. 依存関係分析: プロジェクト間の依存関係を考慮した優先順位付け

Example:
    python backend/xbacklog/analyze.py XBACKLOG_001
    python backend/xbacklog/analyze.py XBACKLOG_001 --save --json
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, execute_query, fetch_one, fetch_all, DatabaseError
from utils.validation import ValidationError


def extract_keywords(text: str) -> List[str]:
    """
    テキストからキーワードを抽出

    Args:
        text: 分析対象テキスト

    Returns:
        キーワードリスト
    """
    if not text:
        return []

    # 日本語・英語のキーワードを抽出
    # CamelCase、snake_case、日本語名詞を考慮
    keywords = []

    # 英語キーワード（CamelCase分割含む）
    english_words = re.findall(r'[A-Z][a-z]+|[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)', text)
    keywords.extend([w.lower() for w in english_words if len(w) > 2])

    # snake_case分割
    snake_words = re.findall(r'[a-z]+(?=_)|(?<=_)[a-z]+', text)
    keywords.extend(snake_words)

    # 日本語キーワード（カタカナ・漢字の連続）
    japanese_words = re.findall(r'[ァ-ヶー]+|[一-龯]+', text)
    keywords.extend(japanese_words)

    # 重複排除
    return list(set(keywords))


def search_project_for_keywords(
    project_path: str,
    keywords: List[str],
    base_path: str
) -> Dict[str, Any]:
    """
    プロジェクト内でキーワードを検索

    Args:
        project_path: プロジェクトのパス（相対）
        keywords: 検索キーワード
        base_path: ベースパス

    Returns:
        マッチング結果
    """
    full_path = os.path.join(base_path, project_path)

    if not os.path.exists(full_path):
        return {'matches': [], 'score': 0}

    matches = []
    total_score = 0

    # 検索対象の拡張子
    target_extensions = {'.py', '.ts', '.tsx', '.js', '.jsx', '.md', '.sql'}

    try:
        for root, dirs, files in os.walk(full_path):
            # 除外ディレクトリ
            dirs[:] = [d for d in dirs if d not in {
                '__pycache__', 'node_modules', '.git', 'venv', '.venv', 'dist', 'build'
            }]

            for file in files:
                _, ext = os.path.splitext(file)
                if ext not in target_extensions:
                    continue

                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, base_path)

                # ファイル名でのマッチング
                file_lower = file.lower()
                file_matches = []
                for kw in keywords:
                    if kw.lower() in file_lower:
                        file_matches.append(kw)
                        total_score += 2  # ファイル名マッチは高スコア

                # ファイル内容でのマッチング（サイズ制限あり）
                try:
                    if os.path.getsize(file_path) < 100000:  # 100KB未満
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            for kw in keywords:
                                if kw.lower() in content.lower():
                                    if kw not in file_matches:
                                        file_matches.append(kw)
                                        total_score += 1
                except (IOError, OSError):
                    pass

                if file_matches:
                    matches.append({
                        'file': rel_path,
                        'keywords': file_matches
                    })

    except Exception as e:
        pass  # ファイルアクセスエラーは無視

    return {
        'matches': matches[:20],  # 上位20件
        'score': total_score,
        'match_count': len(matches)
    }


def analyze_keyword_match(
    xbacklog: Dict[str, Any],
    projects: List[Dict[str, Any]],
    base_path: str
) -> Dict[str, Any]:
    """
    キーワードマッチング分析

    Args:
        xbacklog: 横断バックログ情報
        projects: Supervisor配下のプロジェクト一覧
        base_path: ベースパス

    Returns:
        分析結果
    """
    # キーワード抽出
    text = f"{xbacklog['title']} {xbacklog.get('description', '')}"
    keywords = extract_keywords(text)

    if not keywords:
        return {
            'keywords': [],
            'project_scores': {},
            'recommended_project': None,
            'confidence': 'low'
        }

    # 各プロジェクトでキーワード検索
    project_scores = {}
    for proj in projects:
        result = search_project_for_keywords(proj['path'], keywords, base_path)
        project_scores[proj['id']] = {
            'score': result['score'],
            'match_count': result['match_count'],
            'sample_matches': result['matches'][:5]
        }

    # 最高スコアのプロジェクトを推奨
    recommended = None
    max_score = 0
    for proj_id, data in project_scores.items():
        if data['score'] > max_score:
            max_score = data['score']
            recommended = proj_id

    # 信頼度判定
    confidence = 'low'
    if max_score >= 10:
        confidence = 'high'
    elif max_score >= 5:
        confidence = 'medium'

    return {
        'keywords': keywords,
        'project_scores': project_scores,
        'recommended_project': recommended,
        'max_score': max_score,
        'confidence': confidence
    }


def analyze_dependencies(
    projects: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    プロジェクト間の依存関係を分析

    Args:
        projects: プロジェクト一覧

    Returns:
        依存関係情報
    """
    # 簡易的な依存関係推定（プロジェクト名やパスから推測）
    dependencies = {}

    for proj in projects:
        proj_id = proj['id']
        dependencies[proj_id] = {
            'depends_on': [],
            'depended_by': []
        }

    # フレームワークプロジェクト（AI_PM_PJ）への依存を推定
    framework_projects = [p for p in projects if 'framework' in p['name'].lower() or p['id'] == 'AI_PM_PJ']
    app_projects = [p for p in projects if p not in framework_projects]

    for app in app_projects:
        for fw in framework_projects:
            dependencies[app['id']]['depends_on'].append(fw['id'])
            dependencies[fw['id']]['depended_by'].append(app['id'])

    return dependencies


def analyze_xbacklog(
    xbacklog_id: str,
    save: bool = False,
    base_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    横断バックログを分析

    Args:
        xbacklog_id: 横断バックログID
        save: 分析結果をDBに保存するか
        base_path: ベースパス（省略時はカレントディレクトリ）

    Returns:
        分析結果
    """
    if base_path is None:
        base_path = os.getcwd()

    conn = get_connection()
    try:
        # 横断バックログ取得
        xbacklog = fetch_one(
            conn,
            """
            SELECT x.*, s.name as supervisor_name
            FROM cross_project_backlog x
            JOIN supervisors s ON x.supervisor_id = s.id
            WHERE x.id = ?
            """,
            (xbacklog_id,)
        )

        if not xbacklog:
            raise ValidationError(f"横断バックログ '{xbacklog_id}' が見つかりません")

        xbacklog = dict(xbacklog)

        # Supervisor配下のプロジェクト取得
        projects = fetch_all(
            conn,
            """
            SELECT id, name, path, status
            FROM projects
            WHERE supervisor_id = ?
            """,
            (xbacklog['supervisor_id'],)
        )
        projects = [dict(p) for p in projects]

        if not projects:
            return {
                'xbacklog_id': xbacklog_id,
                'title': xbacklog['title'],
                'error': 'Supervisor配下にプロジェクトがありません',
                'recommendations': []
            }

        # 分析実行
        keyword_analysis = analyze_keyword_match(xbacklog, projects, base_path)
        dependency_analysis = analyze_dependencies(projects)

        # 総合推奨を算出
        recommendations = []
        for proj in projects:
            proj_id = proj['id']
            kw_score = keyword_analysis['project_scores'].get(proj_id, {}).get('score', 0)

            # 依存関係によるボーナス/ペナルティ
            dep_adjustment = 0
            if dependency_analysis[proj_id]['depended_by']:
                dep_adjustment = -1  # 他から依存されているプロジェクトは後回し
            if dependency_analysis[proj_id]['depends_on']:
                dep_adjustment = 1  # 依存先があるプロジェクトを先に

            total_score = kw_score + dep_adjustment

            recommendations.append({
                'project_id': proj_id,
                'project_name': proj['name'],
                'keyword_score': kw_score,
                'dependency_adjustment': dep_adjustment,
                'total_score': total_score,
                'sample_matches': keyword_analysis['project_scores'].get(proj_id, {}).get('sample_matches', [])
            })

        # スコア順にソート
        recommendations.sort(key=lambda x: x['total_score'], reverse=True)

        result = {
            'xbacklog_id': xbacklog_id,
            'title': xbacklog['title'],
            'supervisor_id': xbacklog['supervisor_id'],
            'analyzed_at': datetime.now().isoformat(),
            'keywords': keyword_analysis['keywords'],
            'keyword_analysis': keyword_analysis,
            'dependency_analysis': dependency_analysis,
            'recommendations': recommendations,
            'top_recommendation': recommendations[0] if recommendations else None
        }

        # DB保存
        if save and recommendations:
            analysis_json = json.dumps(result, ensure_ascii=False, default=str)
            execute_query(
                conn,
                """
                UPDATE cross_project_backlog
                SET status = 'ANALYZING',
                    analysis_result = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (analysis_json, datetime.now().isoformat(), xbacklog_id)
            )
            conn.commit()
            result['saved'] = True

        return result

    finally:
        conn.close()


def main():
    """CLI エントリーポイント"""
    try:
        from config import setup_utf8_output
    except ImportError:
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="横断バックログの振り分け分析を実行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("xbacklog_id", help="横断バックログID")
    parser.add_argument("--save", action="store_true",
                        help="分析結果をDBに保存")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        result = analyze_xbacklog(
            args.xbacklog_id,
            save=args.save,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"\n=== 振り分け分析結果: {result['xbacklog_id']} ===")
            print(f"タイトル: {result['title']}")
            print(f"Supervisor: {result['supervisor_id']}")
            print(f"\n抽出キーワード: {', '.join(result.get('keywords', []))}")

            if result.get('error'):
                print(f"\n[エラー] {result['error']}")
                return

            print(f"\n--- 推奨プロジェクト ---")
            for i, rec in enumerate(result.get('recommendations', [])[:5], 1):
                score_bar = '★' * min(rec['total_score'], 10)
                print(f"\n  {i}. {rec['project_id']}: {rec['project_name']}")
                print(f"     スコア: {rec['total_score']} {score_bar}")
                print(f"     キーワードマッチ: {rec['keyword_score']}")
                if rec.get('sample_matches'):
                    print(f"     マッチファイル例: {rec['sample_matches'][0]['file'] if rec['sample_matches'] else 'なし'}")

            if result.get('top_recommendation'):
                top = result['top_recommendation']
                print(f"\n【推奨】{top['project_id']} ({top['project_name']})")

            if result.get('saved'):
                print(f"\n[保存済み] 分析結果をDBに保存しました")

    except (ValidationError, DatabaseError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
