import React from 'react';

interface HeaderProps {}

export const Header: React.FC<HeaderProps> = () => {
  return (
    <header className="h-12 bg-white border-b border-gray-200 flex items-center justify-between px-4 shadow-sm">
      <h1 className="text-lg font-semibold text-gray-800">AI PM Manager</h1>
      <div className="flex items-center gap-1">
        <button
          onClick={() => window.electronAPI?.openTerminal()}
          className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-md transition-colors"
          aria-label="Open Terminal"
          title="ターミナルを開く"
        >
          <svg
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
        </button>
      </div>
    </header>
  );
};
