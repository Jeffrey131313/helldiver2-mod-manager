from __future__ import annotations

from pathlib import Path

import yaml

from .paths import MOD_LOCKS_FILE


class ModLockService:
    def __init__(self, path: Path = MOD_LOCKS_FILE) -> None:
        self.path = path

    def load_groups(self) -> list[set[str]]:
        if not self.path.exists():
            return []
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or []
        groups: list[set[str]] = []
        for item in raw:
            if isinstance(item, dict):
                ids = item.get("mods") or []
            else:
                ids = item
            group = {str(mod_id) for mod_id in ids if str(mod_id).strip()}
            if len(group) >= 2:
                groups.append(group)
        return self._merge_overlaps(groups)

    def save_groups(self, groups: list[set[str]]) -> None:
        data = [{"mods": sorted(group)} for group in self._merge_overlaps(groups) if len(group) >= 2]
        if data:
            self.path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        elif self.path.exists():
            self.path.unlink()

    def linked_ids(self, mod_id: str) -> set[str]:
        for group in self.load_groups():
            if mod_id in group:
                return set(group)
        return {mod_id}

    def expand_ids(self, mod_ids: set[str] | list[str]) -> set[str]:
        expanded = set(mod_ids)
        changed = True
        groups = self.load_groups()
        while changed:
            changed = False
            for group in groups:
                if expanded.intersection(group) and not group.issubset(expanded):
                    expanded.update(group)
                    changed = True
        return expanded

    def lock(self, mod_ids: set[str] | list[str]) -> None:
        new_group = set(mod_ids)
        if len(new_group) < 2:
            return
        groups = self.load_groups()
        groups.append(new_group)
        self.save_groups(groups)

    def unlock(self, mod_ids: set[str] | list[str]) -> None:
        selected = set(mod_ids)
        if not selected:
            return
        groups = [group for group in self.load_groups() if not group.intersection(selected)]
        self.save_groups(groups)

    def lock_map(self) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        for group in self.load_groups():
            for mod_id in group:
                result[mod_id] = set(group)
        return result

    def prune(self, valid_ids: set[str]) -> None:
        groups = [group.intersection(valid_ids) for group in self.load_groups()]
        self.save_groups(groups)

    def _merge_overlaps(self, groups: list[set[str]]) -> list[set[str]]:
        merged: list[set[str]] = []
        for group in groups:
            current = set(group)
            index = 0
            while index < len(merged):
                if current.intersection(merged[index]):
                    current.update(merged.pop(index))
                    index = 0
                else:
                    index += 1
            merged.append(current)
        return merged
