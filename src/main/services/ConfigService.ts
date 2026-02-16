/**
 * ConfigService
 *
 * アプリケーション設定の永続化を担当するサービス
 *
 * V2統合: UIとフレームワークが1リポジトリに統合されたため、
 * frameworkPath = リポジトリルート（固定）。
 * AppData DBは廃止し、設定はconfig.jsonのみで管理。
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { app } from 'electron';

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
 * アプリケーション設定（config.jsonに保存）
 */
export interface AppConfig {
  version: string;
  window?: WindowConfig;
}

/**
 * 設定ファイルのデフォルト値
 */
const DEFAULT_CONFIG: AppConfig = {
  version: '2.0.0',
  window: {
    width: 1200,
    height: 800,
    x: null,
    y: null,
  },
};

/**
 * ConfigService クラス
 *
 * V2統合アーキテクチャ:
 * - frameworkPath = リポジトリルート（固定、DB不要）
 * - DB = data/aipm.db（1つのみ）
 * - 設定 = config.json（ウィンドウサイズ等のUI設定のみ）
 */
export class ConfigService {
  private configPath: string;
  private _frameworkPath: string;

  constructor() {
    const userDataPath = app.getPath('userData');
    const aipmDir = path.join(userDataPath, '.aipm');
    this.configPath = path.join(aipmDir, 'config.json');

    // V2統合: リポジトリルート = frameworkPath
    if (app.isPackaged) {
      this._frameworkPath = path.join(process.resourcesPath, 'framework');
    } else {
      this._frameworkPath = app.getAppPath();
    }
  }

  /**
   * 設定ディレクトリを確保
   */
  private ensureConfigDirectory(): void {
    const dir = path.dirname(this.configPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  }

  /**
   * JSON設定ファイルを読み込む
   */
  private readConfigFile(): Partial<AppConfig> {
    try {
      if (fs.existsSync(this.configPath)) {
        const content = fs.readFileSync(this.configPath, 'utf-8');
        return JSON.parse(content) as Partial<AppConfig>;
      }
    } catch (error) {
      console.error('[ConfigService] Failed to read config file:', error);
    }
    return {};
  }

  /**
   * JSON設定ファイルに書き込む
   */
  private writeConfigFile(config: Partial<AppConfig>): void {
    try {
      this.ensureConfigDirectory();
      fs.writeFileSync(this.configPath, JSON.stringify(config, null, 2), 'utf-8');
    } catch (error) {
      console.error('[ConfigService] Failed to write config file:', error);
      throw error;
    }
  }

  /**
   * アプリケーション設定を読み込む
   */
  load(): AppConfig {
    const fileConfig = this.readConfigFile();
    return {
      version: fileConfig.version ?? DEFAULT_CONFIG.version,
      window: fileConfig.window ?? DEFAULT_CONFIG.window,
    };
  }

  /**
   * フレームワークパスを取得（V2: 固定パス）
   *
   * V2ではUI+フレームワークが1リポジトリに統合されているため、
   * リポジトリルートが常にframeworkPath。
   */
  getActiveFrameworkPath(): string {
    return this._frameworkPath;
  }

  /**
   * AI PM Frameworkのルートパスを取得
   * getActiveFrameworkPath() と同一
   */
  getAipmFrameworkPath(): string {
    return this._frameworkPath;
  }

  /**
   * AI PM Framework DB（aipm.db）のパスを取得
   */
  getAipmDbPath(): string {
    return path.join(this._frameworkPath, 'data', 'aipm.db');
  }

  /**
   * DB優先モードが有効かどうかを取得
   * V2では常にtrue（DB駆動のみ）
   */
  isDbPriorityEnabled(): boolean {
    return true;
  }

  /**
   * PROJECTSディレクトリを確保
   */
  ensureProjectsDirectory(): void {
    const projectsDir = path.join(this._frameworkPath, 'PROJECTS');
    if (!fs.existsSync(projectsDir)) {
      fs.mkdirSync(projectsDir, { recursive: true });
      console.log('[ConfigService] Created PROJECTS directory:', projectsDir);
    }
  }

  /**
   * ウィンドウ設定を保存
   */
  saveWindowConfig(windowConfig: WindowConfig): void {
    const fileConfig = this.readConfigFile();
    this.writeConfigFile({
      ...fileConfig,
      window: windowConfig,
    });
  }

  /**
   * ウィンドウ設定を取得
   */
  getWindowConfig(): WindowConfig {
    const fileConfig = this.readConfigFile();
    return fileConfig.window ?? DEFAULT_CONFIG.window!;
  }

  /**
   * 設定ファイルのパスを取得
   */
  getConfigPath(): string {
    return this.configPath;
  }
}

// シングルトンインスタンス
let configServiceInstance: ConfigService | null = null;

/**
 * ConfigServiceのシングルトンインスタンスを取得
 */
export function getConfigService(): ConfigService {
  if (!configServiceInstance) {
    configServiceInstance = new ConfigService();
  }
  return configServiceInstance;
}

/**
 * ConfigServiceインスタンスをリセット（テスト用）
 */
export function resetConfigService(): void {
  configServiceInstance = null;
}
