# AI PM Manager v2

Next generation AI Project Manager with Clean Architecture.

## Overview

AI PM Manager v2 is a complete rewrite of the AI PM framework, designed with clean architecture principles and modern best practices.

## Architecture

- **Frontend**: Electron + TypeScript + React
- **Backend**: Python (FastAPI/Flask)
- **CLI**: Python-based command-line interface
- **Integration**: Claude Code skills for AI-powered project management

## Project Structure

```
ai-pm-manager-v2/
├── src/              # Electron frontend (TypeScript)
├── backend/          # Python backend API
├── cli/              # CLI tools
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
