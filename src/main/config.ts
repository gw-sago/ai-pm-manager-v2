/**
 * Config IPC Handlers
 *
 * 設定永続化のためのIPC通信ハンドラ
 *
 * V2統合: frameworkPathは固定（リポジトリルート）のため、
 * パス追加/削除/切替のハンドラは不要。
 * ウィンドウ設定のみconfig.jsonで管理。
 */

import { ipcMain } from 'electron';
import { getConfigService } from './services/ConfigService';
import type { AppConfig, WindowConfig } from './services/ConfigService';

/**
 * 設定保存リクエストの型
 */
export interface SaveConfigRequest {
  windowConfig?: WindowConfig;
}

/**
 * 設定保存結果の型
 */
export interface SaveConfigResult {
  success: boolean;
  config?: AppConfig;
  error?: string;
}

/**
 * IPC ハンドラを登録
 */
export function registerConfigHandlers(): void {
  const configService = getConfigService();

  // 設定読み込み
  ipcMain.handle('config:load', async (): Promise<AppConfig> => {
    return configService.load();
  });

  // 設定保存（ウィンドウ設定のみ）
  ipcMain.handle(
    'config:save',
    async (_event, request: SaveConfigRequest): Promise<SaveConfigResult> => {
      try {
        if (request.windowConfig) {
          configService.saveWindowConfig(request.windowConfig);
        }
        return { success: true, config: configService.load() };
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        console.error('[Config] Save failed:', message);
        return { success: false, error: message };
      }
    }
  );

  // アクティブなフレームワークパスを取得（V2: 固定パス）
  ipcMain.handle('config:get-active-path', async (): Promise<string> => {
    return configService.getActiveFrameworkPath();
  });

  // ウィンドウ設定を取得
  ipcMain.handle('config:get-window', async (): Promise<WindowConfig> => {
    return configService.getWindowConfig();
  });

  // ウィンドウ設定を保存
  ipcMain.handle(
    'config:save-window',
    async (_event, windowConfig: WindowConfig): Promise<SaveConfigResult> => {
      try {
        configService.saveWindowConfig(windowConfig);
        return { success: true, config: configService.load() };
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        console.error('[Config] Save window config failed:', message);
        return { success: false, error: message };
      }
    }
  );

  console.log('[Config] IPC handlers registered');
}
