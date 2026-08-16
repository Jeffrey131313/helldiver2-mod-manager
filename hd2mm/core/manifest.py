from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import ManifestOption


def load_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"//.*?$|/\*.*?\*/", "", text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)


def parse_manifest_metadata(manifest_dir: Path) -> dict[str, str]:
    data = load_manifest(manifest_dir / "manifest.json")
    guid = _find_first(data, "Guid", "guid", "GUID", "Uuid", "uuid", "ID", "id")
    name = _find_first(data, "Name", "name", "Title", "title", "ModName", "modName")
    description = _find_first(data, "Description", "description", "Desc", "desc", "Summary", "summary")
    return {
        "guid": str(guid).strip() if guid else "",
        "name": str(name).strip() if name else "",
        "description": str(description).strip() if description else "",
    }


def parse_manifest_options(manifest_dir: Path) -> list[ManifestOption]:
    data = load_manifest(manifest_dir / "manifest.json")
    raw_options = _find_first(data, "Options", "options", "mods", "Mods", "packages", "Packages") or []
    if isinstance(raw_options, dict):
        raw_options = raw_options.values()
    return [_parse_option(option) for option in raw_options if isinstance(option, dict)]


def _parse_option(raw: dict[str, Any]) -> ManifestOption:
    name = str(_find_first(raw, "Name", "name", "Title", "title") or "未命名Mod")
    include_raw = _find_first(raw, "Include", "include", "Includes", "includes", "Files", "files") or []
    if isinstance(include_raw, str):
        include = [_clean_path_text(include_raw)]
    elif isinstance(include_raw, list):
        include = [_clean_path_text(item) for item in include_raw]
    else:
        include = []

    image = _find_first(raw, "Image", "image", "Preview", "preview", "Icon", "icon")
    description = str(_find_first(raw, "Description", "description", "Desc", "desc") or "")
    multiple = bool(_find_first(raw, "Multiple", "multiple", "SelectMany", "selectMany", "MultiSelect", "multiSelect") or False)
    sub_raw = _find_first(raw, "SubOptions", "subOptions", "suboptions", "Options", "options")
    sub_options = None
    if isinstance(sub_raw, list):
        sub_options = [_parse_option(item) for item in sub_raw if isinstance(item, dict)]
    return ManifestOption(
        name=name,
        include=include,
        image=_clean_path_text(image) if image else None,
        description=description,
        sub_options=sub_options,
        multiple=multiple,
    )


def _find_first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _clean_path_text(value: Any) -> str:
    return str(value).strip().strip('"\'').replace("\\r", "").replace("\\n", "")
