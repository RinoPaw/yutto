from __future__ import annotations

import os
import sys
from pathlib import Path


def user_config_home() -> Path:
    """Return the per-user configuration directory used by yutto."""
    if (env := os.environ.get("XDG_CONFIG_HOME")) and (path := Path(env)).is_absolute():
        return path
    home = Path.home()
    if sys.platform == "win32":
        return home / "AppData" / "Roaming"
    return home / ".config"
