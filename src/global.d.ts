// ElectronAPI type declarations for renderer process
// These augment the Window interface so that window.electronAPI is typed correctly
// The actual implementation is in src/preload.ts
import type { ElectronAPI } from './preload';

declare global {
  // Webpack DefinePlugin variables for Electron Forge
  const MAIN_WINDOW_WEBPACK_ENTRY: string;
  const MAIN_WINDOW_PRELOAD_WEBPACK_ENTRY: string;

  interface Window {
    electronAPI: ElectronAPI;
  }
}
