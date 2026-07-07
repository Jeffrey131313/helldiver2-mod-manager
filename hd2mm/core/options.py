from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import yaml

from .models import ManifestOption, OptionChoice, OptionGroup
from .paths import MODS_DIR
from .repository import sanitize_name

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
PREFERRED_IMAGE_NAMES = ("icon", "preview", "cover", "thumbnail", "thumb")


class OptionService:
    def options_file(self, mod_id: str) -> Path:
        return MODS_DIR / mod_id / "options.yml"

    def payloads_dir(self, mod_id: str) -> Path:
        return MODS_DIR / mod_id / "payloads"

    def images_dir(self, mod_id: str) -> Path:
        return MODS_DIR / mod_id / "images"

    def load_groups(self, mod_id: str) -> list[OptionGroup]:
        path = self.options_file(mod_id)
        if not path.exists():
            return []
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        return [self._group_from_dict(item, MODS_DIR / mod_id) for item in raw]

    def save_groups(self, mod_id: str, groups: list[OptionGroup]) -> None:
        path = self.options_file(mod_id)
        data = [self._group_to_dict(group, MODS_DIR / mod_id) for group in groups]
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def create_from_manifest_options(self, mod_id: str, source: Path, options: list[ManifestOption]) -> None:
        groups: list[OptionGroup] = []
        for option in options:
            group = OptionGroup(
                id=self._id(option.name),
                name=option.name,
                description=option.description,
                image=self._copy_image(mod_id, source, option.image),
                choices=[],
                multiple=option.multiple,
            )
            choices = option.sub_options or [option]
            for index, choice in enumerate(choices):
                group.choices.append(self._copy_manifest_choice(mod_id, source, choice, selected=index == 0))
            groups.append(group)
        self.save_groups(mod_id, groups)

    def create_from_directory_options(self, mod_id: str, directories: list[Path], group_name: str) -> None:
        choices: list[OptionChoice] = []
        for index, directory in enumerate(directories):
            choice_id = self._id(str(directory.relative_to(directory.parent)))
            target = self.payloads_dir(mod_id) / choice_id
            target.mkdir(parents=True, exist_ok=True)
            for item in directory.iterdir():
                destination = target / item.name
                if item.is_dir():
                    shutil.copytree(item, destination, dirs_exist_ok=True)
                elif item.is_file():
                    shutil.copy2(item, destination)
            image = self._copy_existing_image(mod_id, self._find_directory_image(directory), directory)
            choices.append(
                OptionChoice(
                    id=choice_id,
                    name=directory.name,
                    image=image,
                    payload=target.relative_to(MODS_DIR / mod_id),
                    selected=index == 0,
                    children=[],
                )
            )
        self.save_groups(
            mod_id,
            [
                OptionGroup(
                    id=self._id(group_name),
                    name=group_name,
                    choices=choices,
                    multiple=False,
                )
            ],
        )

    def selected_payload_roots(self, mod_id: str) -> list[Path]:
        roots: list[Path] = []
        base = MODS_DIR / mod_id
        for group in self.load_groups(mod_id):
            for choice in group.choices or []:
                self._collect_selected(choice, roots, base)
        return roots

    def set_choice_selected(self, mod_id: str, group_id: str, choice_id: str, selected: bool) -> None:
        groups = self.load_groups(mod_id)
        for group in groups:
            if group.id != group_id:
                continue
            for choice in group.choices or []:
                if group.multiple:
                    if choice.id == choice_id:
                        choice.selected = selected
                else:
                    choice.selected = choice.id == choice_id and selected
        self.save_groups(mod_id, groups)

    def set_nested_choice_selected(self, mod_id: str, choice_id: str, selected: bool) -> None:
        groups = self.load_groups(mod_id)
        for group in groups:
            for choice in group.choices or []:
                self._set_nested(choice, choice_id, selected)
        self.save_groups(mod_id, groups)

    def _copy_manifest_choice(self, mod_id: str, source: Path, option: ManifestOption, selected: bool) -> OptionChoice:
        choice_id = self._id(option.name)
        target = self.payloads_dir(mod_id) / choice_id
        target.mkdir(parents=True, exist_ok=True)
        for include in option.include or ["."]:
            include_path = (source / include).resolve()
            if not include_path.exists():
                continue
            if include_path.is_dir():
                for item in include_path.iterdir():
                    destination = target / item.name
                    if item.is_dir():
                        shutil.copytree(item, destination, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, destination)
            else:
                shutil.copy2(include_path, target / include_path.name)
        children = [self._copy_manifest_choice(mod_id, source, child, selected=False) for child in option.sub_options or []]
        return OptionChoice(
            id=choice_id,
            name=option.name,
            description=option.description,
            image=self._copy_image(mod_id, source, option.image),
            payload=target.relative_to(MODS_DIR / mod_id),
            selected=selected,
            children=children,
        )

    def _copy_image(self, mod_id: str, source: Path, image: str | None) -> Path | None:
        if not image:
            return None
        image_path = Path(self._clean_path_text(image))
        image_path = image_path if image_path.is_absolute() else source / image_path
        if not image_path.exists() or not image_path.is_file():
            return None
        target_dir = self.images_dir(mod_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            unique_source = str(image_path.resolve().relative_to(source.resolve()))
        except ValueError:
            unique_source = str(image_path.resolve())
        image_id = self._id(unique_source)
        target = target_dir / f"{image_id}{image_path.suffix.lower()}"
        shutil.copy2(image_path, target)
        return target.relative_to(MODS_DIR / mod_id)

    def _copy_existing_image(self, mod_id: str, image_path: Path | None, source: Path) -> Path | None:
        if not image_path or not image_path.exists() or not image_path.is_file():
            return None
        target_dir = self.images_dir(mod_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            unique_source = str(image_path.resolve().relative_to(source.resolve()))
        except ValueError:
            unique_source = str(image_path.resolve())
        image_id = self._id(f"{source.name}/{unique_source}")
        target = target_dir / f"{image_id}{image_path.suffix.lower()}"
        shutil.copy2(image_path, target)
        return target.relative_to(MODS_DIR / mod_id)

    def _find_directory_image(self, directory: Path) -> Path | None:
        images = [item for item in directory.rglob("*") if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES]
        if not images:
            return None
        for preferred_name in PREFERRED_IMAGE_NAMES:
            for image in images:
                if image.stem.lower() == preferred_name:
                    return image
        return images[0]

    def _collect_selected(self, choice: OptionChoice, roots: list[Path], base: Path) -> None:
        if choice.selected and choice.payload:
            roots.append(base / choice.payload)
        for child in choice.children or []:
            self._collect_selected(child, roots, base)

    def _set_nested(self, choice: OptionChoice, choice_id: str, selected: bool) -> None:
        if choice.id == choice_id:
            choice.selected = selected
        for child in choice.children or []:
            self._set_nested(child, choice_id, selected)

    def _group_from_dict(self, raw: dict[str, Any], base: Path) -> OptionGroup:
        return OptionGroup(
            id=str(raw.get("id") or self._id(str(raw.get("name") or "选项"))),
            name=str(raw.get("name") or "选项"),
            description=str(raw.get("description") or ""),
            image=self._path(raw.get("image"), base),
            choices=[self._choice_from_dict(item, base) for item in raw.get("choices") or []],
            multiple=bool(raw.get("multiple", False)),
        )

    def _choice_from_dict(self, raw: dict[str, Any], base: Path) -> OptionChoice:
        return OptionChoice(
            id=str(raw.get("id") or self._id(str(raw.get("name") or "变体"))),
            name=str(raw.get("name") or "变体"),
            description=str(raw.get("description") or ""),
            image=self._path(raw.get("image"), base),
            payload=self._path(raw.get("payload"), base, absolute=False),
            selected=bool(raw.get("selected", False)),
            children=[self._choice_from_dict(item, base) for item in raw.get("children") or []],
        )

    def _group_to_dict(self, group: OptionGroup, base: Path) -> dict[str, Any]:
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "image": self._stringify(group.image, base),
            "multiple": group.multiple,
            "choices": [self._choice_to_dict(choice, base) for choice in group.choices or []],
        }

    def _choice_to_dict(self, choice: OptionChoice, base: Path) -> dict[str, Any]:
        return {
            "id": choice.id,
            "name": choice.name,
            "description": choice.description,
            "image": self._stringify(choice.image, base),
            "payload": self._stringify(choice.payload, base),
            "selected": choice.selected,
            "children": [self._choice_to_dict(child, base) for child in choice.children or []],
        }

    def _path(self, value: str | None, base: Path, absolute: bool = True) -> Path | None:
        if not value:
            return None
        path = Path(self._clean_path_text(value))
        if absolute and not path.is_absolute():
            return base / path
        return path

    def _clean_path_text(self, value: object) -> str:
        return str(value).strip().strip('"\'').replace("\\r", "").replace("\\n", "")

    def _stringify(self, path: Path | None, base: Path) -> str | None:
        if not path:
            return None
        try:
            return str(path.relative_to(base))
        except ValueError:
            return str(path)

    def _id(self, value: str) -> str:
        safe = sanitize_name(value).lower().replace(" ", "_")
        digest = hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:8]
        return f"{safe}_{digest}"
