/**
 * NotificationService
 *
 * デスクトップ通知を管理するサービス
 * ORDER_039: ワンクリック自動実行機能
 *
 * 機能:
 * - スクリプト実行完了時の通知
 * - 成功/失敗に応じた通知内容
 * - 通知クリック時のアクション
 */

import { Notification, app } from 'electron';
import type { ExecutionResult } from './ScriptExecutionService';

// =============================================================================
// 型定義
// =============================================================================

/**
 * 通知オプション
 */
export interface NotificationOptions {
  /** タイトル */
  title: string;
  /** 本文 */
  body: string;
  /** 成功/失敗 */
  type?: 'success' | 'error' | 'info';
  /** クリック時のコールバック */
  onClick?: () => void;
}

// =============================================================================
// NotificationService
// =============================================================================

/**
 * 通知サービス
 */
export class NotificationService {
  /**
   * 通知を表示
   */
  show(options: NotificationOptions): void {
    // 通知がサポートされているか確認
    if (!Notification.isSupported()) {
      console.warn('[NotificationService] Notifications are not supported on this platform');
      return;
    }

    const notification = new Notification({
      title: options.title,
      body: options.body,
      icon: this.getIcon(options.type),
      silent: false,
    });

    // クリックハンドラ
    if (options.onClick) {
      notification.on('click', options.onClick);
    }

    notification.show();

    console.log('[NotificationService] Notification shown:', {
      title: options.title,
      type: options.type,
    });
  }

  /**
   * スクリプト実行結果の通知を表示
   */
  showExecutionResult(result: ExecutionResult): void {
    const isSuccess = result.success;
    const typeLabel = result.type === 'pm' ? 'PM処理' : 'Worker処理';
    const durationSec = (result.durationMs / 1000).toFixed(1);

    let title: string;
    let body: string;

    if (isSuccess) {
      title = `${typeLabel}完了`;
      body = `${result.targetId} の処理が完了しました（${durationSec}秒）`;
    } else {
      title = `${typeLabel}失敗`;
      body = result.error || `${result.targetId} の処理が失敗しました`;
    }

    this.show({
      title,
      body,
      type: isSuccess ? 'success' : 'error',
    });
  }

  /**
   * PM処理開始通知
   */
  showPmStarted(projectId: string, backlogId: string): void {
    this.show({
      title: 'PM処理開始',
      body: `${backlogId} のPM処理を開始しました`,
      type: 'info',
    });
  }

  /**
   * Worker処理開始通知
   */
  showWorkerStarted(projectId: string, orderId: string): void {
    this.show({
      title: 'Worker処理開始',
      body: `${orderId} のWorker処理を開始しました`,
      type: 'info',
    });
  }

  /**
   * 通知タイプに応じたアイコンパスを取得
   */
  private getIcon(type?: 'success' | 'error' | 'info'): string | undefined {
    // Electronでは、アプリアイコンがデフォルトで使用される
    // カスタムアイコンを使用する場合は、ここでパスを返す
    // 現時点ではデフォルトアイコンを使用
    return undefined;
  }
}

// =============================================================================
// シングルトンインスタンス
// =============================================================================

let notificationService: NotificationService | null = null;

/**
 * NotificationServiceのシングルトンインスタンスを取得
 */
export function getNotificationService(): NotificationService {
  if (!notificationService) {
    notificationService = new NotificationService();
  }
  return notificationService;
}

/**
 * NotificationServiceをリセット（テスト用）
 */
export function resetNotificationService(): void {
  notificationService = null;
}
