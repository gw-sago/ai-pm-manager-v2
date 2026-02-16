/**
 * RefreshService - 定期リフレッシュサービス
 *
 * UI表示データの定期的な自動リフレッシュを管理するサービス
 * DBの変更を定期的にポーリングし、UIへ通知する
 *
 * ORDER_015: UI定期リフレッシュ機能の実装
 * TASK_256: 定期リフレッシュ機能の実装
 * TASK_257: ファイル監視との統合・debounce処理
 */

import { EventEmitter } from 'node:events';
import { getProjectService } from './ProjectService';
import { fileWatcherService, type FileChangeEvent } from './FileWatcherService';

/**
 * リフレッシュ間隔定数（ミリ秒）
 */
export const REFRESH_INTERVAL_MS = 10 * 1000; // 10秒（ORDER_051: リアルタイム性向上）

/**
 * debounce待機時間（ミリ秒）
 */
export const DEBOUNCE_DELAY_MS = 500;

/**
 * 最大リトライ回数
 */
export const MAX_RETRY_COUNT = 3;

/**
 * リトライ基本待機時間（ミリ秒）
 */
export const RETRY_BASE_DELAY_MS = 1000;

/**
 * 連続エラーしきい値（これを超えると警告ログ出力）
 */
export const CONSECUTIVE_ERROR_THRESHOLD = 5;

/**
 * リフレッシュ結果
 */
export interface RefreshResult {
  /** リフレッシュ成功かどうか */
  success: boolean;
  /** リフレッシュ完了時刻 */
  timestamp: Date;
  /** エラーメッセージ（失敗時のみ） */
  error?: string;
}

/**
 * RefreshServiceのステータス
 */
export interface RefreshServiceStatus {
  /** タイマーが動作中か */
  isRunning: boolean;
  /** リフレッシュ間隔（ミリ秒） */
  intervalMs: number;
  /** 最終リフレッシュ時刻 */
  lastRefreshAt: Date | null;
  /** 次回リフレッシュ予定時刻（概算） */
  nextRefreshAt: Date | null;
  /** 連続エラー回数 */
  consecutiveErrorCount: number;
}

/**
 * RefreshService クラス
 *
 * 定期的にProjectServiceのデータをリフレッシュし、
 * 変更があった場合にイベントを発行する
 *
 * TASK_257で追加された機能:
 * - FileWatcherとの統合（debounce処理付き）
 * - リトライ処理（指数バックオフ）
 * - 連続エラー時の警告ログ
 */
export class RefreshService extends EventEmitter {
  private timerId: NodeJS.Timeout | null = null;
  private debounceTimerId: NodeJS.Timeout | null = null;
  private isRunning = false;
  private intervalMs: number = REFRESH_INTERVAL_MS;
  private lastRefreshAt: Date | null = null;
  private consecutiveErrorCount = 0;
  private isListeningToWatcher = false;
  private pendingRefreshSource: string | null = null;

  /**
   * リフレッシュタイマーを開始
   *
   * @param intervalMs リフレッシュ間隔（ミリ秒、省略時はデフォルト30秒）
   */
  start(intervalMs?: number): void {
    if (this.isRunning) {
      console.log('[RefreshService] Already running, skipping start');
      return;
    }

    if (intervalMs !== undefined) {
      this.intervalMs = intervalMs;
    }

    console.log(`[RefreshService] Starting refresh timer (interval: ${this.intervalMs}ms)`);

    // 初回は即座にリフレッシュ
    this.performRefresh();

    // 定期リフレッシュタイマーを設定
    this.timerId = setInterval(() => {
      this.performRefresh();
    }, this.intervalMs);

    this.isRunning = true;
    this.emit('started', { intervalMs: this.intervalMs });
  }

  /**
   * リフレッシュタイマーを停止
   */
  stop(): void {
    if (!this.isRunning) {
      console.log('[RefreshService] Not running, skipping stop');
      return;
    }

    if (this.timerId) {
      clearInterval(this.timerId);
      this.timerId = null;
    }

    // debounceタイマーもクリア
    if (this.debounceTimerId) {
      clearTimeout(this.debounceTimerId);
      this.debounceTimerId = null;
    }

    // FileWatcher監視を停止
    this.stopListeningToWatcher();

    this.isRunning = false;
    this.consecutiveErrorCount = 0;
    this.pendingRefreshSource = null;
    console.log('[RefreshService] Stopped refresh timer');
    this.emit('stopped');
  }

  /**
   * タイマーをリセット（再開）
   *
   * リフレッシュ間隔をリセットしてタイマーを再開始する
   */
  reset(): void {
    console.log('[RefreshService] Resetting timer');
    this.stop();
    this.start(this.intervalMs);
  }

  /**
   * リフレッシュを実行（リトライ処理付き）
   *
   * @param retryCount 現在のリトライ回数
   * @param source リフレッシュのトリガー源（ログ用）
   */
  private performRefresh(retryCount = 0, source = 'timer'): void {
    const sourceInfo = source !== 'timer' ? ` (source: ${source})` : '';
    console.log(`[RefreshService] Performing refresh...${sourceInfo}`);

    try {
      const projectService = getProjectService();

      // キャッシュをクリアして再取得
      projectService.clearCache();
      const result = projectService.getProjects();

      this.lastRefreshAt = new Date();
      this.consecutiveErrorCount = 0;

      const refreshResult: RefreshResult = {
        success: !result.error,
        timestamp: this.lastRefreshAt,
        error: result.error,
      };

      console.log(
        `[RefreshService] Refresh completed: ${result.projects.length} projects (DB mode)`
      );

      // リフレッシュ完了イベントを発行
      this.emit('refreshed', refreshResult);

    } catch (error) {
      this.consecutiveErrorCount++;
      const errorMessage = error instanceof Error ? error.message : String(error);

      // リトライ処理
      if (retryCount < MAX_RETRY_COUNT) {
        const delay = RETRY_BASE_DELAY_MS * Math.pow(2, retryCount); // 指数バックオフ
        console.warn(
          `[RefreshService] Refresh failed (attempt ${retryCount + 1}/${MAX_RETRY_COUNT + 1}), ` +
          `retrying in ${delay}ms: ${errorMessage}`
        );

        setTimeout(() => {
          this.performRefresh(retryCount + 1, source);
        }, delay);
        return;
      }

      // 最終リトライも失敗
      console.error(
        `[RefreshService] Refresh failed after ${MAX_RETRY_COUNT + 1} attempts: ${errorMessage}`
      );

      // 連続エラーしきい値を超えた場合は警告
      if (this.consecutiveErrorCount >= CONSECUTIVE_ERROR_THRESHOLD) {
        console.error(
          `[RefreshService] WARNING: ${this.consecutiveErrorCount} consecutive failures. ` +
          'Please check framework path and file system access.'
        );
      }

      const refreshResult: RefreshResult = {
        success: false,
        timestamp: new Date(),
        error: errorMessage,
      };

      this.emit('refreshed', refreshResult);
      this.emit('error', error);
    }
  }

  /**
   * 手動でリフレッシュを実行（タイマーとは独立）
   *
   * @returns リフレッシュ結果
   */
  manualRefresh(): RefreshResult {
    console.log('[RefreshService] Manual refresh requested');

    try {
      const projectService = getProjectService();

      projectService.clearCache();
      const result = projectService.getProjects();

      this.lastRefreshAt = new Date();
      this.consecutiveErrorCount = 0;

      // タイマーをリセットして次のリフレッシュまでの時間をリセット
      if (this.isRunning) {
        this.reset();
      }

      return {
        success: !result.error,
        timestamp: this.lastRefreshAt,
        error: result.error,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      return {
        success: false,
        timestamp: new Date(),
        error: errorMessage,
      };
    }
  }

  /**
   * サービスの状態を取得
   */
  getStatus(): RefreshServiceStatus {
    let nextRefreshAt: Date | null = null;

    if (this.isRunning && this.lastRefreshAt) {
      nextRefreshAt = new Date(this.lastRefreshAt.getTime() + this.intervalMs);
    }

    return {
      isRunning: this.isRunning,
      intervalMs: this.intervalMs,
      lastRefreshAt: this.lastRefreshAt,
      nextRefreshAt,
      consecutiveErrorCount: this.consecutiveErrorCount,
    };
  }

  /**
   * タイマーが動作中かどうか
   */
  isActive(): boolean {
    return this.isRunning;
  }

  /**
   * FileWatcherServiceからの変更通知を監視開始
   *
   * TASK_257: ファイル監視との統合
   */
  startListeningToWatcher(): void {
    if (this.isListeningToWatcher) {
      console.log('[RefreshService] Already listening to watcher');
      return;
    }

    fileWatcherService.on('change', this.handleFileChange.bind(this));
    this.isListeningToWatcher = true;
    console.log('[RefreshService] Started listening to FileWatcher');
  }

  /**
   * FileWatcherServiceからの監視を停止
   */
  stopListeningToWatcher(): void {
    if (!this.isListeningToWatcher) {
      return;
    }

    fileWatcherService.removeListener('change', this.handleFileChange.bind(this));
    this.isListeningToWatcher = false;
    console.log('[RefreshService] Stopped listening to FileWatcher');
  }

  /**
   * FileWatcher変更イベントハンドラ（debounce処理付き）
   *
   * TASK_257: debounce処理の実装
   * - 短時間の連続更新を抑制（DEBOUNCE_DELAY_MS待機）
   * - 重複更新を防止
   */
  private handleFileChange(event: FileChangeEvent): void {
    const { projectName, eventType } = event;

    console.log(
      `[RefreshService] File change detected: ${projectName} (${eventType}), ` +
      'scheduling debounced refresh'
    );

    // 既存のdebounceタイマーがあればキャンセル
    if (this.debounceTimerId) {
      clearTimeout(this.debounceTimerId);
      console.log('[RefreshService] Cancelled pending debounced refresh');
    }

    // 更新元を記録
    this.pendingRefreshSource = `fileWatcher:${projectName}`;

    // debounce処理: 一定時間待ってからリフレッシュ
    this.debounceTimerId = setTimeout(() => {
      console.log(
        `[RefreshService] Debounce delay completed, performing refresh ` +
        `(source: ${this.pendingRefreshSource})`
      );

      this.performRefresh(0, this.pendingRefreshSource || 'fileWatcher');

      this.debounceTimerId = null;
      this.pendingRefreshSource = null;

      // 定期リフレッシュタイマーをリセット（次のリフレッシュまでの時間をリセット）
      if (this.isRunning) {
        this.resetTimerOnly();
      }
    }, DEBOUNCE_DELAY_MS);
  }

  /**
   * タイマーのみをリセット（状態は維持）
   */
  private resetTimerOnly(): void {
    if (this.timerId) {
      clearInterval(this.timerId);
    }

    this.timerId = setInterval(() => {
      this.performRefresh(0, 'timer');
    }, this.intervalMs);

    console.log('[RefreshService] Timer reset (debounce triggered)');
  }

  /**
   * debounce待機中かどうか
   */
  isPendingDebounce(): boolean {
    return this.debounceTimerId !== null;
  }
}

// シングルトンインスタンス
let refreshServiceInstance: RefreshService | null = null;

/**
 * RefreshServiceのシングルトンインスタンスを取得
 */
export function getRefreshService(): RefreshService {
  if (!refreshServiceInstance) {
    refreshServiceInstance = new RefreshService();
  }
  return refreshServiceInstance;
}

/**
 * RefreshServiceインスタンスをリセット（テスト用）
 */
export function resetRefreshService(): void {
  if (refreshServiceInstance) {
    refreshServiceInstance.stop();
  }
  refreshServiceInstance = null;
}
