from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from .models import OptionChoice, OptionGroup
from .options import OptionService
from .repository import ModRepository, sanitize_name


class LegacyMigrationService:
    def __init__(self, repository: ModRepository, option_service: OptionService) -> None:
        self.repository = repository
        self.option_service = option_service

    def migrate_runtime_mods(self) -> int:
        self.repository.ensure()
        legacy_order = self._load_legacy_order()
        migrated = 0
        for mod_dir in sorted(item for item in self.repository.mods_dir.iterdir() if item.is_dir()):
            if self._migrate_mod_dir(mod_dir, legacy_order.get(mod_dir.name)):
                migrated += 1
        return migrated

    def _migrate_mod_dir(self, mod_dir: Path, legacy_order: int | None) -> bool:
        if (mod_dir / "mod.yml").exists() or (mod_dir / "options.yml").exists():
            return False
        info_file = mod_dir / "mod_info.yml"
        files_dir = mod_dir / "files"
        if not info_file.exists() or not files_dir.exists() or not files_dir.is_dir():
            return False
        raw = self.repository.read_yaml(info_file) or {}
        name = str(raw.get("name") or mod_dir.name)
        author = str(raw.get("author") or "")
        link = str(raw.get("link") or "")
        description = str(raw.get("description") or "由旧版 Mod 数据自动迁移")
        enabled = bool(raw.get("enabled", True))
        order = int(legacy_order if legacy_order is not None else raw.get("order", 9999) or 9999)
        self.repository.save_meta(mod_dir.name, name, author, link, order, enabled, description, "旧版迁移")
        choices = self._migrate_choices(mod_dir, files_dir)
        self.option_service.save_groups(
            mod_dir.name,
            [
                OptionGroup(
                    id="legacy_variants",
                    name="旧版差分",
                    description="从旧版 files/other 结构自动迁移",
                    choices=choices,
                    multiple=False,
                )
            ],
        )
        self._migrate_preview(mod_dir)
        self.repository.clear_payload_mtime_cache(mod_dir.name)
        return True

    def _migrate_choices(self, mod_dir: Path, files_dir: Path) -> list[OptionChoice]:
        choices: list[OptionChoice] = []
        child_dirs = sorted(item for item in files_dir.iterdir() if item.is_dir())
        patch_files = sorted(item for item in files_dir.iterdir() if item.is_file() and "patch_" in item.name)
        other_dir = mod_dir / "other"
        if child_dirs:
            for index, child_dir in enumerate(child_dirs):
                choice_id = sanitize_name(child_dir.name)
                payload = self.option_service.payloads_dir(mod_dir.name) / choice_id
                self._copy_patch_payload(child_dir, payload)
                choices.append(
                    OptionChoice(
                        id=choice_id,
                        name=child_dir.name,
                        description="旧版差分迁移",
                        payload=Path("payloads") / choice_id,
                        selected=index == 0,
                    )
                )
        elif patch_files:
            payload = self.option_service.payloads_dir(mod_dir.name) / "default"
            self._copy_patch_payload(files_dir, payload)
            choices.append(OptionChoice(id="default", name="默认", description="旧版默认文件", payload=Path("payloads/default"), selected=True))
        if other_dir.exists():
            existing_ids = {choice.id for choice in choices}
            for variant_dir in sorted(item for item in other_dir.iterdir() if item.is_dir()):
                choice_id = sanitize_name(variant_dir.name)
                if choice_id in existing_ids:
                    continue
                payload = self.option_service.payloads_dir(mod_dir.name) / choice_id
                self._copy_patch_payload(variant_dir, payload)
                choices.append(
                    OptionChoice(
                        id=choice_id,
                        name=variant_dir.name,
                        description="旧版差分迁移",
                        payload=Path("payloads") / choice_id,
                        selected=not choices,
                    )
                )
        if not choices:
            payload = self.option_service.payloads_dir(mod_dir.name) / "default"
            payload.mkdir(parents=True, exist_ok=True)
            choices.append(OptionChoice(id="default", name="默认", description="旧版默认文件", payload=Path("payloads/default"), selected=True))
        return choices

    def _copy_patch_payload(self, source: Path, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        for item in source.rglob("*"):
            if not item.is_file() or "patch_" not in item.name:
                continue
            relative = item.relative_to(source)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)

    def _migrate_preview(self, mod_dir: Path) -> None:
        preview = mod_dir / "preview.png"
        if not preview.exists():
            return
        target = mod_dir / "images" / "preview.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(preview, target)
        mod = self.repository.get(mod_dir.name)
        self.repository.save_meta(mod.id, mod.name, mod.author, mod.link, mod.order, mod.enabled, mod.description, mod.category, "images/preview.png")

    def _load_legacy_order(self) -> dict[str, int]:
        path = self.repository.mods_dir / "mod_sorted.yml"
        if not path.exists():
            return {}
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        result: dict[str, int] = {}
        for key, value in raw.items():
            try:
                result[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return result
