/**
 * ConfigService
 *
 * アプリケーション設定の永続化を担当するサービス
 *
 * V2パス設計（ORDER_002: DB一元化完了, ORDER_164: Squirrelルート展開, ORDER_001: userData移行）:
 * - backendPath: Pythonスクリプト（読み取り専用）
 *   - 開発時: リポジトリ/backend/
 *   - パッケージ時: Squirrelルート/backend/（resources/から展開済み）
 * - schemaPath: DBスキーマ（読み取り専用）
 *   - 開発時: リポジトリ/data/schema_v2.sql
 *   - パッケージ時: Squirrelルート/data/schema_v2.sql（展開済み）
 * - frameworkPath: バイナリリソース（読み取り専用: backend, schema, python-embed）
 *   - 開発時: リポジトリ/
 *   - パッケージ時: Squirrelルート（exeの1つ上）
 * - userDataPath: ユーザーデータ（読み書き: DB, PROJECTS）
 *   - 常に: app.getPath('userData') = %APPDATA%/ai-pm-manager-v2/
 * - dbPath: DB本体（読み書き）→ userDataPath/data/aipm.db
 * - PROJECTS: プロジェクトデータ → userDataPath/PROJECTS/
 * - configPath: UI設定（config.json）→ %APPDATA%/ai-pm-manager-v2/.aipm/（ユーザー固有）
 * - pythonPath: Python実行ファイル
 *   - 開発時: 'python'（システムPATH）
 *   - パッケージ時: Squirrelルート/python-embed/python.exe（展開済み）
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
 * V2パス設計（ORDER_002: DB一元化, ORDER_001: userData移行）:
 * - backendPath: 読み取り専用リソース（Pythonスクリプト）
 * - frameworkPath: バイナリリソース（backend, schema, python-embed）
 *   開発時=リポジトリルート、パッケージ時=Squirrelルート
 * - userDataPath: ユーザーデータ（DB, PROJECTS）= app.getPath('userData')
 * - configPath: UI設定（config.json）= %APPDATA%/ai-pm-manager-v2/.aipm/（ユーザー固有）
 */
export class ConfigService {
  private configPath: string;
  private _frameworkPath: string;
  private _backendPath: string;
  private _userDataPath: string;

  constructor() {
    // app.getPath('userData') = %APPDATA%/ai-pm-manager-v2/
    // DB・PROJECTSなどユーザーデータの永続的な保存先
    this._userDataPath = app.getPath('userData');

    // config.json はユーザー固有設定のため AppData に保存（変更なし）
    const aipmDir = path.join(this._userDataPath, '.aipm');
    this.configPath = path.join(aipmDir, 'config.json');

    if (app.isPackaged) {
      // パッケージ時: frameworkPath = Squirrelルート（app-X.X.X の親）
      // Squirrel構造: %LOCALAPPDATA%\ai_pm_manager_v2\app-1.0.0\exe
      // exeの1つ上 = Squirrelルート → data/, PROJECTS/ をここに配置
      // バージョン更新時もデータが引き継がれる
      // ORDER_164: deployResources()がresources/→Squirrelルートに展開済み
      this._frameworkPath = path.resolve(path.dirname(process.execPath), '..');
      // パッケージ時: backendPath = Squirrelルート/backend（展開済み）
      this._backendPath = path.join(this._frameworkPath, 'backend');
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
      // ORDER_164: Squirrelルート/data/schema_v2.sql（展開済み）を優先
      const deployedPath = path.join(this._frameworkPath, 'data', 'schema_v2.sql');
      if (fs.existsSync(deployedPath)) {
        return deployedPath;
      }
      // フォールバック: resources/data/配下
      const resourcePath = path.join(process.resourcesPath, 'data', 'schema_v2.sql');
      if (fs.existsSync(resourcePath)) {
        return resourcePath;
      }
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
   * ORDER_001: app.getPath('userData') 配下に移動。
   * Squirrelインストーラーの影響を受けない永続的な場所に配置する。
   * パス: %APPDATA%/ai-pm-manager-v2/data/aipm.db
   */
  getAipmDbPath(): string {
    return path.join(this._userDataPath, 'data', 'aipm.db');
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
   *
   * ORDER_001: app.getPath('userData') 配下に移動。
   * Squirrelインストーラーの影響を受けない永続的な場所に配置する。
   * パス: %APPDATA%/ai-pm-manager-v2/PROJECTS/
   */
  ensureProjectsDirectory(): void {
    const projectsDir = path.join(this._userDataPath, 'PROJECTS');
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

  /**
   * Pythonインタプリタのパスを取得
   *
   * - パッケージ時: Squirrelルート/python-embed/python.exe（展開済み）
   * - 開発時: 'python'（システムPATH上のPython）
   */
  getPythonPath(): string {
    if (app.isPackaged) {
      // ORDER_164: Squirrelルートに展開済みのpython-embedを参照
      return path.join(this._frameworkPath, 'python-embed', 'python.exe');
    }
    return process.platform === 'win32' ? 'python' : 'python3';
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
