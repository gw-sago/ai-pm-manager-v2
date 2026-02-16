#!/usr/bin/env python3
"""
DB整合性検証スクリプトの使用例

このファイルは verify_db_consistency.py の使用方法を示すサンプルです。
タスク完了フローなど、他のスクリプトから呼び出す際の参考にしてください。
"""

import sys
from pathlib import Path

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.verify_db_consistency import DBConsistencyChecker, verify_task_completion


def example_verify_all_projects():
    """全プロジェクトの整合性をチェックする例"""
    print("=" * 60)
    print("例1: 全プロジェクトの整合性チェック")
    print("=" * 60)

    checker = DBConsistencyChecker(verbose=False)
    result = checker.check_all()

    print(f"総チェック数: {result['stats']['total_checks']}")
    print(f"エラー: {result['stats']['errors']}")
    print(f"警告: {result['stats']['warnings']}")
    print(f"情報: {result['stats']['info']}")
    print(f"成功: {'✅' if result['success'] else '❌'}")
    print()

    return result['success']


def example_verify_specific_project(project_id: str):
    """特定プロジェクトの整合性をチェックする例"""
    print("=" * 60)
    print(f"例2: プロジェクト {project_id} の整合性チェック")
    print("=" * 60)

    checker = DBConsistencyChecker(project_id=project_id, verbose=False)
    result = checker.check_all()

    print(f"総チェック数: {result['stats']['total_checks']}")
    print(f"エラー: {result['stats']['errors']}")
    print(f"警告: {result['stats']['warnings']}")
    print(f"情報: {result['stats']['info']}")
    print(f"成功: {'✅' if result['success'] else '❌'}")
    print()

    # エラーがある場合は詳細を表示
    if result['stats']['errors'] > 0:
        print("エラー詳細:")
        error_issues = [i for i in result['issues'] if i['severity'] == 'ERROR']
        for i, issue in enumerate(error_issues[:5], 1):  # 最初の5件のみ
            print(f"  {i}. [{issue['category']}] {issue['message']}")
        if len(error_issues) > 5:
            print(f"  ... 他 {len(error_issues) - 5} 件のエラー")
        print()

    return result['success']


def example_verify_task_on_completion(project_id: str, task_id: str):
    """タスク完了時の整合性チェックの例（推奨使用方法）"""
    print("=" * 60)
    print(f"例3: タスク {task_id} 完了時の検証")
    print("=" * 60)

    result = verify_task_completion(project_id, task_id, verbose=True)

    if 'error' in result:
        print(f"❌ エラー: {result['error']}")
        return False

    print(f"タスクID: {result['task_id']}")
    print(f"ステータス: {result['task_status']}")
    print(f"エラー: {result['stats']['errors']}")
    print(f"警告: {result['stats']['warnings']}")
    print(f"情報: {result['stats']['info']}")
    print()

    # 問題の詳細を表示
    if result['issues']:
        print("検出された問題:")
        for issue in result['issues']:
            severity_icon = {
                "ERROR": "❌",
                "WARNING": "⚠️",
                "INFO": "ℹ️"
            }.get(issue['severity'], "")
            print(f"  {severity_icon} [{issue['category']}] {issue['message']}")
    else:
        print("✅ 問題は検出されませんでした")

    print()
    return result['success']


def example_integration_in_task_flow(project_id: str, task_id: str):
    """タスク完了フローへの組み込み例"""
    print("=" * 60)
    print(f"例4: タスク完了フローへの組み込み")
    print("=" * 60)

    # ステップ1: タスクを実行（省略）
    print(f"ステップ1: タスク {task_id} を実行中...")
    print()

    # ステップ2: タスクステータスをDONEに更新（省略）
    print(f"ステップ2: タスク {task_id} をDONEに更新...")
    print()

    # ステップ3: DB整合性とアーティファクトを検証
    print(f"ステップ3: DB整合性とアーティファクトを検証...")
    result = verify_task_completion(project_id, task_id, verbose=False)

    if not result['success']:
        print(f"❌ 検証失敗: エラー {result['stats']['errors']} 件")
        print("次のタスクへの移行を中止します")
        return False

    if result['stats']['warnings'] > 0:
        print(f"⚠️  警告 {result['stats']['warnings']} 件が検出されました")
        print("続行しますが、確認が必要です")

    print("✅ 検証成功")
    print()

    # ステップ4: レビューキューに追加（省略）
    print(f"ステップ4: タスク {task_id} をレビューキューに追加...")
    print()

    # ステップ5: 次のタスクを起動（省略）
    print("ステップ5: 次のタスクを起動...")
    print()

    return True


if __name__ == "__main__":
    # 例1: 全プロジェクトチェック
    # example_verify_all_projects()

    # 例2: 特定プロジェクトチェック
    example_verify_specific_project("ai_pm_manager")

    # 例3: タスク完了時の検証（推奨）
    example_verify_task_on_completion("ai_pm_manager", "TASK_913")

    # 例4: タスク完了フローへの組み込み
    example_integration_in_task_flow("ai_pm_manager", "TASK_913")
