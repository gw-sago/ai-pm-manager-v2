"""
Tests for config/worker_config.py - Worker resource configuration
"""

import unittest
import os
from pathlib import Path
import sys

# Add parent directory to path
_test_dir = Path(__file__).resolve().parent
_package_root = _test_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from config.worker_config import (
    WorkerResourceConfig,
    WorkerPriorityConfig,
    get_worker_config,
    set_worker_config,
    get_priority_config,
    load_config_from_env,
)


class TestWorkerResourceConfig(unittest.TestCase):
    """Test WorkerResourceConfig dataclass"""

    def test_default_values(self):
        """Test default configuration values"""
        config = WorkerResourceConfig()

        self.assertEqual(config.max_concurrent_workers, 5)
        self.assertEqual(config.max_cpu_percent, 85.0)
        self.assertEqual(config.max_memory_percent, 85.0)
        self.assertEqual(config.worker_timeout, 600)
        self.assertEqual(config.task_timeout, 3600)
        self.assertTrue(config.enable_resource_monitoring)
        self.assertTrue(config.enable_auto_scaling)

    def test_custom_values(self):
        """Test custom configuration values"""
        config = WorkerResourceConfig(
            max_concurrent_workers=10,
            max_cpu_percent=90.0,
            max_memory_percent=80.0,
        )

        self.assertEqual(config.max_concurrent_workers, 10)
        self.assertEqual(config.max_cpu_percent, 90.0)
        self.assertEqual(config.max_memory_percent, 80.0)

    def test_validation_max_workers_too_low(self):
        """Test validation rejects max_workers < 1"""
        with self.assertRaises(ValueError):
            WorkerResourceConfig(max_concurrent_workers=0)

    def test_validation_cpu_out_of_range(self):
        """Test validation rejects CPU percent out of range"""
        with self.assertRaises(ValueError):
            WorkerResourceConfig(max_cpu_percent=150.0)

        with self.assertRaises(ValueError):
            WorkerResourceConfig(max_cpu_percent=-10.0)

    def test_validation_memory_out_of_range(self):
        """Test validation rejects memory percent out of range"""
        with self.assertRaises(ValueError):
            WorkerResourceConfig(max_memory_percent=101.0)

    def test_validation_min_workers_exceeds_max(self):
        """Test validation rejects min_workers > max_workers"""
        with self.assertRaises(ValueError):
            WorkerResourceConfig(
                min_workers=10,
                max_concurrent_workers=5
            )


class TestWorkerPriorityConfig(unittest.TestCase):
    """Test WorkerPriorityConfig dataclass"""

    def test_default_values(self):
        """Test default priority configuration"""
        config = WorkerPriorityConfig()

        self.assertFalse(config.enable_priority_preemption)
        self.assertTrue(config.allow_p0_preemption)
        self.assertIsNone(config.max_p0_workers)
        self.assertIsNone(config.max_p1_workers)

    def test_get_max_workers_for_priority(self):
        """Test getting max workers for specific priority"""
        config = WorkerPriorityConfig(
            max_p0_workers=3,
            max_p1_workers=5,
            max_p2_workers=2,
        )

        self.assertEqual(config.get_max_workers_for_priority("P0"), 3)
        self.assertEqual(config.get_max_workers_for_priority("P1"), 5)
        self.assertEqual(config.get_max_workers_for_priority("P2"), 2)
        self.assertIsNone(config.get_max_workers_for_priority("P3"))


class TestConfigManagement(unittest.TestCase):
    """Test configuration management functions"""

    def setUp(self):
        """Reset global config before each test"""
        import config.worker_config as wc
        wc._default_worker_config = None
        wc._default_priority_config = None

    def test_get_worker_config_default(self):
        """Test get_worker_config returns default config"""
        config = get_worker_config()

        self.assertIsInstance(config, WorkerResourceConfig)
        self.assertEqual(config.max_concurrent_workers, 5)

    def test_set_and_get_worker_config(self):
        """Test setting and getting worker config"""
        custom_config = WorkerResourceConfig(max_concurrent_workers=10)
        set_worker_config(custom_config)

        retrieved_config = get_worker_config()

        self.assertEqual(retrieved_config.max_concurrent_workers, 10)

    def test_get_priority_config_default(self):
        """Test get_priority_config returns default config"""
        config = get_priority_config()

        self.assertIsInstance(config, WorkerPriorityConfig)
        self.assertFalse(config.enable_priority_preemption)


class TestLoadConfigFromEnv(unittest.TestCase):
    """Test loading configuration from environment variables"""

    def setUp(self):
        """Clear relevant environment variables"""
        env_vars = [
            "AIPM_MAX_WORKERS",
            "AIPM_MAX_CPU_PERCENT",
            "AIPM_MAX_MEMORY_PERCENT",
            "AIPM_WORKER_TIMEOUT",
            "AIPM_TASK_TIMEOUT",
            "AIPM_ENABLE_MONITORING",
            "AIPM_ENABLE_AUTO_SCALING",
        ]
        for var in env_vars:
            os.environ.pop(var, None)

    def test_load_config_no_env_vars(self):
        """Test loading config with no environment variables"""
        config = load_config_from_env()

        # Should return default values
        self.assertEqual(config.max_concurrent_workers, 5)
        self.assertEqual(config.max_cpu_percent, 85.0)

    def test_load_config_with_env_vars(self):
        """Test loading config from environment variables"""
        os.environ["AIPM_MAX_WORKERS"] = "10"
        os.environ["AIPM_MAX_CPU_PERCENT"] = "90.0"
        os.environ["AIPM_MAX_MEMORY_PERCENT"] = "80.0"
        os.environ["AIPM_WORKER_TIMEOUT"] = "1200"
        os.environ["AIPM_ENABLE_MONITORING"] = "false"

        config = load_config_from_env()

        self.assertEqual(config.max_concurrent_workers, 10)
        self.assertEqual(config.max_cpu_percent, 90.0)
        self.assertEqual(config.max_memory_percent, 80.0)
        self.assertEqual(config.worker_timeout, 1200)
        self.assertFalse(config.enable_resource_monitoring)

    def test_load_config_boolean_parsing(self):
        """Test boolean environment variable parsing"""
        os.environ["AIPM_ENABLE_MONITORING"] = "true"
        os.environ["AIPM_ENABLE_AUTO_SCALING"] = "false"

        config = load_config_from_env()

        self.assertTrue(config.enable_resource_monitoring)
        self.assertFalse(config.enable_auto_scaling)


if __name__ == "__main__":
    unittest.main()
