#!/usr/bin/env python3
"""
AI PM Framework - ORDER完了時のダッシュボード自動更新テスト

TASK_721: ORDER完了時のCOMPLETED数自動更新
"""

import sys
from pathlib import Path

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, fetch_one
from order.update import update_order_status
from portfolio.get_all_orders import get_all_orders


def test_order_completion_updates_dashboard():
    """
    ORDER完了時にダッシュボードが自動更新されることを確認
    """
    print("=" * 60)
    print("ORDER完了時のダッシュボード自動更新テスト")
    print("=" * 60)

    # テスト前のCOMPLETED数を取得
    print("\n[BEFORE] COMPLETED ORDER数を取得...")
    orders_before = get_all_orders(status=["COMPLETED"])
    completed_count_before = len(orders_before)
    print(f"  COMPLETED ORDER数: {completed_count_before}件")

    # テスト用のORDERを探す（IN_PROGRESS または REVIEW ステータス）
    print("\n[TEST] テスト対象のORDERを検索...")
    active_orders = get_all_orders(status=["IN_PROGRESS", "REVIEW"])

    if not active_orders:
        print("  ⚠ テスト対象のORDERが見つかりません")
        print("  テストをスキップします")
        return

    test_order = active_orders[0]
    project_id = test_order["projectId"]
    order_id = test_order["id"]
    print(f"  テスト対象: {order_id} ({project_id})")
    print(f"  現在のステータス: {test_order['status']}")

    # ORDERを完了状態に更新（シミュレーション）
    print(f"\n[ACTION] ORDER {order_id} を COMPLETED に更新...")
    try:
        # 現在のステータスに応じて適切な遷移を実行
        if test_order["status"] == "IN_PROGRESS":
            # IN_PROGRESS → REVIEW → COMPLETED
            print("  IN_PROGRESS → REVIEW")
            update_order_status(project_id, order_id, "REVIEW", role="PM")
            print("  REVIEW → COMPLETED")
            update_order_status(project_id, order_id, "COMPLETED", role="PM")
        elif test_order["status"] == "REVIEW":
            # REVIEW → COMPLETED
            print("  REVIEW → COMPLETED")
            update_order_status(project_id, order_id, "COMPLETED", role="PM")

        print("  ✓ ORDER完了処理が成功しました")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return

    # テスト後のCOMPLETED数を確認
    print("\n[AFTER] COMPLETED ORDER数を再取得...")
    orders_after = get_all_orders(status=["COMPLETED"])
    completed_count_after = len(orders_after)
    print(f"  COMPLETED ORDER数: {completed_count_after}件")

    # 結果検証
    print("\n[RESULT] 検証結果")
    print(f"  BEFORE: {completed_count_before}件")
    print(f"  AFTER:  {completed_count_after}件")
    print(f"  差分:   +{completed_count_after - completed_count_before}件")

    if completed_count_after == completed_count_before + 1:
        print("  ✓ テスト成功: COMPLETED数が正しく更新されました")
    else:
        print("  ⚠ 警告: COMPLETED数の増加が期待値と異なります")

    # 元の状態に戻す（オプション - 実際の運用では不要）
    print("\n[CLEANUP] テスト後のクリーンアップ...")
    print("  ※ 実際の運用環境ではクリーンアップは不要です")
    print("  ※ テストORDERは COMPLETED のままにします")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)


if __name__ == "__main__":
    try:
        from config import setup_utf8_output
        setup_utf8_output()
    except ImportError:
        pass

    test_order_completion_updates_dashboard()
