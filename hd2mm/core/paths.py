from __future__ import annotations

import os
import re
import sys
from pathlib import Path

APP_ID = "553850"
MODS_DIR = Path("mods")
OTHER_DIR = Path("other")
TEMP_DIR = Path("temp")
CONFIG_FILE = Path("config.yml")
MOD_LOCKS_FILE = Path("mod_locks.yml")
WAR_STATUS_CACHE_FILE = Path("war_status_cache.json")
DEFAULT_PREVIEW = Path("default.png")
ICON_FILE = Path("app_icon.ico")


def resource_path(relative_path: str | Path) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path.cwd()))
    return base_path / relative_path


def ensure_workspace_dirs() -> None:
    MODS_DIR.mkdir(exist_ok=True)
    OTHER_DIR.mkdir(exist_ok=True)
    TEMP_DIR.mkdir(exist_ok=True)


def clear_temp_dir() -> None:
    TEMP_DIR.mkdir(exist_ok=True)
    for item in TEMP_DIR.iterdir():
        if item.is_dir():
            import shutil

            shutil.rmtree(item)
        else:
            item.unlink(missing_ok=True)


def normalize_game_data_path(path: str | Path) -> Path:
    normalized = Path(path).expanduser()
    text = os.path.normpath(str(normalized))
    if text.lower().endswith(os.path.normpath(r"Helldivers 2").lower()):
        return Path(text) / "data"
    return Path(text)


def find_helldivers2_data_dir() -> Path | None:
    if sys.platform != "win32":
        return None

    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
        winreg.CloseKey(key)
    except Exception:
        return None

    steam_path = Path(os.path.normpath(steam_path))
    library_vdf = steam_path / "steamapps" / "libraryfolders.vdf"
    if not library_vdf.exists():
        return None

    libraries = [steam_path / "steamapps"]
    content = library_vdf.read_text(encoding="utf-8", errors="ignore")
    for match in re.finditer(r'"\d+"\s+"([^"]+)"', content):
        libraries.append(Path(match.group(1).replace("\\\\", "\\")) / "steamapps")

    for library in libraries:
        manifest = library / f"appmanifest_{APP_ID}.acf"
        if not manifest.exists():
            continue
        data = manifest.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r'"installdir"\s+"([^"]+)"', data)
        if match:
            return library / "common" / match.group(1) / "data"
    return None
