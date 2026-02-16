/**
 * AI PM Framework ディレクトリ選択ダイアログ
 *
 * Electronのdialog.showOpenDialogを使用してディレクトリを選択し、
 * AI PM Frameworkとしての妥当性を検証します。
 */

import { dialog, BrowserWindow, ipcMain } from 'electron';
import * as fs from 'node:fs';
import * as path from 'node:path';

/**
 * ディレクトリ検証結果
 */
export interface DirectoryValidationResult {
  isValid: boolean;
  path: string;
  errors: string[];
  warnings: string[];
  details: {
    hasProjectsDir: boolean;
    hasReadme: boolean;
    projectCount: number;
    projectNames: string[];
  };
}

/**
 * ディレクトリ選択結果
 */
export interface DirectorySelectionResult {
  canceled: boolean;
  filePaths: string[];
  validation?: DirectoryValidationResult;
}

/**
 * AI PM Frameworkディレクトリの妥当性を検証
 *
 * @param dirPath 検証対象のディレクトリパス
 * @returns 検証結果
 */
export function validateAIPMDirectory(dirPath: string): DirectoryValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  let hasProjectsDir = false;
  let hasReadme = false;
  let projectCount = 0;
  let projectNames: string[] = [];

  // ディレクトリが存在するか確認
  if (!fs.existsSync(dirPath)) {
    errors.push('指定されたパスが存在しません');
    return {
      isValid: false,
      path: dirPath,
      errors,
      warnings,
      details: { hasProjectsDir, hasReadme, projectCount, projectNames },
    };
  }

  // ディレクトリかどうか確認
  const stats = fs.statSync(dirPath);
  if (!stats.isDirectory()) {
    errors.push('指定されたパスはディレクトリではありません');
    return {
      isValid: false,
      path: dirPath,
      errors,
      warnings,
      details: { hasProjectsDir, hasReadme, projectCount, projectNames },
    };
  }

  // PROJECTS/ ディレクトリの存在確認（必須）
  const projectsPath = path.join(dirPath, 'PROJECTS');
  if (fs.existsSync(projectsPath) && fs.statSync(projectsPath).isDirectory()) {
    hasProjectsDir = true;

    // プロジェクト一覧を取得
    try {
      const entries = fs.readdirSync(projectsPath, { withFileTypes: true });
      projectNames = entries
        .filter((entry) => entry.isDirectory())
        .map((entry) => entry.name);
      projectCount = projectNames.length;

      if (projectCount === 0) {
        warnings.push('PROJECTS/ ディレクトリ内にプロジェクトがありません');
      }
    } catch (err) {
      warnings.push('PROJECTS/ ディレクトリの読み取りに失敗しました');
    }
  } else {
    errors.push('PROJECTS/ ディレクトリが存在しません（AI PM Framework必須要件）');
  }

  // README.md の存在確認（オプション）
  const readmePath = path.join(dirPath, 'README.md');
  if (fs.existsSync(readmePath)) {
    hasReadme = true;
  } else {
    warnings.push('README.md が存在しません（オプション）');
  }

  // 総合判定
  const isValid = errors.length === 0;

  return {
    isValid,
    path: dirPath,
    errors,
    warnings,
    details: {
      hasProjectsDir,
      hasReadme,
      projectCount,
      projectNames,
    },
  };
}

/**
 * ディレクトリ選択ダイアログを開く
 *
 * @param parentWindow 親ウィンドウ（nullの場合はモーダルなし）
 * @returns 選択結果と検証結果
 */
export async function openDirectoryDialog(
  parentWindow: BrowserWindow | null
): Promise<DirectorySelectionResult> {
  const options = {
    title: 'AI PM Framework ディレクトリを選択',
    properties: ['openDirectory'] as ('openDirectory')[],
    buttonLabel: '選択',
  };

  const result = parentWindow
    ? await dialog.showOpenDialog(parentWindow, options)
    : await dialog.showOpenDialog(options);

  if (result.canceled || result.filePaths.length === 0) {
    return {
      canceled: true,
      filePaths: [],
    };
  }

  // 選択されたディレクトリを検証
  const selectedPath = result.filePaths[0];
  const validation = validateAIPMDirectory(selectedPath);

  return {
    canceled: false,
    filePaths: result.filePaths,
    validation,
  };
}

/**
 * IPC ハンドラを登録
 *
 * レンダラープロセスから呼び出せるようにIPCハンドラを設定します。
 */
export function registerDialogHandlers(): void {
  // ディレクトリ選択ダイアログ
  ipcMain.handle('dialog:selectDirectory', async (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    return openDirectoryDialog(win);
  });

  // ディレクトリ検証（パス指定）
  ipcMain.handle('dialog:validateDirectory', async (_event, dirPath: string) => {
    return validateAIPMDirectory(dirPath);
  });

  console.log('[Dialog] IPC handlers registered');
}
