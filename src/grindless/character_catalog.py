from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .models import (
    ArtifactSetRequirement,
    BaselineMode,
    BuildConstraints,
    FarmGoal,
    FarmPolicy,
    Slot,
    SlotGoal,
    Stat,
)

TeamMode = Literal["manual", "auto"]
DomainTeamMode = Literal["same", "manual", "auto"]
TeamObjective = Literal["max_dps", "comfort", "stable_rotation"]

TEAM_OBJECTIVE_DESCRIPTIONS: dict[TeamObjective, str] = {
    "max_dps": (
        "Максимальный DPS: приоритет максимальному потолку урона; сложная ротация "
        "и меньший комфорт допустимы, если это честно отмечено."
    ),
    "comfort": (
        "Комфорт: приоритет лечению, щитам, сопротивлению прерыванию и простоте "
        "исполнения; часть максимального урона можно обменять на надёжность."
    ),
    "stable_rotation": (
        "Стабильный DPS и ротация: приоритет повторяемому урону от цикла к циклу, "
        "готовности ресурсов и понятному восстановлению после ошибки."
    ),
}


class CharacterDefinition(BaseModel):
    key: str
    name_ru: str
    avatar_id: int
    alternate_avatar_ids: list[int] = Field(default_factory=list)
    rarity: Literal[4, 5]
    availability: Literal["limited", "starter", "standard", "collab", "unknown"] = "unknown"
    element: str
    role: str = "team candidate"
    primary_set: str = ""
    secondary_set: str = ""
    full_target_support: bool = False
    profile_source_url: str = ""
    profile_source_version: str = ""


class TargetBenchmark(BaseModel):
    stat: Stat
    target: float = Field(gt=0)
    unit: Literal["flat_total", "percent_total"]
    condition_ru: str = Field(min_length=20, max_length=500)
    enforced: Literal[False] = False


class TargetSetOption(BaseModel):
    option_id: str = Field(pattern=r"^[a-z0-9_]{3,80}$")
    label_ru: str = Field(min_length=3, max_length=220)
    requirements: list[ArtifactSetRequirement] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def validate_composition(self) -> TargetSetOption:
        BuildConstraints(stat_weights={}, set_requirements=self.requirements)
        return self


class TargetProfileDefinition(BaseModel):
    key: str
    target_kind: Literal["limited", "starter"]
    role: str = Field(min_length=3, max_length=160)
    primary_set: str = Field(min_length=1, max_length=100)
    secondary_set: str = Field(min_length=1, max_length=100)
    additional_set_options: list[TargetSetOption] = Field(
        default_factory=list, max_length=8
    )
    main_stats: dict[Slot, list[Stat]]
    substat_priority: list[Stat] = Field(min_length=3, max_length=8)
    benchmarks: list[TargetBenchmark] = Field(default_factory=list)
    caveats_ru: list[str] = Field(default_factory=list, max_length=8)
    source_url: str = Field(min_length=10, max_length=500)
    source_label: str = Field(min_length=3, max_length=120)
    source_version: str = Field(min_length=1, max_length=80)
    observed_at: str = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def validate_profile(self) -> TargetProfileDefinition:
        expected_slots = {Slot.SANDS, Slot.GOBLET, Slot.CIRCLET}
        if set(self.main_stats) != expected_slots:
            raise ValueError("target profile must define sands, goblet and circlet")
        for slot, stats in self.main_stats.items():
            if not stats or len(stats) != len(set(stats)):
                raise ValueError(f"target profile has empty or duplicate stats for {slot.value}")
        if len(self.substat_priority) != len(set(self.substat_priority)):
            raise ValueError("target profile repeats a substat priority")
        option_ids = [item.option_id for item in self.additional_set_options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("target profile repeats a set option id")
        if {"primary_4pc", "secondary_4pc"} & set(option_ids):
            raise ValueError("additional set options use a reserved option id")
        compositions = [
            tuple(sorted((item.set_name, item.pieces) for item in option.requirements))
            for option in self.set_options
        ]
        if len(compositions) != len(set(compositions)):
            raise ValueError("target profile repeats a set composition")
        return self

    @property
    def set_options(self) -> list[TargetSetOption]:
        return [
            TargetSetOption(
                option_id="primary_4pc",
                label_ru=f"4 предмета {self.primary_set}",
                requirements=[
                    ArtifactSetRequirement(set_name=self.primary_set, pieces=4)
                ],
            ),
            TargetSetOption(
                option_id="secondary_4pc",
                label_ru=f"4 предмета {self.secondary_set}",
                requirements=[
                    ArtifactSetRequirement(set_name=self.secondary_set, pieces=4)
                ],
            ),
            *self.additional_set_options,
        ]


class TeamIntent(BaseModel):
    target_key: str
    target_objective: TeamObjective = "max_dps"
    target_team_mode: TeamMode = "auto"
    target_team: list[str] = Field(default_factory=list, max_length=4)
    domain_team_mode: DomainTeamMode = "same"
    domain_objective: TeamObjective = "stable_rotation"
    domain_team: list[str] = Field(default_factory=list, max_length=4)
    candidate_pool: list[str] = Field(default_factory=list, max_length=116)

    @model_validator(mode="after")
    def validate_teams(self) -> TeamIntent:
        known = set(CHARACTERS)
        supplied = set(self.target_team + self.domain_team + self.candidate_pool)
        unknown = sorted(supplied - known)
        if self.target_key not in known:
            raise ValueError(f"unsupported target character: {self.target_key}")
        if unknown:
            raise ValueError("unknown character keys: " + ", ".join(unknown))
        if self.target_key in self.candidate_pool:
            raise ValueError("candidate_pool contains teammates only, not the target")
        for label, values in (
            ("target_team", self.target_team),
            ("domain_team", self.domain_team),
            ("candidate_pool", self.candidate_pool),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must not contain duplicate characters")
        if self.target_team_mode == "manual":
            if len(self.target_team) != 4 or self.target_key not in self.target_team:
                raise ValueError(
                    "manual target team must contain exactly four characters including target"
                )
        elif self.target_team:
            raise ValueError("auto target team must not contain a preselected team")
        if self.domain_team_mode == "manual" and len(self.domain_team) != 4:
            raise ValueError("manual domain team must contain exactly four characters")
        if self.domain_team_mode != "manual" and self.domain_team:
            raise ValueError("domain_team is only allowed in manual mode")
        if self.target_team_mode == "auto" and len(self.candidate_pool) < 3:
            raise ValueError("automatic team selection needs at least three candidates")
        if self.domain_team_mode == "auto" and len(self.candidate_pool) < 3:
            raise ValueError("automatic domain team selection needs at least three teammates")
        return self


class TeamPlan(BaseModel):
    target_key: str
    target_team_mode: TeamMode
    target_team: list[str]
    target_objective: TeamObjective
    domain_team_mode: DomainTeamMode
    domain_team: list[str]
    domain_objective: TeamObjective
    candidate_pool: list[str]
    expected_showcase_keys: list[str]
    target_team_status: Literal["confirmed", "pending_optimizer"]
    domain_team_status: Literal["confirmed", "pending_optimizer", "same_as_target"]


_CURATED_CHARACTERS: dict[str, CharacterDefinition] = {
    item.key: item
    for item in [
        CharacterDefinition(key="Mavuika", name_ru="Мавуика", avatar_id=10000106, rarity=5, availability="limited", element="Pyro", role="on-field DPS", primary_set="ObsidianCodex", secondary_set="ScrollOfTheHeroOfCinderCity", full_target_support=True),
        CharacterDefinition(key="Neuvillette", name_ru="Нёвиллет", avatar_id=10000087, rarity=5, availability="limited", element="Hydro", role="charged-attack DPS", primary_set="MarechausseeHunter", secondary_set="GoldenTroupe", full_target_support=True),
        CharacterDefinition(key="Arlecchino", name_ru="Арлекино", avatar_id=10000096, rarity=5, availability="limited", element="Pyro", role="on-field DPS", primary_set="FragmentOfHarmonicWhimsy", secondary_set="UnfinishedReverie", full_target_support=True),
        CharacterDefinition(key="Nahida", name_ru="Нахида", avatar_id=10000073, rarity=5, availability="limited", element="Dendro", role="reaction driver / support", primary_set="DeepwoodMemories", secondary_set="GildedDreams", full_target_support=True),
        CharacterDefinition(key="Xiangling", name_ru="Сян Лин", avatar_id=10000023, rarity=4, availability="starter", element="Pyro", role="off-field DPS", primary_set="EmblemOfSeveredFate", secondary_set="CrimsonWitchOfFlames", full_target_support=True),
        CharacterDefinition(key="Noelle", name_ru="Ноэлль", avatar_id=10000034, rarity=4, availability="starter", element="Geo", role="DEF carry / sustain", primary_set="HuskOfOpulentDreams", secondary_set="RetracingBolide", full_target_support=True),
        CharacterDefinition(key="Kaeya", name_ru="Кэйа", avatar_id=10000015, rarity=4, availability="starter", element="Cryo", role="on-field / off-field DPS", primary_set="BlizzardStrayer", secondary_set="NoblesseOblige", full_target_support=True),
        CharacterDefinition(key="Lisa", name_ru="Лиза", avatar_id=10000006, rarity=4, availability="starter", element="Electro", role="reaction DPS / support", primary_set="ThunderingFury", secondary_set="GildedDreams", full_target_support=True),
        CharacterDefinition(key="Bennett", name_ru="Беннет", avatar_id=10000032, rarity=4, availability="standard", element="Pyro", role="buffer / healer", primary_set="NoblesseOblige", secondary_set="Instructor", full_target_support=False),
        CharacterDefinition(key="Furina", name_ru="Фурина", avatar_id=10000089, rarity=5, availability="limited", element="Hydro", role="buffer / off-field DPS", primary_set="GoldenTroupe", secondary_set="TenacityOfTheMillelith", full_target_support=False),
        CharacterDefinition(key="Zhongli", name_ru="Чжун Ли", avatar_id=10000030, rarity=5, availability="limited", element="Geo", role="shield / resistance shred", primary_set="TenacityOfTheMillelith", secondary_set="ArchaicPetra", full_target_support=False),
        CharacterDefinition(key="Kazuha", name_ru="Кадзуха", avatar_id=10000047, rarity=5, availability="limited", element="Anemo", role="buffer / grouping", primary_set="ViridescentVenerer", secondary_set="Instructor", full_target_support=False),
        CharacterDefinition(key="Xilonen", name_ru="Шилонен", avatar_id=10000103, rarity=5, availability="limited", element="Geo", role="buffer / sustain", primary_set="ScrollOfTheHeroOfCinderCity", secondary_set="HuskOfOpulentDreams", full_target_support=False),
        CharacterDefinition(key="Citlali", name_ru="Ситлали", avatar_id=10000107, rarity=5, availability="limited", element="Cryo", role="shield / reaction support", primary_set="ScrollOfTheHeroOfCinderCity", secondary_set="TenacityOfTheMillelith", full_target_support=False),
        CharacterDefinition(key="Sucrose", name_ru="Сахароза", avatar_id=10000043, rarity=4, availability="standard", element="Anemo", role="EM buffer / grouping", primary_set="ViridescentVenerer", secondary_set="Instructor", full_target_support=False),
        CharacterDefinition(key="Fischl", name_ru="Фишль", avatar_id=10000031, rarity=4, availability="standard", element="Electro", role="off-field DPS", primary_set="GoldenTroupe", secondary_set="ThunderingFury", full_target_support=False),
        CharacterDefinition(key="Xingqiu", name_ru="Син Цю", avatar_id=10000025, rarity=4, availability="standard", element="Hydro", role="off-field DPS / interruption resistance", primary_set="EmblemOfSeveredFate", secondary_set="NoblesseOblige", full_target_support=False),
        CharacterDefinition(key="Yelan", name_ru="Е Лань", avatar_id=10000060, rarity=5, availability="limited", element="Hydro", role="off-field DPS / buffer", primary_set="EmblemOfSeveredFate", secondary_set="NoblesseOblige", full_target_support=False),
        CharacterDefinition(key="KukiShinobu", name_ru="Куки Синобу", avatar_id=10000065, rarity=4, availability="standard", element="Electro", role="healer / reaction trigger", primary_set="FlowerOfParadiseLost", secondary_set="GildedDreams", full_target_support=False),
        CharacterDefinition(key="Chevreuse", name_ru="Шеврёз", avatar_id=10000090, rarity=4, availability="standard", element="Pyro", role="Overload support / healer", primary_set="SongOfDaysPast", secondary_set="NoblesseOblige", full_target_support=False),
    ]
}


def _load_team_roster() -> tuple[dict[str, CharacterDefinition], dict[str, str]]:
    path = Path(__file__).with_name("data") / "team_roster.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load the bundled Genshin roster: {exc}") from exc
    if payload.get("schema_version") != 1 or not isinstance(payload.get("characters"), list):
        raise RuntimeError("bundled Genshin roster has an unsupported schema")

    roster: dict[str, CharacterDefinition] = {}
    for raw in payload["characters"]:
        definition = CharacterDefinition.model_validate(raw)
        if definition.key in roster:
            raise RuntimeError(f"bundled Genshin roster repeats {definition.key}")
        if definition.key == "Aloy":
            definition = definition.model_copy(update={"availability": "collab"})
        roster[definition.key] = definition
    return roster, {
        "game_version": str(payload.get("game_version", "unknown")),
        "retrieved_at": str(payload.get("retrieved_at", "unknown")),
        "source_url": str(payload.get("source_url", "unknown")),
    }


def _load_target_profiles(
    roster: dict[str, CharacterDefinition],
) -> tuple[dict[str, TargetProfileDefinition], dict[str, str]]:
    path = Path(__file__).with_name("data") / "target_profiles.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load bundled target profiles: {exc}") from exc
    if payload.get("schema_version") != 2 or not isinstance(payload.get("profiles"), list):
        raise RuntimeError("bundled target profiles have an unsupported schema")

    profiles: dict[str, TargetProfileDefinition] = {}
    for raw in payload["profiles"]:
        profile = TargetProfileDefinition.model_validate(raw)
        if profile.key in profiles:
            raise RuntimeError(f"bundled target profiles repeat {profile.key}")
        character = roster.get(profile.key)
        if character is None:
            raise RuntimeError(f"target profile references unknown character {profile.key}")
        if profile.target_kind == "limited" and character.rarity != 5:
            raise RuntimeError(f"limited target {profile.key} is not a five-star character")
        if profile.target_kind == "starter" and character.rarity != 4:
            raise RuntimeError(f"starter target {profile.key} is not a four-star character")
        profiles[profile.key] = profile
    limited_count = sum(item.target_kind == "limited" for item in profiles.values())
    starter_count = sum(item.target_kind == "starter" for item in profiles.values())
    if limited_count != 56 or starter_count != 4:
        raise RuntimeError(
            "target profile coverage must contain 56 limited five-stars and 4 starter targets"
        )
    return profiles, {
        "game_version": str(payload.get("game_version", "unknown")),
        "retrieved_at": str(payload.get("retrieved_at", "unknown")),
        "target_rule": str(payload.get("target_rule", "unknown")),
        "primary_source": str(payload.get("primary_source", "unknown")),
    }


CHARACTERS, ROSTER_PROVENANCE = _load_team_roster()
CHARACTERS.update(_CURATED_CHARACTERS)
TARGET_PROFILES, TARGET_PROFILE_PROVENANCE = _load_target_profiles(CHARACTERS)
for _key, _profile in TARGET_PROFILES.items():
    CHARACTERS[_key] = CHARACTERS[_key].model_copy(
        update={
            "availability": _profile.target_kind,
            "role": _profile.role,
            "primary_set": _profile.primary_set,
            "secondary_set": _profile.secondary_set,
            "full_target_support": True,
            "profile_source_url": _profile.source_url,
            "profile_source_version": _profile.source_version,
        }
    )

TARGET_CHARACTER_KEYS = tuple(
    key for key, item in CHARACTERS.items() if item.full_target_support
)
ROSTER_CHARACTER_KEYS = tuple(CHARACTERS)
CHARACTER_BY_AVATAR_ID: dict[int, CharacterDefinition] = {}
for _definition in CHARACTERS.values():
    for _avatar_id in [_definition.avatar_id, *_definition.alternate_avatar_ids]:
        if _avatar_id in CHARACTER_BY_AVATAR_ID:
            raise RuntimeError(f"avatar id {_avatar_id} is assigned more than once")
        CHARACTER_BY_AVATAR_ID[_avatar_id] = _definition


def build_team_plan(intent: TeamIntent) -> TeamPlan:
    target_team = list(intent.target_team)
    domain_team = list(intent.domain_team)
    expected = {intent.target_key}
    if intent.target_team_mode == "manual":
        expected.update(target_team)
    else:
        expected.update(intent.candidate_pool)
    if intent.domain_team_mode == "manual":
        expected.update(domain_team)
    elif intent.domain_team_mode == "auto":
        expected.update(intent.candidate_pool)

    same_team = intent.domain_team_mode == "same"
    return TeamPlan(
        target_key=intent.target_key,
        target_team_mode=intent.target_team_mode,
        target_team=target_team,
        target_objective=intent.target_objective,
        domain_team_mode=intent.domain_team_mode,
        domain_team=target_team if same_team else domain_team,
        domain_objective=intent.domain_objective,
        candidate_pool=list(dict.fromkeys(intent.candidate_pool)),
        expected_showcase_keys=sorted(expected),
        target_team_status=(
            "confirmed" if intent.target_team_mode == "manual" else "pending_optimizer"
        ),
        domain_team_status=(
            "same_as_target"
            if same_team
            else "confirmed"
            if intent.domain_team_mode == "manual"
            else "pending_optimizer"
        ),
    )


def character_goal(key: str, policy: FarmPolicy) -> FarmGoal:
    definition = CHARACTERS.get(key)
    if definition is None or not definition.full_target_support:
        raise ValueError(f"character {key!r} does not have a full target profile")
    profile = TARGET_PROFILES[key]
    priorities = {
        stat: float(len(profile.substat_priority) - index)
        for index, stat in enumerate(profile.substat_priority)
    }

    def target(slot: Slot, allowed_main_stats: set[Stat]) -> SlotGoal:
        return SlotGoal(
            slot=slot,
            allowed_main_stats=allowed_main_stats,
            main_stat_priorities={stat: 2 for stat in allowed_main_stats},
            substat_priorities=priorities,
            min_useful_substats=2,
            min_content_score_gain=1,
            min_gain=0.01,
        )

    return FarmGoal(
        character=key,
        policy=policy,
        baseline_mode=BaselineMode.EMPTY,
        targets=[
            target(Slot.FLOWER, {Stat.HP_FLAT}),
            target(Slot.PLUME, {Stat.ATK_FLAT}),
            target(Slot.SANDS, set(profile.main_stats[Slot.SANDS])),
            target(Slot.GOBLET, set(profile.main_stats[Slot.GOBLET])),
            target(Slot.CIRCLET, set(profile.main_stats[Slot.CIRCLET])),
        ],
        constraints=BuildConstraints(
            stat_weights=priorities,
            set_requirements=[
                ArtifactSetRequirement(set_name=definition.primary_set, pieces=4)
            ],
        ),
    )
