/**
 * ProjectService Unit Tests
 *
 * TASK_018: ProjectService実装（IPC含む）
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { ProjectService, resetProjectService } from '../ProjectService';
import type { Project, ProjectListResult } from '../ProjectService';

// Mock modules
vi.mock('../ConfigService', () => ({
  getConfigService: vi.fn(() => ({
    getActiveFrameworkPath: vi.fn(() => null),
  })),
}));

vi.mock('../FileWatcherService', () => ({
  fileWatcherService: {
    on: vi.fn(),
    removeAllListeners: vi.fn(),
  },
}));

// テスト用のディレクトリを作成
const TEST_DIR = path.join(__dirname, '__test_projects__');
const PROJECTS_DIR = path.join(TEST_DIR, 'PROJECTS');

function createTestStateFile(projectName: string, content: string) {
  const projectDir = path.join(PROJECTS_DIR, projectName);
  if (!fs.existsSync(projectDir)) {
    fs.mkdirSync(projectDir, { recursive: true });
  }
  fs.writeFileSync(path.join(projectDir, 'STATE.md'), content);
}

function cleanupTestDir() {
  if (fs.existsSync(TEST_DIR)) {
    fs.rmSync(TEST_DIR, { recursive: true });
  }
}

describe('ProjectService', () => {
  let service: ProjectService;

  beforeEach(() => {
    cleanupTestDir();
    resetProjectService();
    service = new ProjectService();
  });

  afterEach(() => {
    cleanupTestDir();
    resetProjectService();
  });

  describe('getProjectsFromPath', () => {
    it('should return error when PROJECTS directory does not exist', () => {
      const result = service.getProjectsFromPath(TEST_DIR);

      expect(result.projects).toHaveLength(0);
      expect(result.error).toContain('PROJECTSディレクトリが見つかりません');
    });

    it('should return empty array when no projects exist', () => {
      fs.mkdirSync(PROJECTS_DIR, { recursive: true });

      const result = service.getProjectsFromPath(TEST_DIR);

      expect(result.projects).toHaveLength(0);
      expect(result.error).toBeUndefined();
      expect(result.frameworkPath).toBe(TEST_DIR);
    });

    it('should detect projects with STATE.md files', () => {
      fs.mkdirSync(PROJECTS_DIR, { recursive: true });

      createTestStateFile('Project_A', `
# STATE.md

## プロジェクト情報

- **プロジェクト名**: Project A
- **現在ステータス**: \`IN_PROGRESS\`
- **アクティブORDER数**: 1
- **開始日**: 2026-01-20

## タスク一覧（ORDER_001）【IN_PROGRESS】

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_001 | タスク1 | QUEUED | Worker A | - | - | - |
`);

      createTestStateFile('Project_B', `
# STATE.md

## プロジェクト情報

- **プロジェクト名**: Project B
- **現在ステータス**: \`COMPLETED\`
`);

      const result = service.getProjectsFromPath(TEST_DIR);

      expect(result.projects).toHaveLength(2);
      expect(result.error).toBeUndefined();

      const projectA = result.projects.find(p => p.name === 'Project_A');
      expect(projectA).toBeDefined();
      expect(projectA?.hasStateFile).toBe(true);
      expect(projectA?.state).not.toBeNull();
      expect(projectA?.state?.projectInfo.name).toBe('Project A');
      expect(projectA?.state?.projectInfo.status).toBe('IN_PROGRESS');
      expect(projectA?.state?.tasks).toHaveLength(1);

      const projectB = result.projects.find(p => p.name === 'Project_B');
      expect(projectB).toBeDefined();
      expect(projectB?.state?.projectInfo.status).toBe('COMPLETED');
    });

    it('should handle projects without STATE.md', () => {
      fs.mkdirSync(PROJECTS_DIR, { recursive: true });
      fs.mkdirSync(path.join(PROJECTS_DIR, 'EmptyProject'), { recursive: true });

      createTestStateFile('ValidProject', `
## プロジェクト情報

- **プロジェクト名**: Valid Project
- **現在ステータス**: IN_PROGRESS
`);

      const result = service.getProjectsFromPath(TEST_DIR);

      expect(result.projects).toHaveLength(2);

      const emptyProject = result.projects.find(p => p.name === 'EmptyProject');
      expect(emptyProject).toBeDefined();
      expect(emptyProject?.hasStateFile).toBe(false);
      expect(emptyProject?.state).toBeNull();

      const validProject = result.projects.find(p => p.name === 'ValidProject');
      expect(validProject?.hasStateFile).toBe(true);
      expect(validProject?.state).not.toBeNull();
    });

    it('should sort projects by name', () => {
      fs.mkdirSync(PROJECTS_DIR, { recursive: true });

      createTestStateFile('Zebra_Project', `
## プロジェクト情報
- **プロジェクト名**: Zebra
`);

      createTestStateFile('Alpha_Project', `
## プロジェクト情報
- **プロジェクト名**: Alpha
`);

      createTestStateFile('Middle_Project', `
## プロジェクト情報
- **プロジェクト名**: Middle
`);

      const result = service.getProjectsFromPath(TEST_DIR);

      expect(result.projects).toHaveLength(3);
      expect(result.projects[0].name).toBe('Alpha_Project');
      expect(result.projects[1].name).toBe('Middle_Project');
      expect(result.projects[2].name).toBe('Zebra_Project');
    });

    it('should handle malformed STATE.md gracefully', () => {
      fs.mkdirSync(PROJECTS_DIR, { recursive: true });

      createTestStateFile('MalformedProject', `
This is not a valid STATE.md file.
Just some random text.
`);

      const result = service.getProjectsFromPath(TEST_DIR);

      expect(result.projects).toHaveLength(1);
      const project = result.projects[0];
      expect(project.hasStateFile).toBe(true);
      expect(project.state).not.toBeNull();
      expect(project.state?.projectInfo.name).toBe('');
    });
  });

  describe('getProjectState', () => {
    it('should return null when no framework path is set', () => {
      const result = service.getProjectState('SomeProject');
      expect(result).toBeNull();
    });
  });

  describe('cache operations', () => {
    it('should cache projects after loading', () => {
      fs.mkdirSync(PROJECTS_DIR, { recursive: true });

      createTestStateFile('CachedProject', `
## プロジェクト情報
- **プロジェクト名**: Cached Project
- **現在ステータス**: IN_PROGRESS
`);

      service.getProjectsFromPath(TEST_DIR);

      const cached = service.getCachedProject('CachedProject');
      expect(cached).toBeDefined();
      expect(cached?.state?.projectInfo.name).toBe('Cached Project');
    });

    it('should clear cache', () => {
      fs.mkdirSync(PROJECTS_DIR, { recursive: true });

      createTestStateFile('TestProject', `
## プロジェクト情報
- **プロジェクト名**: Test Project
`);

      service.getProjectsFromPath(TEST_DIR);
      expect(service.getCachedProject('TestProject')).toBeDefined();

      service.clearCache();
      expect(service.getCachedProject('TestProject')).toBeUndefined();
    });
  });

  describe('listening', () => {
    it('should start and stop listening without errors', () => {
      // startListening と stopListening が例外をスローせずに動作することを確認
      expect(() => service.startListening()).not.toThrow();
      expect(() => service.stopListening()).not.toThrow();
    });

    it('should handle multiple start calls gracefully', () => {
      // 複数回呼び出しても例外をスローしない
      expect(() => {
        service.startListening();
        service.startListening();
        service.stopListening();
      }).not.toThrow();
    });
  });

  describe('getProjects (with ConfigService)', () => {
    it('should return error when no framework path is configured', () => {
      const result = service.getProjects();

      expect(result.projects).toHaveLength(0);
      expect(result.error).toContain('フレームワークパスが設定されていません');
    });
  });
});

describe('ProjectService - Task and Order parsing', () => {
  let service: ProjectService;

  beforeEach(() => {
    cleanupTestDir();
    resetProjectService();
    service = new ProjectService();
  });

  afterEach(() => {
    cleanupTestDir();
    resetProjectService();
  });

  it('should parse tasks correctly from STATE.md', () => {
    fs.mkdirSync(PROJECTS_DIR, { recursive: true });

    createTestStateFile('TaskProject', `
# STATE.md

## プロジェクト情報

- **プロジェクト名**: Task Project
- **現在ステータス**: \`IN_PROGRESS\`
- **アクティブORDER**: ORDER_005

## タスク一覧（ORDER_005）【IN_PROGRESS】

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_017 | STATE.mdパーサー実装 | COMPLETED | Worker A | - | 2026-01-23 | 2026-01-23 |
| TASK_018 | ProjectService実装 | IN_PROGRESS | Worker B | TASK_017 | 2026-01-23 | - |
| TASK_019 | UI実装 | BLOCKED | Worker A | TASK_018 | - | - |

## タスク一覧（ORDER_004）【COMPLETED】

| Task ID | タイトル | ステータス | 担当 | 依存 | 開始日 | 完了日 |
|---------|---------|----------|------|------|--------|--------|
| TASK_016 | 前タスク | COMPLETED | Worker A | - | 2026-01-21 | 2026-01-21 |
`);

    const result = service.getProjectsFromPath(TEST_DIR);

    expect(result.projects).toHaveLength(1);
    const project = result.projects[0];

    expect(project.state?.tasks).toHaveLength(4);
    expect(project.state?.orders).toHaveLength(2);

    // ORDER_005のタスク
    const order005 = project.state?.orders.find(o => o.id === 'ORDER_005');
    expect(order005?.tasks).toHaveLength(3);
    expect(order005?.status).toBe('IN_PROGRESS');

    // 依存関係の検証
    const task018 = project.state?.tasks.find(t => t.id === 'TASK_018');
    expect(task018?.dependencies).toEqual(['TASK_017']);
    expect(task018?.status).toBe('IN_PROGRESS');

    // 進捗サマリ
    expect(project.state?.progressSummary.completed).toBe(2);
    expect(project.state?.progressSummary.inProgress).toBe(1);
    expect(project.state?.progressSummary.blocked).toBe(1);
  });

  it('should parse review queue from STATE.md', () => {
    fs.mkdirSync(PROJECTS_DIR, { recursive: true });

    createTestStateFile('ReviewProject', `
# STATE.md

## プロジェクト情報

- **プロジェクト名**: Review Project
- **現在ステータス**: REVIEW

## レビューキュー

| Task ID | 提出日時 | ステータス | レビュアー | 優先度 | 備考 |
|---------|---------|----------|-----------|--------|------|
| TASK_017 | 2026-01-23 15:30 | PENDING | - | P1 | - |
| TASK_016 | 2026-01-21 10:00 | IN_REVIEW | PM | P0 | 再提出 |
`);

    const result = service.getProjectsFromPath(TEST_DIR);

    expect(result.projects).toHaveLength(1);
    const project = result.projects[0];

    expect(project.state?.reviewQueue).toHaveLength(2);

    const review017 = project.state?.reviewQueue.find(r => r.taskId === 'TASK_017');
    expect(review017?.status).toBe('PENDING');
    expect(review017?.priority).toBe('P1');

    const review016 = project.state?.reviewQueue.find(r => r.taskId === 'TASK_016');
    expect(review016?.status).toBe('IN_REVIEW');
    expect(review016?.reviewer).toBe('PM');
    expect(review016?.note).toBe('再提出');
  });
});
