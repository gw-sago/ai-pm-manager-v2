/**
 * Project IPC Handlers
 *
 * プロジェクト管理のためのIPC通信ハンドラ
 * TASK_018: ProjectService実装（IPC含む）
 *
 * IPC チャンネル:
 * - project:get-projects - プロジェクト一覧取得
 * - project:get-state - 指定プロジェクトのSTATE取得
 * - project:state-changed - STATE変更通知（イベント）
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { ipcMain, BrowserWindow, dialog } from 'electron';

const execFileAsync = promisify(execFile);
import {
  getProjectService,
  type Project,
  type ProjectListResult,
  type ProjectStateChangedEvent,
  type ArtifactFile,
  type DataSource,
} from './services/ProjectService';
import type { ParsedState } from './services/StateParser';
import {
  getActionGenerator,
  type RecommendedAction,
} from './services/ActionGenerator';
import {
  getAipmDbService,
  type AipmBacklogItem,
  getOrderResultFile,
  getOrderReportList,
  getOrderReport,
  type OrderResultFile,
  getOrderReleaseReadiness,
  type OrderReleaseReadiness,
  type TaskReviewHistory,
  generateReleaseNote,
  type ReleaseNoteResult,
} from './services/AipmDbService';
import { getConfigService } from './services/ConfigService';
import {
  getRefreshService,
  type RefreshResult,
  type RefreshServiceStatus,
} from './services/RefreshService';
import {
  DashboardService,
  type DashboardContext,
  type BacklogFilters,
  type BacklogItem,
} from './services/DashboardService';
import {
  getReleaseService,
  type OrderReleaseInfo,
  type ReleaseResult,
  type ReleaseDryRunResult,
} from './services/ReleaseService';
import type { TaskProgressInfo } from '../shared/types';

/**
 * プロジェクトIPCハンドラを登録
 */
export function registerProjectHandlers(): void {
  const projectService = getProjectService();

  // プロジェクト一覧取得
  ipcMain.handle(
    'project:get-projects',
    async (): Promise<ProjectListResult> => {
      console.log('[Project IPC] プロジェクト一覧取得リクエスト');
      return projectService.getProjects();
    }
  );

  // 指定プロジェクトのSTATE取得
  ipcMain.handle(
    'project:get-state',
    async (_event, projectName: string): Promise<ParsedState | null> => {
      console.log(`[Project IPC] STATE取得リクエスト: ${projectName}`);
      return projectService.getProjectState(projectName);
    }
  );

  // タスクファイル内容取得
  ipcMain.handle(
    'project:get-task-file',
    async (_event, projectName: string, taskId: string): Promise<string | null> => {
      console.log(`[Project IPC] タスクファイル取得リクエスト: ${projectName}/${taskId}`);
      return projectService.getTaskFileContent(projectName, taskId);
    }
  );

  // REPORTファイル内容取得 (NOTE: TASK_963以降、UIからは未使用。互換性維持のため残存)
  ipcMain.handle(
    'project:get-report-file',
    async (_event, projectName: string, taskId: string): Promise<string | null> => {
      console.log(`[Project IPC] REPORTファイル取得リクエスト: ${projectName}/${taskId}`);
      return projectService.getReportFileContent(projectName, taskId);
    }
  );

  // ORDERファイル内容取得
  ipcMain.handle(
    'project:get-order-file',
    async (_event, projectName: string, orderId: string): Promise<string | null> => {
      console.log(`[Project IPC] ORDERファイル取得リクエスト: ${projectName}/${orderId}`);
      return projectService.getOrderFileContent(projectName, orderId);
    }
  );

  // PROJECT_INFO.mdファイル内容取得 (ORDER_002 / BACKLOG_002)
  ipcMain.handle(
    'project:get-project-info-file',
    async (_event, projectName: string): Promise<string | null> => {
      console.log(`[Project IPC] PROJECT_INFO.mdファイル取得リクエスト: ${projectName}`);
      return projectService.getProjectInfoFileContent(projectName);
    }
  );

  // INFO_PAGESページ一覧取得 (ORDER_002 / BACKLOG_002: プロジェクト情報の深化)
  ipcMain.handle(
    'project:get-info-pages',
    async (_event, projectName: string) => {
      console.log(`[Project IPC] INFO_PAGESページ一覧取得リクエスト: ${projectName}`);
      return projectService.getInfoPages(projectName);
    }
  );

  // INFO_PAGESページコンテンツ取得 (ORDER_002 / BACKLOG_002: プロジェクト情報の深化)
  ipcMain.handle(
    'project:get-info-page-content',
    async (_event, projectName: string, pageId: string): Promise<string | null> => {
      console.log(`[Project IPC] INFO_PAGESページコンテンツ取得リクエスト: ${projectName}/${pageId}`);
      return projectService.getInfoPageContent(projectName, pageId);
    }
  );

  // REVIEWファイル内容取得 (統合フォーマット: 実施内容+判定結果を含む)
  ipcMain.handle(
    'project:get-review-file',
    async (_event, projectName: string, taskId: string): Promise<string | null> => {
      console.log(`[Project IPC] REVIEWファイル取得リクエスト: ${projectName}/${taskId}`);
      return projectService.getReviewFileContent(projectName, taskId);
    }
  );

  // 推奨アクション取得 (TASK_026)
  ipcMain.handle(
    'project:get-recommended-actions',
    async (
      _event,
      projectName: string,
      state: ParsedState
    ): Promise<RecommendedAction[]> => {
      console.log(`[Project IPC] 推奨アクション取得リクエスト: ${projectName}`);
      const actionGenerator = getActionGenerator();
      return actionGenerator.generate(projectName, state);
    }
  );

  // 成果物ファイル一覧取得 (TASK_194)
  ipcMain.handle(
    'project:get-artifact-files',
    async (
      _event,
      projectName: string,
      orderId: string
    ): Promise<ArtifactFile[]> => {
      console.log(`[Project IPC] 成果物ファイル一覧取得リクエスト: ${projectName}/${orderId}`);
      return projectService.getArtifactFiles(projectName, orderId);
    }
  );

  // 成果物ファイル内容取得 (TASK_194)
  ipcMain.handle(
    'project:get-artifact-content',
    async (
      _event,
      projectName: string,
      orderId: string,
      filePath: string
    ): Promise<string | null> => {
      console.log(`[Project IPC] 成果物ファイル内容取得リクエスト: ${projectName}/${orderId}/${filePath}`);
      return projectService.getArtifactContent(projectName, orderId, filePath);
    }
  );

  // データソース取得 (TASK_200) - ORDER_153: 常にDB固定を返す
  ipcMain.handle(
    'project:get-data-source',
    async (): Promise<DataSource> => {
      console.log('[Project IPC] データソース取得リクエスト (固定: db)');
      return 'db';
    }
  );

  // バックログ一覧取得 (TASK_241)
  ipcMain.handle(
    'project:get-backlogs',
    async (_event, projectName: string): Promise<AipmBacklogItem[]> => {
      console.log(`[Project IPC] バックログ一覧取得リクエスト: ${projectName}`);
      try {
        const configService = getConfigService();
        const aipmDbService = getAipmDbService();

        // DB優先モードかつDBが利用可能な場合
        if (configService.isDbPriorityEnabled() && aipmDbService.isAvailable()) {
          return aipmDbService.getBacklogs(projectName);
        }

        // DBが利用できない場合は空配列を返す
        console.log('[Project IPC] DB not available for backlogs');
        return [];
      } catch (error) {
        console.error('[Project IPC] Failed to get backlogs:', error);
        return [];
      }
    }
  );

  // タスク詳細取得 (ORDER_126 / TASK_1118)
  ipcMain.handle(
    'project:get-task-detail',
    async (_event, taskId: string, projectId: string) => {
      console.log(`[Project IPC] タスク詳細取得リクエスト: ${taskId} (${projectId})`);
      try {
        const configService = getConfigService();
        const aipmDbService = getAipmDbService();

        // DB優先モードかつDBが利用可能な場合
        if (configService.isDbPriorityEnabled() && aipmDbService.isAvailable()) {
          return aipmDbService.getTaskDetail(taskId, projectId);
        }

        // DBが利用できない場合はnullを返す
        console.log('[Project IPC] DB not available for task detail');
        return null;
      } catch (error) {
        console.error('[Project IPC] Failed to get task detail:', error);
        return null;
      }
    }
  );

  // STATE変更イベントをレンダラーに転送
  projectService.on('project-state-changed', (event: ProjectStateChangedEvent) => {
    console.log(`[Project IPC] STATE変更通知: ${event.projectName}`);
    const windows = BrowserWindow.getAllWindows();
    windows.forEach((win) => {
      if (!win.isDestroyed()) {
        win.webContents.send('project:state-changed', event);
      }
    });
  });

  // FileWatcherからの変更通知を監視開始
  projectService.startListening();

  // === リフレッシュ関連IPCハンドラ (TASK_256) ===
  const refreshService = getRefreshService();

  // 手動リフレッシュ
  ipcMain.handle(
    'project:refresh',
    async (): Promise<RefreshResult> => {
      console.log('[Project IPC] 手動リフレッシュリクエスト');
      return refreshService.manualRefresh();
    }
  );

  // リフレッシュサービスのステータス取得
  ipcMain.handle(
    'project:get-refresh-status',
    async (): Promise<RefreshServiceStatus> => {
      console.log('[Project IPC] リフレッシュステータス取得リクエスト');
      return refreshService.getStatus();
    }
  );

  // リフレッシュ完了イベントをレンダラーに転送
  refreshService.on('refreshed', (result: RefreshResult) => {
    console.log(`[Project IPC] リフレッシュ完了通知: success=${result.success}`);
    const windows = BrowserWindow.getAllWindows();
    windows.forEach((win) => {
      if (!win.isDestroyed()) {
        win.webContents.send('project:refreshed', result);
      }
    });
  });

  // 定期リフレッシュを開始（30秒間隔）
  refreshService.start();

  // FileWatcherからの変更通知を監視開始（debounce処理付き）
  // TASK_257: ファイル監視との統合
  refreshService.startListeningToWatcher();
  console.log('[Project] Refresh service started with FileWatcher integration');

  // === ダッシュボード関連IPCハンドラ (ORDER_021 / TASK_324) ===
  let dashboardService: DashboardService | null = null;

  /**
   * DashboardServiceを取得（遅延初期化）
   */
  const getDashboardService = (): DashboardService | null => {
    if (dashboardService) {
      return dashboardService;
    }

    try {
      const configService = getConfigService();
      const frameworkPath = configService.getActiveFrameworkPath();

      if (!frameworkPath) {
        console.log('[Project IPC] Dashboard: フレームワークパスが設定されていません');
        return null;
      }

      dashboardService = new DashboardService(frameworkPath);
      console.log('[Project IPC] Dashboard: サービス初期化完了');
      return dashboardService;
    } catch (error) {
      console.error('[Project IPC] Dashboard: サービス初期化エラー', error);
      return null;
    }
  };

  // ダッシュボードコンテキスト取得
  ipcMain.handle(
    'project:get-dashboard',
    async (_event, includeInactive?: boolean): Promise<DashboardContext | null> => {
      console.log(`[Project IPC] ダッシュボード取得リクエスト: includeInactive=${includeInactive}`);
      try {
        const service = getDashboardService();
        if (!service) {
          console.log('[Project IPC] DashboardService not available');
          return null;
        }
        return await service.getDashboardContext(includeInactive ?? false);
      } catch (error) {
        console.error('[Project IPC] ダッシュボード取得エラー:', error);
        return null;
      }
    }
  );

  // 全プロジェクトバックログ取得（フィルタ付き）
  ipcMain.handle(
    'project:get-all-backlogs',
    async (_event, filters?: BacklogFilters): Promise<BacklogItem[]> => {
      console.log('[Project IPC] 全バックログ取得リクエスト:', filters);
      try {
        const service = getDashboardService();
        if (!service) {
          console.log('[Project IPC] DashboardService not available');
          return [];
        }
        return await service.getAllBacklogs(filters);
      } catch (error) {
        console.error('[Project IPC] バックログ取得エラー:', error);
        return [];
      }
    }
  );

  // BACKLOG reorder（起動時sort_order再計算）
  ipcMain.handle(
    'project:reorder-all-backlogs',
    async (): Promise<Array<{ project: string; success: boolean; message: string }>> => {
      console.log('[Project IPC] BACKLOG reorder リクエスト');
      try {
        const service = getDashboardService();
        if (!service) {
          console.log('[Project IPC] DashboardService not available for reorder');
          return [];
        }
        // AipmDbServiceからアクティブプロジェクト一覧を取得
        const aipmDb = getAipmDbService();
        const projects = aipmDb.getProjects(false);
        const projectNames = projects.map((p) => p.id);
        console.log('[Project IPC] reorder対象プロジェクト:', projectNames);
        return await service.reorderAllBacklogs(projectNames);
      } catch (error) {
        console.error('[Project IPC] BACKLOG reorder エラー:', error);
        return [];
      }
    }
  );

  console.log('[Project] Dashboard IPC handlers registered');

  // === リリース情報関連IPCハンドラ (ORDER_045 / TASK_597) ===
  const releaseService = getReleaseService();

  // ORDERリリース情報取得
  ipcMain.handle(
    'project:get-order-release-info',
    async (_event, projectName: string, orderId: string): Promise<OrderReleaseInfo> => {
      console.log(`[Project IPC] ORDERリリース情報取得リクエスト: ${projectName}/${orderId}`);
      try {
        return releaseService.getReleaseInfoByOrderId(projectName, orderId);
      } catch (error) {
        console.error('[Project IPC] ORDERリリース情報取得エラー:', error);
        return { hasRelease: false, releases: [] };
      }
    }
  );

  // ORDER関連情報取得
  ipcMain.handle(
    'project:get-order-related-info',
    async (_event, projectName: string, orderId: string): Promise<{
      relatedBacklogs: Array<{ id: string; title: string; status: string }>;
      dependentOrders: Array<{ id: string; title: string; status: string }>;
    }> => {
      console.log(`[Project IPC] ORDER関連情報取得リクエスト: ${projectName}/${orderId}`);
      try {
        const configService = getConfigService();
        const aipmDbService = getAipmDbService();

        // 関連バックログを取得
        const relatedBacklogs: Array<{ id: string; title: string; status: string }> = [];

        if (configService.isDbPriorityEnabled() && aipmDbService.isAvailable()) {
          const backlogs = aipmDbService.getBacklogs(projectName);
          for (const backlog of backlogs) {
            // related_order_id または converted_to_order_id が一致するものを取得
            if (backlog.relatedOrderId === orderId) {
              relatedBacklogs.push({
                id: backlog.id,
                title: backlog.title,
                status: backlog.status,
              });
            }
          }
        }

        // 依存ORDERは将来拡張（現時点では空配列）
        const dependentOrders: Array<{ id: string; title: string; status: string }> = [];

        return { relatedBacklogs, dependentOrders };
      } catch (error) {
        console.error('[Project IPC] ORDER関連情報取得エラー:', error);
        return { relatedBacklogs: [], dependentOrders: [] };
      }
    }
  );


  // === リリース実行関連IPCハンドラ (ORDER_108 / TASK_994) ===

  // リリース実行
  ipcMain.handle(
    'project:execute-release',
    async (_event, projectName: string, orderId: string): Promise<ReleaseResult> => {
      console.log(`[Project IPC] リリース実行リクエスト: ${projectName}/${orderId}`);
      try {
        return await releaseService.executeRelease(projectName, orderId);
      } catch (error) {
        console.error('[Project IPC] リリース実行エラー:', error);
        return {
          success: false,
          orderId,
          projectId: projectName,
          error: `Unexpected error: ${error instanceof Error ? error.message : String(error)}`,
        };
      }
    }
  );

  // リリースdry-run
  ipcMain.handle(
    'project:execute-release-dryrun',
    async (_event, projectName: string, orderId: string): Promise<ReleaseDryRunResult> => {
      console.log(`[Project IPC] リリースdry-runリクエスト: ${projectName}/${orderId}`);
      try {
        return await releaseService.executeReleaseDryRun(projectName, orderId);
      } catch (error) {
        console.error('[Project IPC] リリースdry-runエラー:', error);
        return {
          success: false,
          orderId,
          projectId: projectName,
          error: `Unexpected error: ${error instanceof Error ? error.message : String(error)}`,
        };
      }
    }
  );

  console.log('[Project] Release execution IPC handlers registered');

  console.log('[Project] Release info IPC handlers registered');

  // === RESULT Markdownファイル読み込みIPCハンドラ (ORDER_127 / TASK_1122) ===

  // RESULT配下の特定Markdownファイル読み込み（01_GOAL.md、02_REQUIREMENTS.md、03_STAFFING.md）
  ipcMain.handle(
    'project:get-order-result-file',
    async (_event, projectId: string, orderId: string, filename: string): Promise<OrderResultFile> => {
      console.log(`[Project IPC] RESULT Markdownファイル取得リクエスト: ${projectId}/${orderId}/${filename}`);
      try {
        return getOrderResultFile(projectId, orderId, filename);
      } catch (error) {
        console.error('[Project IPC] RESULT Markdownファイル取得エラー:', error);
        return {
          filename,
          path: '',
          content: '',
          exists: false,
        };
      }
    }
  );

  // 05_REPORT/配下のレポートファイル一覧取得
  ipcMain.handle(
    'project:get-order-report-list',
    async (_event, projectId: string, orderId: string): Promise<string[]> => {
      console.log(`[Project IPC] REPORTファイル一覧取得リクエスト: ${projectId}/${orderId}`);
      try {
        return getOrderReportList(projectId, orderId);
      } catch (error) {
        console.error('[Project IPC] REPORTファイル一覧取得エラー:', error);
        return [];
      }
    }
  );

  // 05_REPORT/配下の特定レポートファイル読み込み
  ipcMain.handle(
    'project:get-order-report',
    async (_event, projectId: string, orderId: string, reportFilename: string): Promise<OrderResultFile> => {
      console.log(`[Project IPC] REPORTファイル取得リクエスト: ${projectId}/${orderId}/${reportFilename}`);
      try {
        return getOrderReport(projectId, orderId, reportFilename);
      } catch (error) {
        console.error('[Project IPC] REPORTファイル取得エラー:', error);
        return {
          filename: reportFilename,
          path: '',
          content: '',
          exists: false,
        };
      }
    }
  );

  // ORDER_134: TASK_1149 - ORDERリリース準備状況取得API
  ipcMain.handle(
    'project:get-order-release-readiness',
    async (_event, projectId: string, orderId: string): Promise<OrderReleaseReadiness> => {
      console.log(`[Project IPC] リリース準備状況取得リクエスト: ${projectId}/${orderId}`);
      try {
        return getOrderReleaseReadiness(projectId, orderId);
      } catch (error) {
        console.error('[Project IPC] リリース準備状況取得エラー:', error);
        return {
          projectId,
          orderId,
          totalTasks: 0,
          completedTasks: 0,
          allTasksCompleted: false,
          reviewResults: [],
          allReviewsApproved: false,
          reportSummaries: [],
          releaseStatus: 'not_ready',
        };
      }
    }
  );

  console.log('[Project] RESULT Markdown IPC handlers registered');

  // ORDER_017: TASK_052 - リリースノート生成API
  ipcMain.handle(
    'project:generate-release-note',
    async (
      _event,
      projectId: string,
      orderId: string,
      dryRun?: boolean
    ): Promise<ReleaseNoteResult> => {
      console.log(`[Project IPC] リリースノート生成リクエスト: ${projectId}/${orderId} (dryRun=${dryRun})`);
      try {
        return await generateReleaseNote(projectId, orderId, dryRun ?? false);
      } catch (error) {
        console.error('[Project IPC] リリースノート生成エラー:', error);
        return {
          success: false,
          notePath: null,
          noteContent: '',
          taskCount: 0,
          reportCount: 0,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
  );

  console.log('[Project] Release note IPC handler registered (ORDER_017 / TASK_052)');

  // ORDER_128: TASK_1126 - タスクログの末尾行取得API
  ipcMain.handle(
    'project:get-task-log-tail',
    async (
      _event,
      projectId: string,
      orderId: string,
      taskId: string,
      lines?: number
    ): Promise<{ logLines: string[]; logFilePath: string | null } | null> => {
      console.log(
        `[Project IPC] タスクログ末尾取得: ${projectId}/${orderId}/${taskId} (${lines || 2}行)`
      );
      try {
        const aipmDbService = getAipmDbService();
        return aipmDbService.getTaskLogTail(projectId, orderId, taskId, lines);
      } catch (error) {
        console.error('[Project IPC] タスクログ末尾取得エラー:', error);
        return null;
      }
    }
  );

  // ORDER_128: TASK_1127 - 実行中タスクの詳細情報取得API
  ipcMain.handle(
    'project:get-running-tasks-info',
    async (
      _event,
      projectId: string,
      orderId: string
    ): Promise<
      Array<{
        id: string;
        title: string;
        status: string;
        currentStep: string | null;
        stepIndex: number;
        totalSteps: number;
        progressPercent: number;
      }>
    > => {
      console.log(
        `[Project IPC] 実行中タスク情報取得: ${projectId}/${orderId}`
      );
      try {
        const aipmDbService = getAipmDbService();
        return aipmDbService.getRunningTasksInfo(projectId, orderId);
      } catch (error) {
        console.error('[Project IPC] 実行中タスク情報取得エラー:', error);
        return [];
      }
    }
  );

  // ORDER_128: TASK_1127 - デーモンハートビート情報取得API
  ipcMain.handle(
    'project:get-daemon-heartbeat',
    async (
      _event,
      projectId: string,
      orderId: string
    ): Promise<{
      pid: number;
      orderId: string;
      projectId: string;
      timestamp: string;
      activeWorkers: number;
      activeWorkerPids: number[];
      status: string;
      adaptivePollInterval: number | null;
      resourceTrend: string | null;
      ageSeconds: number;
      isAlive: boolean;
    } | null> => {
      console.log(
        `[Project IPC] デーモンハートビート取得: ${projectId}/${orderId}`
      );
      try {
        const aipmDbService = getAipmDbService();
        return aipmDbService.getDaemonHeartbeat(projectId, orderId);
      } catch (error) {
        console.error('[Project IPC] デーモンハートビート取得エラー:', error);
        return null;
      }
    }
  );

  // ORDER_128: TASK_1127 - タスク進捗統合情報取得API
  // ORDER_141: TASK_1171 - TaskProgressInfo型に整合（shared/types.tsから型インポート）
  ipcMain.handle(
    'project:get-task-progress-info',
    async (
      _event,
      projectId: string,
      orderId: string
    ): Promise<TaskProgressInfo> => {
      console.log(
        `[Project IPC] タスク進捗統合情報取得: ${projectId}/${orderId}`
      );
      try {
        const aipmDbService = getAipmDbService();
        return aipmDbService.getTaskProgressInfo(projectId, orderId);
      } catch (error) {
        console.error('[Project IPC] タスク進捗統合情報取得エラー:', error);
        return {
          runningTasks: [],
          completedCount: 0,
          totalCount: 0,
          overallProgress: 0,
        };
      }
    }
  );

  console.log('[Project] Log reading IPC handlers registered');

  // ORDER_138: TASK_1158 - タスクレビュー履歴取得API
  ipcMain.handle(
    'project:get-task-review-history',
    async (
      _event,
      projectId: string,
      taskId: string
    ): Promise<TaskReviewHistory> => {
      console.log(
        `[Project IPC] レビュー履歴取得: ${projectId}/${taskId}`
      );
      try {
        const aipmDbService = getAipmDbService();
        return aipmDbService.getTaskReviewHistory(projectId, taskId);
      } catch (error) {
        console.error('[Project IPC] レビュー履歴取得エラー:', error);
        return {
          reviews: [],
          statusHistory: [],
          escalations: [],
          rejectCount: 0,
          maxRework: 3,
        };
      }
    }
  );

  console.log('[Project] Review history IPC handler registered');

  // ORDER_009: TASK_025 - ORDER構成変更履歴取得IPC
  ipcMain.handle(
    'project:get-order-structure-history',
    async (
      _event,
      projectId: string,
      orderId: string
    ) => {
      try {
        const aipmDbService = getAipmDbService();
        return aipmDbService.getOrderStructureHistory(projectId, orderId);
      } catch (error) {
        console.error('[Project IPC] ORDER構成変更履歴取得エラー:', error);
        return [];
      }
    }
  );

  // ORDER_139: TASK_1161 - バックログ追加・更新・削除IPC API
  ipcMain.handle(
    'project:add-backlog',
    async (
      _event,
      projectId: string,
      title: string,
      description: string | null,
      priority: string,
      category?: string
    ): Promise<{ success: boolean; backlogId?: string; error?: string }> => {
      console.log(`[Project IPC] バックログ追加: ${projectId}`);
      try {
        const aipmDbService = getAipmDbService();
        const result = await aipmDbService.addBacklog(projectId, title, description, priority, category);
        if (result.success) {
          // db:changed イベントを発火してBacklogListを自動更新
          const windows = BrowserWindow.getAllWindows();
          windows.forEach((win) => {
            if (!win.isDestroyed()) {
              win.webContents.send('db:changed', {
                source: 'backlog-added',
                projectId,
                targetId: result.backlogId || '',
                timestamp: new Date().toISOString(),
              });
            }
          });
        }
        return result;
      } catch (error) {
        console.error('[Project IPC] バックログ追加エラー:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
  );

  ipcMain.handle(
    'project:update-backlog',
    async (
      _event,
      projectId: string,
      backlogId: string,
      updates: {
        title?: string;
        description?: string;
        priority?: string;
        status?: string;
        sortOrder?: number;
      }
    ): Promise<{ success: boolean; error?: string }> => {
      console.log(`[Project IPC] バックログ更新: ${projectId}/${backlogId}`);
      try {
        const aipmDbService = getAipmDbService();
        const result = await aipmDbService.updateBacklog(projectId, backlogId, updates);
        if (result.success) {
          // db:changed イベントを発火してBacklogListを自動更新
          const windows = BrowserWindow.getAllWindows();
          windows.forEach((win) => {
            if (!win.isDestroyed()) {
              win.webContents.send('db:changed', {
                source: 'backlog-updated',
                projectId,
                targetId: backlogId,
                timestamp: new Date().toISOString(),
              });
            }
          });
        }
        return result;
      } catch (error) {
        console.error('[Project IPC] バックログ更新エラー:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
  );

  ipcMain.handle(
    'project:delete-backlog',
    async (
      _event,
      projectId: string,
      backlogId: string
    ): Promise<{ success: boolean; error?: string }> => {
      console.log(`[Project IPC] バックログ削除: ${projectId}/${backlogId}`);
      try {
        const aipmDbService = getAipmDbService();
        const result = await aipmDbService.deleteBacklog(projectId, backlogId);
        if (result.success) {
          // db:changed イベントを発火してBacklogListを自動更新
          const windows = BrowserWindow.getAllWindows();
          windows.forEach((win) => {
            if (!win.isDestroyed()) {
              win.webContents.send('db:changed', {
                source: 'backlog-deleted',
                projectId,
                targetId: backlogId,
                timestamp: new Date().toISOString(),
              });
            }
          });
        }
        return result;
      } catch (error) {
        console.error('[Project IPC] バックログ削除エラー:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
  );

  console.log('[Project] Backlog modification IPC handlers registered (ORDER_139 / TASK_1161)');

  // ORDER_144 / TASK_1188: バックログ優先度自動整理IPC
  ipcMain.handle(
    'project:prioritize-backlogs',
    async (
      _event,
      projectId: string,
      options?: {
        dryRun?: boolean;
        days?: number;
        verbose?: boolean;
      }
    ): Promise<{
      success: boolean;
      updatedCount?: number;
      totalCount?: number;
      changes?: Array<{
        backlogId: string;
        title: string;
        oldPriority: string;
        newPriority: string;
        oldSortOrder: number;
        newSortOrder: number;
        reason: string;
      }>;
      message?: string;
      error?: string;
      analysis?: string;
    }> => {
      console.log(`[Project IPC] バックログ優先度整理: ${projectId}`);
      try {
        const aipmDbService = getAipmDbService();
        return await aipmDbService.prioritizeBacklogs(projectId, options || {});
      } catch (error) {
        console.error('[Project IPC] バックログ優先度整理エラー:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
  );

  console.log('[Project] Backlog prioritization IPC handler registered (ORDER_144 / TASK_1188)');

  // ORDER_020 / TASK_062: バックログ自動提案IPC
  ipcMain.handle(
    'backlog:suggest',
    async (
      _event,
      projectId: string
    ): Promise<{
      success: boolean;
      suggestions?: Array<{
        title: string;
        description: string;
        priority: string;
        category: string;
        rationale: string;
      }>;
      error?: string;
    }> => {
      console.log(`[Project IPC] バックログ自動提案: ${projectId}`);
      try {
        const configService = getConfigService();
        const backendPath = configService.getBackendPath();
        if (!backendPath) {
          return { success: false, error: 'Backend path not configured' };
        }

        const suggestScriptPath = path.join(backendPath, 'backlog', 'suggest.py');
        if (!fs.existsSync(suggestScriptPath)) {
          return { success: false, error: `suggest.py not found: ${suggestScriptPath}` };
        }

        const { stdout } = await execFileAsync(
          'python',
          [suggestScriptPath, projectId, '--json'],
          { cwd: path.dirname(suggestScriptPath), timeout: 120000 }
        );

        const result = JSON.parse(stdout);
        if (!result.success) {
          return { success: false, error: result.error || 'Unknown error' };
        }
        return { success: true, suggestions: result.suggestions };
      } catch (error) {
        console.error('[Project IPC] バックログ自動提案エラー:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
  );

  // ORDER_020 / TASK_062: バックログ一括登録IPC
  ipcMain.handle(
    'backlog:bulkAdd',
    async (
      _event,
      projectId: string,
      items: Array<{
        title: string;
        description: string;
        priority: string;
        category: string;
      }>
    ): Promise<{
      success: boolean;
      addedCount?: number;
      errors?: string[];
      error?: string;
    }> => {
      console.log(`[Project IPC] バックログ一括登録: ${projectId} (${items.length}件)`);
      try {
        const aipmDbService = getAipmDbService();
        const errors: string[] = [];
        let addedCount = 0;

        for (const item of items) {
          const result = await aipmDbService.addBacklog(
            projectId,
            item.title,
            item.description || null,
            item.priority,
            item.category
          );
          if (result.success) {
            addedCount++;
          } else {
            errors.push(`${item.title}: ${result.error || 'Unknown error'}`);
          }
        }

        if (addedCount > 0) {
          const windows = BrowserWindow.getAllWindows();
          windows.forEach((win) => {
            if (!win.isDestroyed()) {
              win.webContents.send('db:changed', {
                source: 'backlog-bulk-added',
                projectId,
                targetId: '',
                timestamp: new Date().toISOString(),
              });
            }
          });
        }

        return {
          success: errors.length === 0 || addedCount > 0,
          addedCount,
          errors: errors.length > 0 ? errors : undefined,
        };
      } catch (error) {
        console.error('[Project IPC] バックログ一括登録エラー:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
  );

  console.log('[Project] Backlog suggest/bulkAdd IPC handlers registered (ORDER_020 / TASK_062)');

  // === プロジェクト情報取得・更新IPCハンドラ (ORDER_156 / TASK_1233) ===

  /**
   * プロジェクト情報取得
   */
  ipcMain.handle(
    'project:get-project-info',
    async (_event, projectId: string): Promise<{
      id: number;
      name: string;
      path: string;
      description: string | null;
      purpose: string | null;
      tech_stack: string | null;
      status: string;
      created_at: string;
      updated_at: string;
    } | null> => {
      console.log(`[Project IPC] プロジェクト情報取得: ${projectId}`);
      try {
        const aipmDbService = getAipmDbService();
        if (!aipmDbService.isAvailable()) {
          console.log('[Project IPC] DB not available');
          return null;
        }

        const project = aipmDbService.getProjectByName(projectId);
        return project;
      } catch (error) {
        console.error('[Project IPC] プロジェクト情報取得エラー:', error);
        return null;
      }
    }
  );

  /**
   * プロジェクト情報更新
   */
  ipcMain.handle(
    'project:update-project-info',
    async (
      _event,
      projectId: string,
      updates: {
        description?: string;
        purpose?: string;
        tech_stack?: string;
      }
    ): Promise<{ success: boolean; error?: string }> => {
      console.log(`[Project IPC] プロジェクト情報更新: ${projectId}`, updates);
      try {
        const aipmDbService = getAipmDbService();
        if (!aipmDbService.isAvailable()) {
          return {
            success: false,
            error: 'Database not available',
          };
        }

        aipmDbService.updateProjectInfo(projectId, updates);
        return { success: true };
      } catch (error) {
        console.error('[Project IPC] プロジェクト情報更新エラー:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
  );

  console.log('[Project] Project info IPC handlers registered (ORDER_156 / TASK_1233)');

  // === プロジェクト作成・削除IPCハンドラ (ORDER_002 / BACKLOG_001) ===

  /**
   * プロジェクト作成
   */
  ipcMain.handle(
    'project:create-project',
    async (_event, projectId: string, name?: string): Promise<{
      success: boolean;
      project?: object;
      error?: string;
    }> => {
      console.log(`[Project IPC] プロジェクト作成リクエスト: ${projectId}`);
      try {
        const aipmDbService = getAipmDbService();
        const result = await aipmDbService.createProject(projectId, name);
        if (result.success) {
          // メニュー更新通知を送信
          const windows = BrowserWindow.getAllWindows();
          windows.forEach((win) => {
            if (!win.isDestroyed()) {
              win.webContents.send('menu:update');
            }
          });
        }
        return result;
      } catch (error) {
        console.error('[Project IPC] プロジェクト作成エラー:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
  );

  /**
   * プロジェクト削除
   */
  ipcMain.handle(
    'project:delete-project',
    async (_event, projectId: string, force?: boolean): Promise<{
      success: boolean;
      deletedCounts?: { orders: number; tasks: number; backlogs: number };
      error?: string;
    }> => {
      console.log(`[Project IPC] プロジェクト削除リクエスト: ${projectId} (force=${force})`);
      try {
        const aipmDbService = getAipmDbService();
        const result = await aipmDbService.deleteProject(projectId, force);
        if (result.success) {
          // メニュー更新通知を送信
          const windows = BrowserWindow.getAllWindows();
          windows.forEach((win) => {
            if (!win.isDestroyed()) {
              win.webContents.send('menu:update');
            }
          });
        }
        return result;
      } catch (error) {
        console.error('[Project IPC] プロジェクト削除エラー:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
  );

  console.log('[Project] Project create/delete IPC handlers registered (ORDER_002 / BACKLOG_001)');

  // === プロジェクト紹介ページ生成・エクスポートIPCハンドラ (ORDER_021 / TASK_067) ===

  /**
   * プロジェクト紹介ページHTML生成
   * generate_page.py を spawn で呼び出してHTMLを返す
   */
  ipcMain.handle(
    'generate-project-page',
    async (_event, projectId: string): Promise<{
      success: boolean;
      html?: string;
      error?: string;
    }> => {
      console.log(`[Project IPC] プロジェクト紹介ページ生成: ${projectId}`);
      try {
        const configService = getConfigService();
        const backendPath = configService.getBackendPath();
        if (!backendPath) {
          return { success: false, error: 'Backend path not configured' };
        }

        const scriptPath = path.join(backendPath, 'project', 'generate_page.py');
        if (!fs.existsSync(scriptPath)) {
          return { success: false, error: `generate_page.py not found: ${scriptPath}` };
        }

        const { stdout, stderr } = await execFileAsync(
          'python',
          [scriptPath, projectId, '--json'],
          { cwd: path.dirname(scriptPath), timeout: 60000 }
        );

        if (stderr) {
          console.warn('[Project IPC] generate_page.py stderr:', stderr);
        }

        const result = JSON.parse(stdout);
        if (!result.success) {
          return { success: false, error: result.error || 'Unknown error' };
        }
        return { success: true, html: result.html };
      } catch (error) {
        console.error('[Project IPC] プロジェクト紹介ページ生成エラー:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
  );

  /**
   * プロジェクト紹介ページHTMLファイルエクスポート
   * dialogでファイル保存先を選択し、generate_page.py の出力を保存する
   */
  ipcMain.handle(
    'export-project-page',
    async (_event, projectId: string): Promise<{
      success: boolean;
      filePath?: string;
      canceled?: boolean;
      error?: string;
    }> => {
      console.log(`[Project IPC] プロジェクト紹介ページエクスポート: ${projectId}`);
      try {
        // ファイル保存先をdialogで選択
        const { canceled, filePath: savePath } = await dialog.showSaveDialog({
          title: 'プロジェクト紹介ページを保存',
          defaultPath: `${projectId}_introduction.html`,
          filters: [{ name: 'HTML Files', extensions: ['html'] }],
        });

        if (canceled || !savePath) {
          return { success: false, canceled: true };
        }

        // generate_page.py を呼び出してHTMLを生成
        const configService = getConfigService();
        const backendPath = configService.getBackendPath();
        if (!backendPath) {
          return { success: false, error: 'Backend path not configured' };
        }

        const scriptPath = path.join(backendPath, 'project', 'generate_page.py');
        if (!fs.existsSync(scriptPath)) {
          return { success: false, error: `generate_page.py not found: ${scriptPath}` };
        }

        const { stdout, stderr } = await execFileAsync(
          'python',
          [scriptPath, projectId, '--json'],
          { cwd: path.dirname(scriptPath), timeout: 60000 }
        );

        if (stderr) {
          console.warn('[Project IPC] generate_page.py stderr:', stderr);
        }

        const result = JSON.parse(stdout);
        if (!result.success) {
          return { success: false, error: result.error || 'Failed to generate page' };
        }

        // HTMLファイルを保存
        fs.writeFileSync(savePath, result.html, { encoding: 'utf-8' });
        console.log(`[Project IPC] エクスポート完了: ${savePath}`);
        return { success: true, filePath: savePath };
      } catch (error) {
        console.error('[Project IPC] プロジェクト紹介ページエクスポートエラー:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
  );

  console.log('[Project] Project page generation IPC handlers registered (ORDER_021 / TASK_067)');

  console.log('[Project] IPC handlers registered');
}

/**
 * アプリケーション終了時のクリーンアップ
 */
export function cleanupProject(): void {
  const projectService = getProjectService();
  projectService.stopListening();
  projectService.clearCache();

  // リフレッシュサービスの停止 (TASK_256)
  const refreshService = getRefreshService();
  refreshService.stop();
  console.log('[Project] Cleanup completed');
}
