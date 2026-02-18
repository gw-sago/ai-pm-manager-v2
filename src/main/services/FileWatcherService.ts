/**
 * FileWatcherService - STATE.md file watcher service
 *
 * Monitors AI PM Framework PROJECTS/(star)/STATE.md files for changes in real-time
 * and emits events when changes are detected.
 *
 * FR-004: File monitoring (STATE.md change detection) implementation
 */

import { watch, type FSWatcher } from 'chokidar';
import * as path from 'node:path';
import * as fs from 'node:fs';
import { EventEmitter } from 'node:events';
import { getConfigService } from './ConfigService';

/**
 * File change event payload
 */
export interface FileChangeEvent {
  /** Path to the changed file */
  filePath: string;
  /** Project name (extracted from PROJECTS/{projectName}/STATE.md) */
  projectName: string;
  /** Event type */
  eventType: 'add' | 'change' | 'unlink';
  /** Event timestamp */
  timestamp: Date;
}

/**
 * Watcher status
 */
export interface WatcherStatus {
  /** Whether watching is active */
  isWatching: boolean;
  /** Framework path being watched */
  frameworkPath: string | null;
  /** Watch pattern */
  watchPattern: string | null;
  /** Number of detected projects */
  projectCount: number;
  /** Watch start time */
  startedAt: Date | null;
}

/**
 * FileWatcherService class
 *
 * Uses chokidar to monitor STATE.md file changes.
 */
export class FileWatcherService extends EventEmitter {
  private watcher: FSWatcher | null = null;
  private frameworkPath: string | null = null;
  private isWatching = false;
  private startedAt: Date | null = null;
  private projectCount = 0;

  constructor() {
    super();
  }

  /**
   * Start watching
   *
   * @param frameworkPath AI PM Framework root directory path
   * @returns Watch start result
   */
  public start(frameworkPath: string): { success: boolean; error?: string } {
    // Stop existing watch if already watching
    if (this.isWatching) {
      this.stop();
    }

    // Validate path
    if (!fs.existsSync(frameworkPath)) {
      return {
        success: false,
        error: `Path does not exist: ${frameworkPath}`,
      };
    }

    const configService = getConfigService();
    const projectsDir = configService.getProjectsBasePath();
    if (!fs.existsSync(projectsDir)) {
      return {
        success: false,
        error: `PROJECTS directory does not exist: ${projectsDir}`,
      };
    }

    // Set watch pattern
    // Watch PROJECTS/*/STATE.md
    const watchPattern = path.join(projectsDir, '*', 'STATE.md');

    try {
      // Start file watching with chokidar
      this.watcher = watch(watchPattern, {
        persistent: true,
        ignoreInitial: false, // Detect existing files on initial scan
        awaitWriteFinish: {
          stabilityThreshold: 500, // Consider write complete after 500ms of stability
          pollInterval: 100,
        },
        usePolling: false, // Use native events for better performance
      });

      // Set event handlers
      this.watcher
        .on('add', (filePath) => this.handleFileEvent('add', filePath))
        .on('change', (filePath) => this.handleFileEvent('change', filePath))
        .on('unlink', (filePath) => this.handleFileEvent('unlink', filePath))
        .on('error', (error: unknown) => this.handleError(error))
        .on('ready', () => this.handleReady());

      this.frameworkPath = frameworkPath;
      this.isWatching = true;
      this.startedAt = new Date();
      this.projectCount = this.countProjects(projectsDir);

      console.log(`[FileWatcher] Watch started: ${watchPattern}`);
      console.log(`[FileWatcher] Detected projects: ${this.projectCount}`);

      return { success: true };
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      console.error(`[FileWatcher] Watch start error: ${errorMessage}`);
      return {
        success: false,
        error: `Failed to start watching: ${errorMessage}`,
      };
    }
  }

  /**
   * Stop watching
   */
  public stop(): void {
    if (this.watcher) {
      this.watcher.close().catch((err) => {
        console.error('[FileWatcher] Watch stop error:', err);
      });
      this.watcher = null;
    }

    this.isWatching = false;
    this.frameworkPath = null;
    this.startedAt = null;
    this.projectCount = 0;

    console.log('[FileWatcher] Watch stopped');
    this.emit('stopped');
  }

  /**
   * Get watcher status
   */
  public getStatus(): WatcherStatus {
    return {
      isWatching: this.isWatching,
      frameworkPath: this.frameworkPath,
      watchPattern: this.frameworkPath
        ? path.join(getConfigService().getProjectsBasePath(), '*', 'STATE.md')
        : null,
      projectCount: this.projectCount,
      startedAt: this.startedAt,
    };
  }

  /**
   * Handle file events
   */
  private handleFileEvent(
    eventType: 'add' | 'change' | 'unlink',
    filePath: string
  ): void {
    const projectName = this.extractProjectName(filePath);
    const event: FileChangeEvent = {
      filePath,
      projectName,
      eventType,
      timestamp: new Date(),
    };

    // Log output (for Phase 1 verification)
    console.log(
      `[FileWatcher] ${eventType.toUpperCase()}: ${projectName}/STATE.md`
    );
    console.log(`[FileWatcher] Path: ${filePath}`);
    console.log(`[FileWatcher] Time: ${event.timestamp.toISOString()}`);

    // Emit event
    this.emit('change', event);
  }

  /**
   * Handle errors
   */
  private handleError(error: unknown): void {
    const err = error instanceof Error ? error : new Error(String(error));
    console.error('[FileWatcher] Error:', err.message);
    this.emit('error', err);
  }

  /**
   * Handle initial scan completion
   */
  private handleReady(): void {
    console.log('[FileWatcher] Initial scan complete');
    this.emit('ready');
  }

  /**
   * Extract project name from file path
   */
  private extractProjectName(filePath: string): string {
    // Normalize path (convert Windows backslashes to slashes)
    const normalizedPath = filePath.replace(/\\/g, '/');

    // Extract project name from PROJECTS/{projectName}/STATE.md pattern
    const match = normalizedPath.match(/PROJECTS\/([^/]+)\/STATE\.md$/i);
    return match ? match[1] : 'unknown';
  }

  /**
   * Count projects in PROJECTS directory
   */
  private countProjects(projectsDir: string): number {
    try {
      const entries = fs.readdirSync(projectsDir, { withFileTypes: true });
      return entries.filter((entry) => entry.isDirectory()).length;
    } catch {
      return 0;
    }
  }
}

// Export singleton instance
export const fileWatcherService = new FileWatcherService();
