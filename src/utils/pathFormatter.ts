/**
 * Path Formatter Utilities
 *
 * ORDER_064 / TASK_218: 環境変数ベースのパス表示フォーマットユーティリティ
 *
 * フルパスを APPDATA、LOCALAPPDATA、APP_PATH などの環境変数ベースの
 * 表示形式に変換するユーティリティ関数を提供する。
 *
 * 使用例:
 *   formatEnvPath('C:\\Users\\user\\AppData\\Roaming\\foo', envPaths)
 *   // => '%APPDATA%\\foo'
 */

/**
 * 環境変数パスのマップ
 */
export interface EnvPaths {
  APPDATA: string;
  LOCALAPPDATA: string;
  APP_PATH: string;
}

/**
 * フルパスを環境変数ベースの表示形式に変換する
 *
 * 優先順位: APPDATA > LOCALAPPDATA > APP_PATH
 * 該当するプレフィックスが見つかった場合、環境変数名に置換して返す。
 * 該当するものがない場合はそのまま返す。
 *
 * @param fullPath - 変換対象のフルパス
 * @param envPaths - 環境変数パスのマップ（getEnvPaths() の戻り値）
 * @returns 環境変数ベースの表示形式パス（例: %APPDATA%\foo）
 *
 * @example
 * formatEnvPath(
 *   'C:\\Users\\user\\AppData\\Roaming\\ai-pm-manager-v2',
 *   { APPDATA: 'C:\\Users\\user\\AppData\\Roaming', LOCALAPPDATA: '...', APP_PATH: '...' }
 * )
 * // => '%APPDATA%\\ai-pm-manager-v2'
 */
export function formatEnvPath(fullPath: string, envPaths: EnvPaths): string {
  // パス比較は大文字小文字を区別しない（Windows）
  const lowerPath = fullPath.toLowerCase();

  const candidates: Array<{ key: keyof EnvPaths; varName: string }> = [
    { key: 'APPDATA', varName: '%APPDATA%' },
    { key: 'LOCALAPPDATA', varName: '%LOCALAPPDATA%' },
    { key: 'APP_PATH', varName: '%APP_PATH%' },
  ];

  for (const { key, varName } of candidates) {
    const envValue = envPaths[key];
    if (!envValue) continue;

    const lowerEnv = envValue.toLowerCase();

    if (lowerPath.startsWith(lowerEnv)) {
      const remainder = fullPath.slice(envValue.length);
      // 先頭の区切り文字は除去しない（そのまま連結）
      return `${varName}${remainder}`;
    }
  }

  return fullPath;
}

/**
 * 環境変数パスを非同期で取得し、フルパスをフォーマットして返す
 *
 * IPC 経由で環境変数パスを取得し、formatEnvPath を適用する。
 * electronAPI が利用できない環境（SSR等）ではそのままのパスを返す。
 *
 * @param fullPath - 変換対象のフルパス
 * @returns 環境変数ベースの表示形式パス
 *
 * @example
 * const display = await resolveEnvPath('C:\\Users\\user\\AppData\\Roaming\\ai-pm-manager-v2');
 * // => '%APPDATA%\\ai-pm-manager-v2'
 */
export async function resolveEnvPath(fullPath: string): Promise<string> {
  if (!window.electronAPI?.getEnvPaths) {
    return fullPath;
  }

  const envPaths = await window.electronAPI.getEnvPaths();
  return formatEnvPath(fullPath, envPaths);
}
