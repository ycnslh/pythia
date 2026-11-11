"""
Tiny JSON state store.

Keeps the few things that must survive a restart (event history, RSS "seen" ids,
Uptime Kuma states, recent titles) as small JSON files in DATA_DIR. Writes are
atomic (temp file + rename). If the directory is unset or not writable the store
disables itself and PYTHIA keeps working purely in memory.
"""

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def state_key(prefix: str, name: str) -> str:
    """Filesystem-safe, collision-resistant key for a user-supplied name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "x"
    digest = hashlib.sha1(name.encode()).hexdigest()[:6]
    return f"{prefix}-{slug}-{digest}"


class StateStore:
    def __init__(self, directory: str | None) -> None:
        self._dir: Path | None = None
        if not directory:
            logger.info("Persistence disabled (DATA_DIR is empty)")
            return
        path = Path(directory)
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write-test"
            probe.write_text("ok")
            probe.unlink()
        except OSError as e:
            logger.warning("DATA_DIR %s is not writable (%s) — persistence disabled", path, e)
            return
        self._dir = path
        logger.info("Persistence enabled in %s", path)

    @property
    def enabled(self) -> bool:
        return self._dir is not None

    def load(self, key: str, default: Any = None) -> Any:
        if self._dir is None:
            return default
        try:
            return json.loads((self._dir / f"{key}.json").read_text())
        except FileNotFoundError:
            return default
        except (OSError, ValueError) as e:
            logger.warning("Could not read state %r (%s) — starting empty", key, e)
            return default

    def save(self, key: str, value: Any) -> None:
        if self._dir is None:
            return
        target = self._dir / f"{key}.json"
        tmp = self._dir / f".{key}.json.tmp"
        try:
            tmp.write_text(json.dumps(value))
            os.replace(tmp, target)
        except (OSError, TypeError, ValueError) as e:
            logger.warning("Could not save state %r: %s", key, e)
