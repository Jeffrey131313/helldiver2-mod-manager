from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

from .options import OptionService
from .paths import MODS_DIR, OTHER_DIR
from .repository import ModRepository

PATCH_HEAD = re.compile(r"^(.*?\.patch_\d+)", re.IGNORECASE)
PATCH_FILE = re.compile(r"^(.+?)\.patch_(\d+)(\.\w+)?$", re.IGNORECASE)


class InstallService:
    def __init__(self, repository: ModRepository, option_service: OptionService, install_dir: Path | None) -> None:
        self.repository = repository
        self.option_service = option_service
        self.install_dir = install_dir

    def set_install_dir(self, install_dir: Path) -> None:
        self.install_dir = install_dir

    def remove_all_patch_files(self) -> int:
        self._require_install_dir()
        removed = 0
        for file in self.install_dir.iterdir():
            if file.is_file() and "patch_" in file.name:
                file.unlink()
                removed += 1
        return removed

    def install_enabled_mods(self) -> int:
        self._require_install_dir()
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self._remove_previous_install()

        grouped_files: dict[str, dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))
        for mod in self.repository.list_mods():
            if not mod.enabled:
                continue
            for payload_root in self.option_service.selected_payload_roots(mod.id):
                if payload_root.exists():
                    self._collect_patch_files(payload_root, grouped_files)
        if OTHER_DIR.exists():
            self._collect_patch_files(OTHER_DIR, grouped_files)
        return self._copy_grouped_files(grouped_files)

    def _copy_grouped_files(self, grouped_files: dict[str, dict[str, list[Path]]]) -> int:
        mod_number: dict[str, int] = {}
        mod_name: dict[int, str] = {}
        mod_list: dict[int, int] = {}
        install_index = 1
        copied = 0
        for file_head, patch_group in grouped_files.items():
            for files_in_group in patch_group.values():
                mod_number.setdefault(file_head, 0)
                for file in files_in_group:
                    match = PATCH_FILE.match(file.name)
                    if not match:
                        continue
                    file_prefix, _, file_suffix = match.groups()
                    file_suffix = file_suffix or ""
                    while True:
                        new_file_name = f"{file_prefix}.patch_{mod_number[file_head]}{file_suffix}"
                        destination = self.install_dir / new_file_name
                        if not destination.exists():
                            break
                        mod_number[file_head] += 1
                    shutil.copy2(file, destination)
                    mod_name[install_index] = file_prefix
                    mod_list[install_index] = mod_number[file_head]
                    install_index += 1
                    copied += 1
                mod_number[file_head] += 1
        (MODS_DIR / "mod_name.json").write_text(json.dumps(mod_name, ensure_ascii=False, indent=4), encoding="utf-8")
        (MODS_DIR / "mod_list.json").write_text(json.dumps(mod_list, ensure_ascii=False, indent=4), encoding="utf-8")
        return copied

    def _collect_patch_files(self, folder: Path, grouped_files: dict[str, dict[str, list[Path]]]) -> None:
        for file in sorted(folder.rglob("*")):
            if not file.is_file():
                continue
            match = PATCH_HEAD.match(file.name)
            if not match:
                continue
            head_match = re.match(r"^(\S+)\.patch_(\d+)", match.group(1), re.IGNORECASE)
            if head_match:
                file_head, patch_number = head_match.groups()
                grouped_files[file_head][patch_number].append(file)

    def _remove_previous_install(self) -> None:
        try:
            mod_name = json.loads((MODS_DIR / "mod_name.json").read_text(encoding="utf-8"))
            mod_list = json.loads((MODS_DIR / "mod_list.json").read_text(encoding="utf-8"))
        except Exception:
            return
        suffixes = ["", ".gpu_resources", ".stream"]
        for name in mod_name.values():
            for number in mod_list.values():
                for suffix in suffixes:
                    target = self.install_dir / f"{name}.patch_{number}{suffix}"
                    target.unlink(missing_ok=True)

    def _require_install_dir(self) -> None:
        if not self.install_dir:
            raise RuntimeError("未配置 Helldivers 2 data 目录")
