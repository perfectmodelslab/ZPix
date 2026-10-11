"""OS abstractions."""

import os
from pathlib import Path
from subprocess import run
from sys import platform

MAC_KEY_NAMES = {"Alt": "Option"}
"""Key names labeled differently on Mac keyboards."""


def open_with_default_app(target: Path | str):
    """Open a directory, file or URL using system's default app.

    Args:
        target: Directory, file or URL to open.

    May raise an exception.
    """
    match platform:
        case "linux":
            run(["xdg-open", target], check=True)
        case "darwin":  # macOS
            run(["open", target], check=True)
        case "win32":
            os.startfile(target)
        case _:
            raise OSError(f"Unsupported platform: {platform}")


def get_key_name(key: str) -> str:
    """Get name of a key as labeled on system's keyboards."""
    match platform:
        case "darwin":
            return MAC_KEY_NAMES.get(key, key)
        case _:
            return key
