"""
AI PM Framework - Fault Detection Module

Provides automatic fault detection capabilities for the self-healing pipeline.
"""

from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from .detector import (
    FaultDetector,
    FaultType,
    FaultReport,
    detect_all_faults,
    detect_stuck_tasks,
    detect_invalid_transitions,
    detect_subagent_crashes,
    detect_file_write_failures
)

__all__ = [
    'FaultDetector',
    'FaultType',
    'FaultReport',
    'detect_all_faults',
    'detect_stuck_tasks',
    'detect_invalid_transitions',
    'detect_subagent_crashes',
    'detect_file_write_failures'
]
