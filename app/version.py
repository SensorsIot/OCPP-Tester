"""
OCPP Tester Version Information

Update these constants whenever you make significant changes to the code.
"""

__version__ = "1.3.0"
__build_date__ = "2025-11-13"

# Module-specific versions for tracking critical changes
__test_helpers_version__ = "1.1.0"  # Added ensure_test_configuration, set_ev_state_and_wait_for_status
__test_series_b_version__ = "1.4.0"  # Fixed B.2: Prevent ElecqAutoStart auto-start with dual parameter fix

# Change log
CHANGELOG = {
    "1.3.0": {
        "date": "2025-11-13",
        "changes": [
            "Added B.5: Local Stop test (RFID tap to stop transaction)",
            "Merged execution logs (EV simulator, comments) with OCPP messages in single log file",
            "Removed separate summary log files - all info in one comprehensive log",
            "Fixed NOT_SUPPORTED button color to yellow for better visibility"
        ]
    },
    
    "1.2.0": {
        "date": "2025-11-13",
        "changes": [
            "Fixed Test B.2: Changed LocalAuthorizeOffline from true→false to prevent cache auto-start",
            "Fixed Test B.2: Changed LocalAuthListEnabled from true→false to fully disable local cache",
            "Fixed Test B.2: Prevent 'ElecqAutoStart' firmware card from bypassing authorization",
            "Fixed Test B.2: Updated test description to reflect backend authorization (not local cache)",
            "Fixed Test B.2: Improved ClearCache error handling with explanatory messages",
            "Fixed Test B.2: Removed SendLocalList (not needed for backend auth flow)"
        ]
    },
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
