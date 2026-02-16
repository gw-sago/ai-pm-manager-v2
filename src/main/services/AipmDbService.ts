/**
 * AipmDbService
 *
 * AI PM Framework のDB（data/aipm.db）に接続し、データを読み取るサービス
 * ORDER_011: DB連携実装（Phase 1: 読み取り専用）
 *
 * TASK_196: AipmDbService基本実装
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import Database from 'better-sqlite3';
import { getConfigService } from './ConfigService';
import type { TaskProgressInfo } from '../../shared/types';

const execFileAsync = promisify(execFile);

/**
 * プロジェクト情報（DB由来）
 */
export interface AipmProject {
  id: string;
  name: string;
  path: string;
  status: string;
  currentOrderId: string | null;
  /** アクティブフラグ（false = 非表示対象） */
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

/**
 * ORDER情報（DB由来）
 */
export interface AipmOrder {
  id: string;
  projectId: string;
  title: string;
  priority: string;
  status: string;
  taskCount: number;
  completedTaskCount: number;
  startedAt: string | null;
  completedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * TASK情報（DB由来）
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
 * レビューキュー項目（DB由来）
 */
export interface AipmReviewItem {
  id: number;
  taskId: string;
  submittedAt: string;
  status: string;
  reviewer: string | null;
  priority: string;
  comment: string | null;
  reviewedAt: string | null;
}

/**
 * バックログ項目（DB由来）
 */
export interface AipmBacklogItem {
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
 * AipmDbService クラス
 *
 * AI PM Framework の SQLite データベースへの読み取り専用アクセスを提供
 */
export class AipmDbService {
  private db: Database.Database | null = null;
  private dbPath: string | null = null;
  private autoReorderInitialized = false;

  /**
   * DBファイルのパスを取得
   * ORDER_157: ConfigService.getAipmDbPath()に委譲し、
   * パッケージ時は%APPDATA%配下、開発時はframework/data/を参照
   * @returns DBファイルのパス（存在しない場合はnull）
   */
  getDbPath(): string | null {
    const configService = getConfigService();
    return configService.getAipmDbPath();
  }

  /**
   * DBが利用可能かどうかを判定
   * @returns DBが利用可能ならtrue
   */
  isAvailable(): boolean {
    const dbPath = this.getDbPath();

    if (!dbPath) {
      return false;
    }

    if (!fs.existsSync(dbPath)) {
      return false;
    }

    // 実際に接続できるかをテスト
    try {
      const db = new Database(dbPath, { readonly: true });
      // 簡単なクエリを実行して接続を確認
      db.prepare('SELECT 1').get();
      db.close();
      return true;
    } catch (error) {
      console.error('[AipmDbService] DB connection test failed:', error);
      return false;
    }
  }

  /**
   * DB接続を取得（遅延初期化）
   * @returns DB接続インスタンス
   * @throws DBが利用できない場合はエラー
   */
  private getConnection(): Database.Database {
    const dbPath = this.getDbPath();

    if (!dbPath) {
      throw new Error('Framework path is not configured');
    }

    // 既存の接続があり、パスが同じなら再利用
    if (this.db && this.dbPath === dbPath) {
      return this.db;
    }

    // 古い接続があれば閉じる
    if (this.db) {
      try {
        this.db.close();
      } catch {
        // ignore close errors
      }
    }

    // 新しい接続を作成
    if (!fs.existsSync(dbPath)) {
      throw new Error(`Database file not found: ${dbPath}`);
    }

    this.db = new Database(dbPath, { readonly: true });
    this.dbPath = dbPath;

    // 外部キー制約を有効化
    this.db.pragma('foreign_keys = ON');

    return this.db;
  }

  /**
   * アクティブプロジェクトのIDリストを取得
   * @returns アクティブプロジェクトのID配列
   */
  private getActiveProjectIds(): string[] {
    try {
      const db = this.getConnection();
      const stmt = db.prepare('SELECT id FROM projects WHERE is_active = 1');
      const rows = stmt.all() as Array<{ id: string }>;
      return rows.map((row) => row.id);
    } catch (error) {
      console.error('[AipmDbService] getActiveProjectIds failed:', error);
      return [];
    }
  }

  /**
   * プロジェクト一覧を取得
   * @param includeInactive 非アクティブプロジェクトを含めるか（デフォルト: false）
   * @returns プロジェクト一覧
   */
  getProjects(includeInactive = false): AipmProject[] {
    try {
      const db = this.getConnection();

      // is_active フィルタを適用（デフォルトでアクティブのみ）
      const whereClause = includeInactive ? '' : 'WHERE is_active = 1';
      const stmt = db.prepare(`
        SELECT
          id,
          name,
          path,
          status,
          current_order_id,
          is_active,
          created_at,
          updated_at
        FROM projects
        ${whereClause}
        ORDER BY name
      `);

      const rows = stmt.all() as Array<{
        id: string;
        name: string;
        path: string;
        status: string;
        current_order_id: string | null;
        is_active: number;
        created_at: string;
        updated_at: string;
      }>;

      return rows.map((row) => ({
        id: row.id,
        name: row.name,
        path: row.path,
        status: row.status,
        currentOrderId: row.current_order_id,
        isActive: row.is_active === 1,
        createdAt: row.created_at,
        updatedAt: row.updated_at,
      }));
    } catch (error) {
      console.error('[AipmDbService] getProjects failed:', error);
      throw error;
    }
  }

  /**
   * プロジェクト情報を名前で取得（ORDER_156 / TASK_1233）
   * @param projectName プロジェクト名
   * @returns プロジェクト情報（見つからない場合はnull）
   */
  getProjectByName(projectName: string): {
    id: number;
    name: string;
    path: string;
    description: string | null;
    purpose: string | null;
    tech_stack: string | null;
    status: string;
    created_at: string;
    updated_at: string;
  } | null {
    try {
      const db = this.getConnection();

      const stmt = db.prepare(`
        SELECT
          id,
          name,
          path,
          description,
          purpose,
          tech_stack,
          status,
          created_at,
          updated_at
        FROM projects
        WHERE name = ?
      `);

      const row = stmt.get(projectName) as {
        id: number;
        name: string;
        path: string;
        description: string | null;
        purpose: string | null;
        tech_stack: string | null;
        status: string;
        created_at: string;
        updated_at: string;
      } | undefined;

      return row || null;
    } catch (error) {
      console.error('[AipmDbService] getProjectByName failed:', error);
      throw error;
    }
  }

  /**
   * プロジェクト情報を更新（ORDER_156 / TASK_1233）
   * @param projectName プロジェクト名
   * @param updates 更新内容
   */
  updateProjectInfo(
    projectName: string,
    updates: {
      description?: string;
      purpose?: string;
      tech_stack?: string;
    }
  ): void {
    try {
      const db = this.getConnection();

      // 更新するフィールドを構築
      const setClauses: string[] = [];
      const values: unknown[] = [];

      if (updates.description !== undefined) {
        setClauses.push('description = ?');
        values.push(updates.description);
      }
      if (updates.purpose !== undefined) {
        setClauses.push('purpose = ?');
        values.push(updates.purpose);
      }
      if (updates.tech_stack !== undefined) {
        setClauses.push('tech_stack = ?');
        values.push(updates.tech_stack);
      }

      if (setClauses.length === 0) {
        // 更新するフィールドがない場合は何もしない
        return;
      }

      // updated_atを更新
      setClauses.push('updated_at = ?');
      values.push(new Date().toISOString());

      // WHERE句用のプロジェクト名を追加
      values.push(projectName);

      const stmt = db.prepare(`
        UPDATE projects
        SET ${setClauses.join(', ')}
        WHERE name = ?
      `);

      stmt.run(...values);
      console.log('[AipmDbService] プロジェクト情報更新完了:', projectName);
    } catch (error) {
      console.error('[AipmDbService] updateProjectInfo failed:', error);
      throw error;
    }
  }

  /**
   * ORDER一覧を取得
   * @param projectId プロジェクトID
   * @returns ORDER一覧
   */
  getOrders(projectId: string): AipmOrder[] {
    try {
      const db = this.getConnection();

      const stmt = db.prepare(`
        SELECT
          o.id,
          o.project_id,
          o.title,
          o.priority,
          o.status,
          o.started_at,
          o.completed_at,
          o.created_at,
          o.updated_at,
          (SELECT COUNT(*) FROM tasks t WHERE t.order_id = o.id AND t.project_id = o.project_id) as task_count,
          (SELECT COUNT(*) FROM tasks t WHERE t.order_id = o.id AND t.project_id = o.project_id AND t.status = 'COMPLETED') as completed_task_count
        FROM orders o
        WHERE o.project_id = ?
        ORDER BY o.id
      `);

      const rows = stmt.all(projectId) as Array<{
        id: string;
        project_id: string;
        title: string;
        priority: string;
        status: string;
        started_at: string | null;
        completed_at: string | null;
        created_at: string;
        updated_at: string;
        task_count: number;
        completed_task_count: number;
      }>;

      return rows.map((row) => ({
        id: row.id,
        projectId: row.project_id,
        title: row.title,
        priority: row.priority,
        status: row.status,
        taskCount: row.task_count,
        completedTaskCount: row.completed_task_count,
        startedAt: row.started_at,
        completedAt: row.completed_at,
        createdAt: row.created_at,
        updatedAt: row.updated_at,
      }));
    } catch (error) {
      console.error('[AipmDbService] getOrders failed:', error);
      throw error;
    }
  }

  /**
   * TASK一覧を取得
   * @param orderId ORDER ID
   * @param projectId プロジェクトID（複合キー対応）
   * @returns TASK一覧
   */
  getTasks(orderId: string, projectId: string): AipmTask[] {
    try {
      const db = this.getConnection();

      // メインのタスク情報を取得
      const taskStmt = db.prepare(`
        SELECT
          t.id,
          t.order_id,
          t.project_id,
          t.title,
          t.description,
          t.status,
          t.assignee,
          t.priority,
          t.recommended_model,
          t.started_at,
          t.completed_at,
          t.created_at,
          t.updated_at
        FROM tasks t
        WHERE t.order_id = ? AND t.project_id = ?
        ORDER BY t.id
      `);

      const rows = taskStmt.all(orderId, projectId) as Array<{
        id: string;
        order_id: string;
        project_id: string;
        title: string;
        description: string | null;
        status: string;
        assignee: string | null;
        priority: string;
        recommended_model: string;
        started_at: string | null;
        completed_at: string | null;
        created_at: string;
        updated_at: string;
      }>;

      // 依存関係を取得
      const depStmt = db.prepare(`
        SELECT task_id, depends_on_task_id
        FROM task_dependencies
        WHERE project_id = ?
      `);

      const deps = depStmt.all(projectId) as Array<{
        task_id: string;
        depends_on_task_id: string;
      }>;

      // 依存関係をマップ化
      const depMap = new Map<string, string[]>();
      for (const dep of deps) {
        const existing = depMap.get(dep.task_id) || [];
        existing.push(dep.depends_on_task_id);
        depMap.set(dep.task_id, existing);
      }

      return rows.map((row) => ({
        id: row.id,
        orderId: row.order_id,
        projectId: row.project_id,
        title: row.title,
        description: row.description,
        status: row.status,
        assignee: row.assignee,
        priority: row.priority,
        recommendedModel: row.recommended_model,
        dependencies: depMap.get(row.id) || [],
        startedAt: row.started_at,
        completedAt: row.completed_at,
        createdAt: row.created_at,
        updatedAt: row.updated_at,
      }));
    } catch (error) {
      console.error('[AipmDbService] getTasks failed:', error);
      throw error;
    }
  }

  /**
   * 単一タスクを取得
   * @param taskId タスクID
   * @param projectId プロジェクトID
   * @returns タスク情報（見つからない場合はnull）
   */
  getTask(taskId: string, projectId: string): AipmTask | null {
    try {
      const db = this.getConnection();

      const stmt = db.prepare(`
        SELECT
          t.id,
          t.order_id,
          t.project_id,
          t.title,
          t.description,
          t.status,
          t.assignee,
          t.priority,
          t.recommended_model,
          t.started_at,
          t.completed_at,
          t.created_at,
          t.updated_at
        FROM tasks t
        WHERE t.id = ? AND t.project_id = ?
      `);

      const row = stmt.get(taskId, projectId) as {
        id: string;
        order_id: string;
        project_id: string;
        title: string;
        description: string | null;
        status: string;
        assignee: string | null;
        priority: string;
        recommended_model: string;
        started_at: string | null;
        completed_at: string | null;
        created_at: string;
        updated_at: string;
      } | undefined;

      if (!row) {
        return null;
      }

      // 依存関係を取得
      const depStmt = db.prepare(`
        SELECT depends_on_task_id
        FROM task_dependencies
        WHERE task_id = ? AND project_id = ?
      `);

      const deps = depStmt.all(taskId, projectId) as Array<{
        depends_on_task_id: string;
      }>;

      return {
        id: row.id,
        orderId: row.order_id,
        projectId: row.project_id,
        title: row.title,
        description: row.description,
        status: row.status,
        assignee: row.assignee,
        priority: row.priority,
        recommendedModel: row.recommended_model,
        dependencies: deps.map(d => d.depends_on_task_id),
        startedAt: row.started_at,
        completedAt: row.completed_at,
        createdAt: row.created_at,
        updatedAt: row.updated_at,
      };
    } catch (error) {
      console.error('[AipmDbService] getTask failed:', error);
      return null;
    }
  }

  /**
   * タスク詳細を取得（getTaskのエイリアス）
   * @param taskId タスクID
   * @param projectId プロジェクトID
   * @returns タスク情報（見つからない場合はnull）
   */
  getTaskDetail(taskId: string, projectId: string): AipmTask | null {
    return this.getTask(taskId, projectId);
  }

  /**
   * レビューキューを取得
   *
   * ORDER_145: Phase 2-3 - review_queueテーブルバイパス実装
   * review_queueテーブルを使用せず、DONEステータスのタスクを直接取得
   *
   * @param projectId プロジェクトID
   * @returns レビューキュー項目一覧（DONEステータスのタスク）
   */
  getReviewQueue(projectId: string): AipmReviewItem[] {
    try {
      const db = this.getConnection();

      // DONEステータスのタスクを直接取得
      const stmt = db.prepare(`
        SELECT
          CAST(ROW_NUMBER() OVER (ORDER BY t.updated_at DESC) AS INTEGER) as id,
          t.id as task_id,
          t.updated_at as submitted_at,
          'PENDING' as status,
          t.assignee as reviewer,
          t.priority,
          NULL as comment,
          NULL as reviewed_at
        FROM tasks t
        WHERE t.project_id = ? AND t.status = 'DONE'
        ORDER BY t.updated_at DESC
      `);

      const rows = stmt.all(projectId) as Array<{
        id: number;
        task_id: string;
        submitted_at: string;
        status: string;
        reviewer: string | null;
        priority: string;
        comment: string | null;
        reviewed_at: string | null;
      }>;

      return rows.map((row) => ({
        id: row.id,
        taskId: row.task_id,
        submittedAt: row.submitted_at,
        status: row.status,
        reviewer: row.reviewer,
        priority: row.priority,
        comment: row.comment,
        reviewedAt: row.reviewed_at,
      }));
    } catch (error) {
      console.error('[AipmDbService] getReviewQueue failed:', error);
      // エラー時は空配列を返す（throwせず、UIを壊さない）
      return [];
    }
  }

  /**
   * バックログ一覧を取得
   * @param projectId プロジェクトID
   * @returns バックログ項目一覧
   */
  getBacklogs(projectId: string): AipmBacklogItem[] {
    try {
      const db = this.getConnection();

      const stmt = db.prepare(`
        SELECT
          id,
          project_id,
          title,
          description,
          priority,
          status,
          related_order_id,
          created_at,
          completed_at,
          updated_at
        FROM backlog_items
        WHERE project_id = ?
        ORDER BY
          CASE priority
            WHEN 'High' THEN 1
            WHEN 'Medium' THEN 2
            WHEN 'Low' THEN 3
          END,
          id
      `);

      const rows = stmt.all(projectId) as Array<{
        id: string;
        project_id: string;
        title: string;
        description: string | null;
        priority: string;
        status: string;
        related_order_id: string | null;
        created_at: string;
        completed_at: string | null;
        updated_at: string;
      }>;

      return rows.map((row) => ({
        id: row.id,
        projectId: row.project_id,
        title: row.title,
        description: row.description,
        priority: row.priority,
        status: row.status,
        relatedOrderId: row.related_order_id,
        createdAt: row.created_at,
        completedAt: row.completed_at,
        updatedAt: row.updated_at,
      }));
    } catch (error) {
      console.error('[AipmDbService] getBacklogs failed:', error);
      throw error;
    }
  }

  /**
   * 単一プロジェクトのバックログを再整理
   * @param projectId プロジェクトID
   * @returns 成功/失敗の結果
   */
  private async reorderBacklogForProject(projectId: string): Promise<{ success: boolean; error?: string }> {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return { success: false, error: 'Framework path not configured' };
    }

    const backendPath = configService.getBackendPath();
    if (!backendPath) {
      return { success: false, error: 'Backend path not configured' };
    }
    const reorderScriptPath = path.join(backendPath, 'backlog', 'reorder.py');

    if (!fs.existsSync(reorderScriptPath)) {
      return { success: false, error: `reorder.py not found: ${reorderScriptPath}` };
    }

    try {
      // Python実行: python reorder.py PROJECT_ID --json
      const { stdout } = await execFileAsync('python', [reorderScriptPath, projectId, '--json'], {
        cwd: path.dirname(reorderScriptPath),
        timeout: 30000, // 30秒タイムアウト
      });

      // JSON出力をパース
      const result = JSON.parse(stdout);

      if (!result.success) {
        return { success: false, error: result.error || 'Unknown error' };
      }

      console.log(`[AipmDbService] Backlog reordered for ${projectId}: ${result.updated_count}件更新`);
      return { success: true };
    } catch (error: unknown) {
      // エラーメッセージを構築
      const err = error as { stderr?: string; message?: string };
      const errorMsg = err.stderr || err.message || String(error);
      return { success: false, error: errorMsg };
    }
  }

  /**
   * 全アクティブプロジェクトのバックログを自動再整理
   *
   * アプリ起動時に一度だけ実行される。
   * 各プロジェクトに対してreorder.pyを並列実行し、失敗は警告ログのみ出力。
   */
  async autoReorderAllBacklogs(): Promise<void> {
    // 初回のみ実行
    if (this.autoReorderInitialized) {
      return;
    }

    this.autoReorderInitialized = true;

    try {
      const projectIds = this.getActiveProjectIds();

      if (projectIds.length === 0) {
        console.log('[AipmDbService] No active projects found for backlog auto-reorder');
        return;
      }

      console.log(`[AipmDbService] Starting backlog auto-reorder for ${projectIds.length} projects...`);

      // 全プロジェクトに対して並列実行
      const results = await Promise.allSettled(
        projectIds.map((projectId) => this.reorderBacklogForProject(projectId))
      );

      // 結果を集計
      let successCount = 0;
      let failureCount = 0;

      results.forEach((result, index) => {
        const projectId = projectIds[index];

        if (result.status === 'fulfilled' && result.value.success) {
          successCount++;
        } else {
          failureCount++;
          const errorMsg = result.status === 'fulfilled' ? result.value.error : result.reason;
          console.warn(`[AipmDbService] Backlog reorder failed for ${projectId}:`, errorMsg);
        }
      });

      console.log(
        `[AipmDbService] Backlog auto-reorder completed: ${successCount} succeeded, ${failureCount} failed`
      );
    } catch (error) {
      console.error('[AipmDbService] Unexpected error in autoReorderAllBacklogs:', error);
    }
  }

  /**
   * タスクのレビュー履歴を取得
   *
   * ORDER_138: TASK_1158 - レビュー履歴取得API
   * ORDER_145: Phase 2-3 - review_queueテーブル削除対応
   * change_history、escalations、tasksから関連情報を集約して返す
   * (review_queueテーブルは削除済みのためchange_historyから復元)
   *
   * @param projectId プロジェクトID
   * @param taskId タスクID
   * @returns レビュー履歴情報
   */
  getTaskReviewHistory(projectId: string, taskId: string): TaskReviewHistory {
    try {
      const db = this.getConnection();

      // ORDER_145: review_queueテーブルは削除済み
      // change_historyからレビュー関連の履歴を取得
      const reviewHistoryStmt = db.prepare(`
        SELECT
          ROW_NUMBER() OVER (ORDER BY changed_at DESC) as id,
          entity_id as task_id,
          new_value as status,
          changed_by as reviewer,
          change_reason as comment,
          changed_at as submitted_at,
          changed_at as reviewed_at
        FROM change_history
        WHERE entity_type = 'task'
          AND entity_id = ?
          AND project_id = ?
          AND field_name = 'status'
          AND (old_value = 'DONE' OR new_value = 'DONE' OR new_value IN ('COMPLETED', 'REWORK'))
        ORDER BY changed_at DESC
      `);

      const reviewRows = reviewHistoryStmt.all(taskId, projectId) as Array<{
        id: number;
        task_id: string;
        status: string;
        reviewer: string | null;
        comment: string | null;
        submitted_at: string | null;
        reviewed_at: string | null;
      }>;

      const reviews = reviewRows.map((row) => ({
        id: row.id,
        taskId: row.task_id,
        status: row.status,
        reviewer: row.reviewer,
        comment: row.comment,
        submittedAt: row.submitted_at,
        reviewedAt: row.reviewed_at,
      }));

      // change_history からステータス変更履歴を取得
      const historyStmt = db.prepare(`
        SELECT
          field_name,
          old_value,
          new_value,
          changed_by,
          change_reason,
          changed_at
        FROM change_history
        WHERE entity_type = 'task' AND entity_id = ? AND project_id = ? AND field_name = 'status'
        ORDER BY changed_at DESC
      `);

      const historyRows = historyStmt.all(taskId, projectId) as Array<{
        field_name: string;
        old_value: string | null;
        new_value: string | null;
        changed_by: string | null;
        change_reason: string | null;
        changed_at: string;
      }>;

      const statusHistory = historyRows.map((row) => ({
        fieldName: row.field_name,
        oldValue: row.old_value,
        newValue: row.new_value,
        changedBy: row.changed_by,
        changeReason: row.change_reason,
        changedAt: row.changed_at,
      }));

      // escalations からエスカレーション情報を取得
      const escalationStmt = db.prepare(`
        SELECT
          id,
          description,
          resolved_at,
          resolution,
          created_at
        FROM escalations
        WHERE task_id = ? AND project_id = ?
        ORDER BY created_at DESC
      `);

      const escalationRows = escalationStmt.all(taskId, projectId) as Array<{
        id: string;
        description: string | null;
        resolved_at: string | null;
        resolution: string | null;
        created_at: string;
      }>;

      const escalations = escalationRows.map((row) => ({
        id: row.id,
        reason: row.description,
        resolvedAt: row.resolved_at,
        resolution: row.resolution,
        createdAt: row.created_at,
      }));

      // tasks から reject_count を取得
      const taskStmt = db.prepare(`
        SELECT reject_count
        FROM tasks
        WHERE id = ? AND project_id = ?
      `);

      const taskRow = taskStmt.get(taskId, projectId) as {
        reject_count: number;
      } | undefined;

      const rejectCount = taskRow?.reject_count ?? 0;

      // max_rework はフレームワークのデフォルト値（3）
      const maxRework = 3;

      return {
        reviews,
        statusHistory,
        escalations,
        rejectCount,
        maxRework,
      };
    } catch (error) {
      console.error('[AipmDbService] getTaskReviewHistory failed:', error);
      return {
        reviews: [],
        statusHistory: [],
        escalations: [],
        rejectCount: 0,
        maxRework: 3,
      };
    }
  }

  /**
   * バックログ項目を追加
   * @param projectId プロジェクトID
   * @param title タイトル
   * @param description 説明
   * @param priority 優先度（High/Medium/Low）
   * @param category カテゴリ（省略可）
   * @returns 作成されたバックログ項目
   */
  async addBacklog(
    projectId: string,
    title: string,
    description: string | null,
    priority: string,
    category?: string
  ): Promise<{ success: boolean; backlogId?: string; error?: string }> {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return { success: false, error: 'Framework path not configured' };
    }

    const backendPath = configService.getBackendPath();
    if (!backendPath) {
      return { success: false, error: 'Backend path not configured' };
    }
    const addScriptPath = path.join(backendPath, 'backlog', 'add.py');

    if (!fs.existsSync(addScriptPath)) {
      return { success: false, error: `add.py not found: ${addScriptPath}` };
    }

    try {
      const args = [
        addScriptPath,
        projectId,
        '--title',
        title,
        '--priority',
        priority,
        '--json',
      ];

      if (description) {
        args.push('--description', description);
      }

      if (category) {
        args.push('--category', category);
      }

      const { stdout } = await execFileAsync('python', args, {
        cwd: path.dirname(addScriptPath),
        timeout: 30000,
      });

      const result = JSON.parse(stdout);

      if (!result.success) {
        return { success: false, error: result.error || 'Unknown error' };
      }

      console.log(`[AipmDbService] Backlog added: ${result.backlog_id}`);
      return { success: true, backlogId: result.backlog_id };
    } catch (error: unknown) {
      const err = error as { stderr?: string; message?: string };
      const errorMsg = err.stderr || err.message || String(error);
      return { success: false, error: errorMsg };
    }
  }

  /**
   * バックログ項目を更新
   * @param projectId プロジェクトID
   * @param backlogId バックログID
   * @param updates 更新内容
   * @returns 更新結果
   */
  async updateBacklog(
    projectId: string,
    backlogId: string,
    updates: {
      title?: string;
      description?: string;
      priority?: string;
      status?: string;
      sortOrder?: number;
    }
  ): Promise<{ success: boolean; error?: string }> {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return { success: false, error: 'Framework path not configured' };
    }

    const backendPath = configService.getBackendPath();
    if (!backendPath) {
      return { success: false, error: 'Backend path not configured' };
    }
    const updateScriptPath = path.join(backendPath, 'backlog', 'update.py');

    if (!fs.existsSync(updateScriptPath)) {
      return { success: false, error: `update.py not found: ${updateScriptPath}` };
    }

    try {
      const args = [updateScriptPath, projectId, backlogId, '--json'];

      if (updates.title) {
        args.push('--title', updates.title);
      }

      if (updates.description !== undefined) {
        args.push('--description', updates.description);
      }

      if (updates.priority) {
        args.push('--priority', updates.priority);
      }

      if (updates.status) {
        args.push('--status', updates.status);
      }

      if (updates.sortOrder !== undefined) {
        args.push('--sort-order', updates.sortOrder.toString());
      }

      const { stdout } = await execFileAsync('python', args, {
        cwd: path.dirname(updateScriptPath),
        timeout: 30000,
      });

      const result = JSON.parse(stdout);

      if (!result.success) {
        return { success: false, error: result.error || 'Unknown error' };
      }

      console.log(`[AipmDbService] Backlog updated: ${backlogId}`);
      return { success: true };
    } catch (error: unknown) {
      const err = error as { stderr?: string; message?: string };
      const errorMsg = err.stderr || err.message || String(error);
      return { success: false, error: errorMsg };
    }
  }

  /**
   * バックログ項目を削除（CANCELEDステータスに変更）
   * @param projectId プロジェクトID
   * @param backlogId バックログID
   * @returns 削除結果
   */
  async deleteBacklog(
    projectId: string,
    backlogId: string
  ): Promise<{ success: boolean; error?: string }> {
    // CANCELEDステータスに更新することで論理削除
    return this.updateBacklog(projectId, backlogId, { status: 'CANCELED' });
  }

  /**
   * バックログ優先度を自動整理（prioritize.pyを実行）
   * @param projectId プロジェクトID
   * @param options オプション（dry_run, days, verbose）
   * @returns 優先度整理結果
   */
  async prioritizeBacklogs(
    projectId: string,
    options: {
      dryRun?: boolean;
      days?: number;
      verbose?: boolean;
    } = {}
  ): Promise<{
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
  }> {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return { success: false, error: 'Framework path not configured' };
    }

    const backendPath = configService.getBackendPath();
    if (!backendPath) {
      return { success: false, error: 'Backend path not configured' };
    }
    const prioritizeScriptPath = path.join(backendPath, 'backlog', 'prioritize.py');

    if (!fs.existsSync(prioritizeScriptPath)) {
      return { success: false, error: `prioritize.py not found: ${prioritizeScriptPath}` };
    }

    try {
      const args = [prioritizeScriptPath, projectId, '--json'];

      if (options.dryRun) {
        args.push('--dry-run');
      }

      if (options.days) {
        args.push('--days', options.days.toString());
      }

      if (options.verbose) {
        args.push('--verbose');
      }

      const { stdout } = await execFileAsync('python', args, {
        cwd: path.dirname(prioritizeScriptPath),
        timeout: 60000, // 60秒タイムアウト
      });

      const result = JSON.parse(stdout);

      if (!result.success) {
        return { success: false, error: result.error || 'Unknown error' };
      }

      // フィールド名をキャメルケースに変換
      const changes = result.changes?.map((change: any) => ({
        backlogId: change.backlog_id,
        title: change.title,
        oldPriority: change.old_priority,
        newPriority: change.new_priority,
        oldSortOrder: change.old_sort_order,
        newSortOrder: change.new_sort_order,
        reason: change.reason,
      }));

      console.log(`[AipmDbService] Backlog prioritized for ${projectId}: ${result.updated_count}件更新`);
      return {
        success: true,
        updatedCount: result.updated_count,
        totalCount: result.total_count,
        changes,
        message: result.message,
        analysis: result.analysis,
      };
    } catch (error: unknown) {
      const err = error as { stderr?: string; message?: string };
      const errorMsg = err.stderr || err.message || String(error);
      return { success: false, error: errorMsg };
    }
  }

  /**
   * DB接続を閉じる
   */
  close(): void {
    if (this.db) {
      try {
        this.db.close();
      } catch (error) {
        console.error('[AipmDbService] Failed to close DB connection:', error);
      }
      this.db = null;
      this.dbPath = null;
    }
  }

  /**
   * タスクログファイルの最新行を取得
   *
   * ORDER_128: TASK_1126 - バックエンドログ読み込みAPI
   * LOGS/{task_id}/配下の最新ログファイルから末尾1-2行を取得
   *
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @param taskId タスクID
   * @param lines 取得する行数（デフォルト: 2）
   * @returns ログの末尾行（見つからない場合はnull）
   */
  getTaskLogTail(
    projectId: string,
    orderId: string,
    taskId: string,
    lines = 2
  ): { logLines: string[]; logFilePath: string | null } | null {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return null;
    }

    const logsDir = path.join(
      frameworkPath,
      'PROJECTS',
      projectId,
      'RESULT',
      orderId,
      'LOGS'
    );

    if (!fs.existsSync(logsDir)) {
      return null;
    }

    try {
      // LOGS配下の worker_{taskId}_*.log ファイルを探す
      const files = fs.readdirSync(logsDir);
      const logFiles = files.filter(
        (file) => file.startsWith(`worker_${taskId}_`) && file.endsWith('.log')
      );

      if (logFiles.length === 0) {
        return null;
      }

      // 最新のログファイルを選択（複数ある場合はタイムスタンプでソート）
      const latestLogFile = logFiles.sort().reverse()[0];
      const logFilePath = path.join(logsDir, latestLogFile);

      // ファイル内容を読み込み、末尾の指定行数を取得
      const content = fs.readFileSync(logFilePath, 'utf-8');
      const allLines = content.split('\n').filter((line) => line.trim() !== '');

      if (allLines.length === 0) {
        return { logLines: [], logFilePath };
      }

      const startIndex = Math.max(0, allLines.length - lines);
      const tailLines = allLines.slice(startIndex);

      return { logLines: tailLines, logFilePath };
    } catch (error) {
      console.error(
        `[AipmDbService] Failed to read log tail for ${taskId}:`,
        error
      );
      return null;
    }
  }

  /**
   * 実行中タスクの詳細情報を取得
   *
   * ORDER_128: TASK_1127 - タスク進捗情報取得API
   * ORDER_141: TASK_1170 - stepIndex/totalSteps/progressPercentを計算
   *
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @returns 実行中タスクの詳細情報一覧
   */
  getRunningTasksInfo(
    projectId: string,
    orderId: string
  ): Array<{
    id: string;
    title: string;
    status: string;
    currentStep: string | null;
    stepIndex: number;
    totalSteps: number;
    progressPercent: number;
  }> {
    try {
      const db = this.getConnection();

      const stmt = db.prepare(`
        SELECT
          id,
          title,
          status,
          updated_at
        FROM tasks
        WHERE project_id = ? AND order_id = ? AND status IN ('IN_PROGRESS', 'REWORK')
        ORDER BY started_at DESC
      `);

      const rows = stmt.all(projectId, orderId) as Array<{
        id: string;
        title: string;
        status: string;
        updated_at: string;
      }>;

      return rows.map((row) => {
        // change_historyから実行ステップを推定
        const stepInfo = this.inferExecutionStep(projectId, row.id);

        // ログから現在のステップ表示名を取得（フォールバック）
        let currentStep: string | null = stepInfo.currentStepDisplay;

        if (!currentStep) {
          const logTailResult = this.getTaskLogTail(projectId, orderId, row.id, 1);
          if (logTailResult && logTailResult.logLines.length > 0) {
            // ログ行から [step_name] を抽出
            const lastLine = logTailResult.logLines[logTailResult.logLines.length - 1];
            const match = lastLine.match(/\[([^\]]+)\]/);
            if (match) {
              currentStep = match[1];
            }
          }
        }

        return {
          id: row.id,
          title: row.title,
          status: row.status,
          currentStep,
          stepIndex: stepInfo.stepIndex,
          totalSteps: stepInfo.totalSteps,
          progressPercent: stepInfo.progressPercent,
        };
      });
    } catch (error) {
      console.error(
        `[AipmDbService] getRunningTasksInfo failed:`,
        error
      );
      return [];
    }
  }

  /**
   * change_historyから実行ステップを推定
   *
   * ORDER_141: TASK_1170 - ステップ推定ロジック
   *
   * @param projectId プロジェクトID
   * @param taskId タスクID
   * @returns ステップ情報
   */
  private inferExecutionStep(
    projectId: string,
    taskId: string
  ): {
    currentStep: string;
    currentStepDisplay: string;
    stepIndex: number;
    totalSteps: number;
    progressPercent: number;
  } {
    const EXECUTION_STEPS = [
      'get_task_info',      // タスク情報取得
      'assign_worker',      // Worker割当
      'file_lock',          // ファイルロック取得
      'execute_task',       // AI実行
      'create_report',      // REPORT作成
      'add_review_queue',   // レビューキュー追加
      'update_status_done', // ステータス更新（DONE）
      'auto_review',        // 自動レビュー
    ];

    const STEP_DISPLAY_NAMES: Record<string, string> = {
      get_task_info: 'タスク情報取得',
      assign_worker: 'Worker割当',
      file_lock: 'ファイルロック',
      execute_task: 'AI実行',
      create_report: 'レポート作成',
      add_review_queue: 'レビュー待ち',
      update_status_done: '完了処理',
      auto_review: '自動レビュー',
    };

    try {
      const db = this.getConnection();

      // タスク情報を取得
      const taskStmt = db.prepare(`
        SELECT id, status, assignee, updated_at
        FROM tasks
        WHERE id = ? AND project_id = ?
      `);

      const task = taskStmt.get(taskId, projectId) as {
        id: string;
        status: string;
        assignee: string | null;
        updated_at: string;
      } | undefined;

      if (!task) {
        return {
          currentStep: 'get_task_info',
          currentStepDisplay: 'タスク情報取得',
          stepIndex: 0,
          totalSteps: EXECUTION_STEPS.length,
          progressPercent: 0,
        };
      }

      // REWORK: レビュー差し戻し後の再実行待ち
      if (task.status === 'REWORK') {
        return {
          currentStep: 'execute_task',
          currentStepDisplay: 'リワーク待ち',
          stepIndex: EXECUTION_STEPS.indexOf('execute_task'),
          totalSteps: EXECUTION_STEPS.length,
          progressPercent: Math.round(((EXECUTION_STEPS.indexOf('execute_task') + 1) / EXECUTION_STEPS.length) * 100),
        };
      }

      // change_historyから最新の履歴を取得
      const historyStmt = db.prepare(`
        SELECT field_name, old_value, new_value, changed_at
        FROM change_history
        WHERE entity_type = 'task' AND entity_id = ? AND project_id = ?
        ORDER BY changed_at DESC
        LIMIT 20
      `);

      const history = historyStmt.all(taskId, projectId) as Array<{
        field_name: string;
        old_value: string | null;
        new_value: string | null;
        changed_at: string;
      }>;

      // ステップを推定
      let currentStep = 'get_task_info';

      // ステータスがIN_PROGRESSでない場合は早期リターン
      if (task.status !== 'IN_PROGRESS') {
        // DONEステータスの場合はレビュー待ち
        if (task.status === 'DONE') {
          return {
            currentStep: 'add_review_queue',
            currentStepDisplay: 'レビュー待ち',
            stepIndex: EXECUTION_STEPS.indexOf('add_review_queue'),
            totalSteps: EXECUTION_STEPS.length,
            progressPercent: Math.round(((EXECUTION_STEPS.indexOf('add_review_queue') + 1) / EXECUTION_STEPS.length) * 100),
          };
        }

        return {
          currentStep: '',
          currentStepDisplay: '実行中でない',
          stepIndex: 0,
          totalSteps: EXECUTION_STEPS.length,
          progressPercent: task.status === 'QUEUED' || task.status === 'BLOCKED' ? 0 : 100,
        };
      }

      // IN_PROGRESSの場合のステップ推定
      for (const record of history) {
        const fieldName = record.field_name;
        const newValue = record.new_value || '';

        // Worker割当があればfile_lockステップ
        if (fieldName === 'assignee' && newValue) {
          currentStep = 'file_lock';
          break;
        }
      }

      // file_locksテーブルを確認（ロック取得済み＝execute中）
      const lockStmt = db.prepare(`
        SELECT COUNT(*) as count
        FROM file_locks
        WHERE task_id = ? AND project_id = ?
      `);

      const lockResult = lockStmt.get(taskId, projectId) as { count: number } | undefined;
      if (lockResult && lockResult.count > 0) {
        currentStep = 'execute_task';
      }

      const stepIndex = EXECUTION_STEPS.indexOf(currentStep);
      const progressPercent = Math.round(((stepIndex + 1) / EXECUTION_STEPS.length) * 100);

      return {
        currentStep,
        currentStepDisplay: STEP_DISPLAY_NAMES[currentStep] || currentStep,
        stepIndex: stepIndex >= 0 ? stepIndex : 0,
        totalSteps: EXECUTION_STEPS.length,
        progressPercent,
      };
    } catch (error) {
      console.error(`[AipmDbService] inferExecutionStep failed:`, error);
      return {
        currentStep: 'get_task_info',
        currentStepDisplay: 'タスク情報取得',
        stepIndex: 0,
        totalSteps: EXECUTION_STEPS.length,
        progressPercent: 0,
      };
    }
  }

  /**
   * 並列実行デーモンのハートビート情報を取得
   *
   * ORDER_128: TASK_1127 - タスク進捗情報取得API
   * daemon_heartbeat.jsonから並列実行の状態を読み込む
   *
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @returns ハートビート情報（デーモンが動いていない場合はnull）
   */
  getDaemonHeartbeat(
    projectId: string,
    orderId: string
  ): {
    pid: number;
    orderId: string;
    projectId: string;
    timestamp: string;
    activeWorkers: number;
    activeWorkerPids: number[];
    status: string;
    adaptivePollInterval: number | null;
    resourceTrend: string | null;
    ageSeconds: number;
    isAlive: boolean;
  } | null {
    const configService = getConfigService();
    const frameworkPath = configService.getActiveFrameworkPath();

    if (!frameworkPath) {
      return null;
    }

    const heartbeatPath = path.join(
      frameworkPath,
      'PROJECTS',
      projectId,
      'RESULT',
      orderId,
      'LOGS',
      'daemon_heartbeat.json'
    );

    if (!fs.existsSync(heartbeatPath)) {
      return null;
    }

    try {
      const content = fs.readFileSync(heartbeatPath, 'utf-8');
      const data = JSON.parse(content);

      // ファイルの更新時刻からage_secondsを計算
      const stats = fs.statSync(heartbeatPath);
      const ageSeconds = (Date.now() - stats.mtimeMs) / 1000;

      return {
        pid: data.pid,
        orderId: data.order_id,
        projectId: data.project_id,
        timestamp: data.timestamp,
        activeWorkers: data.active_workers,
        activeWorkerPids: data.active_worker_pids || [],
        status: data.status,
        adaptivePollInterval: data.adaptive_poll_interval || null,
        resourceTrend: data.resource_trend || null,
        ageSeconds: Math.round(ageSeconds * 10) / 10,
        isAlive: ageSeconds < 60,
      };
    } catch (error) {
      console.error(
        `[AipmDbService] Failed to read daemon heartbeat for ${orderId}:`,
        error
      );
      return null;
    }
  }

  /**
   * タスク進捗情報の統合データを取得
   *
   * ORDER_128: TASK_1127 - タスク進捗情報取得API
   * ORDER_141: TASK_1171 - TaskProgressInfo型に整合（shared/types.tsから型インポート）
   * 完了タスク数/総タスク数、実行中タスク詳細、並列実行状況を統合
   *
   * @param projectId プロジェクトID
   * @param orderId ORDER ID
   * @returns タスク進捗統合情報（shared/types.tsのTaskProgressInfo型に準拠）
   */
  getTaskProgressInfo(
    projectId: string,
    orderId: string
  ): TaskProgressInfo {
    try {
      const db = this.getConnection();

      // 総タスク数と完了タスク数を取得
      const countStmt = db.prepare(`
        SELECT
          COUNT(*) as total,
          SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed
        FROM tasks
        WHERE project_id = ? AND order_id = ?
      `);

      const countRow = countStmt.get(projectId, orderId) as {
        total: number;
        completed: number;
      };

      const totalCount = countRow.total || 0;
      const completedCount = countRow.completed || 0;

      // 実行中タスクの詳細を取得
      const runningTasks = this.getRunningTasksInfo(projectId, orderId);

      // ORDER進捗率を計算
      const overallProgress = totalCount > 0
        ? Math.round((completedCount / totalCount) * 100)
        : 0;

      return {
        runningTasks,
        completedCount,
        totalCount,
        overallProgress,
      };
    } catch (error) {
      console.error(
        `[AipmDbService] getTaskProgressInfo failed:`,
        error
      );
      return {
        runningTasks: [],
        completedCount: 0,
        totalCount: 0,
        overallProgress: 0,
      };
    }
  }
}

// シングルトンインスタンス
let aipmDbServiceInstance: AipmDbService | null = null;

/**
 * AipmDbServiceのシングルトンインスタンスを取得
 */
export function getAipmDbService(): AipmDbService {
  if (!aipmDbServiceInstance) {
    aipmDbServiceInstance = new AipmDbService();
  }
  return aipmDbServiceInstance;
}

/**
 * AipmDbServiceインスタンスをリセット（テスト用）
 */
export function resetAipmDbService(): void {
  if (aipmDbServiceInstance) {
    aipmDbServiceInstance.close();
  }
  aipmDbServiceInstance = null;
}

/**
 * ORDER成果物ファイル情報
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
 * RESULT配下のMarkdownファイルを読み込む
 * @param projectId プロジェクトID
 * @param orderId ORDER ID
 * @param filename ファイル名（例: "01_GOAL.md"）
 * @returns ファイル情報（存在しない場合はexists=false）
 */
export function getOrderResultFile(
  projectId: string,
  orderId: string,
  filename: string,
): OrderResultFile {
  const configService = getConfigService();
  const frameworkPath = configService.getActiveFrameworkPath();

  if (!frameworkPath) {
    return {
      filename,
      path: '',
      content: '',
      exists: false,
    };
  }

  const filePath = path.join(
    frameworkPath,
    'PROJECTS',
    projectId,
    'RESULT',
    orderId,
    filename,
  );

  if (!fs.existsSync(filePath)) {
    return {
      filename,
      path: filePath,
      content: '',
      exists: false,
    };
  }

  try {
    const content = fs.readFileSync(filePath, 'utf-8');
    return {
      filename,
      path: filePath,
      content,
      exists: true,
    };
  } catch (error) {
    console.error(`[AipmDbService] Failed to read file ${filePath}:`, error);
    return {
      filename,
      path: filePath,
      content: '',
      exists: false,
    };
  }
}

/**
 * 05_REPORT/配下のレポートファイル一覧を取得
 * @param projectId プロジェクトID
 * @param orderId ORDER ID
 * @returns レポートファイル名一覧
 */
export function getOrderReportList(
  projectId: string,
  orderId: string,
): string[] {
  const configService = getConfigService();
  const frameworkPath = configService.getActiveFrameworkPath();

  if (!frameworkPath) {
    return [];
  }

  const reportDir = path.join(
    frameworkPath,
    'PROJECTS',
    projectId,
    'RESULT',
    orderId,
    '05_REPORT',
  );

  if (!fs.existsSync(reportDir)) {
    return [];
  }

  try {
    const files = fs.readdirSync(reportDir);
    // .mdファイルのみを返す
    return files.filter(file => file.endsWith('.md')).sort();
  } catch (error) {
    console.error(`[AipmDbService] Failed to read report directory ${reportDir}:`, error);
    return [];
  }
}

/**
 * 05_REPORT/配下の特定レポートファイルを読み込む
 * @param projectId プロジェクトID
 * @param orderId ORDER ID
 * @param reportFilename レポートファイル名（例: "REPORT_1234.md"）
 * @returns ファイル情報（存在しない場合はexists=false）
 */
export function getOrderReport(
  projectId: string,
  orderId: string,
  reportFilename: string,
): OrderResultFile {
  const configService = getConfigService();
  const frameworkPath = configService.getActiveFrameworkPath();

  if (!frameworkPath) {
    return {
      filename: reportFilename,
      path: '',
      content: '',
      exists: false,
    };
  }

  const filePath = path.join(
    frameworkPath,
    'PROJECTS',
    projectId,
    'RESULT',
    orderId,
    '05_REPORT',
    reportFilename,
  );

  if (!fs.existsSync(filePath)) {
    return {
      filename: reportFilename,
      path: filePath,
      content: '',
      exists: false,
    };
  }

  try {
    const content = fs.readFileSync(filePath, 'utf-8');
    return {
      filename: reportFilename,
      path: filePath,
      content,
      exists: true,
    };
  } catch (error) {
    console.error(`[AipmDbService] Failed to read report file ${filePath}:`, error);
    return {
      filename: reportFilename,
      path: filePath,
      content: '',
      exists: false,
    };
  }
}

/**
 * レポートから抽出した変更ファイル情報
 */
export interface ReportChangedFile {
  /** ファイルパス */
  path: string;
}

/**
 * レポート差分サマリ情報
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
 * タスクレビュー結果情報
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
 * ORDER全体のリリース準備状況
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
 * REPORTファイルから変更ファイル一覧を抽出
 * @param reportContent REPORTファイルの内容
 * @returns 変更ファイル一覧
 */
function extractChangedFilesFromReport(reportContent: string): ReportChangedFile[] {
  const changedFiles: ReportChangedFile[] = [];

  // "artifacts" フィールドを探す（JSON形式）
  const jsonMatch = reportContent.match(/```json\s*\n([\s\S]*?)\n```/);
  if (jsonMatch) {
    try {
      const jsonData = JSON.parse(jsonMatch[1]);
      if (jsonData.artifacts && Array.isArray(jsonData.artifacts)) {
        for (const artifact of jsonData.artifacts) {
          if (typeof artifact === 'string') {
            changedFiles.push({ path: artifact });
          }
        }
      }
    } catch (error) {
      // JSON parse error は無視
    }
  }

  // "対象ファイル" セクションを探す（Markdown形式）
  const targetFilesMatch = reportContent.match(/##\s*対象ファイル\s*\n([\s\S]*?)(?=\n##|$)/);
  if (targetFilesMatch) {
    const lines = targetFilesMatch[1].split('\n');
    for (const line of lines) {
      // "- `path/to/file.ts`" 形式を抽出
      const fileMatch = line.match(/^-\s*`([^`]+)`/);
      if (fileMatch) {
        const filePath = fileMatch[1].trim();
        if (!changedFiles.some(f => f.path === filePath)) {
          changedFiles.push({ path: filePath });
        }
      }
    }
  }

  return changedFiles;
}

/**
 * REPORTファイルから影響範囲を抽出
 * @param reportContent REPORTファイルの内容
 * @returns 影響範囲テキスト
 */
function extractImpactScopeFromReport(reportContent: string): string | null {
  // "影響範囲" または "Impact" セクションを探す
  const impactMatch = reportContent.match(/##\s*(?:影響範囲|Impact)\s*\n([\s\S]*?)(?=\n##|$)/);
  if (impactMatch) {
    return impactMatch[1].trim();
  }
  return null;
}

/**
 * REPORTファイルからサマリを抽出
 * @param reportContent REPORTファイルの内容
 * @returns サマリテキスト
 */
function extractSummaryFromReport(reportContent: string): string | null {
  // "実施内容" または "Summary" セクションを探す
  const summaryMatch = reportContent.match(/##\s*(?:実施内容|Summary|作業サマリ)\s*\n([\s\S]*?)(?=\n##|$)/);
  if (summaryMatch) {
    return summaryMatch[1].trim();
  }

  // JSON形式のsummaryフィールドを探す
  const jsonMatch = reportContent.match(/```json\s*\n([\s\S]*?)\n```/);
  if (jsonMatch) {
    try {
      const jsonData = JSON.parse(jsonMatch[1]);
      if (jsonData.summary && typeof jsonData.summary === 'string') {
        return jsonData.summary;
      }
    } catch (error) {
      // JSON parse error は無視
    }
  }

  return null;
}

/**
 * PLANNING_FAILED状態のORDERを再実行
 *
 * ORDER_155: TASK_1230 - 再実行APIのバックエンド実装
 *
 * retry_order.pyスクリプトを呼び出し、ORDERステータスをPLANNINGに戻してprocess_order.pyを再実行する
 *
 * @param projectId プロジェクトID
 * @param orderId ORDER ID
 * @param timeout タイムアウト秒数（デフォルト: 600）
 * @param model AIモデル（haiku/sonnet/opus、デフォルト: sonnet）
 * @returns 実行結果
 */
export async function retryOrder(
  projectId: string,
  orderId: string,
  timeout = 600,
  model = 'sonnet',
): Promise<{
  success: boolean;
  message: string;
  stdout?: string;
  stderr?: string;
  error?: string;
}> {
  try {
    const frameworkPath = getConfigService().getAipmFrameworkPath();
    if (!frameworkPath) {
      return {
        success: false,
        message: 'Framework path not configured',
        error: 'Framework path not configured',
      };
    }

    const { spawn } = await import('child_process');
    const path = await import('path');

    const scriptPath = path.join(
      frameworkPath,
      'scripts',
      'aipm-db',
      'order',
      'retry_order.py'
    );

    return new Promise((resolve) => {
      let stdout = '';
      let stderr = '';

      const args = [
        scriptPath,
        projectId,
        orderId,
        '--timeout',
        timeout.toString(),
        '--model',
        model,
        '--json', // JSON形式で出力を取得
      ];

      console.log(`[AipmDbService] Executing retry_order.py: python ${args.join(' ')}`);

      const childProcess = spawn('python', args, {
        cwd: path.join(frameworkPath, 'scripts', 'aipm-db'),
        env: { ...process.env },
      });

      if (childProcess.stdout) {
        childProcess.stdout.setEncoding('utf-8');
        childProcess.stdout.on('data', (data: string) => {
          stdout += data;
          console.log(`[retry_order.py stdout] ${data.trim()}`);
        });
      }

      if (childProcess.stderr) {
        childProcess.stderr.setEncoding('utf-8');
        childProcess.stderr.on('data', (data: string) => {
          stderr += data;
          console.warn(`[retry_order.py stderr] ${data.trim()}`);
        });
      }

      childProcess.on('close', (exitCode) => {
        if (exitCode === 0) {
          // 成功時はJSON出力をパース
          try {
            const result = JSON.parse(stdout);
            resolve({
              success: true,
              message: `ORDER ${orderId} was successfully retried`,
              stdout,
            });
          } catch (e) {
            // JSONパースに失敗してもexitCode 0なら成功とみなす
            resolve({
              success: true,
              message: `ORDER ${orderId} was successfully retried`,
              stdout,
            });
          }
        } else {
          resolve({
            success: false,
            message: `ORDER retry failed with exit code ${exitCode}`,
            stdout,
            stderr,
            error: `Script exited with code ${exitCode}`,
          });
        }
      });

      childProcess.on('error', (error) => {
        console.error(`[AipmDbService] retry_order.py error:`, error);
        resolve({
          success: false,
          message: `Failed to execute retry_order.py: ${error.message}`,
          error: error.message,
        });
      });
    });
  } catch (error) {
    console.error('[AipmDbService] retryOrder failed:', error);
    return {
      success: false,
      message: `Failed to retry ORDER: ${error}`,
      error: String(error),
    };
  }
}

/**
 * ORDERのリリース準備状況を取得
 * @param projectId プロジェクトID
 * @param orderId ORDER ID
 * @returns リリース準備状況
 */
export function getOrderReleaseReadiness(
  projectId: string,
  orderId: string,
): OrderReleaseReadiness {
  const aipmDbService = getAipmDbService();

  // タスク一覧を取得
  const tasks = aipmDbService.getTasks(orderId, projectId);
  const totalTasks = tasks.length;
  const completedTasks = tasks.filter(t => t.status === 'COMPLETED').length;
  const allTasksCompleted = totalTasks > 0 && completedTasks === totalTasks;

  // レビュー結果を取得
  // ORDER_145: review_queueテーブル削除対応 - タスクステータスから判定
  const reviewResults: TaskReviewResult[] = [];
  for (const task of tasks) {
    let reviewStatus = 'PENDING';
    let reviewComment: string | null = null;
    let reviewedAt: string | null = null;
    let reviewer: string | null = null;

    if (task.status === 'COMPLETED') {
      reviewStatus = 'APPROVED';
      reviewedAt = task.completedAt;
      reviewer = task.assignee;
    } else if (task.status === 'DONE') {
      reviewStatus = 'PENDING';
      // DONEステータスの場合はレビュー待ち
    } else if (task.status === 'REWORK') {
      reviewStatus = 'REJECTED';
      // change_historyから差し戻し理由を取得可能（オプション）
    }

    reviewResults.push({
      taskId: task.id,
      reviewStatus,
      reviewComment,
      reviewedAt,
      reviewer,
    });
  }

  const allReviewsApproved = reviewResults.length > 0 &&
    reviewResults.every(r => r.reviewStatus === 'APPROVED');

  // レポート差分サマリを取得
  const reportSummaries: ReportDiffSummary[] = [];
  const reportFiles = getOrderReportList(projectId, orderId);

  for (const reportFilename of reportFiles) {
    const report = getOrderReport(projectId, orderId, reportFilename);
    if (!report.exists) {
      continue;
    }

    // REPORTファイル名からタスクIDを抽出（REPORT_1234.md → TASK_1234）
    const taskIdMatch = reportFilename.match(/REPORT_(\d+)(?:_v\d+)?\.md$/);
    const taskId = taskIdMatch ? `TASK_${taskIdMatch[1]}` : '';

    const changedFiles = extractChangedFilesFromReport(report.content);
    const impactScope = extractImpactScopeFromReport(report.content);
    const summary = extractSummaryFromReport(report.content);

    reportSummaries.push({
      taskId,
      reportFilename,
      changedFiles,
      impactScope,
      summary,
    });
  }

  // リリースステータスを判定
  let releaseStatus: 'ready' | 'partial' | 'not_ready' = 'not_ready';
  if (allTasksCompleted && allReviewsApproved) {
    releaseStatus = 'ready';
  } else if (completedTasks > 0 || reviewResults.some(r => r.reviewStatus === 'APPROVED')) {
    releaseStatus = 'partial';
  }

  return {
    projectId,
    orderId,
    totalTasks,
    completedTasks,
    allTasksCompleted,
    reviewResults,
    allReviewsApproved,
    reportSummaries,
    releaseStatus,
  };
}
