/**
 * DirectorySelector Component
 *
 * AI PM Frameworkのディレクトリを選択し、妥当性を検証するUIコンポーネント
 * FR-003: 設定永続化対応（保存・復元機能追加）
 */

import React, { useState, useCallback, useEffect } from 'react';

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
 * ディレクトリ選択結果
 */
interface DirectorySelectionResult {
  canceled: boolean;
  filePaths: string[];
  validation?: DirectoryValidationResult;
}

/**
 * コンポーネントのProps
 */
interface DirectorySelectorProps {
  /** 選択完了時のコールバック */
  onSelect?: (result: DirectorySelectionResult) => void;
  /** 設定保存完了時のコールバック */
  onSave?: (path: string) => void;
  /** 現在選択されているパス（制御コンポーネント用） */
  selectedPath?: string;
  /** 起動時に保存された設定を自動復元するか */
  autoRestore?: boolean;
  /** クラス名の追加 */
  className?: string;
}

/**
 * 検証ステータス表示用のバッジ
 */
const StatusBadge: React.FC<{ isValid: boolean }> = ({ isValid }) => (
  <span
    className={`inline-flex items-center px-2 py-1 text-xs font-medium rounded-full ${
      isValid
        ? 'bg-green-100 text-green-800'
        : 'bg-red-100 text-red-800'
    }`}
  >
    {isValid ? '有効' : '無効'}
  </span>
);

/**
 * 保存済みバッジ
 */
const SavedBadge: React.FC = () => (
  <span className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-800">
    保存済み
  </span>
);

/**
 * エラー/警告メッセージ表示
 */
const MessageList: React.FC<{
  messages: string[];
  type: 'error' | 'warning' | 'success';
}> = ({ messages, type }) => {
  if (messages.length === 0) return null;

  const styles = {
    error: 'bg-red-50 border-red-200 text-red-700',
    warning: 'bg-yellow-50 border-yellow-200 text-yellow-700',
    success: 'bg-green-50 border-green-200 text-green-700',
  }[type];

  const icon = {
    error: (
      <svg className="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20">
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
          clipRule="evenodd"
        />
      </svg>
    ),
    warning: (
      <svg className="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20">
        <path
          fillRule="evenodd"
          d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
          clipRule="evenodd"
        />
      </svg>
    ),
    success: (
      <svg className="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20">
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
          clipRule="evenodd"
        />
      </svg>
    ),
  }[type];

  return (
    <div className={`mt-2 p-3 border rounded-md ${styles}`}>
      <ul className="space-y-1">
        {messages.map((msg, idx) => (
          <li key={idx} className="flex items-center text-sm">
            {icon}
            {msg}
          </li>
        ))}
      </ul>
    </div>
  );
};

/**
 * プロジェクト詳細表示
 */
const ProjectDetails: React.FC<{
  details: DirectoryValidationResult['details'];
}> = ({ details }) => (
  <div className="mt-3 p-3 bg-gray-50 rounded-md">
    <h4 className="text-sm font-medium text-gray-700 mb-2">検証詳細</h4>
    <div className="grid grid-cols-2 gap-2 text-sm">
      <div className="flex items-center">
        <span
          className={`w-2 h-2 rounded-full mr-2 ${
            details.hasProjectsDir ? 'bg-green-500' : 'bg-red-500'
          }`}
        />
        <span className="text-gray-600">PROJECTS/ ディレクトリ</span>
      </div>
      <div className="flex items-center">
        <span
          className={`w-2 h-2 rounded-full mr-2 ${
            details.hasReadme ? 'bg-green-500' : 'bg-gray-400'
          }`}
        />
        <span className="text-gray-600">README.md</span>
      </div>
    </div>
    {details.projectCount > 0 && (
      <div className="mt-2">
        <span className="text-sm text-gray-600">
          プロジェクト数: {details.projectCount}
        </span>
        <div className="mt-1 flex flex-wrap gap-1">
          {details.projectNames.slice(0, 5).map((name) => (
            <span
              key={name}
              className="px-2 py-0.5 text-xs bg-blue-100 text-blue-800 rounded"
            >
              {name}
            </span>
          ))}
          {details.projectNames.length > 5 && (
            <span className="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded">
              +{details.projectNames.length - 5} more
            </span>
          )}
        </div>
      </div>
    )}
  </div>
);

/**
 * DirectorySelector コンポーネント
 */
export const DirectorySelector: React.FC<DirectorySelectorProps> = ({
  onSelect,
  onSave,
  selectedPath: controlledPath,
  autoRestore = true,
  className = '',
}) => {
  const [internalPath, setInternalPath] = useState<string>('');
  const [validation, setValidation] = useState<DirectoryValidationResult | null>(
    null
  );
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [isRestoring, setIsRestoring] = useState(false);

  // 制御/非制御コンポーネントの切り替え
  const currentPath = controlledPath ?? internalPath;

  /**
   * 起動時に保存された設定を復元
   */
  useEffect(() => {
    if (!autoRestore || !window.electronAPI) return;

    const restoreConfig = async () => {
      setIsRestoring(true);
      try {
        const activePath = await window.electronAPI.getActiveFrameworkPath();
        if (activePath) {
          // パスを検証
          const validationResult = await window.electronAPI.validateDirectory(activePath);
          if (validationResult.isValid) {
            if (!controlledPath) {
              setInternalPath(activePath);
            }
            setValidation(validationResult);
            setIsSaved(true);
            console.log('[DirectorySelector] Restored config:', activePath);
          }
        }
      } catch (error) {
        console.error('[DirectorySelector] Failed to restore config:', error);
      } finally {
        setIsRestoring(false);
      }
    };

    restoreConfig();
  }, [autoRestore, controlledPath]);

  /**
   * ディレクトリ選択ダイアログを開く
   */
  const handleSelectDirectory = useCallback(async () => {
    if (!window.electronAPI) {
      console.error('[DirectorySelector] electronAPI is not available');
      return;
    }

    setIsLoading(true);
    setSaveMessage(null);

    try {
      const result = await window.electronAPI.selectDirectory();

      if (!result.canceled && result.validation) {
        if (!controlledPath) {
          setInternalPath(result.filePaths[0]);
        }
        setValidation(result.validation);
        setIsSaved(false); // 新しい選択なので保存済みフラグをリセット
        onSelect?.(result);
      }
    } catch (error) {
      console.error('[DirectorySelector] Failed to select directory:', error);
    } finally {
      setIsLoading(false);
    }
  }, [controlledPath, onSelect]);

  /**
   * 設定を保存
   */
  const handleSave = useCallback(async () => {
    if (!window.electronAPI || !currentPath || !validation?.isValid) {
      return;
    }

    setIsSaving(true);
    setSaveMessage(null);

    try {
      // V2: frameworkPathは固定値のため保存不要。window設定のみ保存。
      const result = await window.electronAPI.saveConfig({});

      if (result.success) {
        setIsSaved(true);
        setSaveMessage('設定を保存しました');
        onSave?.(currentPath);
        // 成功メッセージを3秒後に消す
        setTimeout(() => setSaveMessage(null), 3000);
      } else {
        setSaveMessage(`保存に失敗しました: ${result.error}`);
      }
    } catch (error) {
      console.error('[DirectorySelector] Failed to save config:', error);
      setSaveMessage('保存中にエラーが発生しました');
    } finally {
      setIsSaving(false);
    }
  }, [currentPath, validation, onSave]);

  /**
   * パスをクリア
   */
  const handleClear = useCallback(() => {
    if (!controlledPath) {
      setInternalPath('');
    }
    setValidation(null);
    setIsSaved(false);
    setSaveMessage(null);
    onSelect?.({
      canceled: true,
      filePaths: [],
    });
  }, [controlledPath, onSelect]);

  // 復元中の表示
  if (isRestoring) {
    return (
      <div className={`w-full ${className}`}>
        <div className="flex items-center gap-2 text-gray-600">
          <svg
            className="animate-spin h-5 w-5"
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
          <span className="text-sm">設定を復元中...</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`w-full ${className}`}>
      {/* 選択ボタンとパス表示 */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSelectDirectory}
          disabled={isLoading}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading ? (
            <span className="flex items-center">
              <svg
                className="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
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
              選択中...
            </span>
          ) : (
            'フォルダを選択'
          )}
        </button>

        {/* 保存ボタン（有効なパスが選択されている場合のみ表示） */}
        {currentPath && validation?.isValid && !isSaved && (
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isSaving ? (
              <span className="flex items-center">
                <svg
                  className="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
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
                保存中...
              </span>
            ) : (
              '設定を保存'
            )}
          </button>
        )}

        {currentPath && (
          <button
            onClick={handleClear}
            className="p-2 text-gray-400 hover:text-gray-600 focus:outline-none"
            title="クリア"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        )}
      </div>

      {/* 保存メッセージ */}
      {saveMessage && (
        <MessageList
          messages={[saveMessage]}
          type={saveMessage.includes('失敗') || saveMessage.includes('エラー') ? 'error' : 'success'}
        />
      )}

      {/* 選択されたパスの表示 */}
      {currentPath && (
        <div className="mt-3">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">
              選択されたパス
            </label>
            <div className="flex items-center gap-2">
              {isSaved && <SavedBadge />}
              {validation && <StatusBadge isValid={validation.isValid} />}
            </div>
          </div>
          <div className="mt-1 p-2 bg-gray-100 rounded-md font-mono text-sm text-gray-800 break-all">
            {currentPath}
          </div>
        </div>
      )}

      {/* 検証結果の表示 */}
      {validation && (
        <>
          <MessageList messages={validation.errors} type="error" />
          <MessageList messages={validation.warnings} type="warning" />
          {validation.isValid && <ProjectDetails details={validation.details} />}
        </>
      )}
    </div>
  );
};

export default DirectorySelector;
