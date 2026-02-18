/**
 * Preload Script
 *
 * レンダラープロセスからメインプロセスのAPIにアクセスするためのブリッジを提供します。
 * contextIsolation: true の環境で安全にAPIを公開します。
 */

import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron';

/**
 * ディレクトリ検証結果の型定義
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
 * ディレクトリ選択結果の型定義
 */
export interface DirectorySelectionResult {
  canceled: boolean;
  filePaths: string[];
  validation?: DirectoryValidationResult;
}

/**
 * ファイル変更イベントの型定義
 */
export interface FileChangeEvent {
  filePath: string;
  projectName: string;
  eventType: 'add' | 'change' | 'unlink';
  timestamp: Date;
}

/**
 * 監視ステータスの型定義
 */
export interface WatcherStatus {
  isWatching: boolean;
  frameworkPath: string | null;
  watchPattern: string | null;
  projectCount: number;
  startedAt: Date | null;
}

/**
 * ウィンドウ設定
 */
export interface WindowConfig {
  width: number;
  height: number;
  x: number | null;
  y: number | null;
}

/**
 * アプリケーション設定
 */
export interface AppConfig {
  version: string;
  window?: WindowConfig;
}

/**
 * 設定保存リクエスト
 */
export interface SaveConfigRequest {
  windowConfig?: WindowConfig;
}

/**
 * 設定保存結果
 */
export interface SaveConfigResult {
  success: boolean;
  config?: AppConfig;
  error?: string;
}

// プロジェクト管理 (TASK_018)

/**
 * プロジェクト情報
 */
export interface ProjectInfo {
  name: string;
  status: string;
  activeOrderCount: number;
  currentOrderId?: string;
  startDate?: string;
  targetCompletionDate?: string;
}

/**
 * タスク情報（簡易版）
 */
export interface TaskInfo {
  id: string;
  title: string;
  status: string;
  assignee: string;
  dependencies: string[];
  startDate?: string;
  completedDate?: string;
}

/**
 * タスク詳細情報（DB由来 - AipmDbServiceと同一）
 * ORDER_126 / TASK_1119: タスク詳細取得API
 */
export interface AipmTask {
  id: string;
  orderId: string;
  projectId: string;
  title: string;
  description: string | null;
  status: string;
  assignee: string | null;
  priority: string;
  recommendedModel: string;
  dependencies: string[];
  startedAt: string | null;
  completedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * レビューキューアイテム
 *
 * @deprecated ORDER_145: review_queueテーブル廃止
 * DONEステータスのタスクを直接参照するように変更されました。
 * この型は後方互換性のために残されています。
 */
export interface ReviewQueueItem {
  taskId: string;
  submittedAt: string;
  status: string;
  reviewer?: string;
  priority: string;
  note?: string;
}

/**
 * 進捗サマリ
 */
export interface ProgressSummary {
  completed: number;
  inProgress: number;
  reviewWaiting: number;
  queued: number;
  blocked: number;
  rework: number;
  total: number;
}

/**
 * ORDER情報
 */
export interface OrderInfo {
  id: string;
  title?: string;
  status: string;
  tasks: TaskInfo[];
}

/**
 * パース済みSTATE
 */
export interface ParsedState {
  projectInfo: ProjectInfo;
  tasks: TaskInfo[];
  reviewQueue: ReviewQueueItem[];
  progressSummary: ProgressSummary;
  orders: OrderInfo[];
}

/**
 * プロジェクト
 */
export interface Project {
  name: string;
  path: string;
  state: ParsedState | null;
  lastUpdated: Date | null;
  hasStateFile: boolean;
}

/**
 * プロジェクト一覧結果
 */
export interface ProjectListResult {
  projects: Project[];
  frameworkPath: string;
  error?: string;
}

/**
 * プロジェクトSTATE変更イベント
 */
export interface ProjectStateChangedEvent {
  projectName: string;
  state: ParsedState | null;
  eventType: 'add' | 'change' | 'unlink';
  timestamp: Date;
}

// 推奨アクション (TASK_026)

/**
 * 成果物ファイル情報
 */
export interface ArtifactFile {
  /** ファイル名 */
  name: string;
  /** 相対パス */
  path: string;
  /** ファイルタイプ */
  type: 'file' | 'directory';
  /** 拡張子（ファイルの場合のみ） */
  extension?: string;
}

/**
 * データソースタイプ（TASK_200）
 */
export type DataSource = 'db' | 'file';

/**
 * バックログ項目（TASK_241, ORDER_032で拡張）
 */
export interface BacklogItem {
  id: string;
  projectId: string;
  title: string;
  description: string | null;
  priority: string;
  status: string;
  relatedOrderId: string | null;
  createdAt: string;
  completedAt: string | null;
  updatedAt: string;
  // ORDER_032追加: ORDER紐付け情報
  orderTitle?: string | null;
  orderStatus?: string | null;
  orderProjectId?: string | null;
  totalTasks?: number;
  completedTasks?: number;
  progressPercent?: number;
  sortOrder?: number;
}

/**
 * バックログ更新パラメータ（ORDER_139 / TASK_1161）
 */
export interface BacklogUpdateParams {
  title?: string;
  description?: string;
  priority?: string;
  status?: string;
  sortOrder?: number;
}

/**
 * バックログ操作結果（ORDER_139 / TASK_1161）
 */
export interface BacklogOperationResult {
  success: boolean;
  backlogId?: string;
  error?: string;
}

/**
 * リフレッシュ結果（TASK_256）
 */
export interface RefreshResult {
  success: boolean;
  timestamp: Date;
  error?: string;
}

/**
 * リフレッシュサービスステータス（TASK_256）
 */
export interface RefreshServiceStatus {
  isRunning: boolean;
  intervalMs: number;
  lastRefreshAt: Date | null;
  nextRefreshAt: Date | null;
  consecutiveErrorCount: number;
}

// ============================================================
// ダッシュボード関連型定義（ORDER_021 / TASK_323）
// ============================================================

/**
 * プロジェクト健康状態（TASK_323）
 */
export interface ProjectHealthData {
  /** プロジェクトID */
  projectId: string;
  /** プロジェクト名 */
  projectName: string;
  /** 健康状態 */
  status: 'healthy' | 'warning' | 'critical' | 'unknown';
  /** 現在のORDER ID */
  currentOrderId?: string;
  /** 現在のORDERタイトル */
  currentOrderTitle?: string;
  /** ORDERステータス */
  orderStatus?: string;
  /** 全タスク数 */
  totalTasks: number;
  /** 完了タスク数 */
  completedTasks: number;
  /** 進行中タスク数 */
  inProgressTasks: number;
  /** ブロックタスク数 */
  blockedTasks: number;
  /** 差戻しタスク数 */
  reworkTasks: number;
  /** 完了率 (0-100) */
  completionRate: number;
  /** レビュー待ち数 */
  pendingReviews: number;
  /** 未解決エスカレーション数 */
  openEscalations: number;
  /** ブロック率 (0-100) */
  blockedRatio: number;
  /** 最終更新日時 */
  lastActivity?: string;
}

/**
 * エスカレーション集約（TASK_323）
 */
export interface EscalationSummary {
  /** 未解決エスカレーション総数 */
  totalOpen: number;
  /** 本日解決数 */
  totalResolvedToday: number;
  /** 最も古い未解決エスカレーションの経過日数 */
  oldestOpenDays: number;
  /** プロジェクト別内訳 */
  byProject: Record<string, number>;
  /** 直近エスカレーション（直近5件） */
  recentEscalations: Array<{
    id: string;
    taskId: string;
    projectId: string;
    title: string;
    status: string;
    createdAt: string;
    resolvedAt?: string;
    daysOpen: number;
  }>;
}

/**
 * 承認待ち集約（TASK_323）
 */
export interface PendingReviewSummary {
  /** 承認待ち総数 */
  totalPending: number;
  /** レビュー中総数 */
  totalInReview: number;
  /** P0（最優先）件数 */
  p0Count: number;
  /** P1（通常）件数 */
  p1Count: number;
  /** P2（低優先）件数 */
  p2Count: number;
  /** プロジェクト別内訳 */
  byProject: Record<string, number>;
  /** 最も古い待ち時間（時間単位） */
  oldestPendingHours: number;
  /** 詳細リスト（優先度順、直近10件） */
  pendingItems: Array<{
    id: string;
    taskId: string;
    projectId: string;
    status: string;
    priority: string;
    submittedAt: string;
    reviewer?: string;
    taskTitle?: string;
    hoursPending: number;
  }>;
}

/**
 * バックログ集約（TASK_323）
 */
export interface BacklogSummaryData {
  /** 全項目数 */
  totalItems: number;
  /** TODO数 */
  todoCount: number;
  /** 進行中数 */
  inProgressCount: number;
  /** High優先度数 */
  highPriorityCount: number;
  /** プロジェクト別内訳 */
  byProject: Record<string, number>;
  /** カテゴリ別内訳 */
  byCategory: Record<string, number>;
  /** 優先度別内訳 */
  byPriority: Record<string, number>;
  /** ステータス別内訳 */
  byStatus: Record<string, number>;
  /** 直近追加項目（直近5件） */
  recentItems: Array<{
    id: string;
    projectId: string;
    title: string;
    priority: string;
    status: string;
    createdAt: string;
  }>;
  /** フィルタ結果（フィルタ適用時のみ） */
  filteredItems: Array<{
    id: string;
    projectId: string;
    title: string;
    priority: string;
    status: string;
    createdAt: string;
  }>;
  /** 適用されたフィルタ */
  appliedFilters: {
    priority?: string[];
    status?: string[];
    project?: string;
  };
}

/**
 * ダッシュボードコンテキスト（TASK_323）
 */
export interface DashboardContext {
  /** プロジェクト健康状態リスト */
  projects: ProjectHealthData[];
  /** エスカレーション集約 */
  escalationSummary: EscalationSummary;
  /** 承認待ち集約 */
  reviewSummary: PendingReviewSummary;
  /** バックログ集約 */
  backlogSummary: BacklogSummaryData;
  /** 全プロジェクト数 */
  totalProjects: number;
  /** 正常プロジェクト数 */
  healthyProjects: number;
  /** 警告プロジェクト数 */
  warningProjects: number;
  /** 危険プロジェクト数 */
  criticalProjects: number;
  /** レンダリング日付 */
  renderDate: string;
  /** レンダリング時刻 */
  renderTime: string;
}

/**
 * バックログフィルタ（TASK_323）
 */
export interface BacklogFilters {
  /** 優先度フィルタ */
  priority?: ('High' | 'Medium' | 'Low')[];
  /** ステータスフィルタ */
  status?: string[];
  /** プロジェクトフィルタ */
  projectId?: string;
  /** ソートキー */
  sortBy?: 'priority' | 'createdAt' | 'status' | 'sortOrder';
  /** ソート順 */
  sortOrder?: 'asc' | 'desc';
}

// ============================================================
// aipm_autoログ関連型定義（ORDER_050）
// ============================================================

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
 * ログ監視状態
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

// ============================================================
// Worker ログ関連型定義（ORDER_111 / TASK_1001）
// ============================================================

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
 * ORDER成果物ファイル情報（ORDER_127 / TASK_1122）
 */
export interface OrderResultFile {
  /** ファイル名（例: "01_GOAL.md"） */
  filename: string;
  /** ファイルの絶対パス */
  path: string;
  /** ファイル内容（Markdown） */
  content: string;
  /** ファイルが存在するか */
  exists: boolean;
}

/**
 * レポートから抽出した変更ファイル情報（ORDER_134 / TASK_1149）
 */
export interface ReportChangedFile {
  /** ファイルパス */
  path: string;
}

/**
 * レポート差分サマリ情報（ORDER_134 / TASK_1149）
 */
export interface ReportDiffSummary {
  /** タスクID */
  taskId: string;
  /** レポートファイル名 */
  reportFilename: string;
  /** 変更ファイル一覧 */
  changedFiles: ReportChangedFile[];
  /** 影響範囲（REPORTから抽出） */
  impactScope: string | null;
  /** REPORTサマリ（実施内容など） */
  summary: string | null;
}

/**
 * タスクレビュー結果情報（ORDER_134 / TASK_1149）
 */
export interface TaskReviewResult {
  /** タスクID */
  taskId: string;
  /** レビューステータス（APPROVED, REJECTED, PENDING, IN_REVIEW） */
  reviewStatus: string;
  /** レビューコメント */
  reviewComment: string | null;
  /** レビュー日時 */
  reviewedAt: string | null;
  /** レビュアー */
  reviewer: string | null;
}

/**
 * ORDER全体のリリース準備状況（ORDER_134 / TASK_1149）
 */
export interface OrderReleaseReadiness {
  /** プロジェクトID */
  projectId: string;
  /** ORDER ID */
  orderId: string;
  /** 総タスク数 */
  totalTasks: number;
  /** 完了タスク数 */
  completedTasks: number;
  /** 全タスク完了済みか */
  allTasksCompleted: boolean;
  /** レビュー結果一覧 */
  reviewResults: TaskReviewResult[];
  /** 全タスクレビュー承認済みか */
  allReviewsApproved: boolean;
  /** レポート差分サマリ一覧 */
  reportSummaries: ReportDiffSummary[];
  /** リリース可否（緑: ready, 黄: partial, 赤: not_ready） */
  releaseStatus: 'ready' | 'partial' | 'not_ready';
}

/**
 * タスクレビュー履歴（ORDER_138 / TASK_1158）
 */
export interface TaskReviewHistory {
  reviews: {
    id: number;
    taskId: string;
    status: string;
    reviewer: string | null;
    comment: string | null;
    submittedAt: string | null;
    reviewedAt: string | null;
  }[];
  statusHistory: {
    fieldName: string;
    oldValue: string | null;
    newValue: string | null;
    changedBy: string | null;
    changeReason: string | null;
    changedAt: string;
  }[];
  escalations: {
    id: string;
    reason: string | null;
    resolvedAt: string | null;
    resolution: string | null;
    createdAt: string;
  }[];
  rejectCount: number;
  maxRework: number;
}

/**
 * タスクログ末尾取得結果（ORDER_128 / TASK_1126）
 */
export interface TaskLogTailResult {
  /** ログ行の配列 */
  logLines: string[];
  /** ログファイルパス */
  logFilePath: string | null;
}

/**
 * タスク進捗情報（ORDER_128 / TASK_1127）
 * ORDER_141 / TASK_1171: TaskProgressInfo型に整合
 */
export interface TaskProgressInfo {
  /** 実行中タスクリスト */
  runningTasks: Array<{
    id: string;
    title: string;
    status: string;
    currentStep: string | null;
    stepIndex: number;
    totalSteps: number;
    progressPercent: number;
  }>;
  /** 完了タスク数 */
  completedCount: number;
  /** 総タスク数 */
  totalCount: number;
  /** ORDER進捗率 (0-100) */
  overallProgress: number;
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

/**
 * ログディレクトリ情報
 */
export interface LogDirectoryInfo {
  /** プロジェクト名 */
  projectName: string;
  /** ログディレクトリパス */
  logDir: string;
  /** 存在するかどうか */
  exists: boolean;
  /** ログファイル数 */
  fileCount?: number;
}

// ============================================================
// リリース情報関連型定義（ORDER_045 / TASK_597）
// ============================================================

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
 * リリース実行結果（ORDER_108 / TASK_994）
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
 * リリースdry-run結果（ORDER_108 / TASK_994）
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

/**
 * ORDER関連情報
 */
export interface OrderRelatedInfo {
  /** 関連バックログ一覧 */
  relatedBacklogs: Array<{
    id: string;
    title: string;
    status: string;
  }>;
  /** 依存ORDER一覧（将来拡張用） */
  dependentOrders: Array<{
    id: string;
    title: string;
    status: string;
  }>;
}

// ============================================================
// DB変更通知型定義（ORDER_004 / TASK_010）
// ============================================================

/**
 * DB変更イベント
 * スクリプト実行完了・タスクステータス変更・全タスク完了・タスククラッシュ時に発火
 */
export interface DbChangedEvent {
  /** 変更元 */
  source: string;
  /** プロジェクトID */
  projectId: string;
  /** ターゲットID（ORDER ID または タスクID） */
  targetId: string;
  /** イベント発生日時（ISO8601） */
  timestamp: string;
}

// ============================================================
// スクリプト実行関連型定義（ORDER_039 / TASK_566）
// ============================================================

/**
 * スクリプト実行結果
 */
export interface ExecutionResult {
  success: boolean;
  /** 実行ID */
  executionId: string;
  /** 実行タイプ */
  type: 'pm' | 'worker';
  /** プロジェクトID */
  projectId: string;
  /** ターゲットID（バックログID または ORDER ID） */
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
  // ORDER_098: 並列実行フィールド
  /** 起動されたWorker数（並列実行時） */
  launched_count?: number;
  /** 起動されたタスク情報（並列実行時） */
  launched_tasks?: Array<{ task_id: string; priority: string; title: string }>;
  /** 並列実行メッセージ */
  message?: string;
}

/**
 * Worker実行結果（並列実行対応）
 * ORDER_098: 並列Worker起動のための拡張インターフェース
 */
export interface ExecuteWorkerResult extends ExecutionResult {
  /** 並列実行されたタスクIDリスト */
  parallelTaskIds?: string[];
  /** 並列実行モードで実行されたかどうか */
  isParallelExecution?: boolean;
}

/**
 * 実行進捗情報
 */
export interface ExecutionProgress {
  /** 実行ID */
  executionId: string;
  /** 実行タイプ */
  type: 'pm' | 'worker';
  /** プロジェクトID */
  projectId: string;
  /** ターゲットID */
  targetId: string;
  /** ステータス */
  status: 'running' | 'completed' | 'failed';
  /** 最新の出力行 */
  lastOutput?: string;
}

/**
 * 実行中ジョブ情報
 */
export interface RunningJob {
  executionId: string;
  type: 'pm' | 'worker';
  projectId: string;
  targetId: string;
  startedAt: string;
}

/**
 * アクションタイプ
 */
export type ActionType = 'review' | 'worker' | 'status';

/**
 * 推奨アクション
 */
export interface RecommendedAction {
  /** 一意識別子 */
  id: string;
  /** アクションタイプ */
  type: ActionType;
  /** 実行コマンド */
  command: string;
  /** 説明テキスト */
  description: string;
  /** 優先度（1が最優先） */
  priority: number;
  /** 関連タスクID（オプション） */
  taskId?: string;
}


// ============================================================
// Supervisor / XBacklog 関連型定義（ORDER_059 / TASK_655）
// ============================================================

/**
 * Supervisor情報
 */
export interface Supervisor {
  id: string;
  name: string;
  description: string | null;
  status: string;
  createdAt: string;
  updatedAt: string;
}

/**
 * Supervisor詳細情報
 */
export interface SupervisorDetail extends Supervisor {
  projectCount: number;
  xbacklogCount: number;
}

/**
 * Supervisor配下プロジェクト情報
 */
export interface SupervisorProject {
  id: string;
  name: string;
  path: string;
  status: string;
  currentOrderId: string | null;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

/**
 * 横断バックログ情報
 */
export interface XBacklog {
  id: string;
  supervisorId: string;
  title: string;
  description: string | null;
  priority: string;
  status: string;
  assignedProjectId: string | null;
  assignedBacklogId: string | null;
  analysisResult: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * XBacklog振り分け分析結果
 */
export interface XBacklogAnalysisResult {
  suggestedProjectId: string | null;
  suggestedProjectName: string | null;
  confidence: number;
  reason: string;
  keywords: string[];
}

/**
 * XBacklog振り分け実行結果
 */
export interface XBacklogDispatchResult {
  success: boolean;
  xbacklogId: string;
  projectId: string;
  backlogId: string | null;
  error?: string;
}

// ============================================================
// ポートフォリオビュー型定義（ORDER_068 / BACKLOG_116）
// ============================================================

/**
 * ポートフォリオ用ORDER情報
 */
export interface PortfolioOrder {
  id: string;
  portfolioId: string;
  projectId: string;
  projectName: string;
  title: string;
  status: string;
  priority: string;
  progress: number;
  taskCount: number;
  completedTaskCount: number;
  createdAt: string;
  updatedAt: string;
}

/**
 * ポートフォリオ用バックログ情報
 */
export interface PortfolioBacklog {
  id: string;
  portfolioId: string;
  projectId: string;
  projectName: string;
  title: string;
  status: string;
  priority: string;
  description: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * ポートフォリオ用タスク情報
 */
export interface PortfolioTask {
  id: string;
  orderId: string;
  title: string;
  status: string;
  priority: string;
  createdAt: string;
}

/**
 * ポートフォリオデータ
 */
export interface PortfolioData {
  orders: PortfolioOrder[];
  backlogs: PortfolioBacklog[];
}

/**
 * Electron API インターフェース
 */
export interface ElectronAPI {
  /**
   * ディレクトリ選択ダイアログを開く
   * @returns 選択結果と検証結果
   */
  selectDirectory: () => Promise<DirectorySelectionResult>;

  /**
   * 指定されたパスのディレクトリを検証する
   * @param dirPath 検証対象のパス
   * @returns 検証結果
   */
  validateDirectory: (dirPath: string) => Promise<DirectoryValidationResult>;

  /**
   * ファイル監視を開始
   * @param frameworkPath AI PM Frameworkのルートパス
   * @returns 開始結果
   */
  startWatcher: (
    frameworkPath: string
  ) => Promise<{ success: boolean; error?: string }>;

  /**
   * ファイル監視を停止
   */
  stopWatcher: () => Promise<void>;

  /**
   * 監視ステータスを取得
   */
  getWatcherStatus: () => Promise<WatcherStatus>;

  /**
   * ファイル変更イベントのリスナーを登録
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onFileChange: (callback: (event: FileChangeEvent) => void) => () => void;

  /**
   * 監視準備完了イベントのリスナーを登録
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onWatcherReady: (callback: () => void) => () => void;

  /**
   * 監視エラーイベントのリスナーを登録
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onWatcherError: (
    callback: (error: { message: string }) => void
  ) => () => void;

  /**
   * 監視停止イベントのリスナーを登録
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onWatcherStopped: (callback: () => void) => () => void;

  // 設定永続化 (FR-003)
  /**
   * 設定を読み込む
   * @returns アプリケーション設定
   */
  loadConfig: () => Promise<AppConfig>;

  /**
   * 設定を保存する
   * @param request 保存リクエスト
   * @returns 保存結果
   */
  saveConfig: (request: SaveConfigRequest) => Promise<SaveConfigResult>;

  /**
   * アクティブなフレームワークパスを取得
   * @returns アクティブなパス（未設定の場合はnull）
   */
  getActiveFrameworkPath: () => Promise<string>;

  // プロジェクト管理 (TASK_018)
  /**
   * プロジェクト一覧を取得
   * @returns プロジェクト一覧
   */
  getProjects: () => Promise<ProjectListResult>;

  /**
   * 指定プロジェクトのSTATE情報を取得
   * @param projectName プロジェクト名
   * @returns パース済みSTATE
   */
  getProjectState: (projectName: string) => Promise<ParsedState | null>;

  /**
   * プロジェクトSTATE変更イベントのリスナーを登録
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onProjectStateChanged: (
    callback: (event: ProjectStateChangedEvent) => void
  ) => () => void;

  // タスク詳細 (TASK_023)
  /**
   * タスクファイル (TASK_XXX.md) の内容を取得
   * @param projectName プロジェクト名
   * @param taskId タスクID
   * @returns ファイル内容（見つからない場合はnull）
   */
  getTaskFile: (projectName: string, taskId: string) => Promise<string | null>;

  /**
   * タスク詳細情報を取得（ORDER_126 / TASK_1118）
   * @param taskId タスクID
   * @param projectId プロジェクトID
   * @returns タスク詳細情報（見つからない場合はnull）
   */
  getTask: (taskId: string, projectId: string) => Promise<AipmTask | null>;

  /**
   * REPORTファイル (REPORT_XXX.md) の内容を取得
   * @param projectName プロジェクト名
   * @param taskId タスクID
   * @returns ファイル内容（見つからない場合はnull）
   */
  getReportFile: (projectName: string, taskId: string) => Promise<string | null>;

  /**
   * ORDERファイル (ORDER_XXX.md) の内容を取得
   * @param projectName プロジェクト名
   * @param orderId ORDER ID
   * @returns ファイル内容（見つからない場合はnull）
   */
  getOrderFile: (projectName: string, orderId: string) => Promise<string | null>;

  /**
   * REVIEWファイル (REVIEW_XXX.md) の内容を取得
   * @param projectName プロジェクト名
   * @param taskId タスクID
   * @returns ファイル内容（見つからない場合はnull）
   */
  getReviewFile: (projectName: string, taskId: string) => Promise<string | null>;

  /**
   * PROJECT_INFO.md ファイルの内容を取得
   * @param projectName プロジェクト名
   * @returns ファイル内容（見つからない場合はnull）
   */
  getProjectInfoFile: (projectName: string) => Promise<string | null>;

  // 推奨アクション (TASK_026)
  /**
   * 推奨アクションを取得
   * @param projectName プロジェクト名
   * @param state パース済みSTATE
   * @returns 推奨アクションの配列
   */
  getRecommendedActions: (
    projectName: string,
    state: ParsedState
  ) => Promise<RecommendedAction[]>;

  // 成果物閲覧 (TASK_194)
  /**
   * 成果物ファイル一覧を取得
   * @param projectName プロジェクト名
   * @param orderId ORDER ID
   * @returns 成果物ファイル一覧
   */
  getArtifactFiles: (
    projectName: string,
    orderId: string
  ) => Promise<ArtifactFile[]>;

  /**
   * 成果物ファイルの内容を取得
   * @param projectName プロジェクト名
   * @param orderId ORDER ID
   * @param filePath 相対ファイルパス
   * @returns ファイル内容（見つからない場合はnull）
   */
  getArtifactContent: (
    projectName: string,
    orderId: string,
    filePath: string
  ) => Promise<string | null>;

  // データソース表示 (TASK_200)
  /**
   * 現在のデータソースを取得
   * @returns 'db' または 'file'
   */
  getDataSource: () => Promise<DataSource>;

  // バックログ一覧 (TASK_241)
  /**
   * バックログ一覧を取得
   * @param projectName プロジェクト名
   * @returns バックログ項目一覧
   */
  getBacklogs: (projectName: string) => Promise<BacklogItem[]>;

  // バックログ操作（ORDER_139 / TASK_1161）
  /**
   * バックログ項目を追加
   * @param projectId プロジェクトID
   * @param title タイトル
   * @param description 説明
   * @param priority 優先度（High/Medium/Low）
   * @param category カテゴリ（省略可）
   * @returns 追加結果
   */
  addBacklog: (
    projectId: string,
    title: string,
    description: string | null,
    priority: string,
    category?: string
  ) => Promise<BacklogOperationResult>;

  /**
   * バックログ項目を更新
   * @param projectId プロジェクトID
   * @param backlogId バックログID
   * @param updates 更新内容
   * @returns 更新結果
   */
  updateBacklog: (
    projectId: string,
    backlogId: string,
    updates: BacklogUpdateParams
  ) => Promise<BacklogOperationResult>;

  /**
   * バックログ項目を削除（CANCELEDステータスに変更）
   * @param projectId プロジェクトID
   * @param backlogId バックログID
   * @returns 削除結果
   */
  deleteBacklog: (
    projectId: string,
    backlogId: string
  ) => Promise<BacklogOperationResult>;

  /**
   * バックログ優先度を自動整理（ORDER_144 / TASK_1188）
   * @param projectId プロジェクトID
   * @param options オプション（dryRun, days, verbose）
   * @returns 優先度整理結果
   */
  prioritizeBacklogs: (
    projectId: string,
    options?: {
      dryRun?: boolean;
      days?: number;
      verbose?: boolean;
    }
  ) => Promise<{
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
  }>;

  // 定期リフレッシュ (TASK_256)
  /**
   * 手動でリフレッシュを実行
   * @returns リフレッシュ結果
   */
  refresh: () => Promise<RefreshResult>;

  /**
   * リフレッシュサービスのステータスを取得
   * @returns ステータス情報
   */
  getRefreshStatus: () => Promise<RefreshServiceStatus>;

  /**
   * リフレッシュ完了イベントのリスナーを登録
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onRefreshed: (callback: (result: RefreshResult) => void) => () => void;

  // ダッシュボード (ORDER_021 / TASK_323)
  /**
   * ダッシュボードコンテキストを取得
   * @param includeInactive 非アクティブプロジェクトを含めるか（デフォルト: false）
   * @returns ダッシュボードコンテキスト
   */
  getDashboard: (includeInactive?: boolean) => Promise<DashboardContext>;

  /**
   * 全プロジェクトのバックログを取得（フィルタ付き）
   * @param filters フィルタ条件
   * @returns バックログ項目一覧
   */
  getAllBacklogs: (filters?: BacklogFilters) => Promise<BacklogItem[]>;

  /**
   * 全アクティブプロジェクトのBACKLOG sort_orderを再計算
   */
  reorderAllBacklogs: () => Promise<Array<{ project: string; success: boolean; message: string }>>;

  // スクリプト実行 (ORDER_039 / TASK_566)
  /**
   * PM処理を実行（バックログ→ORDER化→PM処理）
   * @param projectId プロジェクトID
   * @param backlogId バックログID
   * @returns 実行結果
   */
  executePmProcess: (projectId: string, backlogId: string) => Promise<ExecutionResult>;

  /**
   * Worker処理を実行（タスク並列実行）
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @returns 実行結果
   */
  executeWorkerProcess: (projectId: string, orderId: string) => Promise<ExecutionResult>;

  /**
   * ORDER再実行（PLANNING_FAILED → PLANNING → 再処理）
   * ORDER_155 TASK_1230
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @param options オプション（タイムアウト、モデル、詳細ログ）
   * @returns 実行結果
   */
  retryOrder: (projectId: string, orderId: string, options?: { timeout?: number; model?: string; verbose?: boolean }) => Promise<ExecutionResult>;

  /**
   * 実行中のジョブ一覧を取得
   * @returns 実行中ジョブ一覧
   */
  getRunningJobs: () => Promise<RunningJob[]>;

  /**
   * 特定のジョブが実行中かどうかを確認
   * @param projectId プロジェクトID
   * @param targetId ターゲットID
   * @returns 実行中かどうか
   */
  isJobRunning: (projectId: string, targetId: string) => Promise<boolean>;

  /**
   * 実行中のジョブをキャンセル
   * @param executionId 実行ID
   * @returns キャンセル成功かどうか
   */
  cancelJob: (executionId: string) => Promise<boolean>;

  /**
   * 実行進捗イベントのリスナーを登録
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onExecutionProgress: (callback: (progress: ExecutionProgress) => void) => () => void;

  /**
   * 実行完了イベントのリスナーを登録
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onExecutionComplete: (callback: (result: ExecutionResult) => void) => () => void;

  // 実行履歴管理 (ORDER_040 / TASK_574)
  /**
   * 実行履歴を取得
   * @returns 実行履歴（新しい順）
   */
  getExecutionHistory: () => Promise<ExecutionResult[]>;

  /**
   * 実行履歴をクリア
   */
  clearExecutionHistory: () => Promise<void>;

  // リリース情報 (ORDER_045 / TASK_597)
  /**
   * ORDERのリリース情報を取得
   * @param projectName プロジェクト名
   * @param orderId ORDER ID
   * @returns リリース情報
   */
  getOrderReleaseInfo: (projectName: string, orderId: string) => Promise<OrderReleaseInfo>;

  // リリース実行 (ORDER_108 / TASK_995)
  executeRelease: (projectName: string, orderId: string) => Promise<ReleaseResult>;
  executeReleaseDryRun: (projectName: string, orderId: string) => Promise<ReleaseDryRunResult>;

  /**
   * ORDERの関連情報を取得
   * @param projectName プロジェクト名
   * @param orderId ORDER ID
   * @returns 関連情報
   */
  getOrderRelatedInfo: (projectName: string, orderId: string) => Promise<OrderRelatedInfo>;

  // aipm_autoログ (ORDER_050)
  /**
   * ログディレクトリ一覧を取得
   * @returns ログディレクトリ情報一覧
   */
  getAipmAutoLogDirectories: () => Promise<LogDirectoryInfo[]>;

  /**
   * ログファイル一覧を取得
   * @param projectName プロジェクト名
   * @param orderId ORDER ID（省略時は全ログ）
   * @returns ログファイル情報一覧
   */
  getAipmAutoLogFiles: (projectName: string, orderId?: string) => Promise<LogFileInfo[]>;

  /**
   * ログファイル内容を取得
   * @param filePath ファイルパス
   * @param options 読み込みオプション
   * @returns ログ内容
   */
  readAipmAutoLogFile: (
    filePath: string,
    options?: { tailLines?: number; fromPosition?: number }
  ) => Promise<LogContent | null>;

  /**
   * 最新のログファイルを取得
   * @param projectName プロジェクト名
   * @returns 最新のログファイル情報
   */
  getLatestAipmAutoLog: (projectName: string) => Promise<LogFileInfo | null>;

  /**
   * ログ監視を開始
   * @param projectName プロジェクト名
   * @returns 開始結果
   */
  startAipmAutoLogWatcher: (projectName: string) => Promise<{ success: boolean; error?: string }>;

  /**
   * ログ監視を停止
   */
  stopAipmAutoLogWatcher: () => Promise<void>;

  /**
   * ログ監視状態を取得
   * @returns 監視状態
   */
  getAipmAutoLogWatcherStatus: () => Promise<LogWatcherStatus>;

  /**
   * ログ更新イベントのリスナーを登録
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onAipmAutoLogUpdate: (callback: (event: LogUpdateEvent) => void) => () => void;

  /**
   * ログ監視準備完了イベントのリスナーを登録
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onAipmAutoLogReady: (callback: () => void) => () => void;

  /**
   * ログ監視エラーイベントのリスナーを登録
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onAipmAutoLogError: (callback: (error: { message: string }) => void) => () => void;

  /**
   * ログ監視停止イベントのリスナーを登録
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onAipmAutoLogStopped: (callback: () => void) => () => void;

  // Supervisor / XBacklog (ORDER_059 / TASK_655)
  /**
   * Supervisor一覧を取得
   */
  getSupervisors: () => Promise<Supervisor[]>;

  /**
   * Supervisor詳細を取得
   */
  getSupervisorDetail: (supervisorId: string) => Promise<SupervisorDetail | null>;

  /**
   * Supervisor配下のプロジェクト一覧を取得
   */
  getProjectsBySupervisor: (supervisorId: string, includeInactive?: boolean) => Promise<SupervisorProject[]>;

  /**
   * 横断バックログ一覧を取得
   */
  getXBacklogs: (supervisorId: string) => Promise<XBacklog[]>;

  /**
   * 横断バックログを作成
   */
  createXBacklog: (supervisorId: string, title: string, description: string | null, priority: string) => Promise<XBacklog | null>;

  /**
   * 横断バックログを分析
   */
  analyzeXBacklog: (xbacklogId: string) => Promise<XBacklogAnalysisResult | null>;

  /**
   * 横断バックログを振り分け
   */
  dispatchXBacklog: (xbacklogId: string, projectId: string) => Promise<XBacklogDispatchResult>;

  // ============================================================
  // ポートフォリオビュー（ORDER_068 / BACKLOG_116）
  // ============================================================

  /**
   * ポートフォリオデータを取得
   * @param supervisorId Supervisor ID
   * @returns ポートフォリオデータ（ORDER一覧・バックログ一覧）
   */
  getPortfolioData: (supervisorId: string) => Promise<PortfolioData>;

  /**
   * ORDER配下のタスク一覧を取得
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @returns タスク一覧
   */
  getPortfolioOrderTasks: (projectId: string, orderId: string) => Promise<PortfolioTask[]>;

  // ============================================================
  // メニュー更新イベント（ORDER_063 / TASK_677）
  // ============================================================

  /**
   * メニュー更新イベントのリスナーを登録
   * ボタン操作・自動実行完了時に左メニューを自動更新するためのイベント
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onMenuUpdate: (callback: () => void) => () => void;

  // ============================================================
  // タスクポーリング（ORDER_101）
  // ============================================================

  /**
   * タスクステータスのポーリングを開始
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @param intervalMs ポーリング間隔（ミリ秒）
   */
  startTaskPolling: (projectId: string, orderId: string, intervalMs?: number) => Promise<{ success: boolean }>;

  /**
   * タスクステータスのポーリングを停止
   */
  stopTaskPolling: () => Promise<{ success: boolean }>;

  /**
   * ORDER_119: タスクの実行ステップ情報を取得
   */
  getTaskExecutionSteps: (projectId: string, taskId: string) => Promise<{
    currentStep: string | null;
    currentStepDisplay: string;
    stepIndex: number;
    totalSteps: number;
    progressPercent: number;
    steps: Array<{ step: string; display: string; status: string }>;
  } | null>;

  /**
   * タスクステータス変更イベントのリスナーを登録
   */
  onTaskStatusChanged: (callback: (data: {
    taskId: string;
    title: string;
    oldStatus: string;
    newStatus: string;
    projectId: string;
    orderId: string;
  }) => void) => () => void;

  /**
   * 全タスク完了イベントのリスナーを登録
   */
  onAllTasksCompleted: (callback: (data: {
    projectId: string;
    orderId: string;
    tasks: Array<{ id: string; title: string; status: string }>;
  }) => void) => () => void;

  /**
   * タスクタイムアウトイベントのリスナーを登録
   */
  onTaskTimeout: (callback: (data: {
    taskId: string;
    title: string;
    elapsedMs: number;
    projectId: string;
    orderId: string;
  }) => void) => () => void;

  /**
   * タスクエラーイベントのリスナーを登録
   */
  onTaskError: (callback: (data: {
    taskId: string;
    title: string;
    status: string;
    projectId: string;
    orderId: string;
    logFile?: string;
    message?: string;
  }) => void) => () => void;

  // ============================================================
  // タスククラッシュ通知（ORDER_109）
  // ============================================================

  /**
   * タスククラッシュイベントのリスナーを登録
   * Worker異常終了を検知した際に発火する
   */
  onTaskCrash: (callback: (data: {
    taskId: string;
    projectId: string;
    orderId: string;
    pid: number;
    logFile: string;
    message: string;
  }) => void) => () => void;

  // ============================================================
  // Worker ログ一覧・読み込み・監視（ORDER_111 / TASK_1001）
  // ============================================================

  /**
   * Worker ログファイル一覧を取得
   * @param projectId プロジェクトID
   * @param orderId ORDER ID（省略時は全ORDER）
   * @returns ログファイル情報一覧
   */
  getWorkerLogs: (projectId: string, orderId?: string) => Promise<WorkerLogFileInfo[]>;

  /**
   * Worker ログファイル内容を読み込む
   * @param filePath ログファイルのパス
   * @param options 読み込みオプション（tailLines/fromPosition）
   * @returns ログ内容
   */
  readWorkerLog: (
    filePath: string,
    options?: { tailLines?: number; fromPosition?: number }
  ) => Promise<WorkerLogContent | null>;

  /**
   * Worker ログファイルの監視を開始
   * @param filePath 監視対象のログファイルパス
   */
  watchWorkerLog: (filePath: string) => Promise<void>;

  /**
   * Worker ログファイルの監視を停止
   * @param filePath 監視停止対象のログファイルパス
   */
  unwatchWorkerLog: (filePath: string) => Promise<void>;

  /**
   * Worker ログ更新イベントのリスナーを登録
   * @param callback コールバック関数（差分内容を受け取る）
   * @returns リスナー解除関数
   */
  onWorkerLogUpdate: (callback: (data: WorkerLogUpdateEvent) => void) => () => void;

  // ============================================================
  // タスク依存関係リアルタイム更新（ORDER_122 / TASK_1103）
  // ============================================================

  /**
   * タスク依存関係状態を取得
   * @param projectId プロジェクトID
   * @param taskId タスクID（省略時はORDER単位またはプロジェクト全体）
   * @param orderId ORDER ID（省略時はプロジェクト全体）
   * @returns 依存関係状態リスト
   */
  getDependencyStatus: (projectId: string, taskId?: string, orderId?: string) => Promise<Array<{
    taskId: string;
    projectId: string;
    status: string;
    title: string;
    isBlocked: boolean;
    dependencies: Array<{
      taskId: string;
      title: string;
      status: string;
      isCompleted: boolean;
    }>;
    completedCount: number;
    totalCount: number;
    completionRate: number;
  }>>;

  /**
   * 依存関係更新イベントのリスナーを登録
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onDependencyUpdate: (callback: (data: {
    projectId: string;
    orderId: string;
    taskId: string;
    dependencyStatus: {
      taskId: string;
      projectId: string;
      status: string;
      title: string;
      isBlocked: boolean;
      dependencies: Array<{
        taskId: string;
        title: string;
        status: string;
        isCompleted: boolean;
      }>;
      completedCount: number;
      totalCount: number;
      completionRate: number;
    };
    timestamp: string;
  }) => void) => () => void;

  /**
   * 依存関係イベント監視を開始（ORDER_140 / TASK_1168）
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @returns 開始結果
   */
  startDependencyMonitoring: (projectId: string, orderId: string) => Promise<{ success: boolean }>;

  /**
   * 依存関係イベント監視を停止（ORDER_140 / TASK_1168）
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @returns 停止結果
   */
  stopDependencyMonitoring: (projectId: string, orderId: string) => Promise<{ success: boolean }>;


  // ============================================================
  // RESULT Markdownファイル読み込み（ORDER_127 / TASK_1122）
  // ============================================================

  /**
   * RESULT配下のMarkdownファイルを読み込む（01_GOAL.md、02_REQUIREMENTS.md、03_STAFFING.md）
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @param filename ファイル名
   * @returns ファイル情報
   */
  getOrderResultFile: (projectId: string, orderId: string, filename: string) => Promise<OrderResultFile>;

  /**
   * 05_REPORT/配下のレポートファイル一覧を取得
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @returns レポートファイル名一覧
   */
  getOrderReportList: (projectId: string, orderId: string) => Promise<string[]>;

  /**
   * 05_REPORT/配下の特定レポートファイルを読み込む
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @param reportFilename レポートファイル名
   * @returns ファイル情報
   */
  getOrderReport: (projectId: string, orderId: string, reportFilename: string) => Promise<OrderResultFile>;

  // ============================================================
  // ORDER_134: TASK_1149 - リリース準備状況API
  // ============================================================

  /**
   * ORDERのリリース準備状況を取得
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @returns リリース準備状況
   */
  getOrderReleaseReadiness: (projectId: string, orderId: string) => Promise<OrderReleaseReadiness>;

  // ============================================================
  // ORDER_128: TASK_1126 - タスクログ読み込みAPI
  // ============================================================

  /**
   * タスクログファイルの末尾行を取得
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @param taskId タスクID
   * @param lines 取得する行数（デフォルト: 2）
   * @returns ログの末尾行データ（見つからない場合はnull）
   */
  getTaskLogTail: (projectId: string, orderId: string, taskId: string, lines?: number) => Promise<TaskLogTailResult | null>;

  /**
   * タスク進捗情報を取得
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @returns タスク進捗情報（見つからない場合はnull）
   */
  getTaskProgressInfo: (projectId: string, orderId: string) => Promise<TaskProgressInfo | null>;

  // ============================================================
  // ORDER_138: TASK_1158 - レビュー履歴取得API
  // ============================================================

  /**
   * タスクのレビュー履歴を取得
   * @param projectId プロジェクトID
   * @param taskId タスクID
   * @returns レビュー履歴情報
   */
  getTaskReviewHistory: (projectId: string, taskId: string) => Promise<TaskReviewHistory>;

  // ============================================================
  // ORDER_156: TASK_1233 - プロジェクト情報取得・更新
  // ============================================================

  /**
   * プロジェクト情報を取得
   * @param projectId プロジェクトID
   * @returns プロジェクト情報（見つからない場合はnull）
   */
  getProjectInfo: (projectId: string) => Promise<{
    id: number;
    name: string;
    path: string;
    description: string | null;
    purpose: string | null;
    tech_stack: string | null;
    status: string;
    created_at: string;
    updated_at: string;
  } | null>;

  /**
   * プロジェクト情報を更新
   * @param projectId プロジェクトID
   * @param updates 更新内容
   * @returns 更新結果
   */
  updateProjectInfo: (
    projectId: string,
    updates: {
      description?: string;
      purpose?: string;
      tech_stack?: string;
    }
  ) => Promise<{ success: boolean; error?: string }>;

  // ============================================================
  // ORDER_157: DB初期化ステータス
  // ============================================================

  /**
   * DB初期化ステータスを取得
   * @returns DB初期化ステータス（initialized, error, dbPath）
   */
  getDbInitStatus: () => Promise<{
    initialized: boolean;
    error: string | null;
    dbPath: string | null;
  }>;

  // ORDER_164: ターミナル起動
  /**
   * frameworkPathをカレントディレクトリとしてターミナルを開く
   */
  openTerminal: () => Promise<void>;

  // ============================================================
  // プロジェクト作成・削除（ORDER_002 / BACKLOG_001）
  // ============================================================

  /**
   * プロジェクトを新規作成
   * @param projectId プロジェクトID（英数字+アンダースコア、先頭は英字）
   * @param name プロジェクト表示名（省略時はprojectIdを使用）
   * @returns 作成結果
   */
  createProject: (projectId: string, name?: string) => Promise<{
    success: boolean;
    project?: {
      id: string;
      name: string;
      path: string;
      status: string;
      isActive: boolean;
      createdAt: string;
      updatedAt: string;
    };
    error?: string;
  }>;

  /**
   * プロジェクトを削除
   * @param projectId プロジェクトID
   * @param force アクティブORDERがあっても強制削除
   * @returns 削除結果
   */
  deleteProject: (projectId: string, force?: boolean) => Promise<{
    success: boolean;
    deletedCounts?: { orders: number; tasks: number; backlogs: number };
    error?: string;
  }>;

  // ============================================================
  // DB変更通知（ORDER_004 / TASK_010）
  // ============================================================

  /**
   * DB変更イベントのリスナーを登録
   * スクリプト実行完了・タスクステータス変更・全タスク完了・タスククラッシュ時に発火
   * @param callback コールバック関数
   * @returns リスナー解除関数
   */
  onDbChanged: (callback: (event: DbChangedEvent) => void) => () => void;
}

/**
 * イベントリスナーのヘルパー関数
 */
function createEventListener<T>(
  channel: string,
  callback: (data: T) => void
): () => void {
  const listener = (_event: IpcRendererEvent, data: T) => callback(data);
  ipcRenderer.on(channel, listener);
  return () => {
    ipcRenderer.removeListener(channel, listener);
  };
}

// Electron APIをレンダラープロセスに公開
const electronAPI: ElectronAPI = {
  // ディレクトリ選択
  selectDirectory: () => ipcRenderer.invoke('dialog:selectDirectory'),
  validateDirectory: (dirPath: string) =>
    ipcRenderer.invoke('dialog:validateDirectory', dirPath),

  // ファイル監視
  startWatcher: (frameworkPath: string) =>
    ipcRenderer.invoke('watcher:start', frameworkPath),
  stopWatcher: () => ipcRenderer.invoke('watcher:stop'),
  getWatcherStatus: () => ipcRenderer.invoke('watcher:status'),

  // ファイル監視イベントリスナー
  onFileChange: (callback: (event: FileChangeEvent) => void) =>
    createEventListener('watcher:on-change', callback),
  onWatcherReady: (callback: () => void) =>
    createEventListener('watcher:ready', callback),
  onWatcherError: (callback: (error: { message: string }) => void) =>
    createEventListener('watcher:error', callback),
  onWatcherStopped: (callback: () => void) =>
    createEventListener('watcher:stopped', callback),

  // 設定永続化 (FR-003)
  loadConfig: () => ipcRenderer.invoke('config:load'),
  saveConfig: (request: SaveConfigRequest) =>
    ipcRenderer.invoke('config:save', request),
  getActiveFrameworkPath: () => ipcRenderer.invoke('config:get-active-path'),

  // プロジェクト管理 (TASK_018)
  getProjects: () => ipcRenderer.invoke('project:get-projects'),
  getProjectState: (projectName: string) =>
    ipcRenderer.invoke('project:get-state', projectName),
  onProjectStateChanged: (callback: (event: ProjectStateChangedEvent) => void) =>
    createEventListener('project:state-changed', callback),

  // タスク詳細 (TASK_023)
  getTaskFile: (projectName: string, taskId: string) =>
    ipcRenderer.invoke('project:get-task-file', projectName, taskId),
  getTask: (taskId: string, projectId: string) =>
    ipcRenderer.invoke('project:get-task-detail', taskId, projectId),
  getReportFile: (projectName: string, taskId: string) =>
    ipcRenderer.invoke('project:get-report-file', projectName, taskId),
  getOrderFile: (projectName: string, orderId: string) =>
    ipcRenderer.invoke('project:get-order-file', projectName, orderId),
  getReviewFile: (projectName: string, taskId: string) =>
    ipcRenderer.invoke('project:get-review-file', projectName, taskId),
  getProjectInfoFile: (projectName: string) =>
    ipcRenderer.invoke('project:get-project-info-file', projectName),

  // 推奨アクション (TASK_026)
  getRecommendedActions: (projectName: string, state: ParsedState) =>
    ipcRenderer.invoke('project:get-recommended-actions', projectName, state),

  // 成果物閲覧 (TASK_194)
  getArtifactFiles: (projectName: string, orderId: string) =>
    ipcRenderer.invoke('project:get-artifact-files', projectName, orderId),
  getArtifactContent: (projectName: string, orderId: string, filePath: string) =>
    ipcRenderer.invoke('project:get-artifact-content', projectName, orderId, filePath),

  // データソース表示 (TASK_200)
  getDataSource: () => ipcRenderer.invoke('project:get-data-source'),

  // バックログ一覧 (TASK_241)
  getBacklogs: (projectName: string) =>
    ipcRenderer.invoke('project:get-backlogs', projectName),

  // バックログ操作（ORDER_139 / TASK_1161）
  addBacklog: (
    projectId: string,
    title: string,
    description: string | null,
    priority: string,
    category?: string
  ) => ipcRenderer.invoke('project:add-backlog', projectId, title, description, priority, category),
  updateBacklog: (
    projectId: string,
    backlogId: string,
    updates: BacklogUpdateParams
  ) => ipcRenderer.invoke('project:update-backlog', projectId, backlogId, updates),
  deleteBacklog: (projectId: string, backlogId: string) =>
    ipcRenderer.invoke('project:delete-backlog', projectId, backlogId),

  // ORDER_144 / TASK_1188: バックログ優先度自動整理
  prioritizeBacklogs: (projectId: string, options?: {
    dryRun?: boolean;
    days?: number;
    verbose?: boolean;
  }) => ipcRenderer.invoke('project:prioritize-backlogs', projectId, options),

  // 定期リフレッシュ (TASK_256)
  refresh: () => ipcRenderer.invoke('project:refresh'),
  getRefreshStatus: () => ipcRenderer.invoke('project:get-refresh-status'),
  onRefreshed: (callback: (result: RefreshResult) => void) =>
    createEventListener('project:refreshed', callback),

  // ダッシュボード (ORDER_021 / TASK_323)
  getDashboard: (includeInactive?: boolean) =>
    ipcRenderer.invoke('project:get-dashboard', includeInactive),
  getAllBacklogs: (filters?: BacklogFilters) =>
    ipcRenderer.invoke('project:get-all-backlogs', filters),
  reorderAllBacklogs: () =>
    ipcRenderer.invoke('project:reorder-all-backlogs'),

  // スクリプト実行 (ORDER_039 / TASK_566)
  executePmProcess: (projectId: string, backlogId: string) =>
    ipcRenderer.invoke('script:execute-pm', projectId, backlogId),
  executeWorkerProcess: (projectId: string, orderId: string) =>
    ipcRenderer.invoke('script:execute-worker', projectId, orderId),
  retryOrder: (projectId: string, orderId: string, options?: { timeout?: number; model?: string; verbose?: boolean }) =>
    ipcRenderer.invoke('script:retry-order', projectId, orderId, options),
  getRunningJobs: () =>
    ipcRenderer.invoke('script:get-running-jobs'),
  isJobRunning: (projectId: string, targetId: string) =>
    ipcRenderer.invoke('script:is-running', projectId, targetId),
  cancelJob: (executionId: string) =>
    ipcRenderer.invoke('script:cancel', executionId),
  onExecutionProgress: (callback: (progress: ExecutionProgress) => void) =>
    createEventListener('script:progress', callback),
  onExecutionComplete: (callback: (result: ExecutionResult) => void) =>
    createEventListener('script:complete', callback),

  // 実行履歴管理 (ORDER_040 / TASK_574)
  getExecutionHistory: () =>
    ipcRenderer.invoke('script:get-execution-history'),
  clearExecutionHistory: () =>
    ipcRenderer.invoke('script:clear-execution-history'),

  // リリース情報 (ORDER_045 / TASK_597)
  getOrderReleaseInfo: (projectName: string, orderId: string) =>
    ipcRenderer.invoke('project:get-order-release-info', projectName, orderId),

  // リリース実行 (ORDER_108 / TASK_995)
  executeRelease: (projectName: string, orderId: string) =>
    ipcRenderer.invoke('project:execute-release', projectName, orderId),
  executeReleaseDryRun: (projectName: string, orderId: string) =>
    ipcRenderer.invoke('project:execute-release-dryrun', projectName, orderId),

  getOrderRelatedInfo: (projectName: string, orderId: string) =>
    ipcRenderer.invoke('project:get-order-related-info', projectName, orderId),

  // aipm_autoログ (ORDER_050)
  getAipmAutoLogDirectories: () =>
    ipcRenderer.invoke('aipm-auto-log:list-directories'),
  getAipmAutoLogFiles: (projectName: string, orderId?: string) =>
    ipcRenderer.invoke('aipm-auto-log:list-files', projectName, orderId),
  readAipmAutoLogFile: (
    filePath: string,
    options?: { tailLines?: number; fromPosition?: number }
  ) => ipcRenderer.invoke('aipm-auto-log:read-file', filePath, options),
  getLatestAipmAutoLog: (projectName: string) =>
    ipcRenderer.invoke('aipm-auto-log:get-latest', projectName),
  startAipmAutoLogWatcher: (projectName: string) =>
    ipcRenderer.invoke('aipm-auto-log:watch-start', projectName),
  stopAipmAutoLogWatcher: () =>
    ipcRenderer.invoke('aipm-auto-log:watch-stop'),
  getAipmAutoLogWatcherStatus: () =>
    ipcRenderer.invoke('aipm-auto-log:watch-status'),
  onAipmAutoLogUpdate: (callback: (event: LogUpdateEvent) => void) =>
    createEventListener('aipm-auto-log:update', callback),
  onAipmAutoLogReady: (callback: () => void) =>
    createEventListener('aipm-auto-log:ready', callback),
  onAipmAutoLogError: (callback: (error: { message: string }) => void) =>
    createEventListener('aipm-auto-log:error', callback),
  onAipmAutoLogStopped: (callback: () => void) =>
    createEventListener('aipm-auto-log:stopped', callback),

  // Supervisor / XBacklog (ORDER_059 / TASK_655)
  getSupervisors: () =>
    ipcRenderer.invoke('get-supervisors'),
  getSupervisorDetail: (supervisorId: string) =>
    ipcRenderer.invoke('get-supervisor-detail', supervisorId),
  getProjectsBySupervisor: (supervisorId: string, includeInactive?: boolean) =>
    ipcRenderer.invoke('get-projects-by-supervisor', supervisorId, includeInactive),
  getXBacklogs: (supervisorId: string) =>
    ipcRenderer.invoke('get-xbacklogs', supervisorId),
  createXBacklog: (supervisorId: string, title: string, description: string | null, priority: string) =>
    ipcRenderer.invoke('create-xbacklog', supervisorId, title, description, priority),
  analyzeXBacklog: (xbacklogId: string) =>
    ipcRenderer.invoke('analyze-xbacklog', xbacklogId),
  dispatchXBacklog: (xbacklogId: string, projectId: string) =>
    ipcRenderer.invoke('dispatch-xbacklog', xbacklogId, projectId),

  // ポートフォリオビュー（ORDER_068 / BACKLOG_116）
  getPortfolioData: (supervisorId: string) =>
    ipcRenderer.invoke('get-portfolio-data', supervisorId),
  getPortfolioOrderTasks: (projectId: string, orderId: string) =>
    ipcRenderer.invoke('get-portfolio-order-tasks', projectId, orderId),

  // メニュー更新イベント（ORDER_063 / TASK_677）
  onMenuUpdate: (callback: () => void) =>
    createEventListener('menu:update', callback),

  // タスクポーリング（ORDER_101）
  startTaskPolling: (projectId: string, orderId: string, intervalMs?: number) =>
    ipcRenderer.invoke('script:start-task-polling', projectId, orderId, intervalMs),
  stopTaskPolling: () =>
    ipcRenderer.invoke('script:stop-task-polling'),
  // ORDER_119: タスク実行ステップ取得
  getTaskExecutionSteps: (projectId: string, taskId: string) =>
    ipcRenderer.invoke('script:get-task-execution-steps', projectId, taskId),

  onTaskStatusChanged: (callback: (data: {
    taskId: string; title: string; oldStatus: string; newStatus: string; projectId: string; orderId: string;
  }) => void) =>
    createEventListener('script:task-status-changed', callback),
  onAllTasksCompleted: (callback: (data: {
    projectId: string; orderId: string; tasks: Array<{ id: string; title: string; status: string }>;
  }) => void) =>
    createEventListener('script:all-tasks-completed', callback),
  onTaskTimeout: (callback: (data: {
    taskId: string; title: string; elapsedMs: number; projectId: string; orderId: string;
  }) => void) =>
    createEventListener('script:task-timeout', callback),
  onTaskError: (callback: (data: {
    taskId: string; title: string; status: string; projectId: string; orderId: string; logFile?: string; message?: string;
  }) => void) =>
    createEventListener('script:task-error', callback),

  // タスククラッシュ通知（ORDER_109）
  onTaskCrash: (callback: (data: {
    taskId: string; projectId: string; orderId: string; pid: number; logFile: string; message: string;
  }) => void) =>
    createEventListener('script:task-crash', callback),

  // Worker ログ一覧・読み込み・監視（ORDER_111 / TASK_1001）
  getWorkerLogs: (projectId: string, orderId?: string) =>
    ipcRenderer.invoke('script:get-worker-logs', projectId, orderId),
  readWorkerLog: (
    filePath: string,
    options?: { tailLines?: number; fromPosition?: number }
  ) => ipcRenderer.invoke('script:read-worker-log', filePath, options),
  watchWorkerLog: (filePath: string) =>
    ipcRenderer.invoke('script:watch-worker-log', filePath),
  unwatchWorkerLog: (filePath: string) =>
    ipcRenderer.invoke('script:unwatch-worker-log', filePath),
  onWorkerLogUpdate: (callback: (data: WorkerLogUpdateEvent) => void) =>
    createEventListener('script:worker-log-update', callback),

  // タスク依存関係リアルタイム更新（ORDER_122 / TASK_1103）
  getDependencyStatus: (projectId: string, taskId?: string, orderId?: string) =>
    ipcRenderer.invoke('dependency:get-status', projectId, taskId, orderId),
  onDependencyUpdate: (callback: (data: {
    projectId: string;
    orderId: string;
    taskId: string;
    dependencyStatus: any;
    timestamp: string;
  }) => void) =>
    createEventListener('dependency:update', callback),

  // ORDER_140 / TASK_1168: イベント監視
  startDependencyMonitoring: (projectId: string, orderId: string) =>
    ipcRenderer.invoke('dependency:start-monitoring', projectId, orderId),
  stopDependencyMonitoring: (projectId: string, orderId: string) =>
    ipcRenderer.invoke('dependency:stop-monitoring', projectId, orderId),

  // RESULT Markdownファイル読み込み（ORDER_127 / TASK_1122）
  getOrderResultFile: (projectId: string, orderId: string, filename: string) =>
    ipcRenderer.invoke('project:get-order-result-file', projectId, orderId, filename),
  getOrderReportList: (projectId: string, orderId: string) =>
    ipcRenderer.invoke('project:get-order-report-list', projectId, orderId),
  getOrderReport: (projectId: string, orderId: string, reportFilename: string) =>
    ipcRenderer.invoke('project:get-order-report', projectId, orderId, reportFilename),

  // ORDER_134: TASK_1149 - リリース準備状況取得
  getOrderReleaseReadiness: (projectId: string, orderId: string) =>
    ipcRenderer.invoke('project:get-order-release-readiness', projectId, orderId),

  // ORDER_128: TASK_1126 - タスクログ末尾取得
  getTaskLogTail: (projectId: string, orderId: string, taskId: string, lines?: number) =>
    ipcRenderer.invoke('project:get-task-log-tail', projectId, orderId, taskId, lines),

  // ORDER_128: TASK_1127 - タスク進捗情報取得
  getTaskProgressInfo: (projectId: string, orderId: string) =>
    ipcRenderer.invoke('project:get-task-progress-info', projectId, orderId),

  // ORDER_138: TASK_1158 - レビュー履歴取得
  getTaskReviewHistory: (projectId: string, taskId: string) =>
    ipcRenderer.invoke('project:get-task-review-history', projectId, taskId),

  // ORDER_156: TASK_1233 - プロジェクト情報取得・更新
  getProjectInfo: (projectId: string) =>
    ipcRenderer.invoke('project:get-project-info', projectId),
  updateProjectInfo: (projectId: string, updates: {
    description?: string;
    purpose?: string;
    tech_stack?: string;
  }) =>
    ipcRenderer.invoke('project:update-project-info', projectId, updates),

  // ORDER_157: DB初期化ステータス
  getDbInitStatus: () =>
    ipcRenderer.invoke('db:get-init-status'),

  // ORDER_164: ターミナル起動
  openTerminal: () =>
    ipcRenderer.invoke('terminal:open'),

  // プロジェクト作成・削除（ORDER_002 / BACKLOG_001）
  createProject: (projectId: string, name?: string) =>
    ipcRenderer.invoke('project:create-project', projectId, name),
  deleteProject: (projectId: string, force?: boolean) =>
    ipcRenderer.invoke('project:delete-project', projectId, force),

  // DB変更通知（ORDER_004 / TASK_010）
  onDbChanged: (callback: (event: DbChangedEvent) => void) =>
    createEventListener('db:changed', callback),
};

contextBridge.exposeInMainWorld('electronAPI', electronAPI);

// 型定義をグローバルに追加（TypeScript用）
declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}

console.log('[Preload] Electron API exposed to renderer');
