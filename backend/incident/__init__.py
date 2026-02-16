"""
AI PM Framework - Incident Analysis Module

Provides incident pattern analysis and reporting capabilities.
"""

from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from .analyze_patterns import IncidentPatternAnalyzer
from .generate_report import IncidentReportGenerator

__all__ = [
    'IncidentPatternAnalyzer',
    'IncidentReportGenerator'
]
