/**
 * ConfigService
 *
 * アプリケーション設定の永続化を担当するサービス
 *
 * V2パス設計（ORDER_002: DB一元化完了）:
 * - backendPath: Pythonスクリプト（読み取り専用）
 *   - 開発時: リポジトリ/backend/
 *   - パッケージ時: resources/backend/
 * - schemaPath: DBスキーマ（読み取り専用）
 *   - 開発時: リポジトリ/data/schema_v2.sql
 *   - パッケージ時: resources/data/schema_v2.sql
 * - frameworkPath: PROJECTS配下・DB（読み書き）
 *   - 開発時: リポジトリ/
 *   - パッケージ時: exe実行ディレクトリ（= exeと同階層にdata/, PROJECTS/を配置）
 * - dbPath: DB本体（読み書き）→ 常にframeworkPath/data/aipm.db
 * - configPath: UI設定（config.json）→ %APPDATA%/.aipm/（ユーザー固有）
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
 * V2パス設計（ORDER_002: DB一元化）:
 * - backendPath: 読み取り専用リソース（Pythonスクリプト）
 * - frameworkPath: 読み書き用（PROJECTS、data/aipm.db）
 *   開発時=リポジトリルート、パッケージ時=exe実行ディレクトリ
 * - configPath: UI設定（config.json）= %APPDATA%/.aipm/（ユーザー固有）
 */
export class ConfigService {
  private configPath: string;
  private _frameworkPath: string;
  private _backendPath: string;

  constructor() {
    // config.json はユーザー固有設定のため AppData に保存（変更なし）
    const userDataPath = app.getPath('userData');
    const aipmDir = path.join(userDataPath, '.aipm');
    this.configPath = path.join(aipmDir, 'config.json');

    if (app.isPackaged) {
      // パッケージ時: frameworkPath = exe実行ディレクトリ
      // data/aipm.db, PROJECTS/ はexeと同じフォルダに配置する想定
      this._frameworkPath = path.dirname(process.execPath);
      // パッケージ時: backendPath = resources/backend (読み取り専用)
      this._backendPath = path.join(process.resourcesPath, 'backend');
    } else {
      // 開発時: frameworkPath = リポジトリルート
      this._frameworkPath = app.getAppPath();
      // 開発時: backendPath = リポジトリ/backend
      this._backendPath = path.join(app.getAppPath(), 'backend');
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
   * フレームワークパスを取得（読み書き用）
   *
   * PROJECTS配下やDB等の読み書きが必要なデータのルートパス。
   * - 開発時: リポジトリルート
   * - パッケージ時: exe実行ディレクトリ
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
   * バックエンドパスを取得（読み取り専用）
   *
   * Pythonスクリプト（pm/, worker/, review/等）のルートパス。
   * - 開発時: リポジトリ/backend/
   * - パッケージ時: resources/backend/
   */
  getBackendPath(): string {
    return this._backendPath;
  }

  /**
   * スキーマファイルのパスを取得（読み取り専用）
   *
   * - 開発時: リポジトリ/data/schema_v2.sql（優先）またはframework/data/schema_v2.sql
   * - パッケージ時: resources/data/schema_v2.sql
   */
  getSchemaPath(): string {
    if (app.isPackaged) {
      const primaryPath = path.join(process.resourcesPath, 'data', 'schema_v2.sql');
      if (fs.existsSync(primaryPath)) {
        return primaryPath;
      }
      // フォールバック: framework/data/配下
      return path.join(process.resourcesPath, 'framework', 'data', 'schema_v2.sql');
    } else {
      // 開発時: data/（優先）→ framework/data/（フォールバック）
      const primaryPath = path.join(app.getAppPath(), 'data', 'schema_v2.sql');
      if (fs.existsSync(primaryPath)) {
        return primaryPath;
      }
      return path.join(app.getAppPath(), 'framework', 'data', 'schema_v2.sql');
    }
  }

  /**
   * AI PM Framework DB（aipm.db）のパスを取得（読み書き用）
   *
   * ORDER_002: 開発時・パッケージ時ともに frameworkPath/data/aipm.db を返す。
   * AppData DBは完全廃止。
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
