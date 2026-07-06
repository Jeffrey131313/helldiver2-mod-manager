from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime


@dataclass(slots=True)
class OptionChoice:
    id: str
    name: str
    description: str = ""
    image: Path | None = None
    payload: Path | None = None
    selected: bool = False
    children: list["OptionChoice"] | None = None


@dataclass(slots=True)
class OptionGroup:
    id: str
    name: str
    description: str = ""
    image: Path | None = None
    choices: list[OptionChoice] | None = None
    multiple: bool = False


@dataclass(slots=True)
class ModInfo:
    id: str
    name: str
    guid: str = ""
    author: str = ""
    link: str = ""
    enabled: bool = True
    order: int = 9999
    description: str = ""
    category: str = ""
    preview_path: Path | None = None
    option_count: int = 0
    updated_at: datetime | None = None


@dataclass(slots=True)
class ImportOptions:
    source: Path
    guid: str = ""
    name: str = ""
    author: str = ""
    link: str = ""
    order: int | None = None
    description: str = ""
    category: str = ""
    preview: Path | None = None


@dataclass(slots=True)
class ManifestOption:
    name: str
    include: list[str]
    image: str | None = None
    description: str = ""
    sub_options: list["ManifestOption"] | None = None
    multiple: bool = False
