"""
Graceful shutdown handler for enrichment operations.

This module provides signal handling for SIGINT (Ctrl+C) and SIGTERM
to enable graceful shutdown of enrichment operations per FR-053.

The handler allows in-flight API requests to complete and commits
the current batch before exiting.
"""

from __future__ import annotations

import logging
import signal
import threading
from types import FrameType
from typing import Any, Callable, Optional, Union

from chronovista.exceptions import GracefulShutdownException

# Type for signal handlers as returned by signal.getsignal()
SignalHandlerType = Union[Callable[[int, Optional[FrameType]], Any], int, None]

logger = logging.getLogger(__name__)


class ShutdownHandler:
    """
    Handler for graceful shutdown of enrichment operations.

    This class manages signal handling for SIGINT (Ctrl+C) and SIGTERM,
    allowing the enrichment process to complete the current API request,
    commit the current batch, and write a partial report before exiting.

    Implements FR-053: Graceful shutdown on SIGINT/SIGTERM.

    Attributes
    ----------
    shutdown_requested : bool
        True if a shutdown signal has been received.
    signal_received : str | None
        The name of the signal received (e.g., "SIGINT", "SIGTERM").

    Examples
    --------
    >>> handler = ShutdownHandler()
    >>> handler.install()
    >>> try:
    ...     for video in videos:
    ...         handler.check_shutdown()  # Raises if shutdown requested
    ...         await process_video(video)
    ... except GracefulShutdownException:
    ...     await commit_current_batch()
    ...     raise typer.Exit(130)
    ... finally:
    ...     handler.uninstall()
    """

    # Class-level singleton for signal handling
    _instance: Optional["ShutdownHandler"] = None
    _lock = threading.Lock()

    # Instance attributes with type hints (for mypy)
    _initialized: bool
    _shutdown_requested: bool
    _signal_received: Optional[str]
    _original_sigint: SignalHandlerType
    _original_sigterm: SignalHandlerType
    _installed: bool

    def __new__(cls) -> "ShutdownHandler":
        """Ensure singleton instance for signal handling."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        """Initialize ShutdownHandler."""
        if self._initialized:
            return

        self._shutdown_requested = False
        self._signal_received = None
        self._original_sigint = None
        self._original_sigterm = None
        self._installed = False
        self._initialized = True

    @property
    def shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested

    @property
    def signal_received(self) -> str | None:
        """Get the name of the signal that triggered shutdown."""
        return self._signal_received

    def install(self) -> None:
        """
        Install signal handlers for SIGINT and SIGTERM.

        Saves original handlers so they can be restored on uninstall.
        """
        if self._installed:
            return

        # Save original handlers
        self._original_sigint = signal.getsignal(signal.SIGINT)
        self._original_sigterm = signal.getsignal(signal.SIGTERM)

        # Install custom handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self._installed = True
        logger.debug("Shutdown handlers installed for SIGINT and SIGTERM")

    def uninstall(self) -> None:
        """
        Uninstall signal handlers and restore original handlers.
        """
        if not self._installed:
            return

        # Restore original handlers
        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)
        if self._original_sigterm is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm)

        self._installed = False
        self._shutdown_requested = False
        self._signal_received = None
        logger.debug("Shutdown handlers uninstalled, original handlers restored")

    def _handle_signal(self, signum: int, frame: object) -> None:
        """
        Handle incoming shutdown signal.

        Parameters
        ----------
        signum : int
            Signal number (e.g., signal.SIGINT, signal.SIGTERM).
        frame : object
            Current stack frame (unused but required by signal API).
        """
        signal_name = signal.Signals(signum).name
        self._signal_received = signal_name
        self._shutdown_requested = True

        logger.warning(
            f"Received {signal_name} - initiating graceful shutdown. "
            f"Completing current operation..."
        )

    def check_shutdown(self) -> None:
        """
        Check if shutdown has been requested and raise exception if so.

        This method should be called at safe points in the enrichment
        loop (e.g., between batch commits) to allow graceful shutdown.

        Raises
        ------
        GracefulShutdownException
            If a shutdown signal has been received.
        """
        if self._shutdown_requested:
            raise GracefulShutdownException(
                message=f"Graceful shutdown requested via {self._signal_received}",
                signal_received=self._signal_received or "SIGINT",
            )

    def reset(self) -> None:
        """
        Reset shutdown state.

        This allows the handler to be reused for multiple operations.
        Should be called at the start of each enrichment run.
        """
        self._shutdown_requested = False
        self._signal_received = None
        logger.debug("Shutdown handler state reset")


# Global singleton instance
shutdown_handler = ShutdownHandler()


def get_shutdown_handler() -> ShutdownHandler:
    """
    Get the global shutdown handler instance.

    Returns
    -------
    ShutdownHandler
        The global shutdown handler singleton.
    """
    return shutdown_handler
