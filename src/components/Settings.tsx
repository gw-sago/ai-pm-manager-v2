/**
 * Settings Component
 *
 * 設定画面（フレームワークパス管理機能）
 * TASK_035: サイドバー「設定」クリック時に表示
 */

import React, { useState, useCallback, useEffect } from 'react';

interface SettingsProps {
  /** 設定画面を閉じるコールバック */
  onClose?: () => void;
  /** パス変更時のコールバック（プロジェクト一覧再読み込み用） */
  onPathChange?: (newPath: string) => void;
}

/**
 * ディレクトリ検証結果
 */
interface DirectoryValidationResult {
  isValid: boolean;
  path: string;
  errors: string[];
  warnings: string[];
  details: {
    hasProjectsDir: boolean;
    hasReadme: boolean;
    projectCount: number;
    projectNames: string[];
  };
}

/**
 * 戻るアイコン
 */
const BackIcon: React.FC = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
  </svg>
);

/**
 * フォルダアイコン
 */
const FolderIcon: React.FC = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
    />
  </svg>
);

/**
 * チェックアイコン
 */
const CheckIcon: React.FC = () => (
  <svg className="w-5 h-5 text-green-500" fill="currentColor" viewBox="0 0 20 20">
    <path
      fillRule="evenodd"
      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
      clipRule="evenodd"
    />
  </svg>
);

/**
 * Settings コンポーネント
 */
export const Settings: React.FC<SettingsProps> = ({ onClose, onPathChange }) => {
  const [currentPath, setCurrentPath] = useState<string | null>(null);
  const [validation, setValidation] = useState<DirectoryValidationResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  /**
   * 起動時に現在の設定を読み込む
   */
  useEffect(() => {
    const loadCurrentPath = async () => {
      try {
        const activePath = await window.electronAPI.getActiveFrameworkPath();
        if (activePath) {
          setCurrentPath(activePath);
          const validationResult = await window.electronAPI.validateDirectory(activePath);
          setValidation(validationResult);
        }
      } catch (error) {
        console.error('[Settings] Failed to load current path:', error);
      }
    };

    loadCurrentPath();
  }, []);

  /**
   * フォルダ選択ダイアログを開く
   */
  const handleSelectFolder = useCallback(async () => {
    if (!window.electronAPI) {
      console.error('[Settings] electronAPI is not available');
      return;
    }

    setIsLoading(true);
    setMessage(null);

    try {
      const result = await window.electronAPI.selectDirectory();

      if (!result.canceled && result.validation) {
        const newPath = result.filePaths[0];
        setValidation(result.validation);

        if (result.validation.isValid) {
          // 有効なパスの場合、自動保存
          setIsSaving(true);
          // V2: frameworkPathは固定値のため保存不要。window設定のみ保存。
          const saveResult = await window.electronAPI.saveConfig({});

          if (saveResult.success) {
            setCurrentPath(newPath);
            setMessage({ type: 'success', text: '設定を保存しました' });

            // ファイル監視を再開始
            await window.electronAPI.stopWatcher();
            await window.electronAPI.startWatcher(newPath);

            // 親コンポーネントに通知
            onPathChange?.(newPath);
          } else {
            setMessage({ type: 'error', text: `保存に失敗しました: ${saveResult.error}` });
          }
          setIsSaving(false);
        } else {
          setMessage({ type: 'error', text: 'このフォルダはAI PM Frameworkのルートディレクトリではありません' });
        }
      }
    } catch (error) {
      console.error('[Settings] Failed to select directory:', error);
      setMessage({ type: 'error', text: '予期せぬエラーが発生しました' });
    } finally {
      setIsLoading(false);
    }
  }, [onPathChange]);

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 h-full">
      {/* ヘッダー */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
        <div className="flex items-center gap-3">
          {onClose && (
            <button
              onClick={onClose}
              className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors"
              title="戻る"
            >
              <BackIcon />
            </button>
          )}
          <h2 className="text-lg font-semibold text-gray-900">設定</h2>
        </div>
      </div>

      {/* コンテンツ */}
      <div className="p-6">
        {/* フレームワークパス管理セクション */}
        <section>
          <h3 className="text-sm font-medium text-gray-700 mb-4">フレームワーク設定</h3>

          {/* 現在のパス表示 */}
          <div className="bg-gray-50 rounded-lg p-4 mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                現在のパス
              </span>
              {validation?.isValid && <CheckIcon />}
            </div>
            {currentPath ? (
              <div className="font-mono text-sm text-gray-800 break-all">
                {currentPath}
              </div>
            ) : (
              <div className="text-sm text-gray-400 italic">
                未設定
              </div>
            )}
          </div>

          {/* 検証詳細（パスが設定されている場合） */}
          {validation && currentPath && (
            <div className="mb-4">
              <div className="grid grid-cols-2 gap-2 text-sm text-gray-600">
                <div className="flex items-center">
                  <span
                    className={`w-2 h-2 rounded-full mr-2 ${
                      validation.details.hasProjectsDir ? 'bg-green-500' : 'bg-red-500'
                    }`}
                  />
                  PROJECTS/ ディレクトリ
                </div>
                <div className="flex items-center">
                  <span
                    className={`w-2 h-2 rounded-full mr-2 ${
                      validation.details.hasReadme ? 'bg-green-500' : 'bg-gray-400'
                    }`}
                  />
                  README.md
                </div>
              </div>
              {validation.details.projectCount > 0 && (
                <div className="mt-2 text-sm text-gray-600">
                  プロジェクト数: {validation.details.projectCount}
                </div>
              )}
            </div>
          )}

          {/* メッセージ表示 */}
          {message && (
            <div
              className={`mb-4 p-3 rounded-md text-sm ${
                message.type === 'success'
                  ? 'bg-green-50 text-green-700 border border-green-200'
                  : 'bg-red-50 text-red-700 border border-red-200'
              }`}
            >
              {message.text}
            </div>
          )}

          {/* 変更ボタン */}
          <button
            onClick={handleSelectFolder}
            disabled={isLoading || isSaving}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading || isSaving ? (
              <>
                <svg
                  className="animate-spin h-4 w-4 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                {isSaving ? '保存中...' : '選択中...'}
              </>
            ) : (
              <>
                <FolderIcon />
                フォルダを変更
              </>
            )}
          </button>

          {/* ヘルプテキスト */}
          <p className="mt-3 text-xs text-gray-500">
            AI PM Frameworkのルートディレクトリ（PROJECTS/フォルダを含むディレクトリ）を選択してください。
          </p>
        </section>
      </div>
    </div>
  );
};

export default Settings;
