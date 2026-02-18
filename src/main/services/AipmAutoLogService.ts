/**
 * AipmAutoLogService
 *
 * aipm_auto (Python自動実行スクリプト) の実行ログを監視・取得するサービス
 * ORDER_050: aipm_autoの実行ログをダッシュボードから確認可能にする
 *
 * 機能:
 * - ログディレクトリのファイル監視（chokidar）
 * - ログファイル一覧取得
 * - ログファイル内容読み込み（全文/末尾指定行）
 * - 差分検出とリアルタイム通知
 */

import { watch, type FSWatcher } from 'chokidar';
import * as path from 'node:path';
import * as fs from 'node:fs';
import { EventEmitter } from 'node:events';
import { getConfigService } from './ConfigService';

// =============================================================================
// 型定義
// =============================================================================

/**
 * ログファイル情報
 */
export interface LogFileInfo {
  /** ファイル名 */
  fileName: string;
  /** フルパス */
  filePath: string;
  /** プロジェクト名 */
  projectName: string;
  /** ORDER ID（あれば） */
  orderId?: string;
  /** ファイルサイズ（バイト） */
  size: number;
  /** 更新日時（ISO8601） */
  modifiedAt: string;
  /** 作成日時（ISO8601） */
  createdAt: string;
}

/**
 * ログ内容取得結果
 */
export interface LogContent {
  /** ファイルパス */
  filePath: string;
  /** ログ内容 */
  content: string;
  /** 総行数 */
  totalLines: number;
  /** 取得開始行（0-indexed） */
  startLine: number;
  /** 取得行数 */
  lineCount: number;
  /** ファイル末尾まで取得済みか */
  isAtEnd: boolean;
  /** ファイルサイズ（バイト） */
  fileSize: number;
  /** 読み込み位置（バイト） */
  readPosition: number;
}

/**
 * ログ更新イベント
 */
export interface LogUpdateEvent {
  /** 更新種別 */
  type: 'add' | 'change' | 'unlink';
  /** ファイルパス */
  filePath: string;
  /** プロジェクト名 */
  projectName: string;
  /** ORDER ID（あれば） */
  orderId?: string;
  /** 追加された内容（changeの場合） */
  appendedContent?: string;
  /** 新しいファイルサイズ */
  newSize?: number;
  /** イベント発生日時 */
  timestamp: string;
}

/**
 * 監視状態
 */
export interface LogWatcherStatus {
  /** 監視中かどうか */
  isWatching: boolean;
  /** 監視対象のプロジェクト名 */
  projectName: string | null;
  /** 監視対象のログディレクトリ */
  logDirectory: string | null;
  /** 監視開始日時 */
  startedAt: string | null;
  /** 検出ファイル数 */
  fileCount: number;
}

// =============================================================================
// AipmAutoLogService
// =============================================================================

/**
 * ログファイルの読み込み位置を記録
 */
interface FileReadPosition {
  filePath: string;
  position: number;
  size: number;
}

/**
 * AipmAutoLogService クラス
 *
 * aipm_autoのログファイルを監視し、リアルタイムで内容を取得するサービス
 */
export class AipmAutoLogService extends EventEmitter {
  private watcher: FSWatcher | null = null;
  private watchingProject: string | null = null;
  private watchingDirectory: string | null = null;
  private startedAt: Date | null = null;
  private fileCount = 0;
  private filePositions: Map<string, FileReadPosition> = new Map();

  constructor() {
    super();
  }

  /**
   * AI PM Frameworkのパスを取得
   */
  private getFrameworkPath(): string | null {
    const configService = getConfigService();
    return configService.getActiveFrameworkPath();
  }

  /**
   * プロジェクトのログディレクトリパスを取得
   *
   * aipm_autoのログは以下のいずれかに保存される:
   * 1. {frameworkPath}/logs/aipm_auto/{projectName}/ - プロジェクト共通ログ
   * 2. {frameworkPath}/PROJECTS/{projectName}/RESULT/{orderId}/LOGS/ - ORDER別ログ
   */
  private getLogDirectory(projectName: string, orderId?: string): string | null {
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) return null;

    if (orderId) {
      // ORDER別ログ
      const configService = getConfigService();
      return path.join(configService.getProjectsBasePath(), projectName, 'RESULT', orderId, 'LOGS');
    } else {
      // プロジェクト共通ログ
      return path.join(frameworkPath, 'logs', 'aipm_auto', projectName);
    }
  }

  /**
   * ディレクトリ内のログファイル数をカウント
   */
  private countLogFiles(dirPath: string): number {
    if (!fs.existsSync(dirPath)) return 0;
    try {
      const entries = fs.readdirSync(dirPath, { withFileTypes: true });
      return entries.filter((e) => e.isFile() && e.name.endsWith('.log')).length;
    } catch {
      return 0;
    }
  }

  /**
   * 全プロジェクトのログディレクトリ一覧を取得
   *
   * ログファイルが存在するディレクトリのみを返す。
   * 各ディレクトリにはログファイル数（fileCount）を含める。
   */
  getLogDirectories(): Array<{ projectName: string; logDir: string; exists: boolean; fileCount: number }> {
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) return [];

    const result: Array<{ projectName: string; logDir: string; exists: boolean; fileCount: number }> = [];

    // logs/aipm_auto/ 配下のプロジェクトディレクトリを探索
    const aipmAutoLogsDir = path.join(frameworkPath, 'logs', 'aipm_auto');
    if (fs.existsSync(aipmAutoLogsDir)) {
      try {
        const entries = fs.readdirSync(aipmAutoLogsDir, { withFileTypes: true });
        for (const entry of entries) {
          if (entry.isDirectory()) {
            const logDir = path.join(aipmAutoLogsDir, entry.name);
            const fileCount = this.countLogFiles(logDir);
            // ログファイルが存在するディレクトリのみを追加
            if (fileCount > 0) {
              result.push({
                projectName: entry.name,
                logDir,
                exists: true,
                fileCount,
              });
            }
          }
        }
      } catch (error) {
        console.error('[AipmAutoLog] Error reading log directories:', error);
      }
    }

    return result;
  }

  /**
   * プロジェクトのログファイル一覧を取得
   */
  listLogFiles(projectName: string, orderId?: string): LogFileInfo[] {
    const logDir = this.getLogDirectory(projectName, orderId);
    if (!logDir || !fs.existsSync(logDir)) {
      return [];
    }

    const files: LogFileInfo[] = [];

    try {
      const entries = fs.readdirSync(logDir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isFile() && entry.name.endsWith('.log')) {
          const filePath = path.join(logDir, entry.name);
          const stats = fs.statSync(filePath);

          files.push({
            fileName: entry.name,
            filePath,
            projectName,
            orderId,
            size: stats.size,
            modifiedAt: stats.mtime.toISOString(),
            createdAt: stats.birthtime.toISOString(),
          });
        }
      }

      // 更新日時の降順でソート（最新が先頭）
      files.sort((a, b) => new Date(b.modifiedAt).getTime() - new Date(a.modifiedAt).getTime());
    } catch (error) {
      console.error(`[AipmAutoLog] Error listing log files for ${projectName}:`, error);
    }

    return files;
  }

  /**
   * プロジェクトの全ログファイル一覧を取得（ORDER別含む）
   */
  listAllLogFiles(projectName: string): LogFileInfo[] {
    const allFiles: LogFileInfo[] = [];
    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) return allFiles;

    // プロジェクト共通ログを追加
    allFiles.push(...this.listLogFiles(projectName));

    // RESULT配下のORDER別ログを探索
    const resultDir = path.join(getConfigService().getProjectsBasePath(), projectName, 'RESULT');
    if (fs.existsSync(resultDir)) {
      try {
        const orderDirs = fs.readdirSync(resultDir, { withFileTypes: true });
        for (const orderDir of orderDirs) {
          if (orderDir.isDirectory() && orderDir.name.startsWith('ORDER_')) {
            const logsDir = path.join(resultDir, orderDir.name, 'LOGS');
            if (fs.existsSync(logsDir)) {
              allFiles.push(...this.listLogFiles(projectName, orderDir.name));
            }
          }
        }
      } catch (error) {
        console.error(`[AipmAutoLog] Error listing ORDER logs for ${projectName}:`, error);
      }
    }

    // 更新日時の降順でソート
    allFiles.sort((a, b) => new Date(b.modifiedAt).getTime() - new Date(a.modifiedAt).getTime());

    return allFiles;
  }

  /**
   * ログファイルの内容を取得
   *
   * @param filePath ログファイルのパス
   * @param options 読み込みオプション
   *   - tailLines: 末尾から取得する行数（指定時は末尾から読み込み）
   *   - fromPosition: この位置から読み込み開始（差分取得用）
   */
  readLogFile(
    filePath: string,
    options?: { tailLines?: number; fromPosition?: number }
  ): LogContent | null {
    if (!fs.existsSync(filePath)) {
      return null;
    }

    try {
      const stats = fs.statSync(filePath);
      const fileSize = stats.size;

      if (options?.tailLines !== undefined) {
        // 末尾から指定行数を取得
        return this.readTailLines(filePath, options.tailLines, fileSize);
      }

      if (options?.fromPosition !== undefined) {
        // 指定位置から読み込み（差分取得）
        return this.readFromPosition(filePath, options.fromPosition, fileSize);
      }

      // 全文読み込み
      const content = fs.readFileSync(filePath, 'utf-8');
      const lines = content.split('\n');

      return {
        filePath,
        content,
        totalLines: lines.length,
        startLine: 0,
        lineCount: lines.length,
        isAtEnd: true,
        fileSize,
        readPosition: fileSize,
      };
    } catch (error) {
      console.error(`[AipmAutoLog] Error reading log file ${filePath}:`, error);
      return null;
    }
  }

  /**
   * 末尾から指定行数を読み込み
   */
  private readTailLines(filePath: string, tailLines: number, fileSize: number): LogContent {
    const content = fs.readFileSync(filePath, 'utf-8');
    const lines = content.split('\n');
    const totalLines = lines.length;

    const startLine = Math.max(0, totalLines - tailLines);
    const selectedLines = lines.slice(startLine);

    return {
      filePath,
      content: selectedLines.join('\n'),
      totalLines,
      startLine,
      lineCount: selectedLines.length,
      isAtEnd: true,
      fileSize,
      readPosition: fileSize,
    };
  }

  /**
   * 指定位置から読み込み（差分取得用）
   */
  private readFromPosition(filePath: string, fromPosition: number, fileSize: number): LogContent {
    if (fromPosition >= fileSize) {
      // 新しいデータなし
      return {
        filePath,
        content: '',
        totalLines: 0,
        startLine: 0,
        lineCount: 0,
        isAtEnd: true,
        fileSize,
        readPosition: fileSize,
      };
    }

    const fd = fs.openSync(filePath, 'r');
    try {
      const buffer = Buffer.alloc(fileSize - fromPosition);
      fs.readSync(fd, buffer, 0, buffer.length, fromPosition);
      const content = buffer.toString('utf-8');
      const lines = content.split('\n');

      return {
        filePath,
        content,
        totalLines: lines.length,
        startLine: 0,
        lineCount: lines.length,
        isAtEnd: true,
        fileSize,
        readPosition: fileSize,
      };
    } finally {
      fs.closeSync(fd);
    }
  }

  /**
   * ログ監視を開始
   *
   * @param projectName 監視対象のプロジェクト名
   */
  startWatching(projectName: string): { success: boolean; error?: string } {
    // 既存の監視を停止
    if (this.watcher) {
      this.stopWatching();
    }

    const frameworkPath = this.getFrameworkPath();
    if (!frameworkPath) {
      return { success: false, error: 'Framework path not configured' };
    }

    // プロジェクト共通ログディレクトリ
    const logDir = this.getLogDirectory(projectName);
    if (!logDir) {
      return { success: false, error: 'Failed to get log directory path' };
    }

    // ディレクトリがなければ作成（監視のため）
    if (!fs.existsSync(logDir)) {
      try {
        fs.mkdirSync(logDir, { recursive: true });
      } catch (error) {
        console.warn(`[AipmAutoLog] Could not create log directory: ${logDir}`);
      }
    }

    const watchPattern = path.join(logDir, '*.log');

    try {
      this.watcher = watch(watchPattern, {
        persistent: true,
        ignoreInitial: false,
        awaitWriteFinish: {
          stabilityThreshold: 300,
          pollInterval: 100,
        },
        usePolling: false,
      });

      this.watcher
        .on('add', (filePath) => this.handleFileEvent('add', filePath, projectName))
        .on('change', (filePath) => this.handleFileEvent('change', filePath, projectName))
        .on('unlink', (filePath) => this.handleFileEvent('unlink', filePath, projectName))
        .on('error', (error) => this.handleError(error))
        .on('ready', () => this.handleReady());

      this.watchingProject = projectName;
      this.watchingDirectory = logDir;
      this.startedAt = new Date();
      this.fileCount = 0;

      console.log(`[AipmAutoLog] Started watching: ${watchPattern}`);
      return { success: true };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error(`[AipmAutoLog] Failed to start watching:`, errorMessage);
      return { success: false, error: errorMessage };
    }
  }

  /**
   * ログ監視を停止
   */
  stopWatching(): void {
    if (this.watcher) {
      this.watcher.close().catch((err) => {
        console.error('[AipmAutoLog] Error stopping watcher:', err);
      });
      this.watcher = null;
    }

    this.watchingProject = null;
    this.watchingDirectory = null;
    this.startedAt = null;
    this.fileCount = 0;
    this.filePositions.clear();

    console.log('[AipmAutoLog] Stopped watching');
    this.emit('stopped');
  }

  /**
   * 監視状態を取得
   */
  getStatus(): LogWatcherStatus {
    return {
      isWatching: this.watcher !== null,
      projectName: this.watchingProject,
      logDirectory: this.watchingDirectory,
      startedAt: this.startedAt?.toISOString() ?? null,
      fileCount: this.fileCount,
    };
  }

  /**
   * ファイルイベントを処理
   */
  private handleFileEvent(
    type: 'add' | 'change' | 'unlink',
    filePath: string,
    projectName: string
  ): void {
    console.log(`[AipmAutoLog] ${type.toUpperCase()}: ${path.basename(filePath)}`);

    const event: LogUpdateEvent = {
      type,
      filePath,
      projectName,
      timestamp: new Date().toISOString(),
    };

    if (type === 'add') {
      this.fileCount++;
      // 初期位置を記録
      try {
        const stats = fs.statSync(filePath);
        this.filePositions.set(filePath, {
          filePath,
          position: stats.size,
          size: stats.size,
        });
        event.newSize = stats.size;
      } catch {
        // ファイルが消えた場合など
      }
    } else if (type === 'change') {
      // 差分を取得
      try {
        const stats = fs.statSync(filePath);
        const prevPosition = this.filePositions.get(filePath);
        const prevPos = prevPosition?.position ?? 0;

        if (stats.size > prevPos) {
          // 新しいデータがある
          const content = this.readFromPosition(filePath, prevPos, stats.size);
          if (content && content.content) {
            event.appendedContent = content.content;
          }
        }

        // 位置を更新
        this.filePositions.set(filePath, {
          filePath,
          position: stats.size,
          size: stats.size,
        });
        event.newSize = stats.size;
      } catch {
        // ファイルが消えた場合など
      }
    } else if (type === 'unlink') {
      this.fileCount--;
      this.filePositions.delete(filePath);
    }

    this.emit('update', event);
  }

  /**
   * エラーを処理
   */
  private handleError(error: unknown): void {
    const err = error instanceof Error ? error : new Error(String(error));
    console.error('[AipmAutoLog] Watcher error:', err.message);
    this.emit('error', err);
  }

  /**
   * 準備完了を処理
   */
  private handleReady(): void {
    console.log(`[AipmAutoLog] Watcher ready. Files: ${this.fileCount}`);
    this.emit('ready');
  }

  /**
   * 最新のログファイルを取得
   */
  getLatestLogFile(projectName: string): LogFileInfo | null {
    const files = this.listAllLogFiles(projectName);
    return files.length > 0 ? files[0] : null;
  }
}

// =============================================================================
// シングルトンインスタンス
// =============================================================================

let aipmAutoLogService: AipmAutoLogService | null = null;

/**
 * AipmAutoLogServiceのシングルトンインスタンスを取得
 */
export function getAipmAutoLogService(): AipmAutoLogService {
  if (!aipmAutoLogService) {
    aipmAutoLogService = new AipmAutoLogService();
  }
  return aipmAutoLogService;
}

/**
 * AipmAutoLogServiceをリセット（テスト用）
 */
export function resetAipmAutoLogService(): void {
  if (aipmAutoLogService) {
    aipmAutoLogService.stopWatching();
  }
  aipmAutoLogService = null;
}
