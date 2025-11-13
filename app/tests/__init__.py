"""
OCPP Test Modules - Modular Test Structure

All tests organized by series for better maintainability and clarity.

Test Series Organization (ALL MIGRATED ✓):
- Series A (TestSeriesA): Core Communication & Status (6 tests)
- Series B (TestSeriesB): Authorization & Status Management (8 tests)
- Series C (TestSeriesC): Charging Profile Management (7 tests)
- Series X (TestSeriesX): Utility Functions (2 tests)

Total: 23 tests across 4 series
"""

from app.tests.test_base import OcppTestBase
from app.tests.test_series_a_basic import TestSeriesA
from app.tests.test_series_b_auth import TestSeriesB
from app.tests.test_series_c_charging import TestSeriesC
from app.tests.test_series_x_utility import TestSeriesX

__all__ = [
    "OcppTestBase",
    "TestSeriesA",
    "TestSeriesB",
    "TestSeriesC",
    "TestSeriesX",
]
