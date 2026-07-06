from __future__ import annotations

import json

from dataclasses import dataclass
from datetime import datetime

import requests

from .paths import WAR_STATUS_CACHE_FILE


API_BASE_URL = "https://api.helldivers2.dev/api/v1"
API_HEADERS = {
    "Accept-Language": "zh-Hans",
    "X-Super-Client": "helldiver2-mod-manager",
    "X-Super-Contact": "2314454016@qq.com",
}
REQUEST_TIMEOUT = 12


@dataclass(slots=True)
class WarTaskSummary:
    planet_index: int
    planet_name: str
    sector: str
    objective: str
    owner: str
    progress: float
    players: int

    def display_text(self) -> str:
        if self.owner == "Humans":
            return f"{self.planet_name}\uff1a\u5df2\u89e3\u653e"
        return f"{self.planet_name}\uff1a{self.objective} {self.progress:.1f}%\uff0c{_owner_text(self.owner)}"


@dataclass(slots=True)
class WarStatusSummary:
    title: str
    briefing: str
    reward: int
    expiration: datetime | None
    tasks: list[WarTaskSummary]

    def display_text(self) -> str:
        lines = [self.title]
        if self.briefing:
            lines.append(self.briefing)
        if self.tasks:
            lines.append("\n".join(task.display_text() for task in self.tasks))
        if self.reward:
            lines.append(f"\u5956\u52b1\uff1a{self.reward} \u679a\u5956\u7ae0")
        if self.expiration:
            lines.append(f"\u622a\u6b62\uff1a{self.expiration.astimezone().strftime('%m-%d %H:%M')}")
        return "\n".join(lines)


@dataclass(slots=True)
class PlanetStatus:
    index: int
    name: str
    sector: str
    owner: str
    health: int
    max_health: int
    players: int
    attacking: list[int]

    @property
    def liberation_progress(self) -> float:
        if self.owner == "Humans":
            return 100.0
        if self.max_health <= 0:
            return 0.0
        return max(0.0, min(100.0, (1 - self.health / self.max_health) * 100))


@dataclass(slots=True)
class AssignmentTask:
    type: int
    planet_index: int


@dataclass(slots=True)
class WarAssignment:
    title: str
    briefing: str
    reward: int
    expiration: datetime | None
    tasks: list[AssignmentTask]


OBJECTIVE_BY_TYPE = {
    11: "\u89e3\u653e\u8fdb\u5ea6",
    13: "\u9632\u5b88\u8fdb\u5ea6",
}


class WarApiClient:
    def __init__(self, base_url: str = API_BASE_URL, headers: dict[str, str] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = dict(API_HEADERS if headers is None else headers)
        self.session = requests.Session()

    def current_summary(self) -> WarStatusSummary:
        assignments = self._get_json("assignments")
        planets = self._get_json("planets")
        assignment = self._parse_assignment(assignments)
        planet_map = {planet.index: planet for planet in self._parse_planets(planets)}
        tasks = [self._task_summary(task, planet_map.get(task.planet_index)) for task in assignment.tasks]
        return WarStatusSummary(
            title=assignment.title,
            briefing=assignment.briefing,
            reward=assignment.reward,
            expiration=assignment.expiration,
            tasks=tasks,
        )

    def _get_json(self, endpoint: str) -> object:
        response = self.session.get(f"{self.base_url}/{endpoint}", headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()

    def _parse_assignment(self, raw: object) -> WarAssignment:
        if not isinstance(raw, list) or not raw:
            raise ValueError("\u672a\u627e\u5230\u5f53\u524d MO")
        data = raw[0]
        tasks = []
        for task in data.get("tasks", []):
            values = task.get("values", [])
            if len(values) >= 3:
                tasks.append(AssignmentTask(type=int(task.get("type", 0)), planet_index=int(values[2])))
        return WarAssignment(
            title=str(data.get("title") or "\u91cd\u8981\u6307\u4ee4"),
            briefing=str(data.get("briefing") or ""),
            reward=int((data.get("reward") or {}).get("amount") or 0),
            expiration=self._parse_datetime(data.get("expiration")),
            tasks=tasks,
        )

    def _parse_planets(self, raw: object) -> list[PlanetStatus]:
        if not isinstance(raw, list):
            return []
        planets = []
        for data in raw:
            statistics = data.get("statistics") or {}
            planets.append(
                PlanetStatus(
                    index=int(data.get("index", -1)),
                    name=str(data.get("name") or f"#{data.get('index', '?')}"),
                    sector=str(data.get("sector") or ""),
                    owner=str(data.get("currentOwner") or ""),
                    health=int(data.get("health") or 0),
                    max_health=int(data.get("maxHealth") or 0),
                    players=int(statistics.get("playerCount") or 0),
                    attacking=list(data.get("attacking") or []),
                )
            )
        return planets

    def _task_summary(self, task: AssignmentTask, planet: PlanetStatus | None) -> WarTaskSummary:
        objective = OBJECTIVE_BY_TYPE.get(task.type, "\u4f5c\u6218\u8fdb\u5ea6")
        if planet is None:
            return WarTaskSummary(
                planet_index=task.planet_index,
                planet_name=f"#{task.planet_index}",
                sector="",
                objective=objective,
                owner="",
                progress=0.0,
                players=0,
            )
        return WarTaskSummary(
            planet_index=planet.index,
            planet_name=planet.name,
            sector=planet.sector,
            objective=objective,
            owner=planet.owner,
            progress=planet.liberation_progress,
            players=planet.players,
        )

    def _parse_datetime(self, value: object) -> datetime | None:
        if not value:
            return None
        text = str(value).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None


def fetch_current_war_status() -> WarStatusSummary:
    summary = WarApiClient().current_summary()
    save_war_status_cache(summary.display_text())
    return summary


def load_war_status_cache() -> str | None:
    if not WAR_STATUS_CACHE_FILE.exists():
        return None
    try:
        data = json.loads(WAR_STATUS_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    text = data.get("text") if isinstance(data, dict) else None
    return str(text) if text else None


def save_war_status_cache(text: str) -> None:
    data = {"text": text, "updated_at": datetime.now().astimezone().isoformat()}
    WAR_STATUS_CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _owner_text(owner: str) -> str:
    return {
        "Humans": "\u8d85\u7ea7\u5730\u7403",
        "Automaton": "\u673a\u5668\u4eba",
        "Terminids": "\u866b\u65cf",
        "Illuminate": "\u5149\u80fd\u8005",
    }.get(owner, owner or "\u672a\u77e5")
