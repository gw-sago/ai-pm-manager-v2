// Global type declarations for Webpack DefinePlugin variables
declare const MAIN_WINDOW_WEBPACK_ENTRY: string;
declare const MAIN_WINDOW_PRELOAD_WEBPACK_ENTRY: string;

// ElectronAPI type declarations for renderer process
// These augment the Window interface so that window.electronAPI is typed correctly
// The actual implementation is in src/preload.ts
import type { ElectronAPI } from './preload';

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}
