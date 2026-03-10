"""Atomic file write utilities to prevent data corruption during power loss."""

import json
import os
import tempfile
import shutil
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def atomic_write_json(file_path: str | Path, data: Any, indent: int = 2) -> None:
    """
    Atomically write JSON data to a file using temp file + rename pattern.

    This prevents corruption during power loss by:
    1. Writing to a temporary file in the same directory
    2. Calling fsync to force disk write
    3. Atomically renaming temp file to target (atomic operation on Linux)

    Args:
        file_path: Target file path
        data: Python object to serialize as JSON
        indent: JSON indentation level
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Create temp file in same directory (required for atomic rename)
    fd, temp_path = tempfile.mkstemp(
        dir=file_path.parent,
        prefix=f".{file_path.name}.",
        suffix=".tmp"
    )

    try:
        # Write JSON to temp file
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=indent)
            f.flush()
            # Force write to disk before rename
            os.fsync(f.fileno())

        # Atomic rename (on Linux, this is guaranteed atomic)
        os.replace(temp_path, file_path)
        logger.debug(f"Atomically wrote to {file_path}")

    except Exception as e:
        # Clean up temp file on error
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        logger.error(f"Error during atomic write to {file_path}: {e}")
        raise


def atomic_read_json(file_path: str | Path, default: Any = None) -> Any:
    """
    Read JSON data from a file with corruption detection and recovery.

    If the file is corrupted:
    1. Creates a backup of the corrupted file
    2. Returns the default value

    Args:
        file_path: File path to read
        default: Default value to return if file doesn't exist or is corrupted

    Returns:
        Parsed JSON data or default value
    """
    file_path = Path(file_path)

    if not file_path.exists():
        logger.debug(f"File does not exist: {file_path}, returning default")
        return default

    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        logger.debug(f"Successfully read {file_path}")
        return data

    except json.JSONDecodeError as e:
        # File is corrupted - create backup and return default
        backup_path = file_path.with_suffix(f"{file_path.suffix}.corrupted.{os.getpid()}")
        try:
            shutil.copy2(file_path, backup_path)
            logger.error(
                f"Corrupted JSON file detected: {file_path}. "
                f"Backup created at {backup_path}. "
                f"Using default value. Error: {e}"
            )
        except Exception as backup_error:
            logger.error(f"Failed to create backup of corrupted file: {backup_error}")

        return default

    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return default
