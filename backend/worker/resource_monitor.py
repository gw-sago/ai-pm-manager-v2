"""
AI PM Framework - Resource Monitor

Monitors system resources (CPU, memory) and provides health checks
for parallel worker execution.

Includes trend tracking with rolling window, moving averages,
predictive worker count recommendations, and two-tier thresholds.
"""

import logging
import math
from collections import deque
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ResourceStatus:
    """Current system resource status"""

    cpu_percent: float
    memory_percent: float
    available_memory_mb: float
    timestamp: datetime
    is_healthy: bool
    blocking_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "available_memory_mb": self.available_memory_mb,
            "timestamp": self.timestamp.isoformat(),
            "is_healthy": self.is_healthy,
            "blocking_reason": self.blocking_reason,
        }


@dataclass
class _ResourceSample:
    """A single resource usage sample (internal)."""

    cpu_percent: float
    memory_percent: float
    timestamp: datetime


class ResourceTrendTracker:
    """
    Tracks resource usage trends over a rolling window.

    Uses a deque-based rolling window to store periodic samples of
    CPU and memory usage, and computes moving averages, trend direction,
    and standard deviation for predictive resource management.
    """

    def __init__(
        self,
        window_size: int = 300,
        sample_interval: int = 5,
    ) -> None:
        """
        Initialize the trend tracker.

        Args:
            window_size: Total window duration in seconds (default: 300s = 5 min).
            sample_interval: Expected interval between samples in seconds (default: 5s).
        """
        self.window_size = window_size
        self.sample_interval = sample_interval
        max_samples = window_size // sample_interval
        self._samples: deque[_ResourceSample] = deque(maxlen=max_samples)
        logger.debug(
            f"ResourceTrendTracker initialized: window={window_size}s, "
            f"interval={sample_interval}s, max_samples={max_samples}"
        )

    def add_sample(self, cpu_percent: float, memory_percent: float) -> None:
        """
        Add a resource usage sample.

        Args:
            cpu_percent: Current CPU usage percentage (0-100).
            memory_percent: Current memory usage percentage (0-100).
        """
        sample = _ResourceSample(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            timestamp=datetime.now(),
        )
        self._samples.append(sample)
        logger.debug(
            f"Trend sample added: CPU={cpu_percent:.1f}%, "
            f"Memory={memory_percent:.1f}% "
            f"(total samples: {len(self._samples)})"
        )

    @property
    def sample_count(self) -> int:
        """Return the current number of stored samples."""
        return len(self._samples)

    def get_moving_average(self) -> Dict[str, float]:
        """
        Calculate moving averages for CPU and memory usage over the window.

        Returns:
            Dictionary with 'cpu_avg' and 'memory_avg' keys.
            Returns 0.0 for both if no samples are available.
        """
        if not self._samples:
            return {"cpu_avg": 0.0, "memory_avg": 0.0}

        count = len(self._samples)
        cpu_sum = sum(s.cpu_percent for s in self._samples)
        mem_sum = sum(s.memory_percent for s in self._samples)

        return {
            "cpu_avg": cpu_sum / count,
            "memory_avg": mem_sum / count,
        }

    def get_trend_direction(self) -> Dict[str, str]:
        """
        Determine the trend direction for CPU and memory.

        Compares the average of the first half of samples to the second half.
        A difference of more than 3 percentage points is considered a change.

        Returns:
            Dictionary with 'cpu_trend' and 'memory_trend' keys.
            Each value is one of: "rising", "falling", "stable".
            Returns "stable" for both if insufficient samples (< 4).
        """
        if len(self._samples) < 4:
            return {"cpu_trend": "stable", "memory_trend": "stable"}

        samples_list: List[_ResourceSample] = list(self._samples)
        mid = len(samples_list) // 2
        first_half = samples_list[:mid]
        second_half = samples_list[mid:]

        first_cpu_avg = sum(s.cpu_percent for s in first_half) / len(first_half)
        second_cpu_avg = sum(s.cpu_percent for s in second_half) / len(second_half)
        first_mem_avg = sum(s.memory_percent for s in first_half) / len(first_half)
        second_mem_avg = sum(s.memory_percent for s in second_half) / len(second_half)

        threshold = 3.0  # percentage points

        def _classify(first: float, second: float) -> str:
            diff = second - first
            if diff > threshold:
                return "rising"
            elif diff < -threshold:
                return "falling"
            else:
                return "stable"

        return {
            "cpu_trend": _classify(first_cpu_avg, second_cpu_avg),
            "memory_trend": _classify(first_mem_avg, second_mem_avg),
        }

    def get_std_dev(self) -> Dict[str, float]:
        """
        Calculate standard deviation for CPU and memory usage samples.

        Returns:
            Dictionary with 'cpu_std' and 'memory_std' keys.
            Returns 0.0 for both if fewer than 2 samples.
        """
        if len(self._samples) < 2:
            return {"cpu_std": 0.0, "memory_std": 0.0}

        count = len(self._samples)
        cpu_values = [s.cpu_percent for s in self._samples]
        mem_values = [s.memory_percent for s in self._samples]

        cpu_mean = sum(cpu_values) / count
        mem_mean = sum(mem_values) / count

        cpu_variance = sum((v - cpu_mean) ** 2 for v in cpu_values) / count
        mem_variance = sum((v - mem_mean) ** 2 for v in mem_values) / count

        return {
            "cpu_std": math.sqrt(cpu_variance),
            "memory_std": math.sqrt(mem_variance),
        }


class ResourceMonitor:
    """Monitors system resources for worker execution"""

    def __init__(
        self,
        max_cpu_percent: float = 85.0,
        max_memory_percent: float = 85.0,
        warning_cpu_percent: float = 75.0,
        warning_memory_percent: float = 75.0,
        trend_window_size: int = 300,
        trend_sample_interval: int = 5,
    ):
        """
        Initialize resource monitor

        Args:
            max_cpu_percent: Hard limit CPU usage threshold (0-100)
            max_memory_percent: Hard limit memory usage threshold (0-100)
            warning_cpu_percent: Soft limit CPU usage threshold (0-100)
            warning_memory_percent: Soft limit memory usage threshold (0-100)
            trend_window_size: Rolling window duration in seconds for trend tracking
            trend_sample_interval: Sample interval in seconds for trend tracking
        """
        self.max_cpu_percent = max_cpu_percent
        self.max_memory_percent = max_memory_percent
        self.warning_cpu_percent = warning_cpu_percent
        self.warning_memory_percent = warning_memory_percent

        # Initialize trend tracker
        self.trend_tracker = ResourceTrendTracker(
            window_size=trend_window_size,
            sample_interval=trend_sample_interval,
        )

        # Try to import psutil
        try:
            import psutil
            self.psutil = psutil
            self.monitoring_available = True
            logger.info("Resource monitoring enabled")
        except ImportError:
            self.psutil = None
            self.monitoring_available = False
            logger.warning(
                "psutil not available - resource monitoring disabled. "
                "Install with: pip install psutil"
            )

    def get_status(self) -> ResourceStatus:
        """
        Get current resource status

        Returns:
            ResourceStatus: Current system resource status
        """
        if not self.monitoring_available:
            # Return healthy status if monitoring unavailable
            return ResourceStatus(
                cpu_percent=0.0,
                memory_percent=0.0,
                available_memory_mb=0.0,
                timestamp=datetime.now(),
                is_healthy=True,
                blocking_reason=None,
            )

        try:
            # Get CPU usage (average over 1 second)
            cpu_percent = self.psutil.cpu_percent(interval=1)

            # Get memory usage
            memory = self.psutil.virtual_memory()
            memory_percent = memory.percent
            available_memory_mb = memory.available / (1024 * 1024)

            # Determine health status
            is_healthy = True
            blocking_reason = None

            if cpu_percent > self.max_cpu_percent:
                is_healthy = False
                blocking_reason = f"CPU usage {cpu_percent:.1f}% exceeds threshold {self.max_cpu_percent}%"

            elif memory_percent > self.max_memory_percent:
                is_healthy = False
                blocking_reason = f"Memory usage {memory_percent:.1f}% exceeds threshold {self.max_memory_percent}%"

            return ResourceStatus(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                available_memory_mb=available_memory_mb,
                timestamp=datetime.now(),
                is_healthy=is_healthy,
                blocking_reason=blocking_reason,
            )

        except Exception as e:
            logger.error(f"Failed to get resource status: {e}")
            # Return healthy status on error to avoid blocking
            return ResourceStatus(
                cpu_percent=0.0,
                memory_percent=0.0,
                available_memory_mb=0.0,
                timestamp=datetime.now(),
                is_healthy=True,
                blocking_reason=None,
            )

    def can_launch_worker(self) -> tuple[bool, Optional[str]]:
        """
        Check if system resources allow launching a new worker

        Returns:
            Tuple of (can_launch: bool, reason: Optional[str])
        """
        if not self.monitoring_available:
            # Allow launch if monitoring unavailable
            return (True, None)

        status = self.get_status()

        if not status.is_healthy:
            return (False, status.blocking_reason)

        return (True, None)

    def can_launch_worker_extended(
        self,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Extended launch check with two-tier severity levels.

        Checks both hard limits (block) and soft limits (warning).

        Returns:
            Tuple of (can_launch: bool, reason: Optional[str], severity: Optional[str])
            - severity is one of: "block", "warning", or None
            - "block": hard limit exceeded, launch denied
            - "warning": soft limit exceeded, launch allowed but cautioned
            - None: all clear
        """
        if not self.monitoring_available:
            return (True, None, None)

        status = self.get_status()

        # Check hard limits first (block)
        if not status.is_healthy:
            return (False, status.blocking_reason, "block")

        # Check soft limits (warning)
        if status.cpu_percent > self.warning_cpu_percent:
            reason = (
                f"CPU usage {status.cpu_percent:.1f}% exceeds "
                f"warning threshold {self.warning_cpu_percent}%"
            )
            logger.warning(f"Soft limit reached: {reason}")
            return (True, reason, "warning")

        if status.memory_percent > self.warning_memory_percent:
            reason = (
                f"Memory usage {status.memory_percent:.1f}% exceeds "
                f"warning threshold {self.warning_memory_percent}%"
            )
            logger.warning(f"Soft limit reached: {reason}")
            return (True, reason, "warning")

        return (True, None, None)

    def collect_sample(self) -> None:
        """
        Collect a resource usage sample and add it to the trend tracker.

        This method should be called periodically (at the configured
        sample_interval) to maintain accurate trend data.
        """
        if not self.monitoring_available:
            logger.debug("Cannot collect sample: monitoring not available")
            return

        try:
            # Use non-blocking CPU check to avoid 1s delay per sample
            cpu_percent = self.psutil.cpu_percent(interval=0)
            memory = self.psutil.virtual_memory()
            memory_percent = memory.percent

            self.trend_tracker.add_sample(cpu_percent, memory_percent)

        except Exception as e:
            logger.error(f"Failed to collect resource sample: {e}")

    def get_recommended_worker_count(
        self,
        current_workers: int,
        max_workers: int,
    ) -> int:
        """
        Get recommended worker count based on current resources

        Args:
            current_workers: Current number of workers
            max_workers: Maximum allowed workers

        Returns:
            Recommended worker count (may be less than max_workers)
        """
        if not self.monitoring_available:
            return max_workers

        status = self.get_status()

        # If resources healthy, allow max workers
        if status.is_healthy:
            return max_workers

        # If resources constrained, reduce worker count
        cpu_ratio = status.cpu_percent / 100.0
        memory_ratio = status.memory_percent / 100.0

        # Use the more constrained resource
        constraint_ratio = max(cpu_ratio, memory_ratio)

        # Calculate recommended workers based on constraint
        # If at 90% usage, recommend 50% of max workers
        # If at 95% usage, recommend 25% of max workers
        if constraint_ratio >= 0.95:
            recommended = max(1, max_workers // 4)
        elif constraint_ratio >= 0.90:
            recommended = max(1, max_workers // 2)
        elif constraint_ratio >= 0.85:
            recommended = max(1, int(max_workers * 0.75))
        else:
            recommended = max_workers

        logger.info(
            f"Resource-based recommendation: {recommended}/{max_workers} workers "
            f"(CPU: {status.cpu_percent:.1f}%, Memory: {status.memory_percent:.1f}%)"
        )

        return recommended

    def get_predicted_worker_count(
        self,
        current_workers: int,
        max_workers: int,
    ) -> int:
        """
        Get trend-based predictive recommended worker count.

        Uses the underlying get_recommended_worker_count() as a baseline,
        then adjusts based on resource usage trend direction:
        - Rising trend: reduce recommendation by 20% (preemptive shrink)
        - Falling trend: increase recommendation by 10% (gradual expansion)
        - Stable trend: use baseline recommendation as-is

        The dominant trend (CPU or memory) is used; if either is rising,
        the rising adjustment takes priority.

        Args:
            current_workers: Current number of active workers.
            max_workers: Maximum allowed workers.

        Returns:
            Predicted recommended worker count, clamped to [1, max_workers].
        """
        baseline = self.get_recommended_worker_count(current_workers, max_workers)

        trends = self.trend_tracker.get_trend_direction()
        cpu_trend = trends["cpu_trend"]
        memory_trend = trends["memory_trend"]

        # Determine dominant trend: rising takes priority
        if cpu_trend == "rising" or memory_trend == "rising":
            dominant = "rising"
        elif cpu_trend == "falling" and memory_trend == "falling":
            dominant = "falling"
        elif cpu_trend == "falling" or memory_trend == "falling":
            # One is falling, the other is stable
            dominant = "falling"
        else:
            dominant = "stable"

        if dominant == "rising":
            # Preemptive shrink: reduce by 20%
            adjusted = int(baseline * 0.80)
            logger.info(
                f"Trend-based prediction: rising trend detected, "
                f"reducing {baseline} -> {adjusted} workers"
            )
        elif dominant == "falling":
            # Gradual expansion: increase by 10%
            adjusted = int(baseline * 1.10)
            logger.info(
                f"Trend-based prediction: falling trend detected, "
                f"expanding {baseline} -> {adjusted} workers"
            )
        else:
            adjusted = baseline
            logger.debug(
                f"Trend-based prediction: stable trend, "
                f"keeping {baseline} workers"
            )

        # Clamp to valid range
        result = max(1, min(adjusted, max_workers))
        return result

    def get_trend_status(self) -> Dict[str, Any]:
        """
        Get comprehensive trend information as a dictionary.

        Returns:
            Dictionary containing:
            - moving_average: {cpu_avg, memory_avg}
            - trend_direction: {cpu_trend, memory_trend}
            - std_dev: {cpu_std, memory_std}
            - sample_count: number of stored samples
            - window_size: configured window size in seconds
            - sample_interval: configured sample interval in seconds
        """
        return {
            "moving_average": self.trend_tracker.get_moving_average(),
            "trend_direction": self.trend_tracker.get_trend_direction(),
            "std_dev": self.trend_tracker.get_std_dev(),
            "sample_count": self.trend_tracker.sample_count,
            "window_size": self.trend_tracker.window_size,
            "sample_interval": self.trend_tracker.sample_interval,
        }

    def log_status(self) -> None:
        """Log current resource status including trend information"""
        if not self.monitoring_available:
            logger.debug("Resource monitoring not available")
            return

        status = self.get_status()

        logger.info(
            f"Resource Status: CPU {status.cpu_percent:.1f}%, "
            f"Memory {status.memory_percent:.1f}% "
            f"(Available: {status.available_memory_mb:.0f} MB) "
            f"- {'Healthy' if status.is_healthy else 'Constrained'}"
        )

        if not status.is_healthy and status.blocking_reason:
            logger.warning(f"Resource constraint: {status.blocking_reason}")

        # Log trend information if samples are available
        if self.trend_tracker.sample_count > 0:
            avg = self.trend_tracker.get_moving_average()
            trends = self.trend_tracker.get_trend_direction()
            std = self.trend_tracker.get_std_dev()
            logger.info(
                f"Trend: CPU avg={avg['cpu_avg']:.1f}% ({trends['cpu_trend']}, "
                f"std={std['cpu_std']:.1f}), "
                f"Memory avg={avg['memory_avg']:.1f}% ({trends['memory_trend']}, "
                f"std={std['memory_std']:.1f}) "
                f"[{self.trend_tracker.sample_count} samples]"
            )


def get_system_info() -> Dict[str, Any]:
    """
    Get system information for diagnostics

    Returns:
        Dictionary with system info
    """
    try:
        import psutil
        import platform

        cpu_count_logical = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)
        memory = psutil.virtual_memory()

        return {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "cpu_count_logical": cpu_count_logical,
            "cpu_count_physical": cpu_count_physical,
            "total_memory_gb": memory.total / (1024 ** 3),
            "available_memory_gb": memory.available / (1024 ** 3),
            "memory_percent": memory.percent,
            "monitoring_available": True,
        }

    except ImportError:
        return {
            "platform": "unknown",
            "monitoring_available": False,
            "message": "psutil not installed",
        }
    except Exception as e:
        return {
            "error": str(e),
            "monitoring_available": False,
        }
