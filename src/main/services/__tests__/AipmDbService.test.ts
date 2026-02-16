/**
 * AipmDbService Unit Tests
 *
 * TASK_196: AipmDbService基本実装
 *
 * Note: better-sqlite3はネイティブモジュールのため、このテストでは
 * サービスのユーティリティメソッドとエラーハンドリングのみをテストします。
 * DB接続を使用する実際のメソッドは統合テスト、またはElectron環境で
 * 検証する必要があります。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { AipmDbService, resetAipmDbService } from '../AipmDbService';

// Mock ConfigService
const mockGetActiveFrameworkPath = vi.fn();
const mockGetAipmDbPath = vi.fn();
vi.mock('../ConfigService', () => ({
  getConfigService: vi.fn(() => ({
    getActiveFrameworkPath: mockGetActiveFrameworkPath,
    getAipmDbPath: mockGetAipmDbPath,
  })),
}));

// テスト用パス
const TEST_DIR = path.join(__dirname, '__test_aipm_db__');
const TEST_DB_PATH = path.join(TEST_DIR, 'data', 'aipm.db');

/**
 * テストディレクトリをクリーンアップ
 */
function cleanupTestDir(): void {
  if (fs.existsSync(TEST_DIR)) {
    fs.rmSync(TEST_DIR, { recursive: true });
  }
}

describe('AipmDbService', () => {
  let service: AipmDbService;

  beforeEach(() => {
    cleanupTestDir();
    resetAipmDbService();
    service = new AipmDbService();
    vi.clearAllMocks();
    mockGetActiveFrameworkPath.mockReturnValue(TEST_DIR);
    mockGetAipmDbPath.mockReturnValue(TEST_DB_PATH);
  });

  afterEach(() => {
    service.close();
    cleanupTestDir();
    resetAipmDbService();
  });

  describe('getDbPath', () => {
    it('should delegate to ConfigService.getAipmDbPath()', () => {
      mockGetAipmDbPath.mockReturnValue(path.join('/path/to/framework', 'data', 'aipm.db'));

      const result = service.getDbPath();

      expect(result).toBe(path.join('/path/to/framework', 'data', 'aipm.db'));
    });

    it('should return packaged path when ConfigService returns APPDATA path', () => {
      const appdataPath = path.join('C:\\Users\\test\\AppData\\Roaming\\ai-pm-manager-v2', '.aipm', 'aipm.db');
      mockGetAipmDbPath.mockReturnValue(appdataPath);

      const result = service.getDbPath();

      expect(result).toBe(appdataPath);
    });

    it('should handle Windows-style paths', () => {
      mockGetAipmDbPath.mockReturnValue(path.join('D:\\your_workspace\\AI_PM', 'data', 'aipm.db'));

      const result = service.getDbPath();

      expect(result).toBe(path.join('D:\\your_workspace\\AI_PM', 'data', 'aipm.db'));
    });
  });

  describe('isAvailable', () => {
    it('should return false when DB path is not set', () => {
      mockGetAipmDbPath.mockReturnValue(null);

      expect(service.isAvailable()).toBe(false);
    });

    it('should return false when DB file does not exist', () => {
      fs.mkdirSync(TEST_DIR, { recursive: true });
      // DBファイルは作成しない

      expect(service.isAvailable()).toBe(false);
    });

    // Note: DB接続テストはElectron環境でのみ実行可能
    // better-sqlite3のネイティブモジュールバージョン不一致のため
  });

  describe('error handling (without DB connection)', () => {
    it('should throw error when trying to get projects without framework path', () => {
      mockGetAipmDbPath.mockReturnValue(null);

      expect(() => service.getProjects()).toThrow('Framework path is not configured');
    });

    it('should throw error when trying to get orders without framework path', () => {
      mockGetAipmDbPath.mockReturnValue(null);

      expect(() => service.getOrders('proj_001')).toThrow('Framework path is not configured');
    });

    it('should throw error when trying to get tasks without framework path', () => {
      mockGetAipmDbPath.mockReturnValue(null);

      expect(() => service.getTasks('ORDER_001', 'proj_001')).toThrow('Framework path is not configured');
    });

    it('should throw error when trying to get review queue without framework path', () => {
      mockGetAipmDbPath.mockReturnValue(null);

      expect(() => service.getReviewQueue('proj_001')).toThrow('Framework path is not configured');
    });

    it('should throw error when DB file does not exist', () => {
      fs.mkdirSync(TEST_DIR, { recursive: true });
      // DBファイルは作成しない

      expect(() => service.getProjects()).toThrow('Database file not found');
    });
  });

  describe('close', () => {
    it('should not throw when closing without opening', () => {
      expect(() => service.close()).not.toThrow();
    });

    it('should handle multiple close calls gracefully', () => {
      expect(() => {
        service.close();
        service.close();
        service.close();
      }).not.toThrow();
    });
  });

  describe('singleton pattern', () => {
    it('should reset service instance correctly', () => {
      const service1 = new AipmDbService();
      resetAipmDbService();
      const service2 = new AipmDbService();

      // 両方とも有効なインスタンスであることを確認
      expect(service1.getDbPath).toBeDefined();
      expect(service2.getDbPath).toBeDefined();
    });
  });
});

describe('AipmDbService - Type Definitions', () => {
  /**
   * 型定義のテスト（コンパイル時チェック）
   * 実行時の検証ではなく、TypeScriptの型チェックを活用
   */

  it('should have correct AipmProject type structure', async () => {
    const { AipmDbService } = await import('../AipmDbService');
    const service = new AipmDbService();

    // 型定義が正しいことを確認（コンパイルエラーがなければOK）
    expect(typeof service.getProjects).toBe('function');
    expect(typeof service.getOrders).toBe('function');
    expect(typeof service.getTasks).toBe('function');
    expect(typeof service.getReviewQueue).toBe('function');
    expect(typeof service.isAvailable).toBe('function');
    expect(typeof service.getDbPath).toBe('function');
    expect(typeof service.close).toBe('function');
  });
});
