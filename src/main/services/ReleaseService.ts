/**
 * ReleaseService
 *
 * RELEASE_LOG.md を解析してリリース情報を取得するサービス
 * ORDER_045: ORDER成果物タブの情報充実化
 * TASK_596: ReleaseService実装
 * ORDER_108 / TASK_994: リリース実行機能（release_order.py呼び出し）追加
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { spawn } from 'child_process';
import { getConfigService } from './ConfigService';

/**
 * リリースファイル情報
 */
export interface ReleaseFile {
  /** ファイル種別 (NEW/MODIFIED) */
  type: 'NEW' | 'MODIFIED';
  /** ファイルパス */
  path: string;
}

/**
 * リリース情報
 */
export interface ReleaseInfo {
  /** リリースID (RELEASE_YYYY-MM-DD_NNN) */
  releaseId: string;
  /** リリース日時 */
  date: string;
  /** 実行者 */
  executor: string;
  /** 対象ORDER ID */
  orderId: string;
  /** ファイル数 */
  fileCount: number;
  /** 概要 */
  summary?: string;
  /** リリースファイル一覧 */
  files: ReleaseFile[];
  /** 変更内容 */
  changes?: string[];
}

/**
 * ORDER単位のリリース情報
 */
export interface OrderReleaseInfo {
  /** リリースがあるかどうか */
  hasRelease: boolean;
  /** リリース情報一覧（新しい順） */
  releases: ReleaseInfo[];
  /** 最新バージョン（RELEASE_LOG.mdから推測、なければnull） */
  latestVersion?: string;
}
/**
 * リリース実行結果
 * ORDER_108 / TASK_994
 */
export interface ReleaseResult {
  /** 成功かどうか */
  success: boolean;
  /** ORDER ID */
  orderId: string;
  /** プロジェクトID */
  projectId: string;
  /** ORDERタイトル */
  orderTitle?: string;
  /** リリースID（成功時） */
  releaseId?: string;
  /** リリースログパス（成功時） */
  logPath?: string;
  /** リリース対象ファイル数 */
  fileCount?: number;
  /** リリース対象ファイル一覧 */
  files?: Array<{ path: string; type: string }>;
  /** ステータス更新済みかどうか */
  statusUpdated?: boolean;
  /** 更新されたBACKLOG IDリスト */
  backlogUpdated?: string[];
  /** エラーメッセージ（失敗時） */
  error?: string;
  /** 実行日時 */
  executedAt?: string;
}

/**
 * リリースdry-run結果
 * ORDER_108 / TASK_994
 */
export interface ReleaseDryRunResult {
  /** 成功かどうか */
  success: boolean;
  /** ORDER ID */
  orderId: string;
  /** プロジェクトID */
  projectId: string;
  /** ORDERタイトル */
  orderTitle?: string;
  /** リリース対象ファイル数 */
  fileCount?: number;
  /** リリース対象ファイル一覧 */
  files?: Array<{ path: string; type: string }>;
  /** 関連BACKLOG一覧 */
  backlogItems?: Array<{ id: string; title: string; status: string }>;
  /** メッセージ */
  message?: string;
  /** エラーメッセージ（失敗時） */
  error?: string;
}

/** リリーススクリプト実行タイムアウト（ミリ秒） */
const RELEASE_TIMEOUT_MS = 60 * 1000; // 60秒


/**
 * ReleaseService クラス
 */
export class ReleaseService {
  /**
   * AI PM Frameworkのルートパスを取得
   */
  private getFrameworkPath(): string | null {
    const configService = getConfigService();

    // getAipmFrameworkPath() を使用（aipmFrameworkPath または activeFrameworkPath を返す）
    return configService.getAipmFrameworkPath();
  }

  /**
   * バックエンドパスを取得（Pythonスクリプト用）
   * ORDER_159: frameworkPath/backendPath分離
   */
  private getBackendPath(): string | null {
    const configService = getConfigService();
    return configService.getBackendPath();
  }

  /**
   * release_order.py のパスを取得
   * ORDER_108 / TASK_994
   */
  private getReleaseScriptPath(): string | null {
    const backendPath = this.getBackendPath();
    if (!backendPath) return null;

    const scriptPath = path.join(backendPath, 'release', 'release_order.py');
    if (fs.existsSync(scriptPath)) {
      return scriptPath;
    }

    console.log(`[ReleaseService] release_order.py not found: ${scriptPath}`);
    return null;
  }

  /**
   * Pythonスクリプトを実行する共通ヘルパー
   * ORDER_108 / TASK_994: ScriptExecutionService.runPythonScript と同等パターン
   */
  private async runPythonScript(
    pythonCommand: string,
    args: string[],
    cwd: string,
    timeoutMs: number = RELEASE_TIMEOUT_MS
  ): Promise<{ success: boolean; stdout: string; stderr: string; exitCode: number | null; error?: string }> {
    console.log(`[ReleaseService] Running: ${pythonCommand} ${args.join(' ')}`);

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
          console.error(`[ReleaseService] Script timed out after ${timeoutMs}ms`);
          try {
            childProcess.kill('SIGTERM');
          } catch (e) {
            console.error(`[ReleaseService] Failed to kill process:`, e);
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
          console.log(`[ReleaseService stdout] ${logOutput.trim()}`);
        });
      }

      if (childProcess.stderr) {
        childProcess.stderr.setEncoding('utf-8');
        childProcess.stderr.on('data', (data: string) => {
          stderr += data;
          console.warn(`[ReleaseService stderr] ${data.trim()}`);
        });
      }

      childProcess.on('close', (exitCode) => {
        clearTimeout(timeout);
        if (resolved) return;
        resolved = true;

        console.log(`[ReleaseService] Script completed - exitCode: ${exitCode}`);
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

        console.error(`[ReleaseService] Script error:`, error);
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
   * release_order.py の JSON出力をパース
   * ORDER_108 / TASK_994
   */
  private parseReleaseScriptOutput(stdout: string): Record<string, unknown> | null {
    try {
      const jsonMatch = stdout.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      }
    } catch (e) {
      console.warn(`[ReleaseService] Failed to parse release script output:`, e);
    }
    return null;
  }

  /**
   * リリースを実行
   * ORDER_108 / TASK_994: release_order.py を呼び出してリリース処理を実行
   *
   * @param projectName プロジェクト名
   * @param orderId ORDER ID
   * @returns リリース実行結果
   */
  public async executeRelease(projectName: string, orderId: string): Promise<ReleaseResult> {
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) {
      return { success: false, orderId, projectId: projectName, error: 'Framework path not configured' };
    }

    const scriptPath = this.getReleaseScriptPath();
    if (!scriptPath) {
      return { success: false, orderId, projectId: projectName, error: 'release_order.py not found' };
    }

    const pythonCommand = getConfigService().getPythonPath();
    const args = [scriptPath, projectName, orderId, '--json'];

    console.log(`[ReleaseService] Executing release: ${projectName} ${orderId}`);

    const result = await this.runPythonScript(pythonCommand, args, frameworkPath);

    if (!result.success) {
      const parsed = this.parseReleaseScriptOutput(result.stdout);
      return {
        success: false, orderId, projectId: projectName,
        error: (parsed?.error as string) || result.error || 'Release execution failed',
      };
    }

    const parsed = this.parseReleaseScriptOutput(result.stdout);
    if (!parsed) {
      return { success: false, orderId, projectId: projectName, error: 'Failed to parse release script output' };
    }

    if (!parsed.success) {
      return { success: false, orderId, projectId: projectName, error: (parsed.error as string) || 'Release failed' };
    }

    return {
      success: true,
      orderId,
      projectId: projectName,
      orderTitle: parsed.order_title as string | undefined,
      releaseId: parsed.release_id as string | undefined,
      logPath: parsed.log_path as string | undefined,
      fileCount: parsed.file_count as number | undefined,
      files: parsed.files as Array<{ path: string; type: string }> | undefined,
      statusUpdated: parsed.status_updated as boolean | undefined,
      backlogUpdated: parsed.backlog_updated as string[] | undefined,
      executedAt: parsed.executed_at as string | undefined,
    };
  }

  /**
   * リリースdry-runを実行
   * ORDER_108 / TASK_994: release_order.py --dry-run を呼び出して事前確認
   *
   * @param projectName プロジェクト名
   * @param orderId ORDER ID
   * @returns dry-run結果
   */
  public async executeReleaseDryRun(projectName: string, orderId: string): Promise<ReleaseDryRunResult> {
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) {
      return { success: false, orderId, projectId: projectName, error: 'Framework path not configured' };
    }

    const scriptPath = this.getReleaseScriptPath();
    if (!scriptPath) {
      return { success: false, orderId, projectId: projectName, error: 'release_order.py not found' };
    }

    const pythonCommand = getConfigService().getPythonPath();
    const args = [scriptPath, projectName, orderId, '--dry-run', '--json'];

    console.log(`[ReleaseService] Executing release dry-run: ${projectName} ${orderId}`);

    const result = await this.runPythonScript(pythonCommand, args, frameworkPath);

    if (!result.success) {
      const parsed = this.parseReleaseScriptOutput(result.stdout);
      return {
        success: false, orderId, projectId: projectName,
        error: (parsed?.error as string) || result.error || 'Release dry-run failed',
      };
    }

    const parsed = this.parseReleaseScriptOutput(result.stdout);
    if (!parsed) {
      return { success: false, orderId, projectId: projectName, error: 'Failed to parse release script output' };
    }

    if (!parsed.success) {
      return { success: false, orderId, projectId: projectName, error: (parsed.error as string) || 'Dry-run failed' };
    }

    return {
      success: true,
      orderId,
      projectId: projectName,
      orderTitle: parsed.order_title as string | undefined,
      fileCount: parsed.file_count as number | undefined,
      files: parsed.files as Array<{ path: string; type: string }> | undefined,
      backlogItems: parsed.backlog_items as Array<{ id: string; title: string; status: string }> | undefined,
      message: parsed.message as string | undefined,
    };
  }

  /**
   * プロジェクトのRELEASE_LOG.mdパスを取得
   */
  private getReleaseLogPath(projectName: string): string | null {
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) return null;

    const configService = getConfigService();
    return path.join(configService.getProjectsBasePath(), projectName, 'RELEASE_LOG.md');
  }

  /**
   * RELEASE_LOG.md を読み込んで解析
   */
  private parseReleaseLog(content: string): ReleaseInfo[] {
    const releases: ReleaseInfo[] = [];
    const lines = content.split('\n');

    let currentRelease: Partial<ReleaseInfo> | null = null;
    let inFileTable = false;
    let inChangesSection = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // リリースIDを検出 (## RELEASE_YYYY-MM-DD_NNN)
      const releaseMatch = line.match(/^## (RELEASE_\d{4}-\d{2}-\d{2}_\d{3})/);
      if (releaseMatch) {
        // 前のリリースを保存
        if (currentRelease?.releaseId) {
          releases.push(currentRelease as ReleaseInfo);
        }
        currentRelease = {
          releaseId: releaseMatch[1],
          files: [],
          changes: [],
        };
        inFileTable = false;
        inChangesSection = false;
        continue;
      }

      if (!currentRelease) continue;

      // 日時を検出
      const dateMatch = line.match(/- \*\*日時\*\*:\s*(.+)/);
      if (dateMatch) {
        currentRelease.date = dateMatch[1].trim();
        continue;
      }

      // ORDER IDを検出
      const orderMatch = line.match(/- \*\*ORDER\*\*:\s*(ORDER_\d+)/);
      if (orderMatch) {
        currentRelease.orderId = orderMatch[1];
        continue;
      }

      // 実行者を検出
      const executorMatch = line.match(/- \*\*実行者\*\*:\s*(.+)/);
      if (executorMatch) {
        currentRelease.executor = executorMatch[1].trim();
        continue;
      }

      // ファイル数を検出
      const fileCountMatch = line.match(/- \*\*ファイル数\*\*:\s*(\d+)/);
      if (fileCountMatch) {
        currentRelease.fileCount = parseInt(fileCountMatch[1], 10);
        continue;
      }

      // 概要を検出
      const summaryMatch = line.match(/- \*\*概要\*\*:\s*(.+)/);
      if (summaryMatch) {
        currentRelease.summary = summaryMatch[1].trim();
        continue;
      }

      // リリースファイルセクション検出
      if (line.includes('### リリースファイル')) {
        inFileTable = true;
        inChangesSection = false;
        continue;
      }

      // 変更内容セクション検出
      if (line.includes('### 変更内容')) {
        inFileTable = false;
        inChangesSection = true;
        continue;
      }

      // 次のセクション（---）または次のリリースで終了
      if (line.startsWith('---') || line.startsWith('## ')) {
        inFileTable = false;
        inChangesSection = false;
        if (line.startsWith('---')) continue;
      }

      // ファイルテーブルの解析
      if (inFileTable && line.startsWith('|') && !line.includes('---') && !line.includes('種別')) {
        const columns = line.split('|').map((col) => col.trim()).filter(Boolean);
        if (columns.length >= 3) {
          const typeStr = columns[1].toUpperCase();
          const filePath = columns[2];
          if ((typeStr === 'NEW' || typeStr === 'MODIFIED') && filePath) {
            currentRelease.files!.push({
              type: typeStr as 'NEW' | 'MODIFIED',
              path: filePath,
            });
          }
        }
        continue;
      }

      // 変更内容の解析
      if (inChangesSection && line.startsWith('- ')) {
        currentRelease.changes!.push(line.substring(2).trim());
        continue;
      }
    }

    // 最後のリリースを保存
    if (currentRelease?.releaseId) {
      releases.push(currentRelease as ReleaseInfo);
    }

    return releases;
  }

  /**
   * プロジェクトの全リリース情報を取得
   */
  public getAllReleases(projectName: string): ReleaseInfo[] {
    const releaseLogPath = this.getReleaseLogPath(projectName);
    if (!releaseLogPath) {
      console.log('[ReleaseService] Framework path not configured');
      return [];
    }

    if (!fs.existsSync(releaseLogPath)) {
      console.log(`[ReleaseService] RELEASE_LOG.md not found: ${releaseLogPath}`);
      return [];
    }

    try {
      const content = fs.readFileSync(releaseLogPath, 'utf-8');
      return this.parseReleaseLog(content);
    } catch (error) {
      console.error('[ReleaseService] Failed to read RELEASE_LOG.md:', error);
      return [];
    }
  }

  /**
   * 特定ORDERのリリース情報を取得
   */
  public getReleaseInfoByOrderId(projectName: string, orderId: string): OrderReleaseInfo {
    const allReleases = this.getAllReleases(projectName);

    // ORDER IDでフィルタ
    const orderReleases = allReleases.filter((release) => release.orderId === orderId);

    if (orderReleases.length === 0) {
      return {
        hasRelease: false,
        releases: [],
      };
    }

    // バージョン情報の抽出を試みる（概要からvX.X.X形式を探す）
    let latestVersion: string | undefined;
    for (const release of orderReleases) {
      if (release.summary) {
        const versionMatch = release.summary.match(/v\d+\.\d+\.\d+/);
        if (versionMatch) {
          latestVersion = versionMatch[0];
          break;
        }
      }
      // 変更内容からも探す
      if (release.changes) {
        for (const change of release.changes) {
          const versionMatch = change.match(/v\d+\.\d+\.\d+/);
          if (versionMatch) {
            latestVersion = versionMatch[0];
            break;
          }
        }
        if (latestVersion) break;
      }
    }

    return {
      hasRelease: true,
      releases: orderReleases,
      latestVersion,
    };
  }
}

// シングルトンインスタンス
let releaseServiceInstance: ReleaseService | null = null;

/**
 * ReleaseServiceインスタンスを取得
 */
export function getReleaseService(): ReleaseService {
  if (!releaseServiceInstance) {
    releaseServiceInstance = new ReleaseService();
  }
  return releaseServiceInstance;
}

/**
 * ReleaseServiceインスタンスをリセット（テスト用）
 */
export function resetReleaseService(): void {
  releaseServiceInstance = null;
}
