/**
 * DashboardService - dashboard.py呼び出しサービス
 *
 * ORDER_020で完�Eしたdashboard.pyをElectron UIから呼び出すサービス、E
 * ダチE��ュボ�EドコンチE��ストおよ�Eバックログ一覧を取得する、E
 *
 * @module DashboardService
 * @created 2026-02-02
 * @order ORDER_021
 * @task TASK_322
 */

import { spawn, SpawnOptions } from 'child_process';
import * as path from 'path';

// =============================================================================
// 型定義
// =============================================================================

/**
 * 健康状慁E
 */
export type HealthStatus = 'healthy' | 'warning' | 'critical' | 'unknown';

/**
 * プロジェクト健康状態データ
 */
export interface ProjectHealthData {
  projectId: string;
  projectName: string;
  status: HealthStatus;
  currentOrderId?: string;
  currentOrderTitle?: string;
  orderStatus?: string;
  totalTasks: number;
  completedTasks: number;
  inProgressTasks: number;
  blockedTasks: number;
  reworkTasks: number;
  completionRate: number;
  completionRatePercent: number;
  pendingReviews: number;
  openEscalations: number;
  blockedRatio: number;
  blockedRatioPercent: number;
  lastActivity?: string;
}

/**
 * エスカレーション雁E��E��マリ
 */
export interface EscalationSummary {
  totalOpen: number;
  totalResolvedToday: number;
  oldestOpenDays: number;
  byProject: Record<string, number>;
  recentEscalations: Array<{
    id: number;
    taskId: string;
    projectId: string;
    title: string;
    status: string;
    createdAt: string;
    daysOpen: number;
  }>;
}

/**
 * 承認征E��雁E��E��マリ
 */
export interface PendingReviewSummary {
  totalPending: number;
  totalInReview: number;
  p0Count: number;
  p1Count: number;
  p2Count: number;
  byProject: Record<string, number>;
  oldestPendingHours: number;
  pendingItems: Array<{
    id: number;
    taskId: string;
    projectId: string;
    status: string;
    priority: string;
    submittedAt: string;
    reviewer?: string;
    taskTitle: string;
    hoursPending: number;
  }>;
}

/**
 * バックログ雁E��E��マリ
 */
export interface BacklogSummary {
  totalItems: number;
  todoCount: number;
  inProgressCount: number;
  highPriorityCount: number;
  byProject: Record<string, number>;
  byCategory: Record<string, number>;
  byPriority: Record<string, number>;
  byStatus: Record<string, number>;
  recentItems: Array<{
    id: string;
    projectId: string;
    title: string;
    priority: string;
    status: string;
    createdAt: string;
  }>;
  filteredItems: Array<{
    id: string;
    projectId: string;
    title: string;
    priority: string;
    status: string;
    createdAt: string;
  }>;
  appliedFilters: {
    priority?: string[];
    status?: string[];
    project?: string;
  };
}

/**
 * ダチE��ュボ�EドコンチE��スチE
 */
export interface DashboardContext {
  projects: ProjectHealthData[];
  escalationSummary: EscalationSummary;
  reviewSummary: PendingReviewSummary;
  backlogSummary: BacklogSummary;
  totalProjects: number;
  healthyProjects: number;
  warningProjects: number;
  criticalProjects: number;
  renderDate: string;
  renderTime: string;
}

/**
 * バックログフィルタ
 */
export interface BacklogFilters {
  priority?: ('High' | 'Medium' | 'Low')[];
  status?: string[];
  projectId?: string;
  sortBy?: 'priority' | 'createdAt' | 'status' | 'sortOrder';
  sortOrder?: 'asc' | 'desc';
}

/**
 * バックログ頁E���E�ERDER_032で拡張: ORDER紐付け惁E��追加�E�E
 */
export interface BacklogItem {
  id: string;
  projectId: string;
  title: string;
  description?: string;
  priority: 'High' | 'Medium' | 'Low';
  status: string;
  category?: string;
  relatedOrderId?: string;
  createdAt: string;
  updatedAt?: string;
  // ORDER_032追加: ORDER紐付け惁E��
  orderTitle?: string;
  orderStatus?: string;
  orderProjectId?: string;
  totalTasks?: number;
  completedTasks?: number;
  progressPercent?: number;
  // ORDER_106追加: sort_order�E�数値優先度�E�E
  sortOrder?: number;
}

/**
 * サービスエラー
 */
export class DashboardServiceError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly details?: unknown
  ) {
    super(message);
    this.name = 'DashboardServiceError';
  }
}

// =============================================================================
// 冁E��ヘルパ�E関数
// =============================================================================

/**
 * Python snake_case をTypeScript camelCaseに変換
 */
function snakeToCamel(str: string): string {
  return str.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
}

/**
 * オブジェクト�EキーをcamelCaseに変換�E��E帰皁E��E
 */
function convertKeysToCamelCase<T>(obj: unknown): T {
  if (Array.isArray(obj)) {
    return obj.map(item => convertKeysToCamelCase(item)) as T;
  }
  if (obj !== null && typeof obj === 'object') {
    const converted: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
      const camelKey = snakeToCamel(key);
      converted[camelKey] = convertKeysToCamelCase(value);
    }
    return converted as T;
  }
  return obj as T;
}

// =============================================================================
// DashboardService クラス
// =============================================================================

/**
 * ダチE��ュボ�Eドサービス
 *
 * dashboard.pyを呼び出してダチE��ュボ�Eドデータを取得する、E
 *
 * @example
 * ```typescript
 * const service = new DashboardService('/path/to/AI_PM');
 *
 * // ダチE��ュボ�EドコンチE��スト取征E
 * const context = await service.getDashboardContext();
 *
 * // バックログ一覧取得（フィルタ付き�E�E
 * const backlogs = await service.getAllBacklogs({
 *   priority: ['High'],
 *   status: ['TODO'],
 * });
 * ```
 */
export class DashboardService {
  private readonly aiPmRoot: string;
  private readonly pythonPath: string;
  private readonly scriptPath: string;

  /**
   * コンストラクタ
   *
   * @param aiPmRoot - AI PM Frameworkのルートディレクトリパス
   * @param pythonPath - Pythonインタープリタのパス�E�デフォルチE 'python'�E�E
   */
  constructor(aiPmRoot: string, pythonPath: string = 'python') {
    this.aiPmRoot = aiPmRoot;
    this.pythonPath = pythonPath;
    // NOTE: v2移行後、scripts/aipm-db は backend に統合
    this.scriptPath = path.join(
      aiPmRoot,
      'backend',
      'render',
      'dashboard.py'
    );
  }

  /**
   * ダチE��ュボ�EドコンチE��ストを取征E
   *
   * @param includeInactive - 非アクチE��ブ�Eロジェクトを含めるか（デフォルチE false�E�E
   * @returns ダチE��ュボ�EドコンチE��スチE
   * @throws DashboardServiceError - スクリプト実行エラー晁E
   */
  async getDashboardContext(
    includeInactive: boolean = false
  ): Promise<DashboardContext> {
    const args = ['--json'];
    if (includeInactive) {
      args.push('--all');
    }

    const result = await this.runDashboardScript(args);
    return this.parseDashboardContext(result);
  }

  /**
   * 全プロジェクト�Eバックログを取得（フィルタ・ソート対応！E
   *
   * @param filters - バックログフィルタ
   * @returns バックログ頁E��リスチE
   * @throws DashboardServiceError - スクリプト実行エラー晁E
   */
  async getAllBacklogs(filters?: BacklogFilters): Promise<BacklogItem[]> {
    // backlog/list.py を使用して全件取征E
    // NOTE: v2移行後、scripts/aipm-db は backend に統合
    const scriptPath = path.join(
      this.aiPmRoot,
      'backend',
      'backlog',
      'list.py'
    );

    const args: string[] = ['--json'];

    // プロジェクトフィルタ
    if (filters?.projectId) {
      args.unshift(filters.projectId);
    }

    // 優先度フィルタ�E�褁E��値はスペ�Eス区刁E��で個別引数として渡す！E
    if (filters?.priority && filters.priority.length > 0) {
      args.push('--priority', ...filters.priority);
    }

    // スチE�Eタスフィルタ�E�褁E��値はスペ�Eス区刁E��で個別引数として渡す！E
    if (filters?.status && filters.status.length > 0) {
      args.push('--status', ...filters.status);
    }

    console.log('[DashboardService] getAllBacklogs called with filters:', filters);
    console.log('[DashboardService] Script path:', scriptPath);
    console.log('[DashboardService] Args:', args);

    return new Promise((resolve, reject) => {
      const spawnOptions: SpawnOptions = {
        cwd: this.aiPmRoot,
        env: {
          ...process.env,
          PYTHONIOENCODING: 'utf-8',
        },
        shell: process.platform === 'win32',
      };

      console.log('[DashboardService] Spawning python with args:', [scriptPath, ...args]);
      const proc = spawn(this.pythonPath, [scriptPath, ...args], spawnOptions);

      let stdout = '';
      let stderr = '';

      proc.stdout?.on('data', (data: Buffer) => {
        stdout += data.toString('utf-8');
      });

      proc.stderr?.on('data', (data: Buffer) => {
        stderr += data.toString('utf-8');
      });

      proc.on('error', (error: Error) => {
        console.error('[DashboardService] backlog/list.py error:', error);
        resolve([]);
      });

      proc.on('close', (code: number | null) => {
        console.log('[DashboardService] Process closed with code:', code);
        console.log('[DashboardService] stdout length:', stdout.length);
        console.log('[DashboardService] stderr:', stderr || '(empty)');
        if (code === 0) {
          try {
            const data = JSON.parse(stdout);
            console.log('[DashboardService] Parsed data success:', data.success, 'items count:', data.items?.length);
            if (data.success && Array.isArray(data.items)) {
              const items: BacklogItem[] = data.items.map((item: {
                id: string;
                project_id: string;
                title: string;
                description?: string;
                priority: string;
                status: string;
                related_order_id?: string;
                created_at: string;
                updated_at?: string;
                // ORDER_032追加: ORDER紐付け惁E��
                order_title?: string;
                order_status?: string;
                order_project_id?: string;
                total_tasks?: number;
                completed_tasks?: number;
                progress_percent?: number;
                // ORDER_106追加: sort_order
                sort_order?: number;
              }) => ({
                id: item.id,
                projectId: item.project_id,
                title: item.title,
                description: item.description,
                priority: item.priority as 'High' | 'Medium' | 'Low',
                status: item.status,
                relatedOrderId: item.related_order_id,
                createdAt: item.created_at,
                updatedAt: item.updated_at,
                // ORDER_032追加: ORDER紐付け惁E��
                orderTitle: item.order_title,
                orderStatus: item.order_status,
                orderProjectId: item.order_project_id,
                totalTasks: item.total_tasks,
                completedTasks: item.completed_tasks,
                progressPercent: item.progress_percent,
                // ORDER_106追加: sort_order
                sortOrder: item.sort_order,
              }));
              resolve(items);
            } else {
              console.error('[DashboardService] Invalid backlog data:', data);
              resolve([]);
            }
          } catch (e) {
            console.error('[DashboardService] JSON parse error:', e, stdout);
            resolve([]);
          }
        } else {
          console.error('[DashboardService] backlog/list.py failed:', stderr);
          resolve([]);
        }
      });

      // タイムアウト設定！E5秒！E
      setTimeout(() => {
        proc.kill('SIGTERM');
        resolve([]);
      }, 15000);
    });
  }

  /**
   * dashboard.pyスクリプトを実衁E
   *
   * @param args - コマンドライン引数
   * @returns 標準�E力！ESON斁E���E�E�E
   * @throws DashboardServiceError - 実行エラー晁E
   */
  private async runDashboardScript(args: string[]): Promise<string> {
    return new Promise((resolve, reject) => {
      const spawnOptions: SpawnOptions = {
        cwd: this.aiPmRoot,
        env: {
          ...process.env,
          PYTHONIOENCODING: 'utf-8',
        },
        shell: process.platform === 'win32',
      };

      const proc = spawn(
        this.pythonPath,
        [this.scriptPath, ...args],
        spawnOptions
      );

      let stdout = '';
      let stderr = '';

      proc.stdout?.on('data', (data: Buffer) => {
        stdout += data.toString('utf-8');
      });

      proc.stderr?.on('data', (data: Buffer) => {
        stderr += data.toString('utf-8');
      });

      proc.on('error', (error: Error) => {
        reject(
          new DashboardServiceError(
            `Failed to spawn dashboard.py: ${error.message}`,
            'SPAWN_ERROR',
            error
          )
        );
      });

      proc.on('close', (code: number | null) => {
        if (code === 0) {
          resolve(stdout);
        } else {
          reject(
            new DashboardServiceError(
              `dashboard.py exited with code ${code}: ${stderr}`,
              'SCRIPT_ERROR',
              { code, stderr }
            )
          );
        }
      });

      // タイムアウト設定！E0刁E��！ERDER_084: タイムアウト値延長�E�E
      const timeout = setTimeout(() => {
        proc.kill('SIGTERM');
        reject(
          new DashboardServiceError(
            'dashboard.py execution timed out',
            'TIMEOUT_ERROR'
          )
        );
      }, 1800000);

      proc.on('close', () => clearTimeout(timeout));
    });
  }

  /**
   * JSON出力をDashboardContextにパ�Eス
   *
   * @param jsonStr - JSON斁E���E
   * @returns DashboardContext
   * @throws DashboardServiceError - パ�Eスエラー晁E
   */
  /**
   * 全アクティブプロジェクトのBACKLOGをreorder（sort_order再計算）
   *
   * アプリ起動時に呼び出し、sort_orderを最新状態に整理する
   * バックグラウンドで実行し、失敗してもアプリ動作には影響しない
   *
   * @param projectNames - 対象プロジェクト名の配列
   * @returns reorder結果の配列
   */
  async reorderAllBacklogs(projectNames: string[]): Promise<Array<{ project: string; success: boolean; message: string }>> {
    // NOTE: v2移行後、scripts/aipm-db は backend に統合
    const reorderScript = path.join(
      this.aiPmRoot,
      'backend',
      'backlog',
      'reorder.py'
    );

    const results: Array<{ project: string; success: boolean; message: string }> = [];

    for (const projectName of projectNames) {
      try {
        const result = await new Promise<string>((resolve, reject) => {
          const spawnOptions: SpawnOptions = {
            cwd: this.aiPmRoot,
            env: {
              ...process.env,
              PYTHONIOENCODING: 'utf-8',
            },
            shell: process.platform === 'win32',
          };

          const proc = spawn(this.pythonPath, [reorderScript, projectName, '--json'], spawnOptions);

          let stdout = '';
          let stderr = '';

          proc.stdout?.on('data', (data: Buffer) => {
            stdout += data.toString('utf-8');
          });

          proc.stderr?.on('data', (data: Buffer) => {
            stderr += data.toString('utf-8');
          });

          proc.on('error', (error: Error) => {
            reject(error);
          });

          proc.on('close', (code: number | null) => {
            if (code === 0) {
              resolve(stdout);
            } else {
              reject(new Error(`reorder.py exited with code ${code}: ${stderr}`));
            }
          });

          // 30秒タイムアウト
          setTimeout(() => {
            try { proc.kill(); } catch { /* ignore */ }
            reject(new Error('reorder.py timed out'));
          }, 30000);
        });

        const data = JSON.parse(result);
        results.push({
          project: projectName,
          success: data.success ?? false,
          message: data.message ?? '',
        });
        console.log(`[DashboardService] reorder ${projectName}: ${data.message}`);
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        console.error(`[DashboardService] reorder ${projectName} failed:`, msg);
        results.push({
          project: projectName,
          success: false,
          message: msg,
        });
      }
    }

    return results;
  }

  private parseDashboardContext(jsonStr: string): DashboardContext {
    try {
      const raw = JSON.parse(jsonStr);
      return convertKeysToCamelCase<DashboardContext>(raw);
    } catch (error) {
      throw new DashboardServiceError(
        `Failed to parse dashboard output: ${error instanceof Error ? error.message : String(error)}`,
        'PARSE_ERROR',
        { jsonStr: jsonStr.slice(0, 500) }
      );
    }
  }
}

// =============================================================================
// チE��ォルトエクスポ�EチE
// =============================================================================

export default DashboardService;
