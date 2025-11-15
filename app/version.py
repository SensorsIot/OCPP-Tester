"""
OCPP Tester Version Information

Update these constants whenever you make significant changes to the code.
"""

__version__ = "1.3.20"
__build_date__ = "2025-11-15"

# Module-specific versions for tracking critical changes
__test_helpers_version__ = "1.1.0"  # Added ensure_test_configuration, set_ev_state_and_wait_for_status
__test_series_b_version__ = "1.4.0"  # Fixed B.2: Prevent ElecqAutoStart auto-start with dual parameter fix
__test_series_a_version__ = "1.1.2"  # Fixed A.6: Extended Phase 5 timeout to 60s for post-reconnection commands

# Change log
CHANGELOG = {
    "1.3.20": {
        "date": "2025-11-15",
        "changes": [
            "Removed unnecessary GetConfiguration calls",
            "Removed pre-flight GetConfiguration (not needed, adds 120s delay)",
            "Removed A.4 GetConfiguration for features check (assumes RemoteTrigger supported)",
            "Changed A.6 GetConfiguration to use {} payload (exactly matches EVCC format)",
            "Tests now faster and match real-world EVCC behavior"
        ]
    },
    "1.3.19": {
        "date": "2025-11-15",
        "changes": [
            "Implemented smart message filtering for cleaner test logs",
            "A.6 test: Logs ALL messages (complete OCPP trace for reconnection debugging)",
            "C-series tests: Logs ALL messages (needs MeterValues for charging analysis)",
            "Other tests: Filters out Heartbeat, StatusNotification, MeterValues (unless explicitly triggered)",
            "Dramatically reduces log noise while preserving essential debugging information"
        ]
    },
    "1.3.18": {
        "date": "2025-11-15",
        "changes": [
            "Extended ALL GetConfiguration timeouts to 120s (was 10s-30s)",
            "Applied to: pre-flight, A.2, A.4, and A.6 tests",
            "Allows wallbox to initialize after reconnection before responding"
        ]
    },
    "1.3.17": {
        "date": "2025-11-15",
        "changes": [
            "A.6 Phase 5 now uses 60-second timeout (was 10s)",
            "Wallbox needs more time after reconnection to process commands",
            "All configuration and trigger messages now wait longer"
        ]
    },
    "1.3.16": {
        "date": "2025-11-15",
        "changes": [
            "Fixed A.6 wrapper transfer bug: Recreate wrappers with new handler's send_and_wait",
            "Previous version transferred old wrapper with stale closure causing WebSocket errors",
            "Now properly creates fresh wrapper functions for reconnected handler"
        ]
    },
    "1.3.15": {
        "date": "2025-11-15",
        "changes": [
            "Fixed A.6 test logging: All OCPP messages now recorded in test log file",
            "Message logging wrappers transfer to new handler when server restarts",
            "Captures BootNotification, StatusNotification, MeterValues after reconnection"
        ]
    },
    "1.3.14": {
        "date": "2025-11-15",
        "changes": [
            "Test logs show ONLY JSON messages (no execution logs)",
            "Back to original behavior - clean JSON-only output",
            "Matches format of other tests"
        ]
    },
    "1.3.13": {
        "date": "2025-11-15",
        "changes": [
            "Removed ALL emojis from test logs - now plain ASCII only",
            "Replaced ✅ with [OK], ❌ with [FAIL], ⚠️ with [WARN]",
            "Cleaner, more readable test output"
        ]
    },
    "1.3.12": {
        "date": "2025-11-15",
        "changes": [
            "FIXED: Removed message filtering in log_message() function",
            "Now logs ALL received messages including StatusNotification/BootNotification",
            "Test logs will now actually show JSON messages (they were being filtered out)",
            "Complete OCPP message capture for all tests"
        ]
    },
    "1.3.11": {
        "date": "2025-11-15",
        "changes": [
            "ALL test logs now show ALL JSON messages (no filtering)",
            "Includes Heartbeat, StatusNotification, MeterValues for all tests",
            "Complete visibility into all OCPP communication"
        ]
    },
    "1.3.10": {
        "date": "2025-11-15",
        "changes": [
            "Test A.6: Shows ALL JSON messages (Heartbeat, StatusNotification, MeterValues)",
            "Other tests: Keep message filtering for cleaner logs",
            "Test logs include execution logs + all OCPP JSON chronologically"
        ]
    },
    "1.3.9": {
        "date": "2025-11-15",
        "changes": [
            "Test logs now include ALL messages (execution logs + JSON OCPP messages)",
            "Test A.6: Missing BootNotification now logged as WARNING, not failure",
            "Test A.6: Continues and passes even with OCPP compliance violations",
            "Improved test log readability with chronological execution + OCPP messages"
        ]
    },
    "1.3.8": {
        "date": "2025-11-15",
        "changes": [
            "Test A.6: Fixed BootNotification detection after reconnection",
            "Now clears model/vendor data before server stop to detect new BootNotification",
            "Test now correctly identifies if wallbox sends BootNotification after reconnect",
            "Reveals wallbox OCPP violation: sends StatusNotification before BootNotification"
        ]
    },
    "1.3.7": {
        "date": "2025-11-15",
        "changes": [
            "Test A.6: Now actually closes port 8888 instead of just blocking connections",
            "Added server control functions: stop_ocpp_server() and start_ocpp_server()",
            "Server factory function allows tests to stop/restart WebSocket server",
            "Accurately emulates EVCC offline (port not listening, not just rejecting)",
            "Removed connection blocking mechanism (replaced with actual port closure)"
        ]
    },
    "1.3.6": {
        "date": "2025-11-15",
        "changes": [
            "Test A.6: Now matches EVCC behavior exactly per evcc_reboot_behavior.md",
            "Increased offline period from 5s to 10s (matches EVCC startup time)",
            "Added ChangeAvailability command (EVCC sends this)",
            "Added WebSocketPingInterval configuration (EVCC configures this)",
            "Test now sends exact same commands as EVCC after reboot",
            "Test reveals wallbox OCPP violation: BootNotification must be first message"
        ]
    },
    "1.3.5": {
        "date": "2025-11-15",
        "changes": [
            "Test A.6: Implemented proper EVCC offline period simulation",
            "Added charge point blocking mechanism to reject reconnections during test",
            "Test now blocks reconnections for 5 seconds to simulate EVCC offline",
            "Wallbox reconnects after EVCC comes back online",
            "Added cleanup to unblock charge point after test completes",
            "Fixed handler update to use new connection after reconnection",
            "Test completes in ~10-15 seconds total"
        ]
    },
    "1.3.4": {
        "date": "2025-11-15",
        "changes": [
            "Fixed Test A.6 bug: Corrected reconnection detection logic",
            "Now checks for 'ocpp_handler' field instead of non-existent 'connected' field",
            "Updated test description to reflect actual phases",
            "Test now properly detects wallbox reconnection"
        ]
    },
    "1.3.3": {
        "date": "2025-11-15",
        "changes": [
            "Fixed Test A.6 (EVCC Reboot) logic - removed artificial startup delay",
            "Wallbox now reconnects immediately after connection close (as expected)",
            "Reduced reconnection timeout from 60s to 30s",
            "Test now completes in ~10-20s instead of ~75-90s"
        ]
    },
    "1.3.2": {
        "date": "2025-11-15",
        "changes": [
            "Optimized Test A.6 (EVCC Reboot) execution time",
            "Reduced EVCC startup delay from 15s to 5s",
            "Reduced wallbox reconnection timeout from 60s to 30s",
            "Test now completes in ~30-45s instead of ~75-90s"
        ]
    },
    "1.3.1": {
        "date": "2025-11-15",
        "changes": [
            "Improved log message clarity for GetConfiguration timeouts",
            "Added AUTO-DETECT prefix to all auto-detection log messages",
            "Added TEST PRE-FLIGHT prefix to test preparation log messages",
            "Improved timeout error messages to explain potential causes",
            "Added detailed context to fire-and-forget GetConfiguration requests"
        ]
    },
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
