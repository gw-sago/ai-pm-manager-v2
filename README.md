# AI PM Manager v2

Next generation AI Project Manager with Clean Architecture.

## Overview

AI PM Manager v2 is a complete rewrite of the AI PM framework, designed with clean architecture principles and modern best practices.

## Architecture

- **Frontend**: Electron + TypeScript + React
- **Backend**: Python (FastAPI/Flask)
- **CLI**: Python-based command-line interface
- **Integration**: Claude Code skills for AI-powered project management

## Features

### Project Information Management

V2 includes comprehensive project metadata management:

- **UI Component**: `ProjectInfo.tsx` - Display and edit project description, purpose, and tech stack
- **Database**: `projects` table with `description`, `purpose`, `tech_stack` columns
- **IPC API**: `getProjectInfo` / `updateProjectInfo` for seamless frontend-backend communication
- **Migration Tool**: `scripts/migrate_project_info.py` - Import project info from legacy AI PM repositories

Example usage:

```bash
# Migrate project info from legacy repository
python scripts/migrate_project_info.py ai_pm_manager D:/your_workspace/AI_PM/PROJECTS/ai_pm_manager/PROJECT_INFO.md

# Migrate all projects
python scripts/migrate_all_projects.py
```

## Project Structure

```
ai-pm-manager-v2/
├── src/              # Electron frontend (TypeScript)
│   └── components/   # React components (ProjectInfo, etc.)
├── backend/          # Python backend API
├── cli/              # CLI tools
├── scripts/          # Migration and utility scripts
├── data/             # Data storage (SQLite, configs)
├── templates/        # Project templates
└── .claude/          # Claude Code skill definitions
```

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.11+
- Git

### Installation

```bash
# Install frontend dependencies
npm install

# Install backend dependencies
pip install -r requirements.txt
```

### Development

```bash
# Run Electron app
npm run dev

# Run backend server
python backend/main.py
```

## License

MIT
