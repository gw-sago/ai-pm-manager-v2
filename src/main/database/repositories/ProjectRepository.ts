/**
 * Project Repository
 *
 * プロジェクトのCRUD操作を提供
 */

import { BaseRepository, BaseEntity } from './BaseRepository';
import type { ProjectStatus } from '../schema';

export interface Project extends BaseEntity {
  name: string;
  path: string;
  description?: string | null;
  purpose?: string | null;
  tech_stack?: string | null;
  status: ProjectStatus;
}

export interface CreateProjectInput {
  name: string;
  path: string;
  description?: string;
  purpose?: string;
  tech_stack?: string;
  status?: ProjectStatus;
}

export interface UpdateProjectInput {
  name?: string;
  path?: string;
  description?: string;
  purpose?: string;
  tech_stack?: string;
  status?: ProjectStatus;
}

export class ProjectRepository extends BaseRepository<Project> {
  protected tableName = 'projects';

  /**
   * プロジェクトを作成
   */
  create(input: CreateProjectInput): Project {
    const now = this.now();
    const result = this.db
      .prepare(
        `INSERT INTO projects (name, path, description, purpose, tech_stack, status, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .run(
        input.name,
        input.path,
        input.description ?? null,
        input.purpose ?? null,
        input.tech_stack ?? null,
        input.status ?? 'INITIAL',
        now,
        now
      );

    return this.findById(result.lastInsertRowid as number)!;
  }

  /**
   * プロジェクトを更新
   */
  update(id: number, input: UpdateProjectInput): Project | undefined {
    const project = this.findById(id);
    if (!project) {
      return undefined;
    }

    const updates: string[] = [];
    const values: unknown[] = [];

    if (input.name !== undefined) {
      updates.push('name = ?');
      values.push(input.name);
    }
    if (input.path !== undefined) {
      updates.push('path = ?');
      values.push(input.path);
    }
    if (input.description !== undefined) {
      updates.push('description = ?');
      values.push(input.description);
    }
    if (input.purpose !== undefined) {
      updates.push('purpose = ?');
      values.push(input.purpose);
    }
    if (input.tech_stack !== undefined) {
      updates.push('tech_stack = ?');
      values.push(input.tech_stack);
    }
    if (input.status !== undefined) {
      updates.push('status = ?');
      values.push(input.status);
    }

    if (updates.length === 0) {
      return project;
    }

    updates.push('updated_at = ?');
    values.push(this.now());
    values.push(id);

    this.db
      .prepare(`UPDATE projects SET ${updates.join(', ')} WHERE id = ?`)
      .run(...values);

    return this.findById(id);
  }

  /**
   * 名前でプロジェクトを検索
   */
  findByName(name: string): Project | undefined {
    return this.findOneBy({ name } as Partial<Project>);
  }

  /**
   * ステータスでプロジェクトを検索
   */
  findByStatus(status: ProjectStatus): Project[] {
    return this.findBy({ status } as Partial<Project>);
  }

  /**
   * アクティブなプロジェクトを取得
   */
  findActive(): Project[] {
    return this.db
      .prepare(
        `SELECT * FROM projects
         WHERE status NOT IN ('COMPLETED', 'CANCELLED')
         ORDER BY updated_at DESC`
      )
      .all() as Project[];
  }

  /**
   * プロジェクトのステータスを更新
   */
  updateStatus(id: number, status: ProjectStatus): Project | undefined {
    return this.update(id, { status });
  }
}
