#!/usr/bin/env python3
"""
Fault Detection Module - Test Script

Tests all detection methods to verify functionality.
"""

import sys
from pathlib import Path

# Add parent directory to path
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
sys.path.insert(0, str(_package_root))

from fault_detection import (
    detect_all_faults,
    detect_stuck_tasks,
    detect_invalid_transitions,
    detect_subagent_crashes,
    detect_file_write_failures,
    FaultDetector,
    FaultType
)


def test_all_detections():
    """Test all detection methods"""
    print("=== Fault Detection Module Test ===\n")

    # Test 1: Detect all faults
    print("1. Testing detect_all_faults()...")
    all_faults = detect_all_faults(stuck_threshold_minutes=10, verbose=False)
    print(f"   ✓ Detected {len(all_faults)} faults total\n")

    # Test 2: Detect stuck tasks
    print("2. Testing detect_stuck_tasks()...")
    stuck_faults = detect_stuck_tasks(stuck_threshold_minutes=10)
    print(f"   ✓ Detected {len(stuck_faults)} stuck tasks")
    for fault in stuck_faults:
        print(f"     - {fault.task_id}: {fault.description}")
    print()

    # Test 3: Detect invalid transitions
    print("3. Testing detect_invalid_transitions()...")
    transition_faults = detect_invalid_transitions()
    print(f"   ✓ Detected {len(transition_faults)} invalid transitions")
    for fault in transition_faults:
        print(f"     - {fault.description}")
    print()

    # Test 4: Detect subagent crashes
    print("4. Testing detect_subagent_crashes()...")
    crash_faults = detect_subagent_crashes()
    print(f"   ✓ Detected {len(crash_faults)} subagent crashes")
    for fault in crash_faults:
        print(f"     - {fault.description}")
    print()

    # Test 5: Detect file write failures
    print("5. Testing detect_file_write_failures()...")
    file_faults = detect_file_write_failures()
    print(f"   ✓ Detected {len(file_faults)} file write failures")
    for fault in file_faults:
        print(f"     - {fault.description}")
    print()

    # Test 6: FaultDetector class
    print("6. Testing FaultDetector class...")
    detector = FaultDetector(
        stuck_threshold_minutes=15,
        check_subagent_logs=True,
        check_file_writes=True,
        verbose=False
    )
    class_faults = detector.detect_all()
    print(f"   ✓ FaultDetector.detect_all() returned {len(class_faults)} faults\n")

    # Test 7: FaultReport to_dict()
    if all_faults:
        print("7. Testing FaultReport.to_dict()...")
        fault_dict = all_faults[0].to_dict()
        print(f"   ✓ FaultReport converted to dict with {len(fault_dict)} keys")
        print(f"     Keys: {list(fault_dict.keys())}\n")
    else:
        print("7. Skipping FaultReport.to_dict() (no faults detected)\n")

    # Summary
    print("=== Test Summary ===")
    print(f"Total faults detected: {len(all_faults)}")
    print(f"  - Stuck tasks: {len(stuck_faults)}")
    print(f"  - Invalid transitions: {len(transition_faults)}")
    print(f"  - Subagent crashes: {len(crash_faults)}")
    print(f"  - File write failures: {len(file_faults)}")
    print("\n✓ All tests passed!")


if __name__ == "__main__":
    try:
        test_all_detections()
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Test failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
