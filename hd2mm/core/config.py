from __future__ import annotations

from pathlib import Path

from .paths import CONFIG_FILE, find_helldivers2_data_dir, normalize_game_data_path


class ConfigService:
    def __init__(self, config_file: Path = CONFIG_FILE) -> None:
        self.config_file = config_file

    def load_install_dir(self) -> Path | None:
        if not self.config_file.exists():
            detected = find_helldivers2_data_dir()
            if detected:
                self.save_install_dir(detected)
            return detected

        value = self.config_file.read_text(encoding="utf-8", errors="ignore").strip()
        return normalize_game_data_path(value) if value else None

    def save_install_dir(self, path: str | Path) -> Path:
        data_dir = normalize_game_data_path(path)
        self.config_file.write_text(str(data_dir), encoding="utf-8")
        return data_dir
