const path = require('path');
const { FuseV1Options, FuseVersion } = require('@electron/fuses');

module.exports = {
  packagerConfig: {
    asar: {
      // ネイティブモジュール（.node）とその依存関係をasarから除外
      unpack: '{**/node_modules/better-sqlite3/**/*,**/*.node}',
    },
    // PythonバックエンドとスキーマファイルをextraResourceとして同梱
    // ORDER_157: framework/dataディレクトリごと同梱（schema_v2.sqlのみ含む）
    // ORDER_159: backendは読み取り専用、framework/dataはスキーマ配布用
    // ORDER_164: python-embed, .claude/, CLAUDE.md追加（起動時Squirrelルートに展開）
    // パッケージ後: resources/{backend,python-embed,.claude,CLAUDE.md,data/schema_v2.sql}
    extraResource: [
      path.join(__dirname, 'backend'),
      path.join(__dirname, 'framework', 'data'),
      path.join(__dirname, 'python-embed'),
      path.join(__dirname, '.claude'),
      path.join(__dirname, 'CLAUDE.md'),
    ],
    // 無視パターンからnode_modules/better-sqlite3とchokidarを除外
    ignore: (file) => {
      // .webpackディレクトリは含める
      if (file.startsWith('/.webpack')) return false;
      // package.jsonは含める
      if (file === '/package.json') return false;
      // better-sqlite3は含める（リビルド済みバイナリ使用）
      if (file.includes('/node_modules/better-sqlite3')) return false;
      // bindingsも含める
      if (file.includes('/node_modules/bindings')) return false;
      if (file.includes('/node_modules/file-uri-to-path')) return false;
      // chokidarとその依存モジュールを含める
      if (file.includes('/node_modules/chokidar')) return false;
      if (file.includes('/node_modules/readdirp')) return false;
      if (file.includes('/node_modules/picomatch')) return false;
      if (file.includes('/node_modules/braces')) return false;
      if (file.includes('/node_modules/fill-range')) return false;
      if (file.includes('/node_modules/to-regex-range')) return false;
      if (file.includes('/node_modules/is-number')) return false;
      if (file.includes('/node_modules/normalize-path')) return false;
      if (file.includes('/node_modules/anymatch')) return false;
      if (file.includes('/node_modules/is-glob')) return false;
      if (file.includes('/node_modules/is-extglob')) return false;
      if (file.includes('/node_modules/glob-parent')) return false;
      if (file.includes('/node_modules/is-binary-path')) return false;
      if (file.includes('/node_modules/binary-extensions')) return false;
      // その他のnode_modulesは除外
      if (file.includes('/node_modules/')) return true;
      // srcは除外
      if (file.startsWith('/src')) return true;
      // 設定ファイルは除外
      if (file.endsWith('.config.ts') || file.endsWith('.config.js')) return true;
      if (file.endsWith('.config.mts')) return true;
      if (file === '/tsconfig.json') return true;
      if (file === '/index.html') return true;
      if (file.startsWith('/.')) return true;
      return false;
    },
  },
  rebuildConfig: {
    // パッケージ時のリビルドをスキップ（事前リビルド済みを使用）
    onlyModules: [],
  },
  makers: [
    {
      name: '@electron-forge/maker-squirrel',
      config: {
        name: 'ai_pm_manager_v2',
      },
    },
    {
      name: '@electron-forge/maker-zip',
      platforms: ['darwin', 'linux', 'win32'],
    },
  ],
  plugins: [
    {
      name: '@electron-forge/plugin-auto-unpack-natives',
      config: {},
    },
    {
      name: '@electron-forge/plugin-webpack',
      config: {
        mainConfig: './webpack.main.config.js',
        renderer: {
          config: './webpack.renderer.config.js',
          entryPoints: [
            {
              html: './src/index.html',
              js: './src/renderer.tsx',
              name: 'main_window',
              preload: {
                js: './src/preload.ts',
              },
            },
          ],
        },
      },
    },
    {
      name: '@electron-forge/plugin-fuses',
      config: {
        version: FuseVersion.V1,
        [FuseV1Options.RunAsNode]: false,
        [FuseV1Options.EnableCookieEncryption]: true,
        [FuseV1Options.EnableNodeOptionsEnvironmentVariable]: false,
        [FuseV1Options.EnableNodeCliInspectArguments]: false,
        [FuseV1Options.EnableEmbeddedAsarIntegrityValidation]: true,
        [FuseV1Options.OnlyLoadAppFromAsar]: false,
      },
    },
  ],
};
