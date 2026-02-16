"""
Tests for resource_monitor.py - Resource monitoring and health checks
"""

import unittest
from unittest.mock import Mock, MagicMock
from datetime import datetime
import sys
from pathlib import Path

# Add parent directory to path
_test_dir = Path(__file__).resolve().parent
_package_root = _test_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from worker.resource_monitor import ResourceMonitor, ResourceStatus


class TestResourceMonitor(unittest.TestCase):
    """Test ResourceMonitor class"""

    def test_init_without_psutil(self):
        """Test initialization when psutil is not available"""
        monitor = ResourceMonitor()
        # Should initialize successfully even without psutil
        self.assertIsNotNone(monitor)

    def test_get_status_healthy(self):
        """Test get_status returns healthy status when resources OK"""
        # Create mock psutil
        mock_psutil = Mock()
        mock_psutil.cpu_percent.return_value = 50.0
        mock_memory = Mock()
        mock_memory.percent = 60.0
        mock_memory.available = 4 * 1024 * 1024 * 1024  # 4GB
        mock_psutil.virtual_memory.return_value = mock_memory

        monitor = ResourceMonitor(max_cpu_percent=85.0, max_memory_percent=85.0)
        monitor.psutil = mock_psutil
        monitor.monitoring_available = True

        status = monitor.get_status()

        self.assertIsInstance(status, ResourceStatus)
        self.assertEqual(status.cpu_percent, 50.0)
        self.assertEqual(status.memory_percent, 60.0)
        self.assertTrue(status.is_healthy)
        self.assertIsNone(status.blocking_reason)

    def test_get_status_cpu_exceeded(self):
        """Test get_status detects CPU threshold exceeded"""
        mock_psutil = Mock()
        mock_psutil.cpu_percent.return_value = 90.0
        mock_memory = Mock()
        mock_memory.percent = 60.0
        mock_memory.available = 4 * 1024 * 1024 * 1024
        mock_psutil.virtual_memory.return_value = mock_memory

        monitor = ResourceMonitor(max_cpu_percent=85.0, max_memory_percent=85.0)
        monitor.psutil = mock_psutil
        monitor.monitoring_available = True

        status = monitor.get_status()

        self.assertFalse(status.is_healthy)
        self.assertIsNotNone(status.blocking_reason)
        self.assertIn("CPU", status.blocking_reason)

    def test_get_status_memory_exceeded(self):
        """Test get_status detects memory threshold exceeded"""
        mock_psutil = Mock()
        mock_psutil.cpu_percent.return_value = 50.0
        mock_memory = Mock()
        mock_memory.percent = 90.0
        mock_memory.available = 1 * 1024 * 1024 * 1024
        mock_psutil.virtual_memory.return_value = mock_memory

        monitor = ResourceMonitor(max_cpu_percent=85.0, max_memory_percent=85.0)
        monitor.psutil = mock_psutil
        monitor.monitoring_available = True

        status = monitor.get_status()

        self.assertFalse(status.is_healthy)
        self.assertIsNotNone(status.blocking_reason)
        self.assertIn("Memory", status.blocking_reason)

    def test_get_status_no_monitoring(self):
        """Test get_status returns healthy when monitoring unavailable"""
        monitor = ResourceMonitor()
        monitor.monitoring_available = False

        status = monitor.get_status()

        self.assertTrue(status.is_healthy)
        self.assertIsNone(status.blocking_reason)

    def test_can_launch_worker_healthy(self):
        """Test can_launch_worker allows launch when healthy"""
        mock_psutil = Mock()
        mock_psutil.cpu_percent.return_value = 50.0
        mock_memory = Mock()
        mock_memory.percent = 60.0
        mock_memory.available = 4 * 1024 * 1024 * 1024
        mock_psutil.virtual_memory.return_value = mock_memory

        monitor = ResourceMonitor(max_cpu_percent=85.0, max_memory_percent=85.0)
        monitor.psutil = mock_psutil
        monitor.monitoring_available = True

        can_launch, reason = monitor.can_launch_worker()

        self.assertTrue(can_launch)
        self.assertIsNone(reason)

    def test_can_launch_worker_constrained(self):
        """Test can_launch_worker blocks when resources constrained"""
        mock_psutil = Mock()
        mock_psutil.cpu_percent.return_value = 90.0
        mock_memory = Mock()
        mock_memory.percent = 60.0
        mock_memory.available = 4 * 1024 * 1024 * 1024
        mock_psutil.virtual_memory.return_value = mock_memory

        monitor = ResourceMonitor(max_cpu_percent=85.0, max_memory_percent=85.0)
        monitor.psutil = mock_psutil
        monitor.monitoring_available = True

        can_launch, reason = monitor.can_launch_worker()

        self.assertFalse(can_launch)
        self.assertIsNotNone(reason)

    def test_get_recommended_worker_count(self):
        """Test get_recommended_worker_count scales workers appropriately"""
        mock_psutil = Mock()
        monitor = ResourceMonitor(max_cpu_percent=85.0, max_memory_percent=85.0)
        monitor.psutil = mock_psutil
        monitor.monitoring_available = True

        # Test at 50% - should allow max workers
        mock_psutil.cpu_percent.return_value = 50.0
        mock_memory = Mock()
        mock_memory.percent = 50.0
        mock_memory.available = 4 * 1024 * 1024 * 1024
        mock_psutil.virtual_memory.return_value = mock_memory

        recommended = monitor.get_recommended_worker_count(0, 10)
        self.assertEqual(recommended, 10)

        # Test at 87% - should reduce workers
        mock_psutil.cpu_percent.return_value = 87.0
        recommended = monitor.get_recommended_worker_count(0, 10)
        self.assertLess(recommended, 10)
        self.assertGreaterEqual(recommended, 1)

        # Test at 92% - should significantly reduce
        mock_psutil.cpu_percent.return_value = 92.0
        recommended = monitor.get_recommended_worker_count(0, 10)
        self.assertLess(recommended, 6)
        self.assertGreaterEqual(recommended, 1)

        # Test at 96% - should minimize workers
        mock_psutil.cpu_percent.return_value = 96.0
        recommended = monitor.get_recommended_worker_count(0, 10)
        self.assertLessEqual(recommended, 3)
        self.assertGreaterEqual(recommended, 1)

    def test_resource_status_to_dict(self):
        """Test ResourceStatus.to_dict() serialization"""
        status = ResourceStatus(
            cpu_percent=50.0,
            memory_percent=60.0,
            available_memory_mb=4096.0,
            timestamp=datetime(2026, 2, 6, 12, 0, 0),
            is_healthy=True,
            blocking_reason=None,
        )

        status_dict = status.to_dict()

        self.assertIsInstance(status_dict, dict)
        self.assertEqual(status_dict["cpu_percent"], 50.0)
        self.assertEqual(status_dict["memory_percent"], 60.0)
        self.assertEqual(status_dict["available_memory_mb"], 4096.0)
        self.assertTrue(status_dict["is_healthy"])
        self.assertIsNone(status_dict["blocking_reason"])
        self.assertIn("timestamp", status_dict)


if __name__ == "__main__":
    unittest.main()
