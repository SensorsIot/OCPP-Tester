"""
OCPP Test Modules

Test series organized by functionality:
- Series A: Core Communication & Status (6 tests)
- Series B: Authorization & Status Management (10 tests)
- Series C: Charging Profile Management (5 tests)
- Series D: Smart Charging (2 tests)
- Series E: Remote Operations (7 tests)
- Series X: Utility Functions (2 tests)
"""

from app.tests.test_base import OcppTestBase
from app.tests.test_series_a_basic import TestSeriesA
from app.tests.test_series_b_auth import TestSeriesB
from app.tests.test_series_c_charging import TestSeriesC
from app.tests.test_series_d_smart import TestSeriesD
from app.tests.test_series_e_remote import TestSeriesE
from app.tests.test_series_x_utility import TestSeriesX

__all__ = [
    "OcppTestBase",
    "TestSeriesA",
    "TestSeriesB",
    "TestSeriesC",
    "TestSeriesD",
    "TestSeriesE",
    "TestSeriesX",
]
