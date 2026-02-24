/**
 * ProjectService - プロジェクト管理サービス
 *
 * AI PM Frameworkのプロジェクト一覧取得・状態管理を担当するサービス
 * PROJECTS/配下のプロジェクトディレクトリを検出し、各STATE.mdをパースする
 *
 * TASK_018: ProjectService実装（IPC含む）
 * TASK_198: ProjectService DB統合（ORDER_011 DB連携実装 Phase 1）
 * TASK_963: REVIEWファイル読み込みロジック調整（統合フォーマット対応）
 *   - REVIEWファイルにREPORT内容が統合される前提（「実施内容」+「判定結果」セクション）
 *   - getReportFileContent()は内部利用・互換性維持のため残存
 *   - UIからはgetReviewFileContent()のみ使用（2タブ構成: TASK/REVIEW）
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { EventEmitter } from 'node:events';
import { StateParser, type ParsedState } from './StateParser';
import { getConfigService } from './ConfigService';
import { getAipmDbService, type AipmOrder, type AipmTask } from './AipmDbService';
import { fileWatcherService, type FileChangeEvent } from './FileWatcherService';

/**
 * プロジェクト情報
 */
export interface Project {
  /** プロジェクト名（ディレクトリ名） */
  name: string;
  /** プロジェクトパス */
  path: string;
  /** STATE.mdのパース結果 */
  state: ParsedState | null;
  /** STATE.mdの最終更新日時 */
  lastUpdated: Date | null;
  /** STATE.mdが存在するか */
  hasStateFile: boolean;
}

/**
 * プロジェクト一覧結果
 */
export interface ProjectListResult {
  /** プロジェクト一覧 */
  projects: Project[];
  /** フレームワークパス */
  frameworkPath: string;
  /** エラーメッセージ（あれば） */
  error?: string;
}

/**
 * データソースの種類
 */
export type DataSource = 'db' | 'file';

/**
 * 成果物ファイル情報
 */
export interface ArtifactFile {
  /** ファイル名 */
  name: string;
  /** 相対パス（表示用） */
  path: string;
  /** ファイルタイプ */
  type: 'file' | 'directory';
  /** 拡張子（ファイルの場合のみ） */
  extension?: string;
  /** 実ファイルの絶対パス（REPORTから抽出した開発ディレクトリパス） */
  absolutePath?: string;
  /** 元のREPORTファイルパス */
  reportFile?: string;
}

/**
 * ProjectService クラス
 */
export class ProjectService extends EventEmitter {
  private parser: StateParser;
  private projectCache: Map<string, Project> = new Map();
  private isListening = false;

  constructor() {
    super();
    this.parser = new StateParser();
  }

  /**
   * 現在のデータソースを取得
   * @returns 常に 'db' (DB駆動のみ)
   */
  getDataSource(): DataSource {
    return 'db';
  }

  /**
   * プロジェクト一覧を取得（DB駆動のみ）
   */
  getProjects(): ProjectListResult {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return {
        projects: [],
        frameworkPath: '',
        error: 'フレームワークパスが設定されていません',
      };
    }

    console.log('[ProjectService] Using DB data source');
    return this.getProjectsFromDb(frameworkPath);
  }

  /**
   * DBからプロジェクト一覧を取得
   *
   * ORDER_016: DB直接参照対応
   * - STATE.mdのパースは行わず、getProjectState()呼び出し時にDB由来データを取得
   * - STATE.mdが存在しない場合でも基本情報を返却
   */
  private getProjectsFromDb(frameworkPath: string): ProjectListResult {
    try {
      const configService = getConfigService();
      const aipmDbService = getAipmDbService();
      // デフォルトでアクティブプロジェクトのみ取得（is_active = 1）
      const dbProjects = aipmDbService.getProjects(false);

      console.log(`[ProjectService] Loading ${dbProjects.length} active projects from DB`);

      const projects: Project[] = dbProjects.map((dbProject) => {
        // プロジェクトのIDをnameとして使用（フォルダ名と一致、backlog/list.pyのproject_idとも一致）
        const projectId = dbProject.id;
        // dbProject.pathは相対パス（例: "PROJECTS/ai_pm_manager"）なので、userDataPathと結合
        const projectPath = dbProject.path
          ? path.join(configService.getUserDataPath(), dbProject.path)
          : path.join(configService.getProjectsBasePath(), projectId);
        const stateFilePath = path.join(projectPath, 'STATE.md');
        const hasStateFile = fs.existsSync(stateFilePath);

        // DB駆動: getProjectState()呼び出し時にDB由来データを取得するため
        // ここではstateをnullのままにする（遅延ロード）
        // キャッシュがあればそれを使用
        const cachedProject = this.projectCache.get(projectId);

        let lastUpdated: Date | null = cachedProject?.lastUpdated ?? null;
        if (hasStateFile && !lastUpdated) {
          try {
            const stats = fs.statSync(stateFilePath);
            lastUpdated = stats.mtime;
          } catch {
            // ignore stat errors
          }
        }

        const project: Project = {
          name: projectId, // DBのidを使用（フォルダ名、バックログのproject_idと一致）
          path: projectPath,
          state: cachedProject?.state ?? null, // 遅延ロード: getProjectState()で取得
          lastUpdated,
          hasStateFile,
        };

        // キャッシュを更新
        this.projectCache.set(projectId, project);

        return project;
      });

      // プロジェクト名でソート
      projects.sort((a, b) => a.name.localeCompare(b.name));

      console.log(`[ProjectService] Loaded ${projects.length} projects from DB (data source: db)`);

      return {
        projects,
        frameworkPath,
      };
    } catch (error) {
      console.error('[ProjectService] getProjectsFromDb failed:', error);
      const errorMessage = error instanceof Error ? error.message : String(error);
      return {
        projects: [],
        frameworkPath,
        error: `プロジェクト一覧の取得に失敗しました: ${errorMessage}`,
      };
    }
  }

  /**
   * 指定されたフレームワークパスからプロジェクト一覧を取得
   */
  getProjectsFromPath(frameworkPath: string): ProjectListResult {
    const configService = getConfigService();
    const projectsDir = configService.getProjectsBasePath();

    if (!fs.existsSync(projectsDir)) {
      return {
        projects: [],
        frameworkPath,
        error: `PROJECTSディレクトリが見つかりません: ${projectsDir}`,
      };
    }

    try {
      const entries = fs.readdirSync(projectsDir, { withFileTypes: true });
      const projects: Project[] = [];

      for (const entry of entries) {
        if (!entry.isDirectory()) continue;

        const projectName = entry.name;
        const projectPath = path.join(projectsDir, projectName);
        const stateFilePath = path.join(projectPath, 'STATE.md');

        const project = this.loadProject(projectName, projectPath, stateFilePath);
        projects.push(project);

        // キャッシュを更新
        this.projectCache.set(projectName, project);
      }

      // プロジェクト名でソート
      projects.sort((a, b) => a.name.localeCompare(b.name));

      return {
        projects,
        frameworkPath,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      return {
        projects: [],
        frameworkPath,
        error: `プロジェクト一覧の取得に失敗しました: ${errorMessage}`,
      };
    }
  }

  /**
   * 特定のプロジェクトのSTATE情報を取得（DB駆動のみ）
   *
   * ORDER_016: DB直接参照対応
   * - 常にDBからデータを取得
   * - STATE.mdが存在しなくてもDB由来データを返却（FR-005）
   */
  getProjectState(projectName: string): ParsedState | null {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return null;
    }

    console.log(`[ProjectService] Getting project state from DB for ${projectName} (data source: db)`);
    const dbState = this.getProjectStateFromDb(projectName);
    if (dbState) {
      // DBからの取得成功 - STATE.md有無に関わらずDB由来データを返却
      const stateFilePath = path.join(configService.getProjectsBasePath(), projectName, 'STATE.md');
      const hasStateFile = fs.existsSync(stateFilePath);
      if (!hasStateFile) {
        console.log(`[ProjectService] STATE.md not found for ${projectName}, but returning DB-derived data (FR-005)`);
      }
      return dbState;
    }

    console.log(`[ProjectService] DB query failed for ${projectName}, returning null`);
    return null;
  }

  /**
   * DBからプロジェクト状態を取得し、ParsedState型に変換
   *
   * ORDER_016: DB直接参照対応
   * - ORDER一覧をDBから直接取得（FR-001）
   * - タスク一覧をDBから直接取得（FR-002）
   * - 進捗サマリをDB由来データから計算（FR-004）
   * - STATE.mdのパースは不要
   */
  private getProjectStateFromDb(projectName: string): ParsedState | null {
    try {
      const aipmDbService = getAipmDbService();
      const dbProjects = aipmDbService.getProjects();
      // projectNameはDBのid（例: AI_PM_PJ）なので、p.idで検索
      const dbProject = dbProjects.find((p) => p.id === projectName);

      if (!dbProject) {
        console.warn(`[ProjectService] Project not found in DB: ${projectName}`);
        return null;
      }

      // ORDER一覧をDBから直接取得（FR-001）
      // 注: getOrders()はproject_id（内部ID）を期待するため、dbProject.idを使用
      const orders = aipmDbService.getOrders(dbProject.id);
      console.log(`[ProjectService] [DB] Loaded ${orders.length} orders for ${projectName} (id: ${dbProject.id})`);

      // 現在のORDER（currentOrderIdがある場合はそれを使用、なければ最新）
      const currentOrder = dbProject.currentOrderId
        ? orders.find((o) => o.id === dbProject.currentOrderId)
        : orders[orders.length - 1];

      // 全ORDERのタスク一覧をDBから直接取得（FR-002）
      // 注: getTasks()はproject_id（内部ID）を期待するため、dbProject.idを使用
      const orderInfos = orders.map((order) => {
        const orderTasks = aipmDbService.getTasks(order.id, dbProject.id);
        return {
          order,
          tasks: orderTasks,
        };
      });

      // 全タスク数を計算
      const totalTasks = orderInfos.reduce((sum, oi) => sum + oi.tasks.length, 0);
      console.log(`[ProjectService] [DB] Loaded ${totalTasks} tasks across ${orders.length} orders for ${projectName}`);

      // ParsedState型に変換（進捗サマリはDB由来データから計算: FR-004）
      const state = this.convertDbDataToParsedState(
        projectName,
        dbProject.status,
        currentOrder,
        orderInfos
      );

      console.log(`[ProjectService] [DB] Project state loaded for ${projectName}: completed=${state.progressSummary.completed}, inProgress=${state.progressSummary.inProgress}, total=${state.progressSummary.total}`);

      return state;
    } catch (error) {
      console.error(`[ProjectService] getProjectStateFromDb failed for ${projectName}:`, error);
      return null;
    }
  }

  /**
   * DB由来のデータをParsedState型に変換
   * StateParserのParsedState型に準拠
   */
  private convertDbDataToParsedState(
    projectName: string,
    projectStatus: string,
    currentOrder: AipmOrder | undefined,
    orderInfos: Array<{ order: AipmOrder; tasks: AipmTask[] }>
  ): ParsedState {
    // 全タスクを収集
    const allTasks: AipmTask[] = [];
    for (const { tasks } of orderInfos) {
      allTasks.push(...tasks);
    }

    // タスク情報を変換（StateParserのTaskInfo型に準拠）
    const parsedTasks = allTasks.map((task) => ({
      id: task.id,
      title: task.title,
      status: task.status,
      assignee: task.assignee || '-',
      dependencies: task.dependencies,
      startDate: task.startedAt || undefined,
      completedDate: task.completedAt || undefined,
    }));

    // ステータス別にタスク数を計算
    const completed = allTasks.filter((t) => t.status === 'COMPLETED').length;
    const inProgress = allTasks.filter((t) => t.status === 'IN_PROGRESS').length;
    const reviewWaiting = allTasks.filter((t) => t.status === 'DONE').length;
    const queued = allTasks.filter((t) => t.status === 'QUEUED').length;
    const blocked = allTasks.filter((t) => t.status === 'BLOCKED').length;
    const rework = allTasks.filter((t) => t.status === 'REWORK').length;

    // ORDER一覧を変換（StateParserのOrderInfo型に準拠）
    const parsedOrders = orderInfos.map(({ order, tasks }) => ({
      id: order.id,
      title: order.title,
      status: order.status,
      tasks: tasks.map((task) => ({
        id: task.id,
        title: task.title,
        status: task.status,
        assignee: task.assignee || '-',
        dependencies: task.dependencies,
        startDate: task.startedAt || undefined,
        completedDate: task.completedAt || undefined,
      })),
    }));

    // プロジェクト情報を構築
    const projectInfo = {
      name: projectName,
      status: projectStatus,
      activeOrderCount: orderInfos.filter((o) => o.order.status === 'IN_PROGRESS').length,
      currentOrderId: currentOrder?.id,
    };

    // 進捗サマリを構築
    const progressSummary = {
      completed,
      inProgress,
      reviewWaiting,
      queued,
      blocked,
      rework,
      total: allTasks.length,
    };

    return {
      projectInfo,
      tasks: parsedTasks,
      progressSummary,
      orders: parsedOrders,
    };
  }

  /**
   * プロジェクトを読み込む
   */
  private loadProject(
    projectName: string,
    projectPath: string,
    stateFilePath: string
  ): Project {
    const hasStateFile = fs.existsSync(stateFilePath);
    let state: ParsedState | null = null;
    let lastUpdated: Date | null = null;

    if (hasStateFile) {
      try {
        state = this.parser.parseFile(stateFilePath);
        const stats = fs.statSync(stateFilePath);
        lastUpdated = stats.mtime;
      } catch (error) {
        console.error(`[ProjectService] Failed to parse STATE.md for ${projectName}:`, error);
      }
    }

    return {
      name: projectName,
      path: projectPath,
      state,
      lastUpdated,
      hasStateFile,
    };
  }

  /**
   * FileWatcherServiceからの変更通知を監視開始
   */
  startListening(): void {
    if (this.isListening) return;

    fileWatcherService.on('change', this.handleFileChange.bind(this));
    this.isListening = true;
    console.log('[ProjectService] Started listening for file changes');
  }

  /**
   * 監視停止
   */
  stopListening(): void {
    if (!this.isListening) return;

    fileWatcherService.removeAllListeners('change');
    this.isListening = false;
    console.log('[ProjectService] Stopped listening for file changes');
  }

  /**
   * ファイル変更を処理
   */
  private handleFileChange(event: FileChangeEvent): void {
    const { projectName, filePath, eventType } = event;

    console.log(`[ProjectService] File change detected: ${projectName} (${eventType})`);

    // STATE.mdをリパース
    let state: ParsedState | null = null;
    let lastUpdated: Date | null = null;

    if (eventType !== 'unlink' && fs.existsSync(filePath)) {
      try {
        state = this.parser.parseFile(filePath);
        const stats = fs.statSync(filePath);
        lastUpdated = stats.mtime;
      } catch (error) {
        console.error(`[ProjectService] Failed to parse STATE.md for ${projectName}:`, error);
      }
    }

    // キャッシュを更新
    const cachedProject = this.projectCache.get(projectName);
    if (cachedProject) {
      cachedProject.state = state;
      cachedProject.lastUpdated = lastUpdated;
      cachedProject.hasStateFile = eventType !== 'unlink';
    }

    // イベントを発行
    this.emit('project-state-changed', {
      projectName,
      state,
      eventType,
      timestamp: event.timestamp,
    });
  }

  /**
   * タスクファイル (TASK_XXX.md) の内容を取得
   * ファイルが存在しない場合はDBからタスク情報を取得して疑似Markdown形式で返す
   * @param projectName プロジェクト名
   * @param taskId タスクID (例: "TASK_023")
   * @returns ファイル内容（見つからない場合はnull）
   */
  getTaskFileContent(projectName: string, taskId: string): string | null {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return null;
    }

    const projectPath = path.join(configService.getProjectsBasePath(), projectName);

    // RESULT/ORDER_XXX/04_QUEUE/ の下を検索
    const resultDir = path.join(projectPath, 'RESULT');
    if (fs.existsSync(resultDir)) {
      // ORDER_XXXディレクトリを検索
      try {
        const orderDirs = fs.readdirSync(resultDir, { withFileTypes: true })
          .filter(d => d.isDirectory() && d.name.startsWith('ORDER_'))
          .map(d => d.name)
          .sort((a, b) => b.localeCompare(a)); // 降順ソート（最新ORDER優先）

        for (const orderDir of orderDirs) {
          const taskFileName = `${taskId}.md`;
          // 04_QUEUE と 04_TASK の両方を検索（ORDERのフォーマットにより異なる）
          for (const taskDirName of ['04_QUEUE', '04_TASK']) {
            const taskDir = path.join(resultDir, orderDir, taskDirName);
            if (fs.existsSync(taskDir)) {
              const taskFilePath = path.join(taskDir, taskFileName);
              if (fs.existsSync(taskFilePath)) {
                return fs.readFileSync(taskFilePath, 'utf-8');
              }
            }
          }
        }
      } catch (error) {
        console.error(`[ProjectService] Failed to read task file ${taskId}:`, error);
      }
    }

    // ファイルが見つからない場合はDBから取得
    try {
      const aipmDbService = getAipmDbService();
      if (aipmDbService) {
        const task = aipmDbService.getTask(taskId, projectName);
        if (task) {
          // 疑似Markdownを生成
          const lines: string[] = [
            `# ${task.id}: ${task.title}`,
            '',
            '## 概要',
            '',
            task.description || '（説明なし）',
            '',
            '## 情報',
            '',
            `| 項目 | 値 |`,
            `|------|-----|`,
            `| ORDER ID | ${task.orderId} |`,
            `| ステータス | ${task.status} |`,
            `| 優先度 | ${task.priority} |`,
            `| 担当者 | ${task.assignee || '-'} |`,
            `| 推奨モデル | ${task.recommendedModel} |`,
            `| 依存タスク | ${task.dependencies.length > 0 ? task.dependencies.join(', ') : '-'} |`,
            `| 開始日時 | ${task.startedAt || '-'} |`,
            `| 完了日時 | ${task.completedAt || '-'} |`,
            '',
            '---',
            '',
            '*このデータはDBから取得されました（TASKファイルが存在しません）*',
          ];
          return lines.join('\n');
        }
      }
    } catch (error) {
      console.error(`[ProjectService] Failed to get task from DB ${taskId}:`, error);
    }

    return null;
  }

  /**
   * REPORTファイル (REPORT_XXX.md) の内容を取得
   *
   * NOTE (TASK_963): TASK_960以降、REVIEWファイルにREPORT内容が統合されるため、
   * UIからはgetReviewFileContent()のみ使用される（2タブ構成: TASK/REVIEW）。
   * この関数は内部利用・互換性維持のために残す。IPC経由(project:get-report-file)も残存。
   *
   * @param projectName プロジェクト名
   * @param taskId タスクID (例: "TASK_023")
   * @returns ファイル内容（見つからない場合はnull）
   * @internal UIからは直接呼ばれない（TASK_962で2タブ構成に変更済み）
   */
  getReportFileContent(projectName: string, taskId: string): string | null {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return null;
    }

    const projectPath = path.join(configService.getProjectsBasePath(), projectName);

    // RESULT/ORDER_XXX/05_REPORT/ の下を検索
    const resultDir = path.join(projectPath, 'RESULT');
    if (!fs.existsSync(resultDir)) {
      return null;
    }

    // タスクIDから番号を抽出 (例: "TASK_023" -> "023")
    const taskNumber = taskId.replace('TASK_', '');

    try {
      const orderDirs = fs.readdirSync(resultDir, { withFileTypes: true })
        .filter(d => d.isDirectory() && d.name.startsWith('ORDER_'))
        .map(d => d.name)
        .sort((a, b) => b.localeCompare(a)); // 降順ソート（最新ORDER優先）

      for (const orderDir of orderDirs) {
        const reportDir = path.join(resultDir, orderDir, '05_REPORT');
        if (fs.existsSync(reportDir)) {
          const reportFileName = `REPORT_${taskNumber}.md`;
          const reportFilePath = path.join(reportDir, reportFileName);
          if (fs.existsSync(reportFilePath)) {
            return fs.readFileSync(reportFilePath, 'utf-8');
          }
        }
      }
    } catch (error) {
      console.error(`[ProjectService] Failed to read report file for ${taskId}:`, error);
    }

    return null;
  }

  /**
   * REVIEWファイル (REVIEW_XXX.md) の内容を取得
   *
   * TASK_960以降、REVIEWファイルには統合フォーマットが使用される:
   * - 「## 基本情報」: タスクID、タスク名、レビュー日時、判定
   * - 「## 実施内容」: REPORT内容（Worker実行結果）が統合されたセクション
   * - 「## 判定結果」: PM判定理由・チェックリスト・指摘事項・改善提案
   *
   * この関数はファイル全体をそのまま返すため、統合フォーマットに特別な処理は不要。
   * UIのMarkdownレンダラーが各セクションを適切に表示する。
   *
   * @param projectName プロジェクト名
   * @param taskId タスクID (例: "TASK_023")
   * @returns ファイル内容（見つからない場合はnull）
   */
  getReviewFileContent(projectName: string, taskId: string): string | null {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      console.warn(`[ProjectService] getReviewFileContent: frameworkPath not set for ${taskId}`);
      return null;
    }

    // Roaming絶対パスを使用（getProjectsBasePath()は%APPDATA%/ai-pm-manager-v2/PROJECTS/を返す）
    const projectsBasePath = configService.getProjectsBasePath();
    const projectPath = path.join(projectsBasePath, projectName);

    // RESULT/ORDER_XXX/07_REVIEW/ の下を検索
    const resultDir = path.join(projectPath, 'RESULT');
    console.log(`[ProjectService] getReviewFileContent: searching in ${resultDir} for ${taskId}`);

    if (!fs.existsSync(resultDir)) {
      console.warn(`[ProjectService] getReviewFileContent: RESULT dir not found: ${resultDir}`);
      return null;
    }

    // タスクIDから番号を抽出 (例: "TASK_023" -> "023")
    const taskNumber = taskId.replace('TASK_', '');

    try {
      const orderDirs = fs.readdirSync(resultDir, { withFileTypes: true })
        .filter(d => d.isDirectory() && d.name.startsWith('ORDER_'))
        .map(d => d.name)
        .sort((a, b) => b.localeCompare(a)); // 降順ソート（最新ORDER優先）

      console.log(`[ProjectService] getReviewFileContent: scanning ${orderDirs.length} ORDER dirs for REVIEW_${taskNumber}.md`);

      for (const orderDir of orderDirs) {
        const reviewDir = path.join(resultDir, orderDir, '07_REVIEW');
        if (fs.existsSync(reviewDir)) {
          const reviewFileName = `REVIEW_${taskNumber}.md`;
          const reviewFilePath = path.join(reviewDir, reviewFileName);
          if (fs.existsSync(reviewFilePath)) {
            console.log(`[ProjectService] getReviewFileContent: found ${reviewFilePath}`);
            return fs.readFileSync(reviewFilePath, 'utf-8');
          }
        }
      }
      console.log(`[ProjectService] getReviewFileContent: REVIEW_${taskNumber}.md not found in any ORDER dir`);
    } catch (error) {
      console.error(`[ProjectService] Failed to read review file for ${taskId}:`, error);
    }

    return null;
  }

  /**
   * ORDERファイル (ORDER_XXX.md) の内容を取得
   * ファイルが存在しない場合はDBからORDER情報を取得して疑似Markdown形式で返す
   * @param projectName プロジェクト名
   * @param orderId ORDER ID (例: "ORDER_010")
   * @returns ファイル内容（見つからない場合はnull）
   */
  getOrderFileContent(projectName: string, orderId: string): string | null {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return null;
    }

    const projectPath = path.join(configService.getProjectsBasePath(), projectName);

    // ORDERS/ORDER_XXX.md を検索
    const ordersDir = path.join(projectPath, 'ORDERS');
    if (fs.existsSync(ordersDir)) {
      const orderFileName = `${orderId}.md`;
      const orderFilePath = path.join(ordersDir, orderFileName);
      if (fs.existsSync(orderFilePath)) {
        try {
          return fs.readFileSync(orderFilePath, 'utf-8');
        } catch (error) {
          console.error(`[ProjectService] Failed to read order file ${orderId}:`, error);
        }
      }
    }

    // ファイルが見つからない場合はDBから取得
    try {
      const aipmDbService = getAipmDbService();
      if (aipmDbService && aipmDbService.isAvailable()) {
        const orders = aipmDbService.getOrders(projectName);
        const order = orders.find((o) => o.id === orderId);
        if (order) {
          const progress = order.taskCount > 0
            ? Math.round((order.completedTaskCount / order.taskCount) * 100)
            : 0;

          // タスク一覧も取得
          let taskLines: string[] = [];
          try {
            const tasks = aipmDbService.getTasks(orderId, projectName);
            if (tasks && tasks.length > 0) {
              taskLines = [
                '',
                '## タスク一覧',
                '',
                '| ID | タイトル | ステータス | 優先度 |',
                '|-----|---------|----------|--------|',
                ...tasks.map((t) =>
                  `| ${t.id} | ${t.title} | ${t.status} | ${t.priority} |`
                ),
              ];
            }
          } catch {
            // タスク取得失敗時は無視
          }

          const lines: string[] = [
            `# ${order.title}`,
            '',
            `**${order.id}** | ${order.status} | ${order.priority} | 進捗 ${progress}% (${order.completedTaskCount}/${order.taskCount})`,
            '',
            '---',
            '',
            '## 基本情報',
            '',
            `- **プロジェクト**: ${order.projectId}`,
            `- **作成日時**: ${order.createdAt}`,
            ...(order.startedAt ? [`- **開始日時**: ${order.startedAt}`] : []),
            ...(order.completedAt ? [`- **完了日時**: ${order.completedAt}`] : []),
            ...taskLines,
          ];
          return lines.join('\n');
        }
      }
    } catch (error) {
      console.error(`[ProjectService] Failed to get order from DB ${orderId}:`, error);
    }

    return null;
  }

  /**
   * PROJECT_INFO.md ファイルの内容を取得
   * @param projectName プロジェクト名
   * @returns ファイル内容（見つからない場合はnull）
   */
  getProjectInfoFileContent(projectName: string): string | null {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return null;
    }

    const projectInfoPath = path.join(configService.getProjectsBasePath(), projectName, 'PROJECT_INFO.md');
    if (fs.existsSync(projectInfoPath)) {
      try {
        return fs.readFileSync(projectInfoPath, 'utf-8');
      } catch (error) {
        console.error(`[ProjectService] Failed to read PROJECT_INFO.md for ${projectName}:`, error);
      }
    }

    return null;
  }

  /**
   * INFO_PAGESのページ一覧を取得（index.json）
   * @param projectName プロジェクト名
   * @returns ページ一覧（INFO_PAGESが存在しない場合はnull）
   */
  getInfoPages(projectName: string): { version: string; project_id: string; pages: Array<{ id: string; title: string; file: string; icon: string; description: string }> } | null {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return null;
    }

    const indexPath = path.join(configService.getProjectsBasePath(), projectName, 'INFO_PAGES', 'index.json');
    if (fs.existsSync(indexPath)) {
      try {
        const content = fs.readFileSync(indexPath, 'utf-8');
        return JSON.parse(content);
      } catch (error) {
        console.error(`[ProjectService] Failed to read INFO_PAGES/index.json for ${projectName}:`, error);
      }
    }

    return null;
  }

  /**
   * INFO_PAGESの指定ページのコンテンツを取得
   * @param projectName プロジェクト名
   * @param pageId ページID
   * @returns ページコンテンツ（見つからない場合はnull）
   */
  getInfoPageContent(projectName: string, pageId: string): string | null {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return null;
    }

    // index.jsonからファイル名を取得
    const pages = this.getInfoPages(projectName);
    if (!pages) {
      return null;
    }

    const page = pages.pages.find(p => p.id === pageId);
    if (!page) {
      return null;
    }

    const pagePath = path.join(configService.getProjectsBasePath(), projectName, 'INFO_PAGES', page.file);
    if (fs.existsSync(pagePath)) {
      try {
        return fs.readFileSync(pagePath, 'utf-8');
      } catch (error) {
        console.error(`[ProjectService] Failed to read INFO_PAGES/${page.file} for ${projectName}:`, error);
      }
    }

    return null;
  }

  /**
   * 成果物ファイル一覧を取得（REPORTパース方式）
   * RESULT/ORDER_XXX/05_REPORT/REPORT_*.md を列挙し、
   * 各ファイルのJSONブロック内 artifacts フィールドからファイルパスを抽出して返す。
   * @param projectName プロジェクト名
   * @param orderId ORDER ID (例: "ORDER_010")
   * @returns 成果物ファイル一覧
   */
  getArtifactFiles(projectName: string, orderId: string): ArtifactFile[] {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return [];
    }

    const projectPath = path.join(configService.getProjectsBasePath(), projectName);
    const reportDir = path.join(projectPath, 'RESULT', orderId, '05_REPORT');

    if (!fs.existsSync(reportDir)) {
      return [];
    }

    return this.parseArtifactsFromReports(reportDir);
  }

  /**
   * 05_REPORT/REPORT_*.md を列挙し、各JSONブロックの artifacts フィールドからファイルパスを抽出
   */
  private parseArtifactsFromReports(reportDir: string): ArtifactFile[] {
    const results: ArtifactFile[] = [];
    const seen = new Set<string>();

    let entries: string[];
    try {
      entries = fs.readdirSync(reportDir);
    } catch {
      return [];
    }

    const reportFiles = entries
      .filter(f => f.startsWith('REPORT_') && f.endsWith('.md'))
      .sort();

    for (const reportFileName of reportFiles) {
      const reportFilePath = path.join(reportDir, reportFileName);
      let content: string;
      try {
        content = fs.readFileSync(reportFilePath, 'utf-8');
      } catch {
        continue;
      }

      // JSONブロック（```json ... ```）を抽出してartifactsフィールドをパース
      const jsonBlockMatch = content.match(/```json\s*([\s\S]*?)\s*```/);
      if (!jsonBlockMatch) continue;

      let parsed: unknown;
      try {
        parsed = JSON.parse(jsonBlockMatch[1]);
      } catch {
        continue;
      }

      if (
        typeof parsed !== 'object' ||
        parsed === null ||
        !Array.isArray((parsed as Record<string, unknown>)['artifacts'])
      ) {
        continue;
      }

      const artifacts = (parsed as Record<string, unknown>)['artifacts'] as unknown[];
      for (const artifact of artifacts) {
        if (typeof artifact !== 'string' || !artifact) continue;

        const absolutePath = artifact;
        if (seen.has(absolutePath)) continue;
        seen.add(absolutePath);

        const fileName = path.basename(absolutePath);
        const ext = path.extname(fileName).toLowerCase();

        results.push({
          name: fileName,
          path: absolutePath, // 表示用に絶対パスをそのまま使用
          type: 'file',
          extension: ext || undefined,
          absolutePath,
          reportFile: reportFilePath,
        });
      }
    }

    return results;
  }

  /**
   * 成果物ファイルの内容を取得（実パス読み取り方式）
   * REPORTのartifactsフィールドに記録された実ファイルパス（開発ディレクトリ絶対パス）から
   * ファイル内容を直接読み取る。06_ARTIFACTS/配下のコピーファイルは参照しない。
   * @param projectName プロジェクト名（API互換性維持のため残存、内部では未使用）
   * @param orderId ORDER ID（API互換性維持のため残存、内部では未使用）
   * @param filePath 絶対ファイルパス（REPORTのartifactsフィールドから抽出した実パス）
   * @returns ファイル内容（見つからない場合はnull）
   */
  getArtifactContent(_projectName: string, _orderId: string, filePath: string): string | null {
    if (!filePath) {
      return null;
    }

    // REPORTのartifactsフィールドから取得した絶対パスを直接読み取る
    const normalizedPath = path.normalize(filePath);
    if (!path.isAbsolute(normalizedPath)) {
      console.warn(`[ProjectService] getArtifactContent: 絶対パスのみサポートしています: ${filePath}`);
      return null;
    }

    if (fs.existsSync(normalizedPath) && fs.statSync(normalizedPath).isFile()) {
      try {
        return fs.readFileSync(normalizedPath, 'utf-8');
      } catch (error) {
        console.error(`[ProjectService] Failed to read artifact file:`, error);
      }
    }

    return null;
  }

  /**
   * キャッシュをクリア
   */
  clearCache(): void {
    this.projectCache.clear();
  }

  /**
   * キャッシュからプロジェクトを取得
   */
  getCachedProject(projectName: string): Project | undefined {
    return this.projectCache.get(projectName);
  }
}

/**
 * ProjectStateChangedイベントのペイロード
 */
export interface ProjectStateChangedEvent {
  projectName: string;
  state: ParsedState | null;
  eventType: 'add' | 'change' | 'unlink';
  timestamp: Date;
}

// シングルトンインスタンス
let projectServiceInstance: ProjectService | null = null;

/**
 * ProjectServiceのシングルトンインスタンスを取得
 */
export function getProjectService(): ProjectService {
  if (!projectServiceInstance) {
    projectServiceInstance = new ProjectService();
  }
  return projectServiceInstance;
}

/**
 * ProjectServiceインスタンスをリセット（テスト用）
 */
export function resetProjectService(): void {
  if (projectServiceInstance) {
    projectServiceInstance.stopListening();
    projectServiceInstance.clearCache();
  }
  projectServiceInstance = null;
}
