from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .models import OptionChoice, OptionGroup
from .options import OptionService
from .paths import DEFAULT_PREVIEW
from .repository import ModRepository, sanitize_name

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


class ArsenalImportService:
    def __init__(self, repository: ModRepository, option_service: OptionService) -> None:
        self.repository = repository
        self.option_service = option_service

    @staticmethod
    def is_arsenal_library(path: Path) -> bool:
        path = Path(path)
        return (path / "hd2a_data.json").is_file() and (path / "mods").is_dir()

    def import_library(self, source_root: Path) -> int:
        source_root = Path(source_root)
        data_file = source_root / "hd2a_data.json"
        if not data_file.is_file():
            raise FileNotFoundError(data_file)
        data = json.loads(data_file.read_text(encoding="utf-8"), strict=False)
        profile_name = str(data.get("selectedProfile") or "default")
        profile = (data.get("modsList") or {}).get(profile_name) or (data.get("modsList") or {}).get("default") or {}
        mods = profile.get("mods") or []
        if not isinstance(mods, list):
            raise ValueError("hd2a_data.json 中没有可导入的 mods 列表")
        imported = 0
        for order, raw_mod in enumerate(mods, start=1):
            if not isinstance(raw_mod, dict):
                continue
            if self.import_mod(raw_mod, order):
                imported += 1
        return imported

    def import_mod(self, raw_mod: dict[str, Any], order: int) -> bool:
        source_dir = Path(self._clean(raw_mod.get("path") or ""))
        if not source_dir.is_dir():
            return False
        guid = self._clean(raw_mod.get("uuid") or raw_mod.get("contentHash") or "")
        label = self._clean(raw_mod.get("label") or source_dir.name)
        description = self._clean(raw_mod.get("description") or "")
        enabled = bool(raw_mod.get("enabled", True))
        existing = self.repository.find_by_guid(guid)
        if existing:
            mod_dir = self.repository.mods_dir / existing.id
            mod_order = existing.order
            category = existing.category or self._category(raw_mod)
        else:
            mod_dir = self.repository.create_mod(label, order=order, description=description, category=self._category(raw_mod), guid=guid)
            mod_order = order
            category = self._category(raw_mod)
        self._clear_generated_content(mod_dir)
        preview = self._copy_preview(raw_mod, source_dir, mod_dir)
        self.repository.save_meta(
            mod_dir.name,
            label,
            "",
            self._link(raw_mod),
            mod_order,
            enabled,
            description,
            category,
            preview,
            guid=guid,
        )
        groups = self._build_groups(mod_dir.name, source_dir, raw_mod.get("options") or [])
        if not groups:
            groups = [self._default_group(mod_dir.name, source_dir)]
        self.option_service.save_groups(mod_dir.name, groups)
        self.repository.clear_payload_mtime_cache(mod_dir.name)
        return True

    def _clear_generated_content(self, mod_dir: Path) -> None:
        for name in ("payloads", "images", "options.yml"):
            target = mod_dir / name
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()

    def _build_groups(self, mod_id: str, source_dir: Path, raw_options: list[Any]) -> list[OptionGroup]:
        groups: list[OptionGroup] = []
        for raw_option in raw_options:
            if not isinstance(raw_option, dict):
                continue
            suboptions = [item for item in raw_option.get("suboptions") or [] if isinstance(item, dict)]
            if suboptions:
                choices = [self._choice_from_raw(mod_id, source_dir, sub, raw_option) for sub in suboptions]
                groups.append(
                    OptionGroup(
                        id=self._id(raw_option.get("name") or "option"),
                        name=self._clean(raw_option.get("name") or "选项"),
                        description=self._clean(raw_option.get("description") or ""),
                        image=self._copy_image(mod_id, source_dir, raw_option.get("iconPath")),
                        choices=choices,
                        multiple=False,
                    )
                )
            else:
                choice = self._choice_from_raw(mod_id, source_dir, raw_option, None)
                groups.append(
                    OptionGroup(
                        id=self._id(raw_option.get("name") or "option"),
                        name=self._clean(raw_option.get("name") or "选项"),
                        description=self._clean(raw_option.get("description") or ""),
                        image=self._copy_image(mod_id, source_dir, raw_option.get("iconPath")),
                        choices=[choice],
                        multiple=False,
                    )
                )
        return groups

    def _choice_from_raw(self, mod_id: str, source_dir: Path, raw_choice: dict[str, Any], parent: dict[str, Any] | None) -> OptionChoice:
        name = self._clean(raw_choice.get("name") or "默认")
        includes = raw_choice.get("include") or []
        if parent and not includes:
            includes = parent.get("include") or []
        choice_id = self._id(name)
        payload = self.option_service.payloads_dir(mod_id) / choice_id
        self._copy_includes(source_dir, payload, includes)
        return OptionChoice(
            id=choice_id,
            name=name,
            description=self._clean(raw_choice.get("description") or ""),
            image=self._copy_image(mod_id, source_dir, raw_choice.get("iconPath")),
            payload=Path("payloads") / choice_id,
            selected=bool(raw_choice.get("enabled", False)),
        )

    def _default_group(self, mod_id: str, source_dir: Path) -> OptionGroup:
        choice_id = "default"
        payload = self.option_service.payloads_dir(mod_id) / choice_id
        self._copy_patch_files(source_dir, payload)
        return OptionGroup(
            id="arsenal_default",
            name="默认文件",
            description="从 HD2 Arsenal 无选项 Mod 导入",
            choices=[OptionChoice(id=choice_id, name="默认", payload=Path("payloads/default"), selected=True)],
            multiple=False,
        )

    def _copy_includes(self, source_dir: Path, payload: Path, includes: list[Any]) -> None:
        if not includes:
            payload.mkdir(parents=True, exist_ok=True)
            return
        for include in includes:
            include_path = source_dir / self._clean(include)
            if include_path.is_dir():
                self._copy_patch_files(include_path, payload)
            elif include_path.is_file() and "patch_" in include_path.name:
                payload.mkdir(parents=True, exist_ok=True)
                shutil.copy2(include_path, payload / include_path.name)

    def _copy_patch_files(self, source: Path, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        for item in source.rglob("*"):
            if not item.is_file() or "patch_" not in item.name:
                continue
            destination = target / item.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)

    def _copy_preview(self, raw_mod: dict[str, Any], source_dir: Path, mod_dir: Path) -> str | None:
        image = self._resolve_image(source_dir, raw_mod.get("iconPath")) or self._find_image(source_dir) or self._default_preview()
        if not image:
            return None
        target = mod_dir / "images" / "preview.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image, target)
        return "images/preview.png"

    def _copy_image(self, mod_id: str, source_dir: Path, value: Any) -> Path | None:
        image = self._resolve_image(source_dir, value)
        if not image:
            return None
        target_dir = self.option_service.images_dir(mod_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{self._id(str(image))}{image.suffix.lower()}"
        shutil.copy2(image, target)
        return target.relative_to(self.repository.mods_dir / mod_id)

    def _resolve_image(self, source_dir: Path, value: Any) -> Path | None:
        text = self._clean(value or "")
        if not text:
            return None
        path = Path(text)
        path = path if path.is_absolute() else source_dir / path
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            return path
        return None

    def _find_image(self, source_dir: Path) -> Path | None:
        for name in ("preview.png", "icon.png"):
            path = source_dir / name
            if path.is_file():
                return path
        for item in source_dir.iterdir():
            if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES:
                return item
        return None

    def _default_preview(self) -> Path | None:
        return DEFAULT_PREVIEW if DEFAULT_PREVIEW.exists() else None

    def _category(self, raw_mod: dict[str, Any]) -> str:
        tags = raw_mod.get("tags") or []
        return self._clean(tags[0]) if tags else "HD2 Arsenal"

    def _link(self, raw_mod: dict[str, Any]) -> str:
        nexus = raw_mod.get("nexusData") or {}
        mod_id = nexus.get("modId") if isinstance(nexus, dict) else None
        return f"https://www.nexusmods.com/helldivers2/mods/{mod_id}" if mod_id else ""

    def _clean(self, value: Any) -> str:
        return str(value).strip().strip('"\'').replace("\\r", "").replace("\\n", "").replace("\r", "").replace("\n", "")

    def _id(self, value: Any) -> str:
        return sanitize_name(self._clean(value)).lower().replace(" ", "_")
