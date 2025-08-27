"""
This module contains the EVSimulatorManager class, which encapsulates all
logic for interacting with the EV simulator.
"""
import asyncio
import logging

import aiohttp

from app.state import EV_SIMULATOR_STATE, SERVER_SETTINGS
from app.status_streamer import EVStatusStreamer
from app.config import (
    EV_SIMULATOR_BASE_URL,
    EV_STATUS_POLL_INTERVAL,
    EV_WAIT_MAX_BACKOFF,
)

logger = logging.getLogger(__name__)


class EVSimulatorManager:
    """
    Manages all interactions with the EV simulator, including startup,
    polling, and handling runtime enable/disable toggles.
    """

    def __init__(self, status_streamer: EVStatusStreamer, refresh_trigger: asyncio.Event):
        self._status_streamer = status_streamer
        self._refresh_trigger = refresh_trigger
        self._was_enabled = SERVER_SETTINGS.get("use_simulator", False)
        self._url_status = f"{EV_SIMULATOR_BASE_URL}/api/status"
        self._url_set_state = f"{EV_SIMULATOR_BASE_URL}/api/set_state"

    async def start(self):
        """The main entry point and loop for the simulator manager task."""
        logger.info("EV Simulator Manager polling task started.")
        while True:
            try:
                if SERVER_SETTINGS.get("use_simulator"):
                    await self._handle_enabled_state()
                else:
                    await self._handle_disabled_state()

            except asyncio.CancelledError:
                logger.info("EV Simulator Manager task cancelled.")
                break
            except Exception as e:
                logger.error(f"Unhandled error in EVSimulatorManager: {e}", exc_info=True)
                await asyncio.sleep(30) # Avoid fast-spinning loop on unexpected errors

    async def _handle_enabled_state(self):
        """Logic for when the simulator is enabled."""
        if not self._was_enabled:
            logger.info("EV simulator has been enabled. Performing setup...")
            await self.wait_for_simulator()
            await self.set_initial_state()
            logger.info("Initial setup for EV simulator complete. Resuming regular polling.")
        
        self._was_enabled = True
        await self._poll_and_wait()

    async def _handle_disabled_state(self):
        """Logic for when the simulator is disabled."""
        if self._was_enabled:  # It was just turned off
            if EV_SIMULATOR_STATE:
                EV_SIMULATOR_STATE.clear()
                await self._status_streamer.broadcast_status({})
            
            # Immediately update status for responsive UI
            SERVER_SETTINGS["ev_simulator_available"] = False

            logger.info("EV simulator has been disabled. Cleared state and pausing poller.")
        
        self._was_enabled = False
        await self.probe_simulator_availability()
        await asyncio.sleep(5)  # Probe every 5 seconds

    async def wait_for_simulator(self):
        """Blocks until the EV simulator is available."""
        backoff = 1
        logger.info(f"Waiting for EV simulator at {self._url_status} ...")
        while SERVER_SETTINGS.get("use_simulator"):
            try:
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(self._url_status) as resp:
                        if resp.status == 200:
                            logger.info("EV simulator is available.")
                            return
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.debug(f"EV simulator not available ({type(e).__name__}). Backing off {backoff}s...")
            
            # Sleep in 1-second increments to remain responsive to the setting being disabled.
            for _ in range(backoff):
                if not SERVER_SETTINGS.get("use_simulator"):
                    # The setting was changed during our backoff period. Exit immediately.
                    break
                await asyncio.sleep(1)

            backoff = min(backoff * 2, EV_WAIT_MAX_BACKOFF)
        logger.info("EV simulator disabled while waiting. Aborting wait.")

    async def set_initial_state(self):
        """Sets the EV simulator to a known initial state ('A')."""
        if not SERVER_SETTINGS.get("use_simulator"): return
        logger.info("Setting initial EV simulator state to 'A'...")
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(self._url_set_state, json={"state": "A"}, timeout=5) as r:
                    if r.status != 200: logger.error(f"Failed to set initial EV state: {r.status}.")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Error setting initial EV state: {e}")

    async def probe_simulator_availability(self):
        """Quietly checks if the simulator is available and updates state."""
        is_available_now = False
        try:
            timeout = aiohttp.ClientTimeout(total=2)  # Short timeout for a probe
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self._url_status) as resp:
                    if resp.status == 200:
                        is_available_now = True
        except (aiohttp.ClientError, asyncio.TimeoutError):
            is_available_now = False  # It's not available
        finally:
            # Update global availability state if it has changed
            if SERVER_SETTINGS.get("ev_simulator_available") != is_available_now:
                logger.info(f"EV simulator availability probe status: {is_available_now}")
                SERVER_SETTINGS["ev_simulator_available"] = is_available_now
                if is_available_now:
                    # Automatically enable simulator mode if it becomes available and no user interaction is needed
                    SERVER_SETTINGS["use_simulator"] = True
                    logger.info("Automatically enabled EV simulator mode as it is now available.")

    async def _poll_and_wait(self):
        """Performs a single poll of the simulator status and then waits."""
        backoff = EV_STATUS_POLL_INTERVAL
        is_available_now = False
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(self._url_status, timeout=5) as r:
                    if r.status == 200:
                        EV_SIMULATOR_STATE.update(await r.json())
                        is_available_now = True
                    else:
                        EV_SIMULATOR_STATE.clear()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            EV_SIMULATOR_STATE.clear()
            backoff = min(max(backoff * 2, EV_STATUS_POLL_INTERVAL), 60)
        
        if SERVER_SETTINGS.get("ev_simulator_available") != is_available_now:
            logger.info(f"EV simulator availability changed to: {is_available_now}")
            SERVER_SETTINGS["ev_simulator_available"] = is_available_now

        await self._status_streamer.broadcast_status(EV_SIMULATOR_STATE)

        sleep_task = asyncio.create_task(asyncio.sleep(backoff))
        trigger_task = asyncio.create_task(self._refresh_trigger.wait())
        done, pending = await asyncio.wait({sleep_task, trigger_task}, return_when=asyncio.FIRST_COMPLETED)
        if trigger_task in done: self._refresh_trigger.clear()
        for task in pending: task.cancel()