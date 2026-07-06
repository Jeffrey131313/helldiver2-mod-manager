from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

import yaml

from .models import ModInfo
from .paths import DEFAULT_PREVIEW, MODS_DIR


class ModRepository:
    def __init__(self, mods_dir: Path = MODS_DIR) -> None:
        self.mods_dir = mods_dir
        self.payload_mtime_cache: dict[str, datetime | None] = {}

    def ensure(self) -> None:
        self.mods_dir.mkdir(exist_ok=True)

    def list_mods(self) -> list[ModInfo]:
        self.ensure()
        mods: list[ModInfo] = []
        for mod_dir in self.mods_dir.iterdir():
            mod = self._load_mod(mod_dir)
            if mod is not None:
                mods.append(mod)
        return sorted(mods, key=lambda mod: (mod.order, mod.name.lower()))

    def list_mods_with_progress(self, callback=None) -> list[ModInfo]:
        self.ensure()
        mod_dirs = [mod_dir for mod_dir in self.mods_dir.iterdir() if mod_dir.is_dir() and (mod_dir / "mod.yml").exists()]
        total = len(mod_dirs)
        mods: list[ModInfo] = []
        for index, mod_dir in enumerate(mod_dirs, start=1):
            if callback:
                callback(index, total, mod_dir.name)
            mod = self._load_mod(mod_dir)
            if mod is not None:
                mods.append(mod)
        return sorted(mods, key=lambda mod: (mod.order, mod.name.lower()))

    def get(self, mod_id: str) -> ModInfo:
        mod = self._load_mod(self.mods_dir / mod_id)
        if mod is None:
            raise FileNotFoundError(mod_id)
        return mod

    def refresh_payload_mtime(self, mod_id: str) -> datetime | None:
        updated_at = self._latest_payload_mtime(self.mods_dir / mod_id)
        self.payload_mtime_cache[mod_id] = updated_at
        return updated_at

    def clear_payload_mtime_cache(self, mod_id: str | None = None) -> None:
        if mod_id is None:
            self.payload_mtime_cache.clear()
            return
        self.payload_mtime_cache.pop(mod_id, None)

    def next_order(self) -> int:
        orders = [mod.order for mod in self.list_mods()]
        return max(orders, default=0) + 1

    def create_mod(
        self,
        name: str,
        author: str = "",
        link: str = "",
        order: int | None = None,
        description: str = "",
        category: str = "",
        guid: str = "",
    ) -> Path:
        mod_dir = self.unique_folder(name)
        mod_dir.mkdir(parents=True)
        if order is None:
            order = self.next_order()
        self.save_meta(mod_dir.name, name, author, link, order, True, description, category=category, guid=guid)
        return mod_dir

    def save_meta(
        self,
        mod_id: str,
        name: str,
        author: str,
        link: str,
        order: int,
        enabled: bool,
        description: str = "",
        category: str = "",
        preview: str | None = None,
        guid: str | None = None,
    ) -> None:
        mod_dir = self.mods_dir / mod_id
        current = self.read_yaml(mod_dir / "mod.yml") if (mod_dir / "mod.yml").exists() else {}
        data = {
            "guid": guid if guid is not None else current.get("guid", ""),
            "name": name,
            "author": author,
            "link": link,
            "order": int(order),
            "enabled": bool(enabled),
            "description": description,
            "category": category if category is not None else current.get("category", ""),
            "preview": preview if preview is not None else current.get("preview"),
        }
        self.write_yaml(mod_dir / "mod.yml", data)

    def save_order(self, mod_id: str, order: int) -> None:
        mod_file = self.mods_dir / mod_id / "mod.yml"
        current = self.read_yaml(mod_file) if mod_file.exists() else {}
        current["order"] = int(order)
        self.write_yaml(mod_file, current)

    def find_by_guid(self, guid: str) -> ModInfo | None:
        normalized_guid = guid.strip().lower()
        if not normalized_guid:
            return None
        for mod in self.list_mods():
            if mod.guid.strip().lower() == normalized_guid:
                return mod
        return None

    def set_enabled(self, mod_id: str, enabled: bool) -> None:
        mod = self.get(mod_id)
        self.save_meta(mod.id, mod.name, mod.author, mod.link, mod.order, enabled, mod.description, mod.category)

    def delete(self, mod_id: str) -> None:
        self.clear_payload_mtime_cache(mod_id)
        shutil.rmtree(self.mods_dir / mod_id)

    def _load_mod(self, mod_dir: Path) -> ModInfo | None:
        if not mod_dir.is_dir():
            return None
        meta_file = mod_dir / "mod.yml"
        if not meta_file.exists():
            return None
        raw = self.read_yaml(meta_file) or {}
        options = self.read_yaml(mod_dir / "options.yml") if (mod_dir / "options.yml").exists() else []
        preview_path = self._ensure_preview(mod_dir, raw)
        updated_at = self.payload_mtime_cache.get(mod_dir.name)
        if mod_dir.name not in self.payload_mtime_cache:
            updated_at = self.refresh_payload_mtime(mod_dir.name)
        return ModInfo(
            id=mod_dir.name,
            name=str(raw.get("name") or mod_dir.name),
            guid=str(raw.get("guid") or ""),
            author=str(raw.get("author") or ""),
            link=str(raw.get("link") or ""),
            enabled=bool(raw.get("enabled", True)),
            order=int(raw.get("order", 9999) or 9999),
            description=str(raw.get("description") or ""),
            category=str(raw.get("category") or ""),
            preview_path=preview_path or DEFAULT_PREVIEW,
            option_count=len(options or []),
            updated_at=updated_at,
        )

    def _ensure_preview(self, mod_dir: Path, raw: dict) -> Path | None:
        preview = raw.get("preview")
        preview_path = mod_dir / preview if preview else None
        if preview_path and preview_path.exists():
            return preview_path
        if not DEFAULT_PREVIEW.exists():
            return None
        target = mod_dir / "images" / "preview.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(DEFAULT_PREVIEW, target)
        raw["preview"] = "images/preview.png"
        self.write_yaml(mod_dir / "mod.yml", raw)
        return target

    def _latest_payload_mtime(self, mod_dir: Path) -> datetime | None:
        payloads_dir = mod_dir / "payloads"
        if not payloads_dir.exists():
            return None
        latest: float | None = None
        for file in payloads_dir.rglob("*"):
            if not file.is_file():
                continue
            mtime = file.stat().st_mtime
            latest = mtime if latest is None else max(latest, mtime)
        return datetime.fromtimestamp(latest) if latest is not None else None

    def unique_folder(self, desired_name: str) -> Path:
        safe_name = sanitize_name(desired_name or "未命名Mod")
        candidate = self.mods_dir / safe_name
        index = 1
        while candidate.exists():
            candidate = self.mods_dir / f"{safe_name}({index})"
            index += 1
        return candidate

    @staticmethod
    def read_yaml(path: Path) -> object:
        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    @staticmethod
    def write_yaml(path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)


def sanitize_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", value.strip())
    return cleaned or "未命名Mod"
