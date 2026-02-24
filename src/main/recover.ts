/**
 * Recover IPC Handlers
 *
 * ORDER/TASKの失敗状態検出・修復のIPCハンドラ
 * ORDER_060: リカバリ機能
 */

import { ipcMain } from 'electron';
import { spawn } from 'child_process';
import * as path from 'node:path';
import * as fs from 'node:fs';
import { getConfigService } from './services/ConfigService';

export interface RecoverOrderResult {
  success: boolean;
  project_id: string;
  order_id: string;
  dry_run?: boolean;
  detected?: {
    order: Record<string, unknown> | null;
    stalled_tasks: Array<Record<string, unknown>>;
    rejected_tasks: Array<Record<string, unknown>>;
    has_failure: boolean;
    failure_reasons: string[];
  };
  recovered_tasks?: Array<{
    task_id: string;
    previous_status: string;
    new_status: string | null;
    reason: string;
    locks_released?: number;
    reject_count_reset?: boolean;
    error?: string;
  }>;
  order_recovered?: boolean;
  message?: string;
  error?: string;
}

/**
 * リカバリIPCハンドラを登録
 */
export function registerRecoverHandlers(): void {
  // ORDER_060: ORDER失敗状態検出・修復
  ipcMain.handle(
    'recover-order',
    async (
      _event,
      projectId: string,
      orderId: string,
      options?: { stallMinutes?: number; dryRun?: boolean }
    ): Promise<RecoverOrderResult> => {
      console.log('[Recover IPC] recover-order called:', { projectId, orderId, options });

      const configService = getConfigService();
      const backendPath = configService.getBackendPath();
      const pythonScript = path.join(backendPath, 'recover', 'ipc_recover.py');

      if (!fs.existsSync(pythonScript)) {
        console.error(`[Recover IPC] ipc_recover.py not found: ${pythonScript}`);
        return {
          success: false,
          project_id: projectId,
          order_id: orderId,
          error: `Recovery script not found: ${pythonScript}`,
        };
      }

      const pythonCommand = configService.getPythonPath();
      const args = [pythonScript, projectId, orderId];

      if (options?.stallMinutes !== undefined) {
        args.push('--stall-minutes', String(options.stallMinutes));
      }
      if (options?.dryRun) {
        args.push('--dry-run');
      }

      console.log('[Recover IPC] Executing:', pythonCommand, args.join(' '));

      return new Promise((resolve) => {
        const proc = spawn(pythonCommand, args, {
          cwd: path.dirname(pythonScript),
          env: {
            ...process.env,
            PYTHONIOENCODING: 'utf-8',
          },
        });

        let stdout = '';
        let stderr = '';

        proc.on('error', (err) => {
          console.error('[Recover IPC] Failed to spawn python:', err.message);
          resolve({
            success: false,
            project_id: projectId,
            order_id: orderId,
            error: `Failed to spawn recovery script: ${err.message}`,
          });
        });

        proc.stdout.on('data', (data) => {
          stdout += data.toString();
        });

        proc.stderr.on('data', (data) => {
          stderr += data.toString();
        });

        proc.on('close', (code) => {
          if (stderr) {
            console.warn('[Recover IPC] stderr:', stderr);
          }

          if (code !== 0 && !stdout) {
            console.error('[Recover IPC] Python script failed with code:', code, 'stderr:', stderr);
            resolve({
              success: false,
              project_id: projectId,
              order_id: orderId,
              error: `Recovery script failed (exit code ${code}): ${stderr}`,
            });
            return;
          }

          try {
            const result = JSON.parse(stdout) as RecoverOrderResult;
            console.log('[Recover IPC] Result:', JSON.stringify(result).substring(0, 200));
            resolve(result);
          } catch (parseError) {
            console.error('[Recover IPC] JSON parse error:', parseError, 'stdout:', stdout);
            resolve({
              success: false,
              project_id: projectId,
              order_id: orderId,
              error: `Failed to parse recovery result: ${parseError}`,
            });
          }
        });
      });
    }
  );

  console.log('[Recover] IPC handlers registered');
}
