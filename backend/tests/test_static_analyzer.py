#!/usr/bin/env python3
"""
AI PM Framework - StaticAnalyzer / AutoFixer / Integration Tests

TASK_1040: static_analyzer, auto_fixer, execute_task integration tests.

Test targets:
    1. quality.static_analyzer.StaticAnalyzer, AnalysisIssue, AnalysisResult
    2. quality.auto_fixer.AutoFixer
    3. worker.execute_task._step_static_analysis (DB column check only)

All subprocess calls are mocked to avoid external tool dependencies.
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest import mock

import pytest

# Ensure the package root is on sys.path
_test_dir = Path(__file__).resolve().parent
_package_root = _test_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from quality.static_analyzer import (
    AnalysisIssue,
    AnalysisResult,
    StaticAnalyzer,
    TOOL_TIMEOUT_SECONDS,
)
from quality.auto_fixer import AutoFixer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with a dummy Python file."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    py_file = src_dir / "main.py"
    py_file.write_text("import os\nprint('hello')\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def analyzer(tmp_project):
    """Create a StaticAnalyzer instance rooted at tmp_project."""
    return StaticAnalyzer(str(tmp_project))


@pytest.fixture
def fixer(tmp_project):
    """Create an AutoFixer instance rooted at tmp_project."""
    return AutoFixer(str(tmp_project))


# ===================================================================
# StaticAnalyzer Tests
# ===================================================================

class TestDetectTools:
    """detect_tools() returns a dict of tool name -> bool."""

    def test_detect_tools_returns_dict(self, analyzer):
        """detect_tools() must return a dict with exactly 4 bool-valued keys."""
        with mock.patch.object(analyzer, "_command_exists", return_value=False), \
             mock.patch.object(analyzer, "_npx_available", return_value=False):
            result = analyzer.detect_tools()

        assert isinstance(result, dict)
        expected_keys = {"ruff", "mypy", "tsc", "eslint"}
        assert set(result.keys()) == expected_keys
        for key, value in result.items():
            assert isinstance(value, bool), (
                f"detect_tools()['{key}'] should be bool, got {type(value).__name__}"
            )


class TestAnalyzeEmptyAndNone:
    """analyze() edge cases for empty / None file lists."""

    def test_analyze_empty_files(self, analyzer):
        """Empty file list should return score=100 with no errors/warnings."""
        result = analyzer.analyze([])
        assert result["score"] == 100
        assert result["errors"] == []
        assert result["warnings"] == []
        assert result["tools_used"] == []

    def test_analyze_none_files(self, analyzer):
        """None should be treated as empty list (BUG_001 mitigation test)."""
        result = analyzer.analyze(None)
        assert result["score"] == 100
        assert result["errors"] == []
        assert result["warnings"] == []


class TestScoreCalculation:
    """_calculate_score() logic: error=-10, warning=-2, min=0."""

    @pytest.mark.parametrize(
        "errors, warnings, expected",
        [
            (0, 0, 100),
            (1, 0, 90),
            (0, 1, 98),
            (2, 3, 74),      # 100 - 20 - 6 = 74
            (10, 0, 0),      # 100 - 100 = 0
            (5, 30, 0),      # 100 - 50 - 60 = -10 -> clamped to 0
            (100, 100, 0),   # large counts -> clamped to 0
        ],
    )
    def test_score_calculation(self, errors, warnings, expected):
        score = StaticAnalyzer._calculate_score(errors, warnings)
        assert score == expected


class TestRuffCheckParse:
    """_run_ruff_check() parses ruff JSON output correctly (mocked subprocess)."""

    def test_ruff_check_parse(self, analyzer):
        """Ruff JSON output should be parsed into AnalysisIssue objects."""
        ruff_json = json.dumps([
            {
                "code": "F401",
                "message": "os imported but unused",
                "filename": "src/main.py",
                "location": {"row": 1, "column": 1},
            },
            {
                "code": "W291",
                "message": "trailing whitespace",
                "filename": "src/main.py",
                "location": {"row": 2, "column": 10},
            },
        ])

        fake_proc = subprocess.CompletedProcess(
            args=["ruff", "check", "--output-format", "json", "src/main.py"],
            returncode=1,
            stdout=ruff_json,
            stderr="",
        )

        with mock.patch.object(analyzer, "_run_subprocess", return_value=fake_proc):
            issues = analyzer._run_ruff_check(["src/main.py"])

        assert len(issues) == 2

        # First issue: F401 -> severity "error"
        assert issues[0].file == "src/main.py"
        assert issues[0].line == 1
        assert issues[0].col == 1
        assert issues[0].tool == "ruff"
        assert issues[0].severity == "error"
        assert "F401" in issues[0].message

        # Second issue: W291 -> severity "warning"
        assert issues[1].severity == "warning"
        assert "W291" in issues[1].message


class TestMypyParse:
    """_run_mypy() parses mypy text output correctly (mocked subprocess)."""

    def test_mypy_parse(self, analyzer):
        """Mypy text output should be parsed into AnalysisIssue objects."""
        mypy_output = textwrap.dedent("""\
            src/main.py:10:5: error: Incompatible types in assignment
            src/main.py:20:1: warning: Missing return type
            src/main.py:30:1: note: This is just a note
        """)

        fake_proc = subprocess.CompletedProcess(
            args=["mypy", "src/main.py"],
            returncode=1,
            stdout=mypy_output,
            stderr="",
        )

        with mock.patch.object(analyzer, "_run_subprocess", return_value=fake_proc):
            issues = analyzer._run_mypy(["src/main.py"])

        # "note" lines should be ignored
        assert len(issues) == 2

        assert issues[0].file == "src/main.py"
        assert issues[0].line == 10
        assert issues[0].col == 5
        assert issues[0].tool == "mypy"
        assert issues[0].severity == "error"
        assert "Incompatible types" in issues[0].message

        assert issues[1].severity == "warning"
        assert issues[1].line == 20


class TestToolTimeout:
    """_run_subprocess() should raise RuntimeError on timeout."""

    def test_tool_timeout(self, analyzer):
        """When subprocess.TimeoutExpired is raised, RuntimeError must follow."""
        with mock.patch(
            "quality.static_analyzer.subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["ruff", "check"], timeout=TOOL_TIMEOUT_SECONDS
            ),
        ):
            with pytest.raises(RuntimeError, match="timed out"):
                analyzer._run_subprocess(["ruff", "check", "src/main.py"])


# ===================================================================
# AutoFixer Tests
# ===================================================================

class TestAutoFixerEmptyAndNone:
    """fix() edge cases for empty / None file lists."""

    def test_fix_empty_files(self, fixer):
        """Empty file list should return empty result dict."""
        result = fixer.fix([])
        assert result["fixed_count"] == 0
        assert result["fixed_files"] == []
        assert result["fixes"] == []
        assert result["failed"] == []

    def test_fix_none_files(self, fixer):
        """None should be treated as empty list (BUG_001 mitigation test)."""
        result = fixer.fix(None)
        assert result["fixed_count"] == 0
        assert result["fixed_files"] == []
        assert result["fixes"] == []
        assert result["failed"] == []


class TestCaptureDiff:
    """_capture_diff() generates unified diff."""

    def test_capture_diff(self, fixer):
        """Unified diff should contain expected markers."""
        before = "line1\nline2\nline3\n"
        after = "line1\nline2_modified\nline3\n"

        diff = fixer._capture_diff("test.py", before, after)

        assert "--- a/test.py" in diff
        assert "+++ b/test.py" in diff
        assert "-line2" in diff
        assert "+line2_modified" in diff


class TestResolvePath:
    """_resolve_path() resolves relative and absolute paths."""

    def test_resolve_path_relative(self, fixer):
        """Relative paths should be resolved against project_root."""
        result = fixer._resolve_path("src/main.py")
        expected = fixer.project_root / "src" / "main.py"
        assert result == expected

    def test_resolve_path_absolute(self, fixer, tmp_project):
        """Absolute paths should be returned as-is."""
        abs_path = str(tmp_project / "src" / "main.py")
        result = fixer._resolve_path(abs_path)
        assert result == Path(abs_path)


# ===================================================================
# Integration Test: DB Column Check
# ===================================================================

class TestDBColumnExists:
    """Verify that the tasks table has the static_analysis_score column."""

    def test_db_column_exists(self):
        """tasks table must have static_analysis_score column in the real DB."""
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "aipm.db"
        if not db_path.exists():
            pytest.skip(f"DB not found at {db_path}")

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "static_analysis_score" in columns, (
                f"Column 'static_analysis_score' not found in tasks table. "
                f"Existing columns: {sorted(columns)}"
            )
        finally:
            conn.close()
