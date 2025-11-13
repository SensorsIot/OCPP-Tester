"""
OCPP Tester Version Information

Update these constants whenever you make significant changes to the code.
"""

__version__ = "1.1.0"
__build_date__ = "2025-11-13"

# Module-specific versions for tracking critical changes
__test_helpers_version__ = "1.1.0"  # Added ensure_test_configuration, set_ev_state_and_wait_for_status
__test_series_b_version__ = "1.2.0"  # Fixed B.1: Added State C transition, parameter validation, timing fixes

# Change log
CHANGELOG = {
    "1.1.0": {
        "date": "2025-11-13",
        "changes": [
            "Added ensure_test_configuration() helper for parameter validation",
            "Added set_ev_state_and_wait_for_status() helper for reliable state changes",
            "Fixed Test B.1: Added missing State C transition",
            "Fixed Test B.1: Added parameter validation (LocalPreAuthorize, LocalAuthorizeOffline, AllowOfflineTxForUnknownId)",
            "Fixed Test B.1: Clear stale RFID data before waiting for tap",
            "Fixed Test B.1: Better preparation messages for user",
            "Implemented version management system"
        ]
    },
    "1.0.0": {
        "date": "2025-11-12",
        "changes": [
            "Initial version"
        ]
    }
}

def get_version_info():
    """Get formatted version information."""
    return {
        "version": __version__,
        "build_date": __build_date__,
        "modules": {
            "test_helpers": __test_helpers_version__,
            "test_series_b": __test_series_b_version__
        },
        "changelog": CHANGELOG.get(__version__, {})
    }

def get_version_string():
    """Get a simple version string."""
    return f"v{__version__} ({__build_date__})"
