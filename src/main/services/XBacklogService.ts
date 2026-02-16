/**
 * XBacklogService - TASK_655
 */

import * as fs from 'node:fs';
import Database from 'better-sqlite3';
import { getConfigService } from './ConfigService';

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

export interface AnalysisResult {
  suggestedProjectId: string | null;
  suggestedProjectName: string | null;
  confidence: number;
  reason: string;
  keywords: string[];
}

export interface DispatchResult {
  success: boolean;
  xbacklogId: string;
  projectId: string;
  backlogId: string | null;
  error?: string;
}

export class XBacklogService {
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
      console.error('[XBacklogService] DB test failed:', error);
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

  private getWriteConnection(): Database.Database {
    const dbPath = this.getDbPath();
    if (!dbPath) throw new Error('Framework path is not configured');
    if (!fs.existsSync(dbPath)) throw new Error('Database file not found: ' + dbPath);
    const db = new Database(dbPath, { readonly: false });
    db.pragma('foreign_keys = ON');
    return db;
  }

  getXBacklogs(supervisorId: string): XBacklog[] {
    try {
      const db = this.getConnection();
      const sql = "SELECT id, supervisor_id, title, description, priority, status, assigned_project_id, assigned_backlog_id, analysis_result, created_at, updated_at FROM cross_project_backlog WHERE supervisor_id = ? ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 END, created_at DESC";
      const rows = db.prepare(sql).all(supervisorId) as Array<{id:string;supervisor_id:string;title:string;description:string|null;priority:string;status:string;assigned_project_id:string|null;assigned_backlog_id:string|null;analysis_result:string|null;created_at:string;updated_at:string}>;
      return rows.map((r) => ({ id:r.id, supervisorId:r.supervisor_id, title:r.title, description:r.description, priority:r.priority, status:r.status, assignedProjectId:r.assigned_project_id, assignedBacklogId:r.assigned_backlog_id, analysisResult:r.analysis_result, createdAt:r.created_at, updatedAt:r.updated_at }));
    } catch (error) { console.error('[XBacklogService] getXBacklogs failed:', error); throw error; }
  }

  createXBacklog(supervisorId: string, title: string, description: string | null, priority: string): XBacklog {
    const db = this.getWriteConnection();
    try {
      const existingMax = db.prepare("SELECT MAX(CAST(SUBSTR(id, 10) AS INTEGER)) as max_num FROM cross_project_backlog").get() as { max_num: number | null };
      const nextNum = (existingMax?.max_num || 0) + 1;
      const id = 'XBACKLOG_' + String(nextNum).padStart(3, '0');
      const now = new Date().toISOString();
      db.prepare("INSERT INTO cross_project_backlog (id, supervisor_id, title, description, priority, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)").run(id, supervisorId, title, description, priority, now, now);
      db.close();
      return { id, supervisorId, title, description, priority, status: 'PENDING', assignedProjectId: null, assignedBacklogId: null, analysisResult: null, createdAt: now, updatedAt: now };
    } catch (error) { db.close(); console.error('[XBacklogService] createXBacklog failed:', error); throw error; }
  }

  analyzeXBacklog(xbacklogId: string): AnalysisResult {
    try {
      const db = this.getConnection();
      const xbacklog = db.prepare("SELECT id, supervisor_id, title, description FROM cross_project_backlog WHERE id = ?").get(xbacklogId) as {id:string;supervisor_id:string;title:string;description:string|null}|undefined;
      if (!xbacklog) throw new Error('XBacklog not found: ' + xbacklogId);
      const projects = db.prepare("SELECT id, name FROM projects WHERE supervisor_id = ? AND is_active = 1").all(xbacklog.supervisor_id) as Array<{id:string;name:string}>;
      if (projects.length === 0) return { suggestedProjectId: null, suggestedProjectName: null, confidence: 0, reason: 'No active projects found', keywords: [] };
      const text = (xbacklog.title + ' ' + (xbacklog.description || '')).toLowerCase();
      const keywords: string[] = [];
      let bestMatch: {id:string;name:string;score:number}|null = null;
      for (const project of projects) {
        const nameWords = project.name.toLowerCase().split(/[\s_-]+/);
        let score = 0;
        for (const word of nameWords) { if (word.length >= 2 && text.includes(word)) { score++; keywords.push(word); } }
        if (score > 0 && (!bestMatch || score > bestMatch.score)) { bestMatch = { id: project.id, name: project.name, score }; }
      }
      if (bestMatch) {
        const confidence = Math.min(bestMatch.score * 0.3, 0.9);
        return { suggestedProjectId: bestMatch.id, suggestedProjectName: bestMatch.name, confidence, reason: 'Keyword match: ' + keywords.join(', '), keywords };
      }
      return { suggestedProjectId: projects[0].id, suggestedProjectName: projects[0].name, confidence: 0.1, reason: 'Default assignment (no keyword match)', keywords: [] };
    } catch (error) { console.error('[XBacklogService] analyzeXBacklog failed:', error); throw error; }
  }

  dispatchXBacklog(xbacklogId: string, projectId: string): DispatchResult {
    const db = this.getWriteConnection();
    try {
      const now = new Date().toISOString();
      db.prepare("UPDATE cross_project_backlog SET assigned_project_id = ?, status = 'DISPATCHED', updated_at = ? WHERE id = ?").run(projectId, now, xbacklogId);
      db.close();
      return { success: true, xbacklogId, projectId, backlogId: null };
    } catch (error) { db.close(); console.error('[XBacklogService] dispatchXBacklog failed:', error); return { success: false, xbacklogId, projectId, backlogId: null, error: String(error) }; }
  }

  close(): void { if (this.db) { try { this.db.close(); } catch (e) { console.error('[XBacklogService] close failed:', e); } this.db = null; this.dbPath = null; } }
}

let xbacklogServiceInstance: XBacklogService | null = null;
export function getXBacklogService(): XBacklogService { if (!xbacklogServiceInstance) xbacklogServiceInstance = new XBacklogService(); return xbacklogServiceInstance; }
export function resetXBacklogService(): void { if (xbacklogServiceInstance) xbacklogServiceInstance.close(); xbacklogServiceInstance = null; }
