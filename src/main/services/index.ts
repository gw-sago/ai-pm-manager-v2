/**
 * Services Module
 *
 * サービス層のエクスポート
 * ADR-001に基づき、状態管理をDB管理方式で実装
 */

export { FileWatcherService, fileWatcherService } from './FileWatcherService';
export type {
  FileChangeEvent,
  WatcherStatus,
} from './FileWatcherService';

export { ConfigService, getConfigService, resetConfigService } from './ConfigService';
export type {
  AppConfig,
  WindowConfig,
} from './ConfigService';

export { StateParser, StateParseError } from './StateParser';
export type {
  ParsedState,
  ProjectInfo,
  TaskInfo,
  ProgressSummary,
  OrderInfo,
} from './StateParser';

export { ProjectService, getProjectService, resetProjectService } from './ProjectService';
export type {
  Project,
  ProjectListResult,
  ProjectStateChangedEvent,
} from './ProjectService';

export { ActionGenerator, getActionGenerator, resetActionGenerator } from './ActionGenerator';
export type {
  RecommendedAction,
  ActionType,
  ActionGeneratorOptions,
} from './ActionGenerator';

export { AipmDbService, getAipmDbService, resetAipmDbService } from './AipmDbService';
export type {
  AipmProject,
  AipmOrder,
  AipmTask,
} from './AipmDbService';

export {
  RefreshService,
  getRefreshService,
  resetRefreshService,
  REFRESH_INTERVAL_MS,
  DEBOUNCE_DELAY_MS,
  MAX_RETRY_COUNT,
  RETRY_BASE_DELAY_MS,
  CONSECUTIVE_ERROR_THRESHOLD,
} from './RefreshService';
export type {
  RefreshResult,
  RefreshServiceStatus,
} from './RefreshService';

export {
  ScriptExecutionService,
  getScriptExecutionService,
  resetScriptExecutionService,
} from './ScriptExecutionService';
export type {
  ExecutionResult,
  ExecutionProgress,
} from './ScriptExecutionService';

export {
  NotificationService,
  getNotificationService,
  resetNotificationService,
} from './NotificationService';
export type {
  NotificationOptions,
} from './NotificationService';

export {
  ReleaseService,
  getReleaseService,
  resetReleaseService,
} from './ReleaseService';
export type {
  ReleaseFile,
  ReleaseInfo,
  OrderReleaseInfo,
} from './ReleaseService';

export {
  AipmAutoLogService,
  getAipmAutoLogService,
  resetAipmAutoLogService,
} from './AipmAutoLogService';
export type {
  LogFileInfo,
  LogContent,
  LogUpdateEvent,
  LogWatcherStatus,
} from './AipmAutoLogService';

export {
  SupervisorService,
  getSupervisorService,
  resetSupervisorService,
} from './SupervisorService';
export type {
  Supervisor,
  SupervisorDetail,
  SupervisorProject,
} from './SupervisorService';

export {
  XBacklogService,
  getXBacklogService,
  resetXBacklogService,
} from './XBacklogService';
export type {
  XBacklog,
  AnalysisResult,
  DispatchResult,
} from './XBacklogService';
