/**
 * Artifact Path Utilities
 *
 * ORDER_053 / TASK_179: Roaming絶対パス解決ユーティリティ
 *
 * タスク詳細・レポート画面でORDER IDとプロジェクトIDを受け取り、
 * Roaming絶対パスで 06_ARTIFACTS/ ディレクトリパスおよび
 * 個別ファイルの絶対パスを構築するユーティリティ関数。
 *
 * 設計:
 * - userDataPath は IPC 経由で取得（%APPDATA%/ai-pm-manager-v2/）
 * - パス構造: {userDataPath}/PROJECTS/{projectId}/RESULT/{orderId}/06_ARTIFACTS/
 * - 代替パス: 08_ARTIFACTS も考慮（06_ARTIFACTS が標準）
 *
 * @see BUG_011 - WorkerがPROJECTS/配下を相対パスで参照すると
 *               LocalAppDataに書き込まれる問題の防止
 */

/** パス区切り文字（Windows: \、その他: /） */
const SEP = '\\';

/**
 * パスセグメントを結合する（Windows形式）
 */
function joinPath(...segments: string[]): string {
  return segments.join(SEP);
}

/**
 * 06_ARTIFACTS ディレクトリの絶対パスを構築する
 *
 * @param userDataPath - %APPDATA%/ai-pm-manager-v2/ のRoaming絶対パス
 * @param projectId - プロジェクトID（例: ai_pm_manager_v2）
 * @param orderId - ORDER ID（例: ORDER_053）
 * @returns 06_ARTIFACTS ディレクトリの絶対パス
 *
 * @example
 * buildArtifactsDirPath(
 *   'C:\\Users\\user\\AppData\\Roaming\\ai-pm-manager-v2',
 *   'ai_pm_manager_v2',
 *   'ORDER_053'
 * )
 * // => 'C:\\Users\\user\\AppData\\Roaming\\ai-pm-manager-v2\\PROJECTS\\ai_pm_manager_v2\\RESULT\\ORDER_053\\06_ARTIFACTS'
 */
export function buildArtifactsDirPath(
  userDataPath: string,
  projectId: string,
  orderId: string
): string {
  return joinPath(userDataPath, 'PROJECTS', projectId, 'RESULT', orderId, '06_ARTIFACTS');
}

/**
 * 成果物ファイルの絶対パスを構築する
 *
 * @param userDataPath - %APPDATA%/ai-pm-manager-v2/ のRoaming絶対パス
 * @param projectId - プロジェクトID（例: ai_pm_manager_v2）
 * @param orderId - ORDER ID（例: ORDER_053）
 * @param relativeFilePath - 06_ARTIFACTS/ からの相対ファイルパス（例: report.md）
 * @returns ファイルの絶対パス
 *
 * @example
 * buildArtifactFilePath(
 *   'C:\\Users\\user\\AppData\\Roaming\\ai-pm-manager-v2',
 *   'ai_pm_manager_v2',
 *   'ORDER_053',
 *   'report.md'
 * )
 * // => 'C:\\Users\\user\\AppData\\Roaming\\ai-pm-manager-v2\\PROJECTS\\ai_pm_manager_v2\\RESULT\\ORDER_053\\06_ARTIFACTS\\report.md'
 */
export function buildArtifactFilePath(
  userDataPath: string,
  projectId: string,
  orderId: string,
  relativeFilePath: string
): string {
  return joinPath(
    buildArtifactsDirPath(userDataPath, projectId, orderId),
    relativeFilePath
  );
}

/**
 * ユーザーデータパスを非同期で取得し、06_ARTIFACTS ディレクトリの絶対パスを解決する
 *
 * IPC 経由で %APPDATA%/ai-pm-manager-v2/ を取得し、
 * Roaming絶対パスを構築して返す。
 *
 * @param projectId - プロジェクトID（例: ai_pm_manager_v2）
 * @param orderId - ORDER ID（例: ORDER_053）
 * @returns 06_ARTIFACTS ディレクトリのRoaming絶対パス
 *
 * @example
 * const dirPath = await resolveArtifactsDirPath('ai_pm_manager_v2', 'ORDER_053');
 * await window.electronAPI.openArtifactsFolder(dirPath);
 */
export async function resolveArtifactsDirPath(
  projectId: string,
  orderId: string
): Promise<string> {
  const userDataPath = await window.electronAPI.getUserDataPath();
  return buildArtifactsDirPath(userDataPath, projectId, orderId);
}

/**
 * ユーザーデータパスを非同期で取得し、成果物ファイルの絶対パスを解決する
 *
 * IPC 経由で %APPDATA%/ai-pm-manager-v2/ を取得し、
 * Roaming絶対パスを構築して返す。
 *
 * @param projectId - プロジェクトID（例: ai_pm_manager_v2）
 * @param orderId - ORDER ID（例: ORDER_053）
 * @param relativeFilePath - 06_ARTIFACTS/ からの相対ファイルパス（例: report.md）
 * @returns ファイルのRoaming絶対パス
 *
 * @example
 * const filePath = await resolveArtifactFilePath('ai_pm_manager_v2', 'ORDER_053', 'report.md');
 * await window.electronAPI.downloadArtifactFile(filePath, 'report.md');
 */
export async function resolveArtifactFilePath(
  projectId: string,
  orderId: string,
  relativeFilePath: string
): Promise<string> {
  const userDataPath = await window.electronAPI.getUserDataPath();
  return buildArtifactFilePath(userDataPath, projectId, orderId, relativeFilePath);
}
