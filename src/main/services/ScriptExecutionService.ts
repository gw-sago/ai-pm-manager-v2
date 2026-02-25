/**
 * ScriptExecutionService
 *
 * Pythonスクリプトをバックグラウンドで実行するサービス
 * ORDER_039: ワンクリック自動実行機能
 * ORDER_041: aipm-auto スクリプト統合リファクタリング
 * ORDER_046: 親スクリプト活用版への移行
 *
 * 機能:
 * - 親スクリプト経由でのPM/Worker/Review処理（ORDER_046）
 * - aipm-auto Pythonスクリプト経由でのclaude -p実行（フォールバック）
 * - orchestrator.pyによるWorker→Review自動サイクル（フォールバック）
 * - 実行状態管理（実行中/完了/エラー）
 * - 標準出力/エラー出力のキャプチャ
 * - 実行結果の構造化
 */

import { spawn, exec, ChildProcess } from 'child_process';
import * as path from 'node:path';
import * as fs from 'node:fs';
import * as fsPromises from 'node:fs/promises';
import { EventEmitter } from 'events';
import { watch, type FSWatcher } from 'chokidar';
import { getConfigService } from './ConfigService';

// =============================================================================
// 型定義
// =============================================================================

/**
 * スクリプト実行結果
 */
export interface ExecutionResult {
  success: boolean;
  /** 実行ID（一意識別子） */
  executionId: string;
  /** 実行タイプ */
  type: 'pm' | 'worker' | 'review';
  /** プロジェクトID */
  projectId: string;
  /** バックログID または ORDER ID */
  targetId: string;
  /** 標準出力 */
  stdout: string;
  /** 標準エラー出力 */
  stderr: string;
  /** 終了コード */
  exitCode: number | null;
  /** エラーメッセージ（失敗時） */
  error?: string;
  /** 開始時刻 */
  startedAt: string;
  /** 完了時刻 */
  completedAt: string;
  /** 実行時間（ミリ秒） */
  durationMs: number;
  /** 完了サイクル数（orchestrator使用時） */
  cyclesCompleted?: number;
  /** 停止理由（orchestrator使用時） */
  stopReason?: string;
}

/**
 * 実行進捗情報
 */
export interface ExecutionProgress {
  /** 実行ID */
  executionId: string;
  /** 実行タイプ */
  type: 'pm' | 'worker' | 'review';
  /** プロジェクトID */
  projectId: string;
  /** ターゲットID */
  targetId: string;
  /** ステータス */
  status: 'running' | 'completed' | 'failed';
  /** 最新の出力行 */
  lastOutput?: string;
  /** 進捗率（0-100、推定） */
  progress?: number;
}

/**
 * 実行中のジョブ情報
 */
interface RunningJob {
  executionId: string;
  type: 'pm' | 'worker' | 'review';
  projectId: string;
  targetId: string;
  process: ChildProcess;
  stdout: string;
  stderr: string;
  startedAt: Date;
}

/**
 * orchestrator.py の出力結果型
 */
interface OrchestratorOutput {
  success: boolean;
  cycles_completed: number;
  stop_reason: string;
  stop_message: string;
  cycle_results: Array<{
    cycle_number: number;
    task_id: string;
    worker_success: boolean;
    review_success: boolean;
    review_outcome: string;
    next_task_id: string | null;
    error_message: string;
  }>;
  total_cost_usd: number;
  started_at: string;
  completed_at: string;
}

/**
 * ORDER_109: PID監視対象プロセス情報
 */
interface MonitoredProcess {
  taskId: string;
  projectId: string;
  logFile: string;
  orderId: string;
}

// =============================================================================
// ORDER_111: Worker ログ関連型定義
// =============================================================================

/**
 * Worker ログファイル情報
 */
export interface WorkerLogFileInfo {
  /** ファイルのフルパス */
  filePath: string;
  /** ファイル名 */
  fileName: string;
  /** タスクID（ファイル名から抽出） */
  taskId: string;
  /** ORDER ID */
  orderId: string;
  /** ステータス（running/success/failed/unknown） */
  status: 'running' | 'success' | 'failed' | 'unknown';
  /** ファイルサイズ（バイト） */
  fileSize: number;
  /** 更新日時（ISO8601） */
  modifiedAt: string;
}

/**
 * Worker ログファイル一覧のページネーション付きレスポンス（ORDER_090）
 */
export interface WorkerLogFileListResponse {
  /** ログファイル情報の配列 */
  items: WorkerLogFileInfo[];
  /** 総件数 */
  totalCount: number;
  /** 取得開始位置 */
  offset: number;
  /** 取得件数上限 */
  limit: number;
}

/**
 * Worker ログ内容
 */
export interface WorkerLogContent {
  /** ログ内容テキスト */
  content: string;
  /** ファイルサイズ（バイト） */
  fileSize: number;
  /** 読み込み位置（バイト） */
  readPosition: number;
}

/**
 * Worker ログ更新イベント
 */
export interface WorkerLogUpdateEvent {
  /** ファイルパス */
  filePath: string;
  /** 追加された内容 */
  appendedContent: string;
  /** ファイルサイズ（バイト） */
  fileSize: number;
  /** 読み込み位置（バイト） */
  readPosition: number;
}

// =============================================================================
// ScriptExecutionService
// =============================================================================

/** 実行履歴の最大保持件数 */
const MAX_HISTORY_ITEMS = 100;

/** デフォルトタイムアウト（ミリ秒） */
const DEFAULT_TIMEOUT_MS = 10 * 60 * 1000; // 10分

/** Worker/Review実行用タイムアウト（ミリ秒）- AI処理は時間がかかるため長めに設定 */
const WORKER_TIMEOUT_MS = 60 * 60 * 1000; // 60分

/**
 * スクリプト実行サービス
 *
 * ORDER_041: aipm-autoスクリプト統合
 * - PM処理: claude_runner.py経由でclaude -pを実行
 * - Worker処理: orchestrator.py経由でWorker→Review自動サイクル
 */
export class ScriptExecutionService extends EventEmitter {
  /** 実行中のジョブ */
  private runningJobs: Map<string, RunningJob> = new Map();

  /** 実行カウンタ（ID生成用） */
  private executionCounter = 0;

  /** 実行履歴（ORDER_040追加） */
  private executionHistory: ExecutionResult[] = [];

  /** ORDER_101: タスクポーリング用タイマー (ORDER_119: setTimeout方式に変更) */
  private pollingTimeout: ReturnType<typeof setTimeout> | null = null;

  /** ORDER_119: ポーリング対象のプロジェクトID・ORDER ID */
  private pollingProjectId: string | null = null;
  private pollingOrderId: string | null = null;

  /** ORDER_119: ポーリング間隔定数（ミリ秒） */
  private static readonly POLLING_FAST_MS = 3000;   // IN_PROGRESSタスク存在時
  private static readonly POLLING_NORMAL_MS = 7000;  // 通常時

  /** ORDER_101: 前回のタスクステータス（変化検知用） */
  private previousTaskStatuses: Map<string, string> = new Map();

  /** ORDER_101 TASK_971: taskStartTimes for timeout detection */
  private taskStartTimes: Map<string, Date> = new Map();

  /** ORDER_109: PID監視対象プロセス (pid -> MonitoredProcess) */
  private monitoredProcesses: Map<number, MonitoredProcess> = new Map();

  /** ORDER_109: PID監視タイマー */
  private pidMonitorInterval: ReturnType<typeof setInterval> | null = null;

  /** ORDER_109: PID監視間隔（ミリ秒） */
  private static readonly PID_MONITOR_INTERVAL_MS = 5000;

  /** ORDER_111: Worker ログファイル監視用 watcher */
  private workerLogWatchers: Map<string, FSWatcher> = new Map();

  /** ORDER_111: Worker ログファイルの前回読み込み位置 */
  private workerLogPositions: Map<string, number> = new Map();

  /** ORDER_090: ログファイルステータスキャッシュ（filePath → {status, mtimeMs}） */
  private logStatusCache: Map<string, { status: 'running' | 'success' | 'failed' | 'unknown'; mtimeMs: number }> = new Map();

  constructor() {
    super();
  }

  /**
   * 実行履歴を取得（ORDER_040追加）
   * @returns 実行履歴（新しい順）
   */
  getExecutionHistory(): ExecutionResult[] {
    return [...this.executionHistory];
  }

  /**
   * 実行履歴をクリア（ORDER_040追加）
   */
  clearExecutionHistory(): void {
    this.executionHistory = [];
  }

  /**
   * 実行結果を履歴に追加（ORDER_040追加）
   */
  private addToHistory(result: ExecutionResult): void {
    // 先頭に追加（新しい順）
    this.executionHistory.unshift(result);
    // 最大件数を超えたら古いものを削除
    if (this.executionHistory.length > MAX_HISTORY_ITEMS) {
      this.executionHistory = this.executionHistory.slice(0, MAX_HISTORY_ITEMS);
    }
  }

  /**
   * AI PM Frameworkのパスを取得（読み書き用: PROJECTS, DB等）
   */
  private getFrameworkPath(): string | null {
    const configService = getConfigService();
    return configService.getActiveFrameworkPath();
  }

  /**
   * バックエンドパスを取得（読み取り専用: Pythonスクリプト）
   * ORDER_159: frameworkPath/backendPath分離
   */
  private getBackendPath(): string | null {
    const configService = getConfigService();
    return configService.getBackendPath();
  }

  /**
   * Pythonコマンドを取得
   */
  private getPythonCommand(): string {
    // ConfigServiceから取得（パッケージ時: python-embed/python.exe、開発時: システムPython）
    return getConfigService().getPythonPath();
  }

  /**
   * 一意の実行IDを生成
   */
  private generateExecutionId(): string {
    this.executionCounter++;
    const timestamp = Date.now();
    return `exec_${timestamp}_${this.executionCounter}`;
  }

  /**
   * aipm-autoスクリプトのパスを取得
   */
  private getAipmAutoPath(scriptName: string): string | null {
    const backendPath = this.getBackendPath();
    if (!backendPath) return null;

    const scriptPath = path.join(backendPath, 'aipm_auto', scriptName);
    return fs.existsSync(scriptPath) ? scriptPath : null;
  }

  /**
   * 親スクリプト（aipm-db配下）のパスを取得
   *
   * ORDER_046: 親スクリプト活用版への移行
   *
   * @param scriptType スクリプトタイプ（pm/worker/review）
   * @returns スクリプトパス（存在しない場合はnull）
   */
  private getParentScriptPath(scriptType: 'pm' | 'worker' | 'review'): string | null {
    const backendPath = this.getBackendPath();
    if (!backendPath) return null;

    // スクリプトタイプに応じたパスを決定（backendPathベース）
    const scriptMap: Record<string, string> = {
      pm: path.join(backendPath, 'pm', 'process_order.py'),
      worker: path.join(backendPath, 'worker', 'execute_task.py'),
      review: path.join(backendPath, 'review', 'process_review.py'),
    };

    const scriptPath = scriptMap[scriptType];
    if (scriptPath && fs.existsSync(scriptPath)) {
      console.log(`[ScriptExecution] Found parent script: ${scriptPath}`);
      return scriptPath;
    }

    console.log(`[ScriptExecution] Parent script not found: ${scriptPath}`);
    return null;
  }

  /**
   * parallel_launcher.pyのパスを取得
   *
   * ORDER_098: 並列Worker起動スクリプト
   */
  private getParallelLauncherPath(): string | null {
    const backendPath = this.getBackendPath();
    if (!backendPath) return null;
    const scriptPath = path.join(backendPath, 'worker', 'parallel_launcher.py');
    if (fs.existsSync(scriptPath)) {
      console.log(`[ScriptExecution] Found parallel_launcher.py: ${scriptPath}`);
      return scriptPath;
    }
    console.log(`[ScriptExecution] parallel_launcher.py not found: ${scriptPath}`);
    return null;
  }

  /**
   * parallel_detector.pyのパスを取得
   *
   * ORDER_098: 並列実行可能タスク検出スクリプト
   */
  private getParallelDetectorPath(): string | null {
    const backendPath = this.getBackendPath();
    if (!backendPath) return null;
    const scriptPath = path.join(backendPath, 'worker', 'parallel_detector.py');
    if (fs.existsSync(scriptPath)) {
      console.log(`[ScriptExecution] Found parallel_detector.py: ${scriptPath}`);
      return scriptPath;
    }
    console.log(`[ScriptExecution] parallel_detector.py not found: ${scriptPath}`);
    return null;
  }

  /**
   * 並列実行可能なタスクを検出
   *
   * ORDER_098 / TASK_957: parallel_detector.pyを呼び出して結果を返す
   */
  async detectParallelTasks(
    projectId: string,
    orderId: string,
    maxTasks?: number
  ): Promise<{
    success: boolean;
    tasks?: Array<{ id: string; title: string; status: string }>;
    error?: string;
  }> {
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) {
      return { success: false, error: 'Framework path not configured' };
    }
    const detectorPath = this.getParallelDetectorPath();
    if (!detectorPath) {
      return { success: false, error: 'parallel_detector.py not found' };
    }
    const pythonCommand = this.getPythonCommand();
    const args = [detectorPath, projectId, orderId, '--json'];
    if (maxTasks) {
      args.push('--max-tasks', String(maxTasks));
    }
    try {
      const result = await this.runPythonScript(pythonCommand, args, frameworkPath, 30000);
      if (!result.success) {
        return { success: false, error: result.error || 'Detection failed' };
      }
      const parsed = this.parseParallelDetectorOutput(result.stdout);
      if (parsed && parsed.tasks) {
        return { success: true, tasks: parsed.tasks };
      }
      return { success: true, tasks: [] };
    } catch (error) {
      console.error('[ScriptExecution] detectParallelTasks error:', error);
      return {
        success: false,
        error: `Detection error: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
  }

  /**
   * parallel_detector.pyの出力をパース
   * ORDER_098 / TASK_958
   */
  private parseParallelDetectorOutput(stdout: string): {
    is_parallel_possible?: boolean;
    parallel_launchable_count?: number;
    tasks?: Array<{ id: string; title: string; status: string }>;
  } | null {
    try {
      const jsonMatch = stdout.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      }
    } catch (e) {
      console.warn('[ScriptExecution] Failed to parse parallel_detector output:', e);
    }
    return null;
  }

  /**
   * PM処理を実行（バックログ→ORDER化→PM処理）
   *
   * ORDER_046: 親スクリプト（process_order.py）を優先的に使用
   * ORDER_041: claude_runner.py経由でclaude -pを実行（フォールバック）
   *
   * 処理フロー:
   * 1. process_order.py が存在する場合 → 親スクリプト経由で実行
   * 2. claude_runner.py が存在する場合 → claude_runner.py経由で実行
   * 3. どちらもない場合 → 直接claude -p実行
   *
   * @param projectId プロジェクトID
   * @param backlogId バックログID
   * @returns 実行結果
   */
  async executePmProcess(
    projectId: string,
    backlogId: string
  ): Promise<ExecutionResult> {
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) {
      return this.createErrorResult('pm', projectId, backlogId, 'Framework path not configured');
    }

    const executionId = this.generateExecutionId();
    const startedAt = new Date();

    // ORDER_046: 親スクリプト（process_order.py）を優先
    const parentScriptPath = this.getParentScriptPath('pm');
    if (parentScriptPath) {
      console.log(`[ScriptExecution] Using parent script (process_order.py) for PM process`);
      return this.executePmViaProcessOrder(projectId, backlogId, executionId, startedAt);
    }

    // フォールバック1: aipm-autoスクリプト経由
    const claudeRunnerPath = this.getAipmAutoPath('claude_runner.py');
    if (claudeRunnerPath) {
      console.log(`[ScriptExecution] Fallback: Using claude_runner.py for PM process`);
      return this.executePmViaClaudeRunner(projectId, backlogId, executionId, startedAt);
    }

    // フォールバック2: 直接claude -p実行
    console.log(`[ScriptExecution] Fallback: Direct claude -p execution`);
    return this.executePmDirect(projectId, backlogId, executionId, startedAt);
  }

  /**
   * PM処理（process_order.py経由）
   *
   * ORDER_046: 親スクリプト活用版
   *
   * 処理手順:
   * 1. backlog/to_order.py でBACKLOGからORDERを作成
   * 2. pm/process_order.py でPM処理（要件定義＋タスク発行）を実行
   */
  private async executePmViaProcessOrder(
    projectId: string,
    backlogId: string,
    executionId: string,
    startedAt: Date
  ): Promise<ExecutionResult> {
    const frameworkPath = this.getFrameworkPath()!;
    const pythonCommand = this.getPythonCommand();

    // ジョブを登録して進捗イベントを発行
    const job: RunningJob = {
      executionId,
      type: 'pm',
      projectId,
      targetId: backlogId,
      process: null as unknown as ChildProcess,
      stdout: '',
      stderr: '',
      startedAt,
    };
    this.runningJobs.set(executionId, job);

    // 開始イベントを発行
    this.emit('progress', {
      executionId,
      type: 'pm',
      projectId,
      targetId: backlogId,
      status: 'running',
      lastOutput: 'PM処理を開始（親スクリプト経由）...',
    } as ExecutionProgress);

    try {
      let orderId: string;
      const backendPath = this.getBackendPath()!;

      // ORDER_091: DB駆動ORDER対応 - ORDER_IDが直接渡された場合はStep1をスキップ
      if (backlogId.startsWith('ORDER_')) {
        // DB駆動ORDER: backlogIdは実際にはORDER ID
        orderId = backlogId;
        console.log(`[ScriptExecution] ========================================`);
        console.log(`[ScriptExecution] Step 1: Skipped (DB-driven ORDER: ${orderId})`);
        console.log(`[ScriptExecution] ========================================`);

        this.emit('progress', {
          executionId,
          type: 'pm',
          projectId,
          targetId: backlogId,
          status: 'running',
          lastOutput: `Step 1: DB駆動ORDER検出、ステータス更新中 (${orderId})...`,
        } as ExecutionProgress);

        // DRAFT/PLANNINGの場合はIN_PROGRESSに遷移
        const updateScript = path.join(backendPath, 'order', 'update.py');
        const updateArgs = [updateScript, projectId, orderId, '--status', 'IN_PROGRESS', '--reason', 'PM処理開始（UI経由）', '--json'];
        const updateResult = await this.runPythonScript(pythonCommand, updateArgs, frameworkPath);
        job.stdout += `[Step 1: order/update.py (DB-driven)]\n${updateResult.stdout}\n`;
        job.stderr += updateResult.stderr;

        // ステータス更新失敗は警告のみ（既にIN_PROGRESSの場合など）
        if (!updateResult.success) {
          console.warn(`[ScriptExecution] Step 1: ORDER status update warning: ${updateResult.stderr}`);
        }

        console.log(`[ScriptExecution] Step 1 complete: Using existing ${orderId}`);
      } else {
        // 従来フロー: BACKLOG_IDからORDER作成
        console.log(`[ScriptExecution] ========================================`);
        console.log(`[ScriptExecution] Step 1: Creating ORDER from ${backlogId} via to_order.py`);
        console.log(`[ScriptExecution] ========================================`);

        this.emit('progress', {
          executionId,
          type: 'pm',
          projectId,
          targetId: backlogId,
          status: 'running',
          lastOutput: `Step 1: ORDER作成中 (${backlogId})...`,
        } as ExecutionProgress);

        const toOrderScript = path.join(backendPath, 'backlog', 'to_order.py');
        const step1Args = [toOrderScript, projectId, backlogId, '--json'];

        const step1Result = await this.runPythonScript(pythonCommand, step1Args, frameworkPath);
        job.stdout += `[Step 1: to_order.py]\n${step1Result.stdout}\n`;
        job.stderr += step1Result.stderr;

        if (!step1Result.success) {
          console.error(`[ScriptExecution] Step 1 failed`);
          this.runningJobs.delete(executionId);
          const result = this.createExecutionResult(
            'pm', projectId, backlogId, executionId, startedAt,
            false, job.stdout, job.stderr, step1Result.exitCode,
            `Step 1 failed: ${step1Result.error || 'Unknown error'}`
          );
          this.addToHistory(result);
          this.emitComplete(result);
          return result;
        }

        // ORDER IDを出力から抽出
        const extractedOrderId = this.extractOrderIdFromJson(step1Result.stdout) ||
                  this.extractOrderIdFromOutput(step1Result.stdout);

        if (!extractedOrderId) {
          console.error(`[ScriptExecution] Failed to extract ORDER ID from output`);
          this.runningJobs.delete(executionId);
          const result = this.createExecutionResult(
            'pm', projectId, backlogId, executionId, startedAt,
            false, job.stdout, job.stderr, 0,
            'Failed to extract ORDER ID from to_order.py output'
          );
          this.addToHistory(result);
          this.emitComplete(result);
          return result;
        }

        orderId = extractedOrderId;
        console.log(`[ScriptExecution] Step 1 complete: Created ${orderId}`);
      }

      // Step 2: pm/process_order.py でPM処理
      console.log(`[ScriptExecution] ========================================`);
      console.log(`[ScriptExecution] Step 2: Running PM process for ${orderId} via process_order.py`);
      console.log(`[ScriptExecution] ========================================`);

      this.emit('progress', {
        executionId,
        type: 'pm',
        projectId,
        targetId: backlogId,
        status: 'running',
        lastOutput: `Step 2: PM処理実行中 (${orderId})...`,
      } as ExecutionProgress);

      const orderNumber = orderId.replace('ORDER_', '');
      const processOrderScript = this.getParentScriptPath('pm')!;
      const step2Args = [processOrderScript, projectId, orderNumber, '--json', '--verbose'];

      // Step2の詳細ログをリアルタイムでUIに通知
      const step2Result = await this.runPythonScript(
        pythonCommand,
        step2Args,
        frameworkPath,
        DEFAULT_TIMEOUT_MS,
        (line: string) => {
          // process_order.pyのログ行をパースしてUIに通知
          // 例: "2026-02-05 18:22:59 [INFO] [step2_1_goal] start: 01_GOAL.md作成開始"
          const match = line.match(/\[INFO\]\s*\[([^\]]+)\]\s*(\w+):\s*(.*)/);
          if (match) {
            const [, step, , detail] = match;
            this.emit('progress', {
              executionId,
              type: 'pm',
              projectId,
              targetId: backlogId,
              status: 'running',
              lastOutput: `Step 2: ${step} - ${detail}`,
            } as ExecutionProgress);
          }
        }
      );
      job.stdout += `\n[Step 2: process_order.py]\n${step2Result.stdout}\n`;
      job.stderr += step2Result.stderr;

      console.log(`[ScriptExecution] Step 2 complete: success=${step2Result.success}`);

      // ジョブを削除
      this.runningJobs.delete(executionId);

      const result = this.createExecutionResult(
        'pm', projectId, orderId, executionId, startedAt,
        step2Result.success, job.stdout, job.stderr,
        step2Result.exitCode, step2Result.error
      );

      this.addToHistory(result);
      this.emitComplete(result);
      return result;

    } catch (error) {
      console.error(`[ScriptExecution] PM process error:`, error);
      this.runningJobs.delete(executionId);
      const result = this.createExecutionResult(
        'pm', projectId, backlogId, executionId, startedAt,
        false, job.stdout, job.stderr, null,
        `Unexpected error: ${error instanceof Error ? error.message : String(error)}`
      );
      this.addToHistory(result);
      this.emitComplete(result);
      return result;
    }
  }

  /**
   * Pythonスクリプトを実行
   *
   * ORDER_046: 共通のPythonスクリプト実行ヘルパー
   */
  private async runPythonScript(
    pythonCommand: string,
    args: string[],
    cwd: string,
    timeoutMs: number = DEFAULT_TIMEOUT_MS,
    onOutput?: (line: string) => void
  ): Promise<{ success: boolean; stdout: string; stderr: string; exitCode: number | null; error?: string }> {
    console.log(`[ScriptExecution] Running: ${pythonCommand} ${args.join(' ')}`);

    return new Promise((resolve) => {
      let stdout = '';
      let stderr = '';
      let resolved = false;

      const childProcess = spawn(pythonCommand, args, {
        cwd,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        shell: true,
        windowsHide: true,
      });

      const timeout = setTimeout(() => {
        if (!resolved) {
          console.error(`[ScriptExecution] Script timed out after ${timeoutMs}ms`);
          try {
            childProcess.kill('SIGTERM');
          } catch (e) {
            console.error(`[ScriptExecution] Failed to kill process:`, e);
          }
          resolved = true;
          resolve({
            success: false,
            stdout,
            stderr,
            exitCode: null,
            error: `Script timed out after ${timeoutMs / 1000} seconds`,
          });
        }
      }, timeoutMs);

      if (childProcess.stdout) {
        childProcess.stdout.setEncoding('utf-8');
        childProcess.stdout.on('data', (data: string) => {
          stdout += data;
          const logOutput = data.length > 500 ? data.substring(0, 500) + '...' : data;
          console.log(`[Python stdout] ${logOutput.trim()}`);
          // コールバックがあれば各行を通知
          if (onOutput) {
            const lines = data.split('\n').filter(line => line.trim());
            lines.forEach(line => onOutput(line));
          }
        });
      }

      if (childProcess.stderr) {
        childProcess.stderr.setEncoding('utf-8');
        childProcess.stderr.on('data', (data: string) => {
          stderr += data;
          console.warn(`[Python stderr] ${data.trim()}`);
        });
      }

      childProcess.on('close', (exitCode) => {
        clearTimeout(timeout);
        if (resolved) return;
        resolved = true;

        console.log(`[ScriptExecution] Script completed - exitCode: ${exitCode}`);
        resolve({
          success: exitCode === 0,
          stdout,
          stderr,
          exitCode,
          error: exitCode !== 0 ? `Script exited with code ${exitCode}` : undefined,
        });
      });

      childProcess.on('error', (error) => {
        clearTimeout(timeout);
        if (resolved) return;
        resolved = true;

        console.error(`[ScriptExecution] Script error:`, error);
        resolve({
          success: false,
          stdout,
          stderr,
          exitCode: null,
          error: `Failed to run script: ${error.message}`,
        });
      });
    });
  }

  /**
   * JSON出力からORDER IDを抽出
   *
   * ORDER_046: to_order.pyのJSON出力に対応
   */
  private extractOrderIdFromJson(output: string): string | null {
    try {
      // JSON部分を抽出（複数行の出力から最後のJSON objectを探す）
      const jsonMatch = output.match(/\{[^{}]*"id"\s*:\s*"ORDER_\d+"[^{}]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        if (parsed.id && parsed.id.startsWith('ORDER_')) {
          return parsed.id;
        }
      }
    } catch (e) {
      console.warn(`[ScriptExecution] Failed to parse JSON for ORDER ID:`, e);
    }
    return null;
  }

  /**
   * PM処理（claude_runner.py経由）
   */
  private async executePmViaClaudeRunner(
    projectId: string,
    backlogId: string,
    executionId: string,
    startedAt: Date
  ): Promise<ExecutionResult> {
    const frameworkPath = this.getFrameworkPath()!;

    // ジョブを登録して進捗イベントを発行
    const job: RunningJob = {
      executionId,
      type: 'pm',
      projectId,
      targetId: backlogId,
      process: null as unknown as ChildProcess, // PM処理は複数プロセスを使うため
      stdout: '',
      stderr: '',
      startedAt,
    };
    this.runningJobs.set(executionId, job);

    // 開始イベントを発行
    this.emit('progress', {
      executionId,
      type: 'pm',
      projectId,
      targetId: backlogId,
      status: 'running',
      lastOutput: 'PM処理を開始...',
    } as ExecutionProgress);

    // Step 1: /aipm-backlog-to-order でORDER作成
    console.log(`[ScriptExecution] ========================================`);
    console.log(`[ScriptExecution] Step 1: Creating ORDER from ${backlogId}`);
    console.log(`[ScriptExecution] ========================================`);

    // Step 1 進捗を発行
    this.emit('progress', {
      executionId,
      type: 'pm',
      projectId,
      targetId: backlogId,
      status: 'running',
      lastOutput: `Step 1: ORDER作成中 (${backlogId})...`,
    } as ExecutionProgress);

    const step1StartTime = Date.now();
    const toOrderResult = await this.runPythonClaudeRunner(
      `/aipm-backlog-to-order ${projectId} ${backlogId}`,
      frameworkPath
    );
    const step1Duration = Date.now() - step1StartTime;

    console.log(`[ScriptExecution] Step 1 completed in ${step1Duration}ms`);
    console.log(`[ScriptExecution] Step 1 success: ${toOrderResult.success}`);
    console.log(`[ScriptExecution] Step 1 exitCode: ${toOrderResult.exitCode}`);

    if (!toOrderResult.success) {
      console.error(`[ScriptExecution] Step 1 failed - aborting PM process`);
      console.error(`[ScriptExecution] Step 1 error: ${toOrderResult.error}`);
      this.runningJobs.delete(executionId);
      const result = this.createExecutionResult(
        'pm', projectId, backlogId, executionId, startedAt,
        false, toOrderResult.stdout, toOrderResult.stderr,
        toOrderResult.exitCode, toOrderResult.error
      );
      this.addToHistory(result);
      this.emitComplete(result);
      return result;
    }

    // ORDER IDを出力から抽出
    const orderId = this.extractOrderIdFromOutput(toOrderResult.stdout);
    console.log(`[ScriptExecution] Extracted ORDER ID: ${orderId}`);

    if (!orderId) {
      console.error(`[ScriptExecution] Failed to extract ORDER ID from output`);
      console.error(`[ScriptExecution] Output was: ${toOrderResult.stdout.substring(0, 500)}...`);
      this.runningJobs.delete(executionId);
      const result = this.createExecutionResult(
        'pm', projectId, backlogId, executionId, startedAt,
        false, toOrderResult.stdout, toOrderResult.stderr,
        0, 'Failed to extract ORDER ID from output'
      );
      this.addToHistory(result);
      this.emitComplete(result);
      return result;
    }

    console.log(`[ScriptExecution] ========================================`);
    console.log(`[ScriptExecution] Step 1 complete: Created ${orderId}`);
    console.log(`[ScriptExecution] ========================================`);

    // Step 2 進捗を発行
    this.emit('progress', {
      executionId,
      type: 'pm',
      projectId,
      targetId: backlogId,
      status: 'running',
      lastOutput: `Step 2: PM処理実行中 (${orderId})...`,
    } as ExecutionProgress);

    // Step 2: /aipm-pm でPM処理実行
    console.log(`[ScriptExecution] ========================================`);
    console.log(`[ScriptExecution] Step 2: Running PM process for ${orderId}`);
    console.log(`[ScriptExecution] ========================================`);

    const orderNumber = orderId.replace('ORDER_', '');
    const step2StartTime = Date.now();
    const pmResult = await this.runPythonClaudeRunner(
      `/aipm-pm ${projectId} ${orderNumber}`,
      frameworkPath
    );
    const step2Duration = Date.now() - step2StartTime;

    console.log(`[ScriptExecution] Step 2 completed in ${step2Duration}ms`);
    console.log(`[ScriptExecution] Step 2 success: ${pmResult.success}`);
    console.log(`[ScriptExecution] Step 2 exitCode: ${pmResult.exitCode}`);

    // ジョブを削除
    this.runningJobs.delete(executionId);

    const result = this.createExecutionResult(
      'pm', projectId, orderId, executionId, startedAt,
      pmResult.success,
      `[Step 1: /aipm-backlog-to-order]\n${toOrderResult.stdout}\n\n[Step 2: /aipm-pm]\n${pmResult.stdout}`,
      `${toOrderResult.stderr}\n${pmResult.stderr}`,
      pmResult.exitCode, pmResult.error
    );

    this.addToHistory(result);
    this.emitComplete(result);
    return result;
  }

  /**
   * PM処理（直接claude -p実行、フォールバック用）
   */
  private async executePmDirect(
    projectId: string,
    backlogId: string,
    executionId: string,
    startedAt: Date
  ): Promise<ExecutionResult> {
    const frameworkPath = this.getFrameworkPath()!;

    // Step 1: /aipm-backlog-to-order でORDER作成
    console.log(`[ScriptExecution] Step 1: Creating ORDER from ${backlogId} via direct claude -p`);

    const toOrderResult = await this.runClaudeCommand(
      `/aipm-backlog-to-order ${projectId} ${backlogId}`,
      frameworkPath
    );

    if (!toOrderResult.success) {
      const result = this.createExecutionResult(
        'pm', projectId, backlogId, executionId, startedAt,
        false, toOrderResult.stdout, toOrderResult.stderr,
        toOrderResult.exitCode, toOrderResult.error
      );
      this.addToHistory(result);
      this.emitComplete(result);
      return result;
    }

    // ORDER IDを出力から抽出
    const orderId = this.extractOrderIdFromOutput(toOrderResult.stdout);
    if (!orderId) {
      const result = this.createExecutionResult(
        'pm', projectId, backlogId, executionId, startedAt,
        false, toOrderResult.stdout, toOrderResult.stderr,
        0, 'Failed to extract ORDER ID from output'
      );
      this.addToHistory(result);
      this.emitComplete(result);
      return result;
    }

    console.log(`[ScriptExecution] Step 1 complete: Created ${orderId}`);

    // Step 2: /aipm-pm でPM処理実行
    console.log(`[ScriptExecution] Step 2: Running PM process for ${orderId}`);

    const orderNumber = orderId.replace('ORDER_', '');
    const pmResult = await this.runClaudeCommand(
      `/aipm-pm ${projectId} ${orderNumber}`,
      frameworkPath
    );

    const result = this.createExecutionResult(
      'pm', projectId, orderId, executionId, startedAt,
      pmResult.success,
      `[Step 1: /aipm-backlog-to-order]\n${toOrderResult.stdout}\n\n[Step 2: /aipm-pm]\n${pmResult.stdout}`,
      `${toOrderResult.stderr}\n${pmResult.stderr}`,
      pmResult.exitCode, pmResult.error
    );

    this.addToHistory(result);
    this.emitComplete(result);
    return result;
  }

  /**
   * Claude Code CLI経由でコマンド実行
   *
   * ORDER_042: claude -p を直接実行（aipm_auto.runは自動サイクル用のため使用しない）
   */
  private async runPythonClaudeRunner(
    prompt: string,
    cwd: string
  ): Promise<{ success: boolean; stdout: string; stderr: string; exitCode: number | null; error?: string }> {
    // claude -p を直接実行
    return this.runClaudeCommand(prompt, cwd);
  }

  /**
   * Claude Code CLI コマンドを直接実行
   *
   * ORDER_042: spawn()のバッファリング問題を修正
   * - execFileを使用して確実に完了を待機
   * - maxBufferを設定して大きな出力に対応
   * - Windows環境での安定性を向上
   */
  private async runClaudeCommand(
    command: string,
    cwd: string
  ): Promise<{ success: boolean; stdout: string; stderr: string; exitCode: number | null; error?: string }> {
    // claude -p (print mode) + --dangerously-skip-permissions で中断なく実行
    const args = ['-p', '--dangerously-skip-permissions', command];

    console.log(`[ScriptExecution] Running: claude ${args.join(' ')}`);
    console.log(`[ScriptExecution] Working directory: ${cwd}`);
    console.log(`[ScriptExecution] Command: ${command}`);

    return new Promise((resolve) => {
      let stdout = '';
      let stderr = '';
      let resolved = false;

      // ORDER_042: Electronからのspawn実行問題を修正
      // stdio: 'pipe' を明示的に指定してストリームを確保
      const childProcess = spawn('claude', args, {
        cwd,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        shell: true, // Windowsでは必要（PATHからclaudeを見つけるため）
        windowsHide: true, // コンソールウィンドウを非表示
        stdio: ['pipe', 'pipe', 'pipe'], // stdin, stdout, stderr を明示的にpipe
      });

      // プロセスIDをログ出力（デバッグ用）
      console.log(`[ScriptExecution] Process started with PID: ${childProcess.pid}`);

      // タイムアウト設定（60分 - AI処理は時間がかかるため）
      const timeoutMs = WORKER_TIMEOUT_MS;
      const timeout = setTimeout(() => {
        if (!resolved) {
          console.error(`[ScriptExecution] Command timed out after ${timeoutMs}ms`);
          try {
            childProcess.kill('SIGTERM');
          } catch (e) {
            console.error(`[ScriptExecution] Failed to kill process:`, e);
          }
          resolved = true;
          resolve({
            success: false,
            stdout,
            stderr,
            exitCode: null,
            error: `Command timed out after ${timeoutMs / 1000} seconds`,
          });
        }
      }, timeoutMs);

      // stdout処理
      if (childProcess.stdout) {
        childProcess.stdout.setEncoding('utf-8');
        childProcess.stdout.on('data', (data: string) => {
          stdout += data;
          // 長い出力は省略してログ
          const logOutput = data.length > 500 ? data.substring(0, 500) + '...' : data;
          console.log(`[Claude stdout] ${logOutput.trim()}`);
        });
      }

      // stderr処理
      if (childProcess.stderr) {
        childProcess.stderr.setEncoding('utf-8');
        childProcess.stderr.on('data', (data: string) => {
          stderr += data;
          console.warn(`[Claude stderr] ${data.trim()}`);
        });
      }

      // プロセス終了処理
      childProcess.on('close', (exitCode, signal) => {
        clearTimeout(timeout);
        if (resolved) return;
        resolved = true;

        console.log(`[ScriptExecution] Claude process closed - exitCode: ${exitCode}, signal: ${signal}`);
        console.log(`[ScriptExecution] stdout length: ${stdout.length}, stderr length: ${stderr.length}`);

        resolve({
          success: exitCode === 0,
          stdout,
          stderr,
          exitCode,
          error: exitCode !== 0 ? `Claude exited with code ${exitCode}` : undefined,
        });
      });

      // exit イベントも監視（closeより先に発火する場合がある）
      childProcess.on('exit', (exitCode, signal) => {
        console.log(`[ScriptExecution] Claude process exit event - exitCode: ${exitCode}, signal: ${signal}`);
      });

      // エラー処理
      childProcess.on('error', (error) => {
        clearTimeout(timeout);
        if (resolved) return;
        resolved = true;

        console.error(`[ScriptExecution] Claude process error:`, error);
        resolve({
          success: false,
          stdout,
          stderr,
          exitCode: null,
          error: `Failed to run claude: ${error.message}`,
        });
      });
    });
  }

  /**
   * 出力からORDER IDを抽出
   */
  private extractOrderIdFromOutput(stdout: string): string | null {
    // ORDER_XXX パターンを検索（最後に出現したものを使用）
    const matches = stdout.match(/ORDER_\d+/g);
    return matches ? matches[matches.length - 1] : null;
  }

  /**
   * Worker処理を実行（タスク自動サイクル）
   *
   * ORDER_046: 親スクリプト（execute_task.py）を優先的に使用
   * ORDER_041: orchestrator.py経由でWorker→Review自動サイクル（フォールバック）
   *
   * 処理フロー:
   * 1. execute_task.py が存在する場合 → 親スクリプト経由でタスク実行
   * 2. orchestrator.py が存在する場合 → orchestrator.py経由で自動サイクル
   *
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @param taskId タスクID（指定時は単一タスク実行）
   * @returns 実行結果
   */
  async executeWorkerProcess(
    projectId: string,
    orderId: string,
    taskId?: string
  ): Promise<ExecutionResult> {
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) {
      return this.createErrorResult('worker', projectId, orderId, 'Framework path not configured');
    }

    const executionId = this.generateExecutionId();
    const startedAt = new Date();

    // ORDER_098: parallel_launcher.pyの存在確認（taskId未指定時のみ）
    if (!taskId) {
      const parallelLauncherPath = this.getParallelLauncherPath();
      if (parallelLauncherPath) {
        console.log(`[ScriptExecution] Checking for parallel launchable tasks via parallel_launcher.py`);
        const parallelResult = await this.tryExecuteWorkerViaParallelLauncher(
          projectId, orderId, executionId, startedAt
        );
        if (parallelResult) {
          return parallelResult;
        }
        console.log(`[ScriptExecution] No parallel launchable tasks, falling back to sequential execution`);
      }
    }

    // ORDER_046: 親スクリプト（execute_task.py）を優先
    const parentScriptPath = this.getParentScriptPath('worker');
    if (parentScriptPath) {
      console.log(`[ScriptExecution] Using parent script (execute_task.py) for Worker process`);
      return this.executeWorkerViaExecuteTask(projectId, orderId, taskId, executionId, startedAt);
    }

    // フォールバック: aipm-autoスクリプト経由
    const orchestratorPath = this.getAipmAutoPath('orchestrator.py');
    if (orchestratorPath) {
      console.log(`[ScriptExecution] Fallback: Using orchestrator.py for Worker process`);
      return this.executeWorkerViaOrchestrator(projectId, orderId, executionId, startedAt);
    }

    return this.createErrorResult('worker', projectId, orderId, 'No worker script found (execute_task.py or orchestrator.py)');
  }

  /**
   * Worker処理（parallel_launcher.py経由での並列実行を試行）
   *
   * ORDER_098: 並列Worker起動
   *
   * 処理手順:
   * 1. parallel_launcher.py を --dry-run で実行して並列実行可能か確認
   * 2. 並列実行可能なタスクがあれば parallel_launcher.py を実際に実行
   * 3. 並列実行できない場合は null を返して通常フローにフォールバック
   */
  private async tryExecuteWorkerViaParallelLauncher(
    projectId: string,
    orderId: string,
    executionId: string,
    startedAt: Date
  ): Promise<ExecutionResult | null> {
    const frameworkPath = this.getFrameworkPath()!;
    const pythonCommand = this.getPythonCommand();
    const parallelLauncherScript = this.getParallelLauncherPath();

    if (!parallelLauncherScript) {
      return null;
    }

    try {
      // ORDER_114: 常駐モード（--daemon）で起動
      // daemonモードはORDER完了まで常駐し、QUEUEDタスクを自動検知・起動する。
      // dry-run事前チェックは不要（daemon自体がポーリングで検知する）。
      console.log(`[ScriptExecution] Launching parallel_launcher in daemon mode for ${orderId}`);

      const launchArgs = [
        parallelLauncherScript,
        projectId,
        orderId,
        '--daemon',
        '--json',
        '--verbose'
      ];

      // spawn で非同期起動（awaitしない）
      const launchProcess = spawn(pythonCommand, launchArgs, {
        cwd: frameworkPath,
        stdio: ['pipe', 'pipe', 'pipe'],
        detached: false,  // Electronプロセスと一緒に終了
      });

      // ジョブを登録（プロセス参照を保持）
      const job: RunningJob = {
        executionId,
        type: 'worker',
        projectId,
        targetId: orderId,
        process: launchProcess,
        stdout: '',
        stderr: '',
        startedAt,
      };
      this.runningJobs.set(executionId, job);

      // 起動イベントを発火
      this.emit('progress', {
        executionId,
        type: 'worker',
        projectId,
        targetId: orderId,
        status: 'running',
        lastOutput: `Daemonモード起動完了（ORDER完了まで常駐）`,
      } as ExecutionProgress);

      // バックグラウンドで stdout/stderr を収集
      launchProcess.stdout?.on('data', (data: Buffer) => {
        const text = data.toString();
        job.stdout += text;
        console.log(`[ParallelLauncher stdout] ${text.trim()}`);
      });

      launchProcess.stderr?.on('data', (data: Buffer) => {
        const text = data.toString();
        job.stderr += text;
        console.warn(`[ParallelLauncher stderr] ${text.trim()}`);
      });

      // ORDER_109: parallel_launcher.pyのstdout完了後にPID・log_file一覧を抽出して監視を開始
      launchProcess.stdout?.on('end', () => {
        const fullOutput = this.parseParallelLauncherOutput(job.stdout);
        if (fullOutput?.launched_tasks && fullOutput.launched_tasks.length > 0) {
          const tasksWithPid = fullOutput.launched_tasks.filter(t => t.pid && t.pid > 0);
          if (tasksWithPid.length > 0) {
            console.log(`[ParallelLauncher] Starting PID monitoring for ${tasksWithPid.length} launched processes`);
            this.startPidMonitoring(tasksWithPid, projectId, orderId);
          }
        }
      });

      // プロセス終了時のハンドリング（バックグラウンド）
      launchProcess.on('exit', (code: number | null) => {
        console.log(`[ParallelLauncher] exited with code ${code}`);
        this.runningJobs.delete(executionId);

        const bgResult = this.createExecutionResult(
          'worker', projectId, orderId, executionId, startedAt,
          code === 0, job.stdout, job.stderr, code, undefined
        );
        this.addToHistory(bgResult);
        this.emitComplete(bgResult);
      });

      launchProcess.on('error', (err: Error) => {
        console.error(`[ParallelLauncher] process error:`, err);
        this.runningJobs.delete(executionId);

        const errResult = this.createExecutionResult(
          'worker', projectId, orderId, executionId, startedAt,
          false, job.stdout, job.stderr, null, err.message
        );
        this.addToHistory(errResult);
        this.emitComplete(errResult);
      });

      // 即座に起動成功の結果を返す（UIをブロックしない）
      // ORDER_114: daemonモードはORDER完了まで常駐するため、タスクID一覧は不要
      const launchMetadata = JSON.stringify({
        mode: 'daemon',
        orderId,
        message: `Daemonモードで起動しました（ORDER完了まで常駐、QUEUEDタスク自動検知・起動）`,
      });

      const result = this.createExecutionResult(
        'worker', projectId, orderId, executionId, startedAt,
        true, // success = 起動成功
        launchMetadata, '', 0, undefined
      );
      return result;

    } catch (error) {
      console.error(`[ScriptExecution] parallel_launcher execution failed:`, error);
      this.runningJobs.delete(executionId);
      // エラー時は null を返してフォールバック
      return null;
    }
  }

  /**
   * parallel_launcher.pyの出力をパース
   *
   * ORDER_098: JSON形式の出力結果を解析
   */
  private parseParallelLauncherOutput(stdout: string): {
    detected_tasks?: string[];
    launched_count?: number;
    launched_tasks?: Array<{ task_id: string; priority: string; title: string; pid?: number; log_file?: string }>;
    message?: string;
  } | null {
    try {
      // JSON部分を抽出（複数行の出力から最後のJSON objectを探す）
      const jsonMatch = stdout.match(/\{[\s\S]*"project_id"[\s\S]*\}/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      }
    } catch (e) {
      console.warn(`[ScriptExecution] Failed to parse parallel_launcher output:`, e);
    }
    return null;
  }

  /**
   * Worker処理（execute_task.py経由）
   *
   * ORDER_046: 親スクリプト活用版
   *
   * 処理手順:
   * 1. タスクIDが指定されている場合: 単一タスクを実行
   * 2. タスクIDが未指定の場合: ORDER配下のQUEUEDタスクを順次実行
   */
  private async executeWorkerViaExecuteTask(
    projectId: string,
    orderId: string,
    taskId: string | undefined,
    executionId: string,
    startedAt: Date
  ): Promise<ExecutionResult> {
    const frameworkPath = this.getFrameworkPath()!;
    const pythonCommand = this.getPythonCommand();

    // ジョブを登録
    const job: RunningJob = {
      executionId,
      type: 'worker',
      projectId,
      targetId: orderId,
      process: null as unknown as ChildProcess,
      stdout: '',
      stderr: '',
      startedAt,
    };
    this.runningJobs.set(executionId, job);

    // 開始イベントを発行
    this.emit('progress', {
      executionId,
      type: 'worker',
      projectId,
      targetId: orderId,
      status: 'running',
      lastOutput: 'Worker処理を開始（親スクリプト経由）...',
    } as ExecutionProgress);

    try {
      const executeTaskScript = this.getParentScriptPath('worker')!;

      if (taskId) {
        // 単一タスク実行
        console.log(`[ScriptExecution] Executing single task: ${taskId}`);
        const result = await this.executeSingleTask(
          pythonCommand, executeTaskScript, projectId, taskId, job, frameworkPath
        );
        return result;
      }

      // ORDER配下のタスクを順次実行
      console.log(`[ScriptExecution] Executing all tasks for ${orderId}`);
      const result = await this.executeOrderTasks(
        pythonCommand, executeTaskScript, projectId, orderId, job, frameworkPath, executionId, startedAt
      );
      return result;

    } catch (error) {
      console.error(`[ScriptExecution] Worker process error:`, error);
      this.runningJobs.delete(executionId);
      const result = this.createExecutionResult(
        'worker', projectId, orderId, executionId, startedAt,
        false, job.stdout, job.stderr, null,
        `Unexpected error: ${error instanceof Error ? error.message : String(error)}`
      );
      this.addToHistory(result);
      this.emitComplete(result);
      return result;
    }
  }

  /**
   * 単一タスクを実行
   * ORDER_072: --loopオプションを追加し、依存関係を考慮した次タスク自動起動を有効化
   */
  private async executeSingleTask(
    pythonCommand: string,
    scriptPath: string,
    projectId: string,
    taskId: string,
    job: RunningJob,
    cwd: string
  ): Promise<ExecutionResult> {
    // ORDER_072: --loopオプションで依存関係を考慮した連続実行を有効化
    const args = [scriptPath, projectId, taskId, '--json', '--verbose', '--loop'];

    // ORDER_055: REWORKタスクに--is-rework/--rework-commentフラグを追加
    const taskStatus = await this.getTaskStatus(pythonCommand, cwd, projectId, taskId);
    if (taskStatus === 'REWORK') {
      args.push('--is-rework');
      const commentResult = await this.getReworkComment(pythonCommand, cwd, projectId, taskId);
      if (commentResult) {
        args.push('--rework-comment', commentResult);
      }
    }

    this.emit('progress', {
      executionId: job.executionId,
      type: 'worker',
      projectId,
      targetId: taskId,
      status: 'running',
      lastOutput: `タスク実行中: ${taskId}`,
    } as ExecutionProgress);

    const result = await this.runPythonScript(pythonCommand, args, cwd, WORKER_TIMEOUT_MS);
    job.stdout += result.stdout;
    job.stderr += result.stderr;

    this.runningJobs.delete(job.executionId);

    const execResult = this.createExecutionResult(
      'worker', projectId, taskId, job.executionId, job.startedAt,
      result.success, job.stdout, job.stderr, result.exitCode, result.error
    );

    this.addToHistory(execResult);
    this.emitComplete(execResult);
    return execResult;
  }

  /**
   * ORDER配下のタスクを順次実行
   * ORDER_072: --loopオプションを使用し、execute_task.py側で依存関係を考慮した連続実行を行う
   */
  private async executeOrderTasks(
    pythonCommand: string,
    scriptPath: string,
    projectId: string,
    orderId: string,
    job: RunningJob,
    cwd: string,
    executionId: string,
    startedAt: Date
  ): Promise<ExecutionResult> {
    // タスク一覧取得スクリプト（QUEUED + REWORK状態）
    const listScript = path.join(cwd, 'backend', 'task', 'list.py');
    const listArgs = [listScript, projectId, '--order', orderId, '--json'];

    const listResult = await this.runPythonScript(pythonCommand, listArgs, cwd);

    if (!listResult.success) {
      this.runningJobs.delete(executionId);
      const result = this.createExecutionResult(
        'worker', projectId, orderId, executionId, startedAt,
        false, listResult.stdout, listResult.stderr, listResult.exitCode,
        'Failed to get task list'
      );
      this.addToHistory(result);
      this.emitComplete(result);
      return result;
    }

    // タスクリストをパース（QUEUED/REWORK状態のタスクをフィルタ）
    const allTasks = this.parseTaskList(listResult.stdout);
    const tasks = allTasks.filter(t => t.status === 'QUEUED' || t.status === 'REWORK');
    console.log(`[ScriptExecution] Found ${tasks.length} executable tasks for ${orderId}`);

    if (tasks.length === 0) {
      this.runningJobs.delete(executionId);
      const result = this.createExecutionResult(
        'worker', projectId, orderId, executionId, startedAt,
        true, 'No executable tasks found', '', 0
      );
      this.addToHistory(result);
      this.emitComplete(result);
      return result;
    }

    // ORDER_072: 最初のタスクを--loopで実行（依存関係を考慮した連続実行）
    const firstTask = tasks[0];
    console.log(`[ScriptExecution] Starting loop execution from task: ${firstTask.id}`);

    this.emit('progress', {
      executionId,
      type: 'worker',
      projectId,
      targetId: orderId,
      status: 'running',
      lastOutput: `連続実行開始: ${firstTask.id}（依存関係を考慮）`,
      progress: 0,
    } as ExecutionProgress);

    // --loopオプションで連続実行（execute_task.py側で依存関係をチェック）
    const taskArgs = [scriptPath, projectId, firstTask.id, '--json', '--verbose', '--loop'];

    // ORDER_055: REWORKタスクに--is-rework/--rework-commentフラグを追加
    if (firstTask.status === 'REWORK') {
      taskArgs.push('--is-rework');
      // change_historyからrework_commentを取得
      const commentResult = await this.getReworkComment(pythonCommand, cwd, projectId, firstTask.id);
      if (commentResult) {
        taskArgs.push('--rework-comment', commentResult);
      }
    }

    const taskResult = await this.runPythonScript(pythonCommand, taskArgs, cwd, WORKER_TIMEOUT_MS);

    job.stdout += taskResult.stdout;
    job.stderr += taskResult.stderr;

    this.runningJobs.delete(executionId);

    const result = this.createExecutionResult(
      'worker', projectId, orderId, executionId, startedAt,
      taskResult.success, job.stdout, job.stderr, taskResult.exitCode,
      taskResult.success ? undefined : taskResult.error
    );

    this.addToHistory(result);
    this.emitComplete(result);
    return result;
  }

  /**
   * タスクリストをパース
   * ORDER_072: status情報も含めて返すように拡張
   */
  private parseTaskList(output: string): Array<{ id: string; title: string; status: string }> {
    try {
      // JSON配列を探す
      const jsonMatch = output.match(/\[[\s\S]*\]/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        if (Array.isArray(parsed)) {
          return parsed.map((t: { id?: string; title?: string; status?: string }) => ({
            id: t.id || '',
            title: t.title || '',
            status: t.status || '',
          })).filter(t => t.id);
        }
      }
    } catch (e) {
      console.warn(`[ScriptExecution] Failed to parse task list:`, e);
    }
    return [];
  }

  // ------------------------------------------------------------------
  // ORDER_055: REWORK support helpers
  // ------------------------------------------------------------------

  /**
   * ORDER_055: タスクのステータスをDBから取得
   */
  private async getTaskStatus(
    pythonCommand: string,
    cwd: string,
    projectId: string,
    taskId: string
  ): Promise<string | null> {
    try {
      const getScript = path.join(cwd, 'backend', 'task', 'get.py');
      const result = await this.runPythonScript(
        pythonCommand, [getScript, projectId, taskId, '--json'], cwd
      );
      if (result.success && result.stdout) {
        const jsonMatch = result.stdout.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          const parsed = JSON.parse(jsonMatch[0]);
          return parsed.status || null;
        }
      }
    } catch (e) {
      console.warn(`[ScriptExecution] Failed to get task status for ${taskId}:`, e);
    }
    return null;
  }

  /**
   * ORDER_055: change_historyから最新の差し戻しコメントを取得
   */
  private async getReworkComment(
    pythonCommand: string,
    cwd: string,
    projectId: string,
    taskId: string
  ): Promise<string | null> {
    try {
      // historyから最新のREWORK遷移の理由を取得
      const script = path.join(cwd, 'backend', 'task', 'get.py');
      const result = await this.runPythonScript(
        pythonCommand, [script, projectId, taskId, '--detail', '--json'], cwd
      );
      if (result.success && result.stdout) {
        const jsonMatch = result.stdout.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          const parsed = JSON.parse(jsonMatch[0]);
          // historyから最新のREWORK関連コメントを取得
          const history = parsed.history || [];
          for (let i = history.length - 1; i >= 0; i--) {
            const entry = history[i] as { new_value?: string; change_reason?: string };
            if (entry.new_value === 'REWORK' && entry.change_reason) {
              return entry.change_reason;
            }
          }
        }
      }
    } catch (e) {
      console.warn(`[ScriptExecution] Failed to get rework comment for ${taskId}:`, e);
    }
    return null;
  }

  /**
   * Review処理を実行
   *
   * ORDER_046: 親スクリプト（process_review.py）を使用
   *
   * @param projectId プロジェクトID
   * @param taskId タスクID
   * @param autoApprove 自動承認フラグ
   * @returns 実行結果
   */
  async executeReviewProcess(
    projectId: string,
    taskId: string,
    autoApprove: boolean = false
  ): Promise<ExecutionResult> {
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) {
      return this.createErrorResult('review', projectId, taskId, 'Framework path not configured');
    }

    const executionId = this.generateExecutionId();
    const startedAt = new Date();

    // 親スクリプト（process_review.py）の存在確認
    const parentScriptPath = this.getParentScriptPath('review');
    if (!parentScriptPath) {
      return this.createErrorResult('review', projectId, taskId, 'process_review.py not found');
    }

    console.log(`[ScriptExecution] Using parent script (process_review.py) for Review process`);
    return this.executeReviewViaProcessReview(projectId, taskId, autoApprove, executionId, startedAt);
  }

  /**
   * Review処理（process_review.py経由）
   *
   * ORDER_046: 親スクリプト活用版
   */
  private async executeReviewViaProcessReview(
    projectId: string,
    taskId: string,
    autoApprove: boolean,
    executionId: string,
    startedAt: Date
  ): Promise<ExecutionResult> {
    const frameworkPath = this.getFrameworkPath()!;
    const pythonCommand = this.getPythonCommand();
    const processReviewScript = this.getParentScriptPath('review')!;

    // ジョブを登録
    const job: RunningJob = {
      executionId,
      type: 'review',
      projectId,
      targetId: taskId,
      process: null as unknown as ChildProcess,
      stdout: '',
      stderr: '',
      startedAt,
    };
    this.runningJobs.set(executionId, job);

    // 開始イベントを発行
    this.emit('progress', {
      executionId,
      type: 'review',
      projectId,
      targetId: taskId,
      status: 'running',
      lastOutput: 'Review処理を開始（親スクリプト経由）...',
    } as ExecutionProgress);

    try {
      console.log(`[ScriptExecution] Executing review for task: ${taskId}`);

      const args = [processReviewScript, projectId, taskId, '--json', '--verbose'];
      if (autoApprove) {
        args.push('--auto-approve');
      }

      this.emit('progress', {
        executionId,
        type: 'review',
        projectId,
        targetId: taskId,
        status: 'running',
        lastOutput: `レビュー実行中: ${taskId}`,
      } as ExecutionProgress);

      const result = await this.runPythonScript(pythonCommand, args, frameworkPath);
      job.stdout = result.stdout;
      job.stderr = result.stderr;

      // レビュー結果をパース
      const reviewResult = this.parseReviewResult(result.stdout);

      this.runningJobs.delete(executionId);

      const execResult = this.createExecutionResult(
        'review', projectId, taskId, executionId, startedAt,
        result.success, job.stdout, job.stderr, result.exitCode, result.error
      );

      // レビュー結果を追加情報として設定
      if (reviewResult) {
        (execResult as ExecutionResult & { verdict?: string }).verdict = reviewResult.verdict;
      }

      this.addToHistory(execResult);
      this.emitComplete(execResult);
      return execResult;

    } catch (error) {
      console.error(`[ScriptExecution] Review process error:`, error);
      this.runningJobs.delete(executionId);
      const result = this.createExecutionResult(
        'review', projectId, taskId, executionId, startedAt,
        false, job.stdout, job.stderr, null,
        `Unexpected error: ${error instanceof Error ? error.message : String(error)}`
      );
      this.addToHistory(result);
      this.emitComplete(result);
      return result;
    }
  }

  /**
   * レビュー結果をパース
   */
  private parseReviewResult(output: string): { verdict: string; summary?: string } | null {
    try {
      // JSON部分を抽出
      const jsonMatch = output.match(/\{[^{}]*"verdict"\s*:\s*"[^"]+"/);
      if (jsonMatch) {
        // より完全なJSONを探す
        const fullJsonMatch = output.match(/\{[^{}]*"verdict"[^{}]*\}/);
        if (fullJsonMatch) {
          const parsed = JSON.parse(fullJsonMatch[0]);
          return {
            verdict: parsed.verdict || 'UNKNOWN',
            summary: parsed.summary,
          };
        }
      }
      // テキストから判定を抽出
      const verdictMatch = output.match(/判定[：:]\s*(APPROVED|REJECTED|ESCALATED)/i);
      if (verdictMatch) {
        return { verdict: verdictMatch[1].toUpperCase() };
      }
    } catch (e) {
      console.warn(`[ScriptExecution] Failed to parse review result:`, e);
    }
    return null;
  }

  /**
   * Worker処理（orchestrator.py経由）
   *
   * ORDER_041: Worker→Review自動サイクルを実行
   */
  private async executeWorkerViaOrchestrator(
    projectId: string,
    orderId: string,
    executionId: string,
    startedAt: Date
  ): Promise<ExecutionResult> {
    const frameworkPath = this.getFrameworkPath()!;
    const pythonCommand = this.getPythonCommand();

    // orchestrator.pyを実行
    // --max-cycles 10 で最大10タスク処理（必要に応じて調整）
    const args = [
      '-m', 'backend.aipm_auto.orchestrator',
      projectId,
      '--max-cycles', '10',
      '--verbose',
    ];

    console.log(`[ScriptExecution] Running orchestrator: ${pythonCommand} ${args.join(' ')}`);

    return new Promise((resolve) => {
      const childProcess = spawn(pythonCommand, args, {
        cwd: frameworkPath,
        env: {
          ...process.env,
          PYTHONIOENCODING: 'utf-8',
        },
        shell: true,
      });

      const job: RunningJob = {
        executionId,
        type: 'worker',
        projectId,
        targetId: orderId,
        process: childProcess,
        stdout: '',
        stderr: '',
        startedAt,
      };

      this.runningJobs.set(executionId, job);

      // 進捗イベントを発行
      this.emit('progress', {
        executionId,
        type: 'worker',
        projectId,
        targetId: orderId,
        status: 'running',
      } as ExecutionProgress);

      childProcess.stdout?.on('data', (data: Buffer) => {
        const output = data.toString('utf-8');
        job.stdout += output;

        // 進捗イベントを発行
        this.emit('progress', {
          executionId,
          type: 'worker',
          projectId,
          targetId: orderId,
          status: 'running',
          lastOutput: output.trim().split('\n').pop(),
        } as ExecutionProgress);

        console.log(`[orchestrator] ${output}`);
      });

      childProcess.stderr?.on('data', (data: Buffer) => {
        const output = data.toString('utf-8');
        job.stderr += output;
        console.warn(`[orchestrator stderr] ${output}`);
      });

      childProcess.on('close', (exitCode) => {
        const completedAt = new Date();
        const durationMs = completedAt.getTime() - startedAt.getTime();

        this.runningJobs.delete(executionId);

        // orchestrator出力をパース
        const orchestratorResult = this.parseOrchestratorOutput(job.stdout);

        const result: ExecutionResult = {
          success: orchestratorResult?.success ?? (exitCode === 0),
          executionId,
          type: 'worker',
          projectId,
          targetId: orderId,
          stdout: job.stdout,
          stderr: job.stderr,
          exitCode,
          startedAt: startedAt.toISOString(),
          completedAt: completedAt.toISOString(),
          durationMs,
          cyclesCompleted: orchestratorResult?.cycles_completed,
          stopReason: orchestratorResult?.stop_reason,
        };

        if (exitCode !== 0 && !orchestratorResult?.success) {
          result.error = orchestratorResult?.stop_message || `Process exited with code ${exitCode}`;
        }

        console.log(`[ScriptExecution] Completed worker process:`, {
          executionId,
          success: result.success,
          exitCode,
          durationMs,
          cyclesCompleted: result.cyclesCompleted,
          stopReason: result.stopReason,
        });

        this.addToHistory(result);
        this.emitComplete(result);
        resolve(result);
      });

      childProcess.on('error', (error) => {
        const completedAt = new Date();
        const durationMs = completedAt.getTime() - startedAt.getTime();

        this.runningJobs.delete(executionId);

        const result: ExecutionResult = {
          success: false,
          executionId,
          type: 'worker',
          projectId,
          targetId: orderId,
          stdout: job.stdout,
          stderr: job.stderr,
          exitCode: null,
          error: error.message,
          startedAt: startedAt.toISOString(),
          completedAt: completedAt.toISOString(),
          durationMs,
        };

        console.error(`[ScriptExecution] Error in worker process:`, error);

        this.addToHistory(result);
        this.emitComplete(result);
        resolve(result);
      });
    });
  }

  /**
   * orchestrator.pyの出力をパース
   */
  private parseOrchestratorOutput(stdout: string): OrchestratorOutput | null {
    try {
      // JSON部分を抽出（最後のJSON objectを探す）
      const jsonMatch = stdout.match(/\{[\s\S]*"success"[\s\S]*\}/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]) as OrchestratorOutput;
      }
    } catch (e) {
      console.warn(`[ScriptExecution] Failed to parse orchestrator output:`, e);
    }
    return null;
  }

  /**
   * ExecutionResult を作成（共通処理）
   */
  private createExecutionResult(
    type: 'pm' | 'worker' | 'review',
    projectId: string,
    targetId: string,
    executionId: string,
    startedAt: Date,
    success: boolean,
    stdout: string,
    stderr: string,
    exitCode: number | null,
    error?: string
  ): ExecutionResult {
    const completedAt = new Date();
    return {
      success,
      executionId,
      type,
      projectId,
      targetId,
      stdout,
      stderr,
      exitCode,
      error,
      startedAt: startedAt.toISOString(),
      completedAt: completedAt.toISOString(),
      durationMs: completedAt.getTime() - startedAt.getTime(),
    };
  }

  /**
   * エラー結果を作成（共通処理）
   */
  private createErrorResult(
    type: 'pm' | 'worker' | 'review',
    projectId: string,
    targetId: string,
    error: string
  ): ExecutionResult {
    const now = new Date().toISOString();
    return {
      success: false,
      executionId: this.generateExecutionId(),
      type,
      projectId,
      targetId,
      stdout: '',
      stderr: '',
      exitCode: null,
      error,
      startedAt: now,
      completedAt: now,
      durationMs: 0,
    };
  }

  /**
   * 完了イベントを発行（共通処理）
   */
  private emitComplete(result: ExecutionResult): void {
    this.emit('complete', result);
    this.emit('progress', {
      executionId: result.executionId,
      type: result.type,
      projectId: result.projectId,
      targetId: result.targetId,
      status: result.success ? 'completed' : 'failed',
    } as ExecutionProgress);
  }

  // =============================================================================
  // ORDER_101: DBステータスポーリング機構
  // =============================================================================

  /**
   * ORDER内のタスクステータスを取得
   *
   * ORDER_101: task/list.py を呼び出してステータスを取得
   *
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @returns タスクステータス配列
   */
  async getTaskStatuses(projectId: string, orderId: string): Promise<Array<{
    id: string;
    title: string;
    status: string;
    assignee?: string;
  }>> {
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) return [];

    const pythonCommand = this.getPythonCommand();
    const backendPath = this.getBackendPath();
    if (!backendPath) return [];
    const taskListScript = path.join(backendPath, 'task', 'list.py');
    const args = [taskListScript, projectId, '--order', orderId, '--json'];

    const result = await this.runPythonScript(pythonCommand, args, frameworkPath, 30000);
    if (!result.success) return [];

    return this.parseTaskList(result.stdout);
  }

  /**
   * ORDER_119: タスクの実行ステップ情報を取得
   *
   * worker/get_execution_steps.py を呼び出して現在の実行ステップを返す
   */
  async getTaskExecutionSteps(projectId: string, taskId: string): Promise<{
    currentStep: string | null;
    currentStepDisplay: string;
    stepIndex: number;
    totalSteps: number;
    progressPercent: number;
    steps: Array<{ step: string; display: string; status: string }>;
  } | null> {
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) return null;

    const pythonCommand = this.getPythonCommand();
    const backendPath = this.getBackendPath();
    if (!backendPath) return null;
    const scriptPath = path.join(backendPath, 'worker', 'get_execution_steps.py');

    // スクリプトの存在チェック
    if (!fs.existsSync(scriptPath)) {
      console.warn(`[ScriptExecution] get_execution_steps.py not found: ${scriptPath}`);
      return null;
    }

    const args = [scriptPath, projectId, taskId, '--json'];
    const result = await this.runPythonScript(pythonCommand, args, frameworkPath, 10000);
    if (!result.success) return null;

    try {
      const data = JSON.parse(result.stdout.trim());
      return {
        currentStep: data.current_step || null,
        currentStepDisplay: data.current_step_display || '',
        stepIndex: data.step_index ?? 0,
        totalSteps: data.total_steps ?? 8,
        progressPercent: data.progress_percent ?? 0,
        steps: (data.steps || []).map((s: { step: string; display: string; status: string }) => ({
          step: s.step,
          display: s.display,
          status: s.status,
        })),
      };
    } catch {
      console.error('[ScriptExecution] Failed to parse execution steps:', result.stdout);
      return null;
    }
  }

  /**
   * タスクステータスのポーリングを開始
   *
   * ORDER_101: 定期的にDBをポーリングし、ステータス変化を検知
   * ORDER_119: IN_PROGRESSタスク存在時は3秒間隔、それ以外は7秒間隔に動的調整
   *            全タスク完了時はポーリング自動停止
   *
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @param intervalMs 初期ポーリング間隔（ミリ秒）デフォルト7000ms（動的に調整される）
   */
  startTaskPolling(projectId: string, orderId: string, intervalMs: number = 7000): void {
    this.stopTaskPolling(); // 既存ポーリングを停止

    this.pollingProjectId = projectId;
    this.pollingOrderId = orderId;

    console.log(`[ScriptExecution] Starting task polling for ${orderId} (dynamic interval: ${ScriptExecutionService.POLLING_FAST_MS}ms/${ScriptExecutionService.POLLING_NORMAL_MS}ms)`);

    // ORDER_119: 初回は即座にポーリング実行
    this.scheduleNextPoll(Math.min(intervalMs, 1000));
  }

  /**
   * ORDER_119: 次のポーリングをスケジュール
   */
  private scheduleNextPoll(delayMs: number): void {
    this.pollingTimeout = setTimeout(() => this.executePollCycle(), delayMs);
  }

  /**
   * ORDER_119: ポーリング1サイクルを実行し、次回間隔を動的に決定
   */
  private async executePollCycle(): Promise<void> {
    const projectId = this.pollingProjectId;
    const orderId = this.pollingOrderId;
    if (!projectId || !orderId) return;

    try {
      const tasks = await this.getTaskStatuses(projectId, orderId);

      // IN_PROGRESSタスクの有無を判定
      const hasInProgress = tasks.some(t => t.status === 'IN_PROGRESS');

      // ORDER_101 TASK_971: Timeout detection (IN_PROGRESS > 30min)
      const TASK_TIMEOUT_MS = 30 * 60 * 1000; // 30min
      for (const task of tasks) {
        if (task.status === 'IN_PROGRESS') {
          const taskStartTime = this.taskStartTimes.get(task.id);
          if (taskStartTime) {
            const elapsed = Date.now() - taskStartTime.getTime();
            if (elapsed > TASK_TIMEOUT_MS) {
              console.warn(`[ScriptExecution] Task ${task.id} timeout detected (${Math.round(elapsed / 60000)}min)`);
              this.emit('task-timeout', {
                taskId: task.id,
                title: task.title,
                elapsedMs: elapsed,
                projectId,
                orderId,
              });
            }
          } else {
            this.taskStartTimes.set(task.id, new Date());
          }
        }
      }

      // ORDER_101 TASK_971: REJECTED/ESCALATED error detection
      for (const task of tasks) {
        const prevStatus = this.previousTaskStatuses.get(task.id);
        if (task.status === 'REJECTED' || task.status === 'ESCALATED') {
          if (prevStatus !== task.status) {
            this.emit('task-error', {
              taskId: task.id,
              title: task.title,
              status: task.status,
              projectId,
              orderId,
            });
          }
        }
      }

      for (const task of tasks) {
        const prevStatus = this.previousTaskStatuses.get(task.id);
        if (prevStatus && prevStatus !== task.status) {
          console.log(`[ScriptExecution] Task ${task.id} status changed: ${prevStatus} → ${task.status}`);
          this.emit('task-status-changed', {
            taskId: task.id,
            title: task.title,
            oldStatus: prevStatus,
            newStatus: task.status,
            projectId,
            orderId,
          });
        }
        this.previousTaskStatuses.set(task.id, task.status);
      }

      // 全タスク完了チェック
      const allDone = tasks.length > 0 && tasks.every(t =>
        t.status === 'COMPLETED' || t.status === 'REJECTED'
      );
      if (allDone) {
        console.log(`[ScriptExecution] All tasks completed for ${orderId}`);
        this.emit('all-tasks-completed', { projectId, orderId, tasks });
        this.stopTaskPolling();
        return; // ポーリング終了
      }

      // ORDER_119: 次回ポーリング間隔を動的決定
      const nextInterval = hasInProgress
        ? ScriptExecutionService.POLLING_FAST_MS
        : ScriptExecutionService.POLLING_NORMAL_MS;
      this.scheduleNextPoll(nextInterval);
    } catch (error) {
      console.error(`[ScriptExecution] Polling error:`, error);
      // エラー時も通常間隔でリトライ
      this.scheduleNextPoll(ScriptExecutionService.POLLING_NORMAL_MS);
    }
  }

  /**
   * タスクステータスのポーリングを停止
   *
   * ORDER_101: clearIntervalでポーリングを停止し、ステータスキャッシュをクリア
   */
  stopTaskPolling(): void {
    if (this.pollingTimeout) {
      clearTimeout(this.pollingTimeout);
      this.pollingTimeout = null;
      this.pollingProjectId = null;
      this.pollingOrderId = null;
      this.previousTaskStatuses.clear();
      this.taskStartTimes.clear();
      console.log('[ScriptExecution] Task polling stopped');
    }
    // ORDER_109: PID監視も停止
    this.stopPidMonitoring();
  }

  /**
   * 実行中のジョブ一覧を取得
   */
  getRunningJobs(): Array<{
    executionId: string;
    type: 'pm' | 'worker' | 'review';
    projectId: string;
    targetId: string;
    startedAt: string;
  }> {
    return Array.from(this.runningJobs.values()).map((job) => ({
      executionId: job.executionId,
      type: job.type,
      projectId: job.projectId,
      targetId: job.targetId,
      startedAt: job.startedAt.toISOString(),
    }));
  }

  /**
   * 特定のジョブが実行中かどうかを確認
   */
  isRunning(projectId: string, targetId: string): boolean {
    for (const job of this.runningJobs.values()) {
      if (job.projectId === projectId && job.targetId === targetId) {
        return true;
      }
    }
    return false;
  }

  // =============================================================================
  // ORDER_109: PID監視・エラー検知
  // =============================================================================

  /**
   * parallel_launcher起動結果からPID・log_file一覧を取得して監視を開始
   *
   * ORDER_109: プロセス生存確認による異常終了検知
   *
   * @param launchedTasks parallel_launcherの起動結果
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   */
  startPidMonitoring(
    launchedTasks: Array<{ task_id: string; pid?: number; log_file?: string }>,
    projectId: string,
    orderId: string
  ): void {
    // 既存の監視を停止してからリセット
    // (monitoredProcessesは追加方式にして複数ORDER分を管理可能にする)

    for (const task of launchedTasks) {
      if (task.pid && task.pid > 0) {
        this.monitoredProcesses.set(task.pid, {
          taskId: task.task_id,
          projectId,
          logFile: task.log_file || '',
          orderId,
        });
        console.log(`[PidMonitor] Registered PID ${task.pid} for ${task.task_id} (log: ${task.log_file || 'N/A'})`);
      }
    }

    if (this.monitoredProcesses.size > 0 && !this.pidMonitorInterval) {
      console.log(`[PidMonitor] Starting PID monitoring (${this.monitoredProcesses.size} processes, ${ScriptExecutionService.PID_MONITOR_INTERVAL_MS}ms interval)`);
      this.pidMonitorInterval = setInterval(() => {
        this.checkMonitoredProcesses();
      }, ScriptExecutionService.PID_MONITOR_INTERVAL_MS);
    }
  }

  /**
   * PID監視を停止
   *
   * ORDER_109: 全タスク完了時またはアプリ終了時に呼び出す
   */
  stopPidMonitoring(): void {
    if (this.pidMonitorInterval) {
      clearInterval(this.pidMonitorInterval);
      this.pidMonitorInterval = null;
    }
    this.monitoredProcesses.clear();
    console.log('[PidMonitor] PID monitoring stopped');
  }

  /**
   * 監視中のプロセスの生存確認を実行
   *
   * ORDER_109: tasklist (Windows) でプロセスの生存を確認
   */
  private async checkMonitoredProcesses(): Promise<void> {
    if (this.monitoredProcesses.size === 0) {
      this.stopPidMonitoring();
      return;
    }

    const pidsToCheck = Array.from(this.monitoredProcesses.keys());

    for (const pid of pidsToCheck) {
      const info = this.monitoredProcesses.get(pid);
      if (!info) continue;

      try {
        const isAlive = await this.isProcessAlive(pid);

        if (!isAlive) {
          console.log(`[PidMonitor] PID ${pid} (${info.taskId}) is no longer running. Checking DB status...`);

          // DBからタスクのステータスを取得して正常終了か異常終了かを判定
          const taskStatuses = await this.getTaskStatuses(info.projectId, info.orderId);
          const taskStatus = taskStatuses.find(t => t.id === info.taskId);
          const currentStatus = taskStatus?.status || 'UNKNOWN';

          if (currentStatus === 'DONE' || currentStatus === 'COMPLETED') {
            // 正常終了: 監視解除のみ
            console.log(`[PidMonitor] Task ${info.taskId} completed normally (status: ${currentStatus}). Removing from monitoring.`);
            this.monitoredProcesses.delete(pid);
          } else if (currentStatus === 'IN_PROGRESS') {
            // 異常終了: IN_PROGRESSのままプロセスが消失
            console.warn(`[PidMonitor] Task ${info.taskId} crashed! (PID: ${pid}, status: ${currentStatus})`);
            this.monitoredProcesses.delete(pid);
            await this.handleProcessCrash(pid, info);
          } else {
            // QUEUED, REWORK, REJECTEDなど: 既に他の理由で状態遷移済み
            console.log(`[PidMonitor] Task ${info.taskId} status is ${currentStatus}. Removing from monitoring.`);
            this.monitoredProcesses.delete(pid);
          }
        }
      } catch (error) {
        console.error(`[PidMonitor] Error checking PID ${pid}:`, error);
      }
    }

    // 全プロセスの監視が終了したら停止
    if (this.monitoredProcesses.size === 0) {
      console.log('[PidMonitor] All monitored processes resolved. Stopping PID monitoring.');
      this.stopPidMonitoring();
    }
  }

  /**
   * プロセスが生存しているかチェック (Windows: tasklist)
   *
   * ORDER_109: Windows環境でのプロセス生存確認
   */
  private isProcessAlive(pid: number): Promise<boolean> {
    return new Promise((resolve) => {
      if (process.platform === 'win32') {
        exec(`tasklist /FI "PID eq ${pid}" /NH`, { windowsHide: true }, (error, stdout) => {
          if (error) {
            // execエラー: プロセスが存在しないとみなす
            resolve(false);
            return;
          }
          // "INFO: No tasks are running which match the specified criteria."
          // この文字列が含まれていればプロセスは存在しない
          const output = stdout.toString();
          if (output.includes('INFO:') || output.includes('No tasks')) {
            resolve(false);
          } else {
            resolve(true);
          }
        });
      } else {
        // Unix系: kill -0 で確認
        try {
          process.kill(pid, 0);
          resolve(true);
        } catch {
          resolve(false);
        }
      }
    });
  }

  /**
   * プロセスクラッシュ時の処理
   *
   * ORDER_109: recover_crashed.pyを呼び出してDB修復 + イベント発行 + 通知
   */
  private async handleProcessCrash(pid: number, info: MonitoredProcess): Promise<void> {
    const { taskId, projectId, logFile, orderId } = info;

    console.log(`[PidMonitor] Handling crash for ${taskId} (PID: ${pid})`);

    // 1. recover_crashed.pyを呼び出してDB修復
    const frameworkPath = this.getFrameworkPath();
    if (frameworkPath) {
      const pythonCommand = this.getPythonCommand();
      const backendPath = this.getBackendPath();
      const recoverScript = backendPath ? path.join(backendPath, 'worker', 'recover_crashed.py') : '';

      if (fs.existsSync(recoverScript)) {
        const reason = `Process crashed (PID: ${pid})`;
        const args = [recoverScript, projectId, taskId, '--reason', reason, '--json'];

        try {
          const result = await this.runPythonScript(pythonCommand, args, frameworkPath, 30000);
          if (result.success) {
            console.log(`[PidMonitor] Recovery successful for ${taskId}`);
          } else {
            console.error(`[PidMonitor] Recovery failed for ${taskId}:`, result.stderr);
          }
        } catch (error) {
          console.error(`[PidMonitor] Recovery script error for ${taskId}:`, error);
        }
      } else {
        console.warn(`[PidMonitor] recover_crashed.py not found at ${recoverScript}`);
      }
    }

    // 2. task-errorイベントを発行（既存のイベントフローに乗せる）
    this.emit('task-error', {
      taskId,
      title: `PID ${pid}`,
      status: 'CRASHED',
      projectId,
      orderId,
      logFile,
      message: `プロセス異常終了 - 自動復旧済み（QUEUED）`,
    });

    // 3. task-crash専用イベントを発行（デスクトップ通知用）
    this.emit('task-crash', {
      taskId,
      projectId,
      orderId,
      pid,
      logFile,
      message: `プロセス異常終了 - 自動復旧済み（QUEUED）`,
    });

    console.log(`[PidMonitor] Crash handling completed for ${taskId}`);
  }

  // =============================================================================
  // ORDER_111: Worker ログ一覧・読み込み・監視
  // =============================================================================

  /**
   * Worker ログファイル一覧を取得（ORDER_090: ページネーション・非同期化・キャッシュ対応）
   *
   * ORDER_111: PROJECTS/{projectId}/RESULT/ORDER_xxx/LOGS/ ディレクトリを走査し、
   * worker_xxx.log および execution_xxx.log ファイルを一覧化する
   *
   * @param projectId プロジェクトID
   * @param orderId ORDER ID（指定時はそのORDERのみ、省略時は全ORDER）
   * @param options ページネーションオプション（limit: 取得件数, offset: 開始位置）
   * @returns ページネーション付きログファイル情報
   */
  async getWorkerLogFiles(
    projectId: string,
    orderId?: string,
    options?: { limit?: number; offset?: number }
  ): Promise<WorkerLogFileListResponse> {
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) return { items: [], totalCount: 0, offset: 0, limit: 0 };

    const limit = options?.limit ?? 100;
    const offset = options?.offset ?? 0;
    const results: WorkerLogFileInfo[] = [];
    const configService = getConfigService();
    const resultDir = path.join(configService.getProjectsBasePath(), projectId, 'RESULT');

    try {
      await fsPromises.access(resultDir);
    } catch {
      return { items: [], totalCount: 0, offset, limit };
    }

    try {
      // ORDER ディレクトリを特定（非同期）
      let orderDirs: string[];
      if (orderId) {
        try {
          await fsPromises.access(path.join(resultDir, orderId));
          orderDirs = [orderId];
        } catch {
          orderDirs = [];
        }
      } else {
        const entries = await fsPromises.readdir(resultDir, { withFileTypes: true });
        orderDirs = entries
          .filter(e => e.isDirectory() && e.name.startsWith('ORDER_'))
          .map(e => e.name);
      }

      // 全LOGSディレクトリからファイル名とmtimeのみ収集（並列実行）
      const scanPromises = orderDirs.map(async (orderDirName) => {
        const logsDir = path.join(resultDir, orderDirName, 'LOGS');
        try {
          await fsPromises.access(logsDir);
        } catch {
          return [];
        }

        const logEntries = await fsPromises.readdir(logsDir, { withFileTypes: true });
        const fileInfoPromises = logEntries
          .filter(entry => entry.isFile() && entry.name.endsWith('.log'))
          .map(async (entry) => {
            const filePath = path.join(logsDir, entry.name);
            try {
              const stats = await fsPromises.stat(filePath);
              return {
                filePath,
                fileName: entry.name,
                taskId: this.extractTaskIdFromLogFileName(entry.name),
                orderId: orderDirName,
                fileSize: stats.size,
                mtimeMs: stats.mtime.getTime(),
                modifiedAt: stats.mtime.toISOString(),
              };
            } catch {
              return null;
            }
          });

        return (await Promise.all(fileInfoPromises)).filter(
          (info): info is NonNullable<typeof info> => info !== null
        );
      });

      const allFileInfos = (await Promise.all(scanPromises)).flat();

      // 更新日時降順でソート
      allFileInfos.sort((a, b) => b.mtimeMs - a.mtimeMs);

      const totalCount = allFileInfos.length;

      // ページネーション: offset/limit適用後のみステータス判定
      const paginatedInfos = allFileInfos.slice(offset, offset + limit);

      // ステータス判定（キャッシュ活用、表示分のみ）
      for (const info of paginatedInfos) {
        const status = await this.detectLogFileStatusCached(info.filePath, info.fileSize, info.mtimeMs);
        results.push({
          filePath: info.filePath,
          fileName: info.fileName,
          taskId: info.taskId,
          orderId: info.orderId,
          status,
          fileSize: info.fileSize,
          modifiedAt: info.modifiedAt,
        });
      }

      return { items: results, totalCount, offset, limit };
    } catch (error) {
      console.error(`[WorkerLog] Error scanning log files for ${projectId}:`, error);
      return { items: [], totalCount: 0, offset, limit };
    }
  }

  /**
   * ログファイル名からタスクIDを抽出
   *
   * パターン例:
   * - worker_TASK_123_20260209_123456.log → TASK_123
   * - execution_20260206_194123.log → (execution)
   */
  private extractTaskIdFromLogFileName(fileName: string): string {
    // worker_{task_id}_{timestamp}.log パターン
    const workerMatch = fileName.match(/^worker_(TASK_\d+)_/);
    if (workerMatch) {
      return workerMatch[1];
    }

    // execution_{timestamp}.log パターン
    if (fileName.startsWith('execution_')) {
      return 'execution';
    }

    // その他のパターン: 拡張子を除いたファイル名を返す
    return path.basename(fileName, '.log');
  }

  /**
   * ログファイルのステータスをキャッシュ付きで判定（ORDER_090: 非同期版）
   *
   * キャッシュヒット条件: filePath + mtimeMs が一致
   * キャッシュミス時のみファイル末尾を読み込んでパターンマッチ
   */
  private async detectLogFileStatusCached(
    filePath: string,
    fileSize: number,
    mtimeMs: number
  ): Promise<'running' | 'success' | 'failed' | 'unknown'> {
    if (fileSize === 0) return 'unknown';

    // 実行中プロセスのログファイルか確認（キャッシュより優先）
    for (const [, info] of this.monitoredProcesses) {
      if (info.logFile === filePath) {
        return 'running';
      }
    }

    // キャッシュチェック
    const cached = this.logStatusCache.get(filePath);
    if (cached && cached.mtimeMs === mtimeMs) {
      return cached.status;
    }

    // キャッシュミス: ファイル末尾を非同期で読み込んでパターンマッチ
    let status: 'running' | 'success' | 'failed' | 'unknown' = 'unknown';
    try {
      const readSize = Math.min(fileSize, 4096);
      const fh = await fsPromises.open(filePath, 'r');
      try {
        const buffer = Buffer.alloc(readSize);
        await fh.read(buffer, 0, readSize, Math.max(0, fileSize - readSize));
        const tailContent = buffer.toString('utf-8');

        if (
          tailContent.includes('SUCCESS') ||
          tailContent.includes('DONE') ||
          tailContent.includes('COMPLETED') ||
          tailContent.includes('タスク完了') ||
          tailContent.includes('exit code: 0')
        ) {
          status = 'success';
        } else if (
          tailContent.includes('FAILED') ||
          tailContent.includes('ERROR') ||
          tailContent.includes('CRASHED') ||
          tailContent.includes('Traceback') ||
          tailContent.includes('異常終了') ||
          tailContent.match(/exit code: [^0]/)
        ) {
          status = 'failed';
        }
      } finally {
        await fh.close();
      }
    } catch {
      // ファイル読み取りエラーは無視
    }

    // running判定（ファイルI/Oで判定できなかった場合）
    if (status === 'unknown') {
      const fiveMinutesAgo = Date.now() - 5 * 60 * 1000;
      if (mtimeMs > fiveMinutesAgo) {
        status = 'running';
      }
    }

    // キャッシュに保存（running以外。runningは動的に変わるためキャッシュしない）
    if (status !== 'running') {
      this.logStatusCache.set(filePath, { status, mtimeMs });
    }

    return status;
  }

  /**
   * Worker ログファイルの内容を読み込む
   *
   * ORDER_111: AipmAutoLogService.readLogFile() と同等の差分読み込みをサポート
   *
   * @param filePath ログファイルのパス
   * @param options 読み込みオプション
   *   - tailLines: 末尾から取得する行数
   *   - fromPosition: 指定バイト位置から読み込み（差分取得用）
   * @returns ログ内容
   */
  readWorkerLogFile(
    filePath: string,
    options?: { tailLines?: number; fromPosition?: number }
  ): WorkerLogContent | null {
    if (!fs.existsSync(filePath)) {
      return null;
    }

    try {
      const stats = fs.statSync(filePath);
      const fileSize = stats.size;

      if (options?.tailLines !== undefined) {
        // 末尾から指定行数を取得
        const content = fs.readFileSync(filePath, 'utf-8');
        const lines = content.split('\n');
        const startLine = Math.max(0, lines.length - options.tailLines);
        const selectedLines = lines.slice(startLine);

        return {
          content: selectedLines.join('\n'),
          fileSize,
          readPosition: fileSize,
        };
      }

      if (options?.fromPosition !== undefined) {
        // 指定位置からの差分読み込み
        if (options.fromPosition >= fileSize) {
          return { content: '', fileSize, readPosition: fileSize };
        }

        const fd = fs.openSync(filePath, 'r');
        try {
          const buffer = Buffer.alloc(fileSize - options.fromPosition);
          fs.readSync(fd, buffer, 0, buffer.length, options.fromPosition);
          return {
            content: buffer.toString('utf-8'),
            fileSize,
            readPosition: fileSize,
          };
        } finally {
          fs.closeSync(fd);
        }
      }

      // 全文読み込み
      const content = fs.readFileSync(filePath, 'utf-8');
      return { content, fileSize, readPosition: fileSize };
    } catch (error) {
      console.error(`[WorkerLog] Error reading log file ${filePath}:`, error);
      return null;
    }
  }

  /**
   * Worker ログファイルの監視を開始
   *
   * ORDER_111: chokidarでファイル変更を監視し、差分内容をイベントとして発行
   *
   * @param filePath 監視対象のログファイルパス
   */
  watchWorkerLog(filePath: string): void {
    // 既に監視中なら何もしない
    if (this.workerLogWatchers.has(filePath)) {
      console.log(`[WorkerLog] Already watching: ${filePath}`);
      return;
    }

    if (!fs.existsSync(filePath)) {
      console.warn(`[WorkerLog] File not found for watching: ${filePath}`);
      return;
    }

    // 初期位置を記録
    try {
      const stats = fs.statSync(filePath);
      this.workerLogPositions.set(filePath, stats.size);
    } catch {
      this.workerLogPositions.set(filePath, 0);
    }

    const watcher = watch(filePath, {
      persistent: true,
      ignoreInitial: true,
      awaitWriteFinish: {
        stabilityThreshold: 200,
        pollInterval: 100,
      },
      usePolling: false,
    });

    watcher.on('change', () => {
      this.handleWorkerLogChange(filePath);
    });

    watcher.on('error', (error) => {
      console.error(`[WorkerLog] Watcher error for ${filePath}:`, error);
    });

    this.workerLogWatchers.set(filePath, watcher);
    console.log(`[WorkerLog] Started watching: ${filePath}`);
  }

  /**
   * Worker ログファイルの監視を停止
   *
   * ORDER_111: chokidar watcherを閉じてリソースを解放
   *
   * @param filePath 監視停止対象のログファイルパス
   */
  unwatchWorkerLog(filePath: string): void {
    const watcher = this.workerLogWatchers.get(filePath);
    if (watcher) {
      watcher.close().catch((err) => {
        console.error(`[WorkerLog] Error closing watcher for ${filePath}:`, err);
      });
      this.workerLogWatchers.delete(filePath);
      this.workerLogPositions.delete(filePath);
      console.log(`[WorkerLog] Stopped watching: ${filePath}`);
    }
  }

  /**
   * Worker ログファイル変更時の差分読み取り
   *
   * ORDER_111: 前回位置からの差分を読み取り、worker-log-update イベントを発行
   */
  private handleWorkerLogChange(filePath: string): void {
    try {
      const stats = fs.statSync(filePath);
      const prevPosition = this.workerLogPositions.get(filePath) ?? 0;

      if (stats.size <= prevPosition) {
        // ファイルが切り詰められた場合はリセット
        this.workerLogPositions.set(filePath, stats.size);
        return;
      }

      // 差分を読み込み
      const fd = fs.openSync(filePath, 'r');
      try {
        const buffer = Buffer.alloc(stats.size - prevPosition);
        fs.readSync(fd, buffer, 0, buffer.length, prevPosition);
        const appendedContent = buffer.toString('utf-8');

        // 位置を更新
        this.workerLogPositions.set(filePath, stats.size);

        // イベント発行
        const event: WorkerLogUpdateEvent = {
          filePath,
          appendedContent,
          fileSize: stats.size,
          readPosition: stats.size,
        };

        this.emit('worker-log-update', event);
      } finally {
        fs.closeSync(fd);
      }
    } catch (error) {
      console.error(`[WorkerLog] Error handling change for ${filePath}:`, error);
    }
  }

  /**
   * PLANNING_FAILEDステータスのORDERを再実行
   * ORDER_155 / TASK_1230
   *
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @param options オプション（timeout, model, verbose）
   * @returns 実行結果
   */
  async retryOrder(
    projectId: string,
    orderId: string,
    options?: { timeout?: number; model?: string; verbose?: boolean }
  ): Promise<ExecutionResult> {
    const timeout = options?.timeout ?? 600;
    const model = options?.model ?? 'sonnet';
    const verbose = options?.verbose ?? false;
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) {
      return this.createErrorResult('pm', projectId, orderId, 'Framework path not configured');
    }

    // retry_order.py のパスを取得（getBackendPath()ベース）
    const backendPath = this.getBackendPath();
    if (!backendPath) {
      return this.createErrorResult('pm', projectId, orderId, 'Backend path not configured');
    }
    const retryScriptPath = path.join(backendPath, 'order', 'retry_order.py');
    if (!fs.existsSync(retryScriptPath)) {
      return this.createErrorResult('pm', projectId, orderId, 'retry_order.py not found');
    }

    const executionId = this.generateExecutionId();
    const startedAt = new Date();
    const pythonCommand = this.getPythonCommand();

    // ジョブを登録
    const job: RunningJob = {
      executionId,
      type: 'pm',
      projectId,
      targetId: orderId,
      process: null as unknown as ChildProcess,
      stdout: '',
      stderr: '',
      startedAt,
    };
    this.runningJobs.set(executionId, job);

    // 開始イベントを発行
    this.emit('progress', {
      executionId,
      type: 'pm',
      projectId,
      targetId: orderId,
      status: 'running',
      lastOutput: 'ORDER再実行を開始...',
    } as ExecutionProgress);

    try {
      const args = [
        retryScriptPath,
        projectId,
        orderId,
        '--timeout', String(timeout),
        '--model', model,
        '--json'
      ];

      if (verbose) {
        args.push('--verbose');
      }

      console.log(`[ScriptExecution] Executing retry_order.py: ${pythonCommand} ${args.join(' ')}`);

      const result = await this.runPythonScript(pythonCommand, args, frameworkPath, timeout * 1000 + 30000);

      this.runningJobs.delete(executionId);

      if (!result.success) {
        const errorResult = this.createExecutionResult(
          'pm', projectId, orderId, executionId, startedAt,
          false, result.stdout, result.stderr, result.exitCode || null,
          result.error || 'ORDER再実行が失敗しました'
        );
        this.addToHistory(errorResult);
        this.emitComplete(errorResult);
        return errorResult;
      }

      // 成功
      const successResult = this.createExecutionResult(
        'pm', projectId, orderId, executionId, startedAt,
        true, result.stdout, result.stderr, result.exitCode || 0
      );
      this.addToHistory(successResult);
      this.emitComplete(successResult);
      return successResult;

    } catch (error) {
      console.error(`[ScriptExecution] Retry order error:`, error);
      this.runningJobs.delete(executionId);
      const errorResult = this.createExecutionResult(
        'pm', projectId, orderId, executionId, startedAt,
        false, job.stdout, job.stderr, null,
        `予期しないエラー: ${error instanceof Error ? error.message : String(error)}`
      );
      this.addToHistory(errorResult);
      this.emitComplete(errorResult);
      return errorResult;
    }
  }

  // =============================================================================
  // ORDER_062: フルオートORDER実行
  // =============================================================================

  /**
   * フルオートORDER実行
   *
   * ORDER_062: PM処理→Worker→レビューを自動ループ実行する
   * backend/worker/full_auto.py をspawnで呼び出す
   *
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @param options オプション（maxCycles, timeout, model, verbose）
   * @returns 実行結果
   */
  async executeFullAuto(
    projectId: string,
    orderId: string,
    options?: { maxCycles?: number; timeout?: number; model?: string; verbose?: boolean }
  ): Promise<ExecutionResult> {
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) {
      return this.createErrorResult('worker', projectId, orderId, 'Framework path not configured');
    }

    const backendPath = this.getBackendPath();
    if (!backendPath) {
      return this.createErrorResult('worker', projectId, orderId, 'Backend path not configured');
    }

    const fullAutoScriptPath = path.join(backendPath, 'worker', 'full_auto.py');
    if (!fs.existsSync(fullAutoScriptPath)) {
      return this.createErrorResult('worker', projectId, orderId, 'full_auto.py not found');
    }

    const maxCycles = options?.maxCycles ?? 50;
    const timeout = options?.timeout ?? 1800;
    const model = options?.model ?? 'sonnet';
    const verbose = options?.verbose ?? false;

    const executionId = this.generateExecutionId();
    const startedAt = new Date();
    const pythonCommand = this.getPythonCommand();

    // ジョブを登録
    const job: RunningJob = {
      executionId,
      type: 'worker',
      projectId,
      targetId: orderId,
      process: null as unknown as ChildProcess,
      stdout: '',
      stderr: '',
      startedAt,
    };
    this.runningJobs.set(executionId, job);

    // 開始イベントを発行
    this.emit('progress', {
      executionId,
      type: 'worker',
      projectId,
      targetId: orderId,
      status: 'running',
      lastOutput: 'フルオート実行を開始...',
    } as ExecutionProgress);

    try {
      const args = [
        fullAutoScriptPath,
        projectId,
        orderId,
        '--max-cycles', String(maxCycles),
        '--timeout', String(timeout),
        '--model', model,
        '--json',
      ];

      if (verbose) {
        args.push('--verbose');
      }

      console.log(`[ScriptExecution] Executing full_auto.py: ${pythonCommand} ${args.join(' ')}`);

      // タイムアウトは全タスクの合計時間を考慮（maxCycles * timeout + バッファ）
      const totalTimeoutMs = maxCycles * timeout * 1000 + 60000;

      const result = await this.runPythonScript(
        pythonCommand,
        args,
        frameworkPath,
        totalTimeoutMs,
        (line) => {
          job.stdout += line + '\n';
          this.emit('progress', {
            executionId,
            type: 'worker',
            projectId,
            targetId: orderId,
            status: 'running',
            lastOutput: line,
          } as ExecutionProgress);
        }
      );

      this.runningJobs.delete(executionId);

      if (!result.success) {
        const errorResult = this.createExecutionResult(
          'worker', projectId, orderId, executionId, startedAt,
          false, result.stdout, result.stderr, result.exitCode || null,
          result.error || 'フルオート実行が失敗しました'
        );
        this.addToHistory(errorResult);
        this.emitComplete(errorResult);
        return errorResult;
      }

      const successResult = this.createExecutionResult(
        'worker', projectId, orderId, executionId, startedAt,
        true, result.stdout, result.stderr, result.exitCode || 0
      );
      this.addToHistory(successResult);
      this.emitComplete(successResult);
      return successResult;

    } catch (error) {
      console.error(`[ScriptExecution] Full auto error:`, error);
      this.runningJobs.delete(executionId);
      const errorResult = this.createExecutionResult(
        'worker', projectId, orderId, executionId, startedAt,
        false, '', '',
        null,
        `Unexpected error: ${error instanceof Error ? error.message : String(error)}`
      );
      this.addToHistory(errorResult);
      this.emitComplete(errorResult);
      return errorResult;
    }
  }

  /**
   * 実行中のジョブをキャンセル
   */
  cancelJob(executionId: string): boolean {
    const job = this.runningJobs.get(executionId);
    if (!job) {
      return false;
    }

    // プロセスを終了
    try {
      if (process.platform === 'win32') {
        // Windowsの場合は taskkill を使用
        spawn('taskkill', ['/pid', String(job.process.pid), '/f', '/t'], { shell: true });
      } else {
        job.process.kill('SIGTERM');
      }
    } catch (e) {
      console.warn(`[ScriptExecution] Failed to kill process:`, e);
    }

    this.runningJobs.delete(executionId);

    console.log(`[ScriptExecution] Cancelled job:`, executionId);

    this.emit('progress', {
      executionId,
      type: job.type,
      projectId: job.projectId,
      targetId: job.targetId,
      status: 'failed',
    } as ExecutionProgress);

    return true;
  }
}

// =============================================================================
// シングルトンインスタンス
// =============================================================================

let scriptExecutionService: ScriptExecutionService | null = null;

/**
 * ScriptExecutionServiceのシングルトンインスタンスを取得
 */
export function getScriptExecutionService(): ScriptExecutionService {
  if (!scriptExecutionService) {
    scriptExecutionService = new ScriptExecutionService();
  }
  return scriptExecutionService;
}

/**
 * ScriptExecutionServiceをリセット（テスト用）
 */
export function resetScriptExecutionService(): void {
  scriptExecutionService = null;
}
