"""
AI PM Framework - Worker Configuration

Defines configuration for parallel worker execution, including:
- Maximum concurrent workers
- Resource limits (CPU, memory)
- Timeout settings
- Retry policies
"""

from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import os


@dataclass
class WorkerResourceConfig:
    """Resource configuration for worker execution"""

    # Maximum number of concurrent workers
    max_concurrent_workers: int = 5

    # CPU usage threshold (0-100%)
    # If system CPU exceeds this, new workers won't be launched
    max_cpu_percent: float = 85.0

    # Memory usage threshold (0-100%)
    # If system memory exceeds this, new workers won't be launched
    max_memory_percent: float = 85.0

    # Worker timeout in seconds
    worker_timeout: int = 600

    # Task execution timeout in seconds (per task)
    task_timeout: int = 3600

    # Retry configuration
    max_retries: int = 2
    retry_delay_seconds: int = 60

    # Monitoring interval in seconds
    monitor_interval: int = 5

    # Enable resource monitoring
    enable_resource_monitoring: bool = True

    # Enable auto-scaling (reduce workers if resources constrained)
    enable_auto_scaling: bool = True

    # Minimum workers to maintain
    min_workers: int = 1

    def __post_init__(self):
        """Validate configuration values"""
        if self.max_concurrent_workers < 1:
            raise ValueError("max_concurrent_workers must be >= 1")

        if self.min_workers < 1:
            raise ValueError("min_workers must be >= 1")

        if self.min_workers > self.max_concurrent_workers:
            raise ValueError("min_workers cannot exceed max_concurrent_workers")

        if not (0 <= self.max_cpu_percent <= 100):
            raise ValueError("max_cpu_percent must be between 0 and 100")

        if not (0 <= self.max_memory_percent <= 100):
            raise ValueError("max_memory_percent must be between 0 and 100")

        if self.worker_timeout < 1:
            raise ValueError("worker_timeout must be >= 1")

        if self.task_timeout < 1:
            raise ValueError("task_timeout must be >= 1")

        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")


@dataclass
class WorkerPriorityConfig:
    """Priority-based worker scheduling configuration"""

    # Allow priority-based preemption
    enable_priority_preemption: bool = False

    # P0 tasks can preempt lower priority tasks
    allow_p0_preemption: bool = True

    # Maximum workers per priority level
    max_p0_workers: Optional[int] = None  # None = no limit
    max_p1_workers: Optional[int] = None
    max_p2_workers: Optional[int] = None
    max_p3_workers: Optional[int] = None

    def get_max_workers_for_priority(self, priority: str) -> Optional[int]:
        """
        Get maximum workers allowed for a given priority

        Args:
            priority: Priority level (P0, P1, P2, P3)

        Returns:
            Maximum workers for this priority, or None if no limit
        """
        priority_map = {
            "P0": self.max_p0_workers,
            "P1": self.max_p1_workers,
            "P2": self.max_p2_workers,
            "P3": self.max_p3_workers,
        }
        return priority_map.get(priority)


# Global default configuration
_default_worker_config: Optional[WorkerResourceConfig] = None
_default_priority_config: Optional[WorkerPriorityConfig] = None


def get_worker_config() -> WorkerResourceConfig:
    """
    Get current worker resource configuration

    Returns:
        WorkerResourceConfig: Current configuration
    """
    global _default_worker_config

    if _default_worker_config is None:
        _default_worker_config = WorkerResourceConfig()

    return _default_worker_config


def set_worker_config(config: WorkerResourceConfig) -> None:
    """
    Set worker resource configuration

    Args:
        config: New configuration
    """
    global _default_worker_config
    _default_worker_config = config


def get_priority_config() -> WorkerPriorityConfig:
    """
    Get current worker priority configuration

    Returns:
        WorkerPriorityConfig: Current configuration
    """
    global _default_priority_config

    if _default_priority_config is None:
        _default_priority_config = WorkerPriorityConfig()

    return _default_priority_config


def set_priority_config(config: WorkerPriorityConfig) -> None:
    """
    Set worker priority configuration

    Args:
        config: New configuration
    """
    global _default_priority_config
    _default_priority_config = config


def load_config_from_env() -> WorkerResourceConfig:
    """
    Load worker configuration from environment variables

    Environment variables:
        AIPM_MAX_WORKERS: Maximum concurrent workers
        AIPM_MAX_CPU_PERCENT: CPU threshold
        AIPM_MAX_MEMORY_PERCENT: Memory threshold
        AIPM_WORKER_TIMEOUT: Worker timeout in seconds
        AIPM_TASK_TIMEOUT: Task timeout in seconds
        AIPM_ENABLE_MONITORING: Enable resource monitoring (true/false)
        AIPM_ENABLE_AUTO_SCALING: Enable auto-scaling (true/false)

    Returns:
        WorkerResourceConfig: Configuration from environment
    """
    config = WorkerResourceConfig()

    # Load numeric values
    if os.getenv("AIPM_MAX_WORKERS"):
        config.max_concurrent_workers = int(os.getenv("AIPM_MAX_WORKERS"))

    if os.getenv("AIPM_MAX_CPU_PERCENT"):
        config.max_cpu_percent = float(os.getenv("AIPM_MAX_CPU_PERCENT"))

    if os.getenv("AIPM_MAX_MEMORY_PERCENT"):
        config.max_memory_percent = float(os.getenv("AIPM_MAX_MEMORY_PERCENT"))

    if os.getenv("AIPM_WORKER_TIMEOUT"):
        config.worker_timeout = int(os.getenv("AIPM_WORKER_TIMEOUT"))

    if os.getenv("AIPM_TASK_TIMEOUT"):
        config.task_timeout = int(os.getenv("AIPM_TASK_TIMEOUT"))

    # Load boolean values
    if os.getenv("AIPM_ENABLE_MONITORING"):
        config.enable_resource_monitoring = os.getenv("AIPM_ENABLE_MONITORING").lower() == "true"

    if os.getenv("AIPM_ENABLE_AUTO_SCALING"):
        config.enable_auto_scaling = os.getenv("AIPM_ENABLE_AUTO_SCALING").lower() == "true"

    return config


def get_recommended_max_workers() -> int:
    """
    Get recommended maximum concurrent workers based on system resources

    Returns:
        Recommended max workers (typically CPU cores - 1, min 1, max 10)
    """
    try:
        import psutil
        cpu_count = psutil.cpu_count(logical=False) or 4
        # Leave one core for system
        return min(max(cpu_count - 1, 1), 10)
    except ImportError:
        # Default to 5 if psutil not available
        return 5
