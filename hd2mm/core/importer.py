from __future__ import annotations

import random
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from py7zr import SevenZipFile

from .manifest import parse_manifest_metadata, parse_manifest_options
from .models import ImportOptions, OptionChoice, OptionGroup
from .options import OptionService
from .paths import DEFAULT_PREVIEW, TEMP_DIR
from .repository import ModRepository

PATCH_PATTERN = re.compile(r".+\.patch_\d+(?:\..+)?$", re.IGNORECASE)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


class ModImporter:
    def __init__(self, repository: ModRepository, option_service: OptionService) -> None:
        self.repository = repository
        self.option_service = option_service

    def import_mod(self, options: ImportOptions) -> str:
        fallback_name = options.source.stem if options.source.is_file() else options.source.name
        source = self._prepare_source(options.source)
        manifest_metadata = parse_manifest_metadata(source) if (source / "manifest.json").exists() else {}
        guid = options.guid or manifest_metadata.get("guid") or ""
        name = options.name or manifest_metadata.get("name") or fallback_name
        description = options.description or manifest_metadata.get("description") or ""
        existing_mod = self.repository.find_by_guid(guid)
        preserved_groups = self.option_service.load_groups(existing_mod.id) if existing_mod else []
        if existing_mod:
            mod_dir = self.repository.mods_dir / existing_mod.id
            self._clear_imported_content(mod_dir)
            order = existing_mod.order if options.order is None else options.order
            author = options.author or existing_mod.author
            link = options.link or existing_mod.link
            category = options.category or existing_mod.category
            enabled = existing_mod.enabled
            self.repository.save_meta(existing_mod.id, name, author, link, order, enabled, description, category, guid=guid)
        else:
            mod_dir = self.repository.create_mod(name, options.author, options.link, options.order, description, options.category, guid=guid)
        if (source / "manifest.json").exists():
            manifest_options = parse_manifest_options(source)
            self.option_service.create_from_manifest_options(mod_dir.name, source, manifest_options)
            if preserved_groups:
                self._restore_option_selection(mod_dir.name, preserved_groups)
        else:
            self._import_as_default_option(mod_dir.name, source)
        self._copy_preview(mod_dir, source, options.preview)
        return mod_dir.name

    def _clear_imported_content(self, mod_dir: Path) -> None:
        for name in ("payloads",):
            target = mod_dir / name
            if target.exists():
                shutil.rmtree(target)
        (mod_dir / "options.yml").unlink(missing_ok=True)

    def _restore_option_selection(self, mod_id: str, old_groups: list[OptionGroup]) -> None:
        groups = self.option_service.load_groups(mod_id)
        old_by_name = {group.name: group for group in old_groups}
        for group in groups:
            old_group = old_by_name.get(group.name)
            if old_group:
                self._restore_choices(group.choices or [], old_group.choices or [])
        self.option_service.save_groups(mod_id, groups)

    def _restore_choices(self, choices: list[OptionChoice], old_choices: list[OptionChoice]) -> None:
        old_by_name = {choice.name: choice for choice in old_choices}
        for choice in choices:
            old_choice = old_by_name.get(choice.name)
            if old_choice:
                choice.selected = old_choice.selected
                self._restore_choices(choice.children or [], old_choice.children or [])

    def _import_as_default_option(self, mod_id: str, source: Path) -> None:
        payload = self.option_service.payloads_dir(mod_id) / "default"
        payload.mkdir(parents=True, exist_ok=True)
        self._copy_payload(source, payload)
        groups = [
            OptionGroup(
                id="default_group",
                name="默认文件",
                description="没有 manifest 的 Mod 会作为默认选项导入",
                choices=[OptionChoice(id="default", name="默认", payload=Path("payloads/default"), selected=True)],
            )
        ]
        self.option_service.save_groups(mod_id, groups)

    def _prepare_source(self, source: Path) -> Path:
        source = Path(source)
        if source.is_dir():
            return source
        if not source.is_file():
            raise FileNotFoundError(source)
        target = TEMP_DIR / f"extract_{random.randint(100000, 999999)}"
        target.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower()
        if suffix == ".zip":
            with zipfile.ZipFile(source, "r") as archive:
                archive.extractall(target)
        elif suffix == ".7z":
            with SevenZipFile(source, mode="r") as archive:
                archive.extractall(target)
        elif suffix == ".rar":
            unrar = Path("UnRAR.exe")
            if not unrar.exists():
                raise RuntimeError("未找到 UnRAR.exe，无法解压 rar 文件")
            subprocess.run([str(unrar), "x", "-y", str(source), str(target)], check=True)
        else:
            raise ValueError(f"不支持的压缩包格式：{source.suffix}")
        items = list(target.iterdir())
        return items[0] if len(items) == 1 and items[0].is_dir() else target

    def _copy_payload(self, source: Path, target: Path) -> None:
        if source.is_dir():
            for item in source.iterdir():
                destination = target / item.name
                if item.is_dir():
                    shutil.copytree(item, destination, dirs_exist_ok=True)
                elif PATCH_PATTERN.match(item.name):
                    shutil.copy2(item, destination)
        elif PATCH_PATTERN.match(source.name):
            shutil.copy2(source, target / source.name)

    def _copy_preview(self, mod_dir: Path, source: Path, preview: Path | None) -> None:
        preview_path = preview if preview and preview.exists() else self._find_preview(source) or self._default_preview()
        if not preview_path:
            return
        target = mod_dir / "images" / "preview.png"
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(preview_path, target)
        mod = self.repository.get(mod_dir.name)
        self.repository.save_meta(mod.id, mod.name, mod.author, mod.link, mod.order, mod.enabled, mod.description, mod.category, "images/preview.png")

    def _find_preview(self, source: Path) -> Path | None:
        for item in source.rglob("*"):
            if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES:
                return item
        return None

    def _default_preview(self) -> Path | None:
        return DEFAULT_PREVIEW if DEFAULT_PREVIEW.exists() else None
