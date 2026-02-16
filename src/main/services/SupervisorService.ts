/**
 * SupervisorService
 *
 * Supervisor管理のためのサービス
 * TASK_655: バックエンドサービス・IPC実装
 */

import * as fs from 'node:fs';
import Database from 'better-sqlite3';
import { getConfigService } from './ConfigService';

export interface Supervisor {
  id: string;
  name: string;
  description: string | null;
  status: string;
  createdAt: string;
  updatedAt: string;
}

export interface SupervisorDetail extends Supervisor {
  projectCount: number;
  xbacklogCount: number;
}

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

// ポートフォリオビュー型定義 (ORDER_068 / BACKLOG_116)
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

export interface PortfolioTask {
  id: string;
  orderId: string;
  title: string;
  status: string;
  priority: string;
  createdAt: string;
}

export interface PortfolioData {
  orders: PortfolioOrder[];
  backlogs: PortfolioBacklog[];
}

export class SupervisorService {
  private db: Database.Database | null = null;
  private dbPath: string | null = null;

  private getDbPath(): string | null {
    const configService = getConfigService();
    return configService.getAipmDbPath();
  }

  isAvailable(): boolean {
    const dbPath = this.getDbPath();
    if (!dbPath || !fs.existsSync(dbPath)) return false;
    try {
      const db = new Database(dbPath, { readonly: true });
      db.prepare('SELECT 1').get();
      db.close();
      return true;
    } catch (error) {
      console.error('[SupervisorService] DB test failed:', error);
      return false;
    }
  }

  private getConnection(): Database.Database {
    const dbPath = this.getDbPath();
    if (!dbPath) throw new Error('Framework path is not configured');
    if (this.db && this.dbPath === dbPath) return this.db;
    if (this.db) { try { this.db.close(); } catch {} }
    if (!fs.existsSync(dbPath)) throw new Error('Database file not found: ' + dbPath);
    this.db = new Database(dbPath, { readonly: true });
    this.dbPath = dbPath;
    this.db.pragma('foreign_keys = ON');
    return this.db;
  }

  getSupervisors(): Supervisor[] {
    try {
      const db = this.getConnection();
      const rows = db.prepare("SELECT id, name, description, status, created_at, updated_at FROM supervisors WHERE status = 'ACTIVE' ORDER BY name").all() as Array<{id:string;name:string;description:string|null;status:string;created_at:string;updated_at:string}>;
      return rows.map((r) => ({ id:r.id, name:r.name, description:r.description, status:r.status, createdAt:r.created_at, updatedAt:r.updated_at }));
    } catch (error) { console.error('[SupervisorService] getSupervisors failed:', error); throw error; }
  }

  getSupervisorDetail(supervisorId: string): SupervisorDetail | null {
    try {
      const db = this.getConnection();
      const row = db.prepare("SELECT s.id, s.name, s.description, s.status, s.created_at, s.updated_at, (SELECT COUNT(*) FROM projects p WHERE p.supervisor_id = s.id) as project_count, (SELECT COUNT(*) FROM cross_project_backlog x WHERE x.supervisor_id = s.id) as xbacklog_count FROM supervisors s WHERE s.id = ?").get(supervisorId) as {id:string;name:string;description:string|null;status:string;created_at:string;updated_at:string;project_count:number;xbacklog_count:number}|undefined;
      if (!row) return null;
      return { id:row.id, name:row.name, description:row.description, status:row.status, createdAt:row.created_at, updatedAt:row.updated_at, projectCount:row.project_count, xbacklogCount:row.xbacklog_count };
    } catch (error) { console.error('[SupervisorService] getSupervisorDetail failed:', error); throw error; }
  }

  getProjectsBySupervisor(supervisorId: string, includeInactive = false): SupervisorProject[] {
    try {
      const db = this.getConnection();
      const sql = includeInactive ? "SELECT id,name,path,status,current_order_id,is_active,created_at,updated_at FROM projects WHERE supervisor_id=? ORDER BY name" : "SELECT id,name,path,status,current_order_id,is_active,created_at,updated_at FROM projects WHERE supervisor_id=? AND is_active=1 ORDER BY name";
      const rows = db.prepare(sql).all(supervisorId) as Array<{id:string;name:string;path:string;status:string;current_order_id:string|null;is_active:number;created_at:string;updated_at:string}>;
      return rows.map((r) => ({ id:r.id, name:r.name, path:r.path, status:r.status, currentOrderId:r.current_order_id, isActive:r.is_active===1, createdAt:r.created_at, updatedAt:r.updated_at }));
    } catch (error) { console.error('[SupervisorService] getProjectsBySupervisor failed:', error); throw error; }
  }

  close(): void {
    if (this.db) { try { this.db.close(); } catch (e) { console.error('[SupervisorService] Failed to close:', e); } this.db = null; this.dbPath = null; }
  }

  // ポートフォリオデータ取得 (ORDER_068 / BACKLOG_116)
  getPortfolioData(supervisorId: string): PortfolioData {
    try {
      const db = this.getConnection();

      // Supervisor配下のプロジェクト一覧を取得
      const projects = db.prepare(
        "SELECT id, name FROM projects WHERE supervisor_id = ? AND is_active = 1"
      ).all(supervisorId) as Array<{ id: string; name: string }>;

      const orders: PortfolioOrder[] = [];
      const backlogs: PortfolioBacklog[] = [];

      for (const project of projects) {
        // ORDER一覧を取得
        const orderRows = db.prepare(`
          SELECT
            o.id, o.title, o.status, o.priority, o.created_at, o.updated_at,
            (SELECT COUNT(*) FROM tasks t WHERE t.order_id = o.id) as task_count,
            (SELECT COUNT(*) FROM tasks t WHERE t.order_id = o.id AND t.status IN ('DONE', 'COMPLETED')) as completed_task_count
          FROM orders o
          WHERE o.project_id = ?
          ORDER BY o.created_at DESC
        `).all(project.id) as Array<{
          id: string; title: string; status: string; priority: string;
          created_at: string; updated_at: string; task_count: number; completed_task_count: number;
        }>;

        for (const row of orderRows) {
          const progress = row.task_count > 0 ? Math.round((row.completed_task_count / row.task_count) * 100) : 0;
          orders.push({
            id: row.id,
            portfolioId: `${project.name}/${row.id}`,
            projectId: project.id,
            projectName: project.name,
            title: row.title,
            status: row.status,
            priority: row.priority,
            progress,
            taskCount: row.task_count,
            completedTaskCount: row.completed_task_count,
            createdAt: row.created_at,
            updatedAt: row.updated_at,
          });
        }

        // バックログ一覧を取得
        const backlogRows = db.prepare(`
          SELECT id, title, status, priority, description, created_at, updated_at
          FROM backlog_items
          WHERE project_id = ?
          ORDER BY created_at DESC
        `).all(project.id) as Array<{
          id: string; title: string; status: string; priority: string;
          description: string | null; created_at: string; updated_at: string;
        }>;

        for (const row of backlogRows) {
          backlogs.push({
            id: row.id,
            portfolioId: `${project.name}/${row.id}`,
            projectId: project.id,
            projectName: project.name,
            title: row.title,
            status: row.status,
            priority: row.priority,
            description: row.description,
            createdAt: row.created_at,
            updatedAt: row.updated_at,
          });
        }
      }

      return { orders, backlogs };
    } catch (error) {
      console.error('[SupervisorService] getPortfolioData failed:', error);
      throw error;
    }
  }

  // ポートフォリオORDERタスク一覧取得 (ORDER_068 / BACKLOG_116)
  getPortfolioOrderTasks(projectId: string, orderId: string): PortfolioTask[] {
    try {
      const db = this.getConnection();
      const rows = db.prepare(`
        SELECT id, order_id, title, status, priority, created_at
        FROM tasks
        WHERE order_id = ?
        ORDER BY priority ASC, created_at ASC
      `).all(orderId) as Array<{
        id: string; order_id: string; title: string; status: string; priority: string; created_at: string;
      }>;

      return rows.map(row => ({
        id: row.id,
        orderId: row.order_id,
        title: row.title,
        status: row.status,
        priority: row.priority,
        createdAt: row.created_at,
      }));
    } catch (error) {
      console.error('[SupervisorService] getPortfolioOrderTasks failed:', error);
      throw error;
    }
  }
}

let supervisorServiceInstance: SupervisorService | null = null;
export function getSupervisorService(): SupervisorService { if (!supervisorServiceInstance) supervisorServiceInstance = new SupervisorService(); return supervisorServiceInstance; }
export function resetSupervisorService(): void { if (supervisorServiceInstance) supervisorServiceInstance.close(); supervisorServiceInstance = null; }
