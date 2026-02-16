/**
 * Supervisor IPC Handlers
 *
 * Supervisor と XBACKLOG 管理のための IPC 通信ハンドラ
 * TASK_655: バックエンドサービス・IPC実装
 */

import { ipcMain } from 'electron';
import {
  getSupervisorService,
  type Supervisor,
  type SupervisorDetail,
  type SupervisorProject,
  type PortfolioData,
  type PortfolioTask,
} from './services/SupervisorService';
import {
  getXBacklogService,
  type XBacklog,
  type AnalysisResult,
  type DispatchResult,
} from './services/XBacklogService';

/**
 * Supervisor IPC ハンドラを登録
 */
export function registerSupervisorHandlers(): void {
  const supervisorService = getSupervisorService();
  const xbacklogService = getXBacklogService();

  // Supervisor 一覧取得
  ipcMain.handle(
    'get-supervisors',
    async (): Promise<Supervisor[]> => {
      console.log('[Supervisor IPC] Supervisor 一覧取得リクエスト');
      try {
        return supervisorService.getSupervisors();
      } catch (error) {
        console.error('[Supervisor IPC] Supervisor 一覧取得エラー:', error);
        return [];
      }
    }
  );

  // Supervisor 詳細取得
  ipcMain.handle(
    'get-supervisor-detail',
    async (_event, supervisorId: string): Promise<SupervisorDetail | null> => {
      console.log('[Supervisor IPC] Supervisor 詳細取得リクエスト:', supervisorId);
      try {
        return supervisorService.getSupervisorDetail(supervisorId);
      } catch (error) {
        console.error('[Supervisor IPC] Supervisor 詳細取得エラー:', error);
        return null;
      }
    }
  );

  // Supervisor 配下プロジェクト一覧取得
  ipcMain.handle(
    'get-projects-by-supervisor',
    async (_event, supervisorId: string, includeInactive?: boolean): Promise<SupervisorProject[]> => {
      console.log('[Supervisor IPC] Supervisor 配下プロジェクト取得リクエスト:', supervisorId);
      try {
        return supervisorService.getProjectsBySupervisor(supervisorId, includeInactive ?? false);
      } catch (error) {
        console.error('[Supervisor IPC] Supervisor 配下プロジェクト取得エラー:', error);
        return [];
      }
    }
  );

  // XBACKLOG 一覧取得
  ipcMain.handle(
    'get-xbacklogs',
    async (_event, supervisorId: string): Promise<XBacklog[]> => {
      console.log('[Supervisor IPC] XBACKLOG 一覧取得リクエスト:', supervisorId);
      try {
        return xbacklogService.getXBacklogs(supervisorId);
      } catch (error) {
        console.error('[Supervisor IPC] XBACKLOG 一覧取得エラー:', error);
        return [];
      }
    }
  );

  // XBACKLOG 作成
  ipcMain.handle(
    'create-xbacklog',
    async (_event, supervisorId: string, title: string, description: string | null, priority: string): Promise<XBacklog | null> => {
      console.log('[Supervisor IPC] XBACKLOG 作成リクエスト:', supervisorId, title);
      try {
        return xbacklogService.createXBacklog(supervisorId, title, description, priority);
      } catch (error) {
        console.error('[Supervisor IPC] XBACKLOG 作成エラー:', error);
        return null;
      }
    }
  );

  // XBACKLOG 振り分け分析
  ipcMain.handle(
    'analyze-xbacklog',
    async (_event, xbacklogId: string): Promise<AnalysisResult | null> => {
      console.log('[Supervisor IPC] XBACKLOG 分析リクエスト:', xbacklogId);
      try {
        return xbacklogService.analyzeXBacklog(xbacklogId);
      } catch (error) {
        console.error('[Supervisor IPC] XBACKLOG 分析エラー:', error);
        return null;
      }
    }
  );

  // XBACKLOG 振り分け実行
  ipcMain.handle(
    'dispatch-xbacklog',
    async (_event, xbacklogId: string, projectId: string): Promise<DispatchResult> => {
      console.log('[Supervisor IPC] XBACKLOG 振り分けリクエスト:', xbacklogId, projectId);
      try {
        return xbacklogService.dispatchXBacklog(xbacklogId, projectId);
      } catch (error) {
        console.error('[Supervisor IPC] XBACKLOG 振り分けエラー:', error);
        return { success: false, xbacklogId, projectId, backlogId: null, error: String(error) };
      }
    }
  );

  // ポートフォリオデータ取得 (ORDER_068 / BACKLOG_116)
  ipcMain.handle(
    'get-portfolio-data',
    async (_event, supervisorId: string): Promise<PortfolioData> => {
      console.log('[Supervisor IPC] ポートフォリオデータ取得リクエスト:', supervisorId);
      try {
        return supervisorService.getPortfolioData(supervisorId);
      } catch (error) {
        console.error('[Supervisor IPC] ポートフォリオデータ取得エラー:', error);
        return { orders: [], backlogs: [] };
      }
    }
  );

  // ポートフォリオORDERタスク一覧取得 (ORDER_068 / BACKLOG_116)
  ipcMain.handle(
    'get-portfolio-order-tasks',
    async (_event, projectId: string, orderId: string): Promise<PortfolioTask[]> => {
      console.log('[Supervisor IPC] ポートフォリオORDERタスク取得リクエスト:', projectId, orderId);
      try {
        return supervisorService.getPortfolioOrderTasks(projectId, orderId);
      } catch (error) {
        console.error('[Supervisor IPC] ポートフォリオORDERタスク取得エラー:', error);
        return [];
      }
    }
  );

  console.log('[Supervisor] IPC handlers registered');
}

/**
 * クリーンアップ
 */
export function cleanupSupervisor(): void {
  const supervisorService = getSupervisorService();
  const xbacklogService = getXBacklogService();
  supervisorService.close();
  xbacklogService.close();
  console.log('[Supervisor] Cleanup completed');
}
