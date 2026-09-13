from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import (
    AccountState,
    Artifact,
    CharacterProfile,
    CharacterTalents,
    Slot,
    Stat,
    Substat,
    WeaponProfile,
)


GOOD_STAT_KEYS: dict[str, Stat] = {
    "hp": Stat.HP_FLAT,
    "hp_": Stat.HP_PCT,
    "atk": Stat.ATK_FLAT,
    "atk_": Stat.ATK_PCT,
    "def": Stat.DEF_FLAT,
    "def_": Stat.DEF_PCT,
    "eleMas": Stat.ELEMENTAL_MASTERY,
    "enerRech_": Stat.ENERGY_RECHARGE,
    "critRate_": Stat.CRIT_RATE,
    "critDMG_": Stat.CRIT_DMG,
    "physical_dmg_": Stat.PHYSICAL_DMG,
    "anemo_dmg_": Stat.ANEMO_DMG,
    "geo_dmg_": Stat.GEO_DMG,
    "electro_dmg_": Stat.ELECTRO_DMG,
    "hydro_dmg_": Stat.HYDRO_DMG,
    "pyro_dmg_": Stat.PYRO_DMG,
    "cryo_dmg_": Stat.CRYO_DMG,
    "dendro_dmg_": Stat.DENDRO_DMG,
    "heal_": Stat.HEALING_BONUS,
}


class GoodSubstat(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    value: Annotated[float, Field(ge=0)]
    initialValue: float | None = None


class GoodArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    setKey: str
    slotKey: str
    level: Annotated[int, Field(ge=0, le=20)]
    rarity: Annotated[int, Field(ge=1, le=5)]
    mainStatKey: str
    location: str = ""
    lock: bool = False
    substats: list[GoodSubstat] = Field(default_factory=list, max_length=4)
    totalRolls: Annotated[int, Field(ge=0, le=9)] | None = None
    astralMark: bool | None = None
    elixirCrafted: bool | None = None
    unactivatedSubstats: list[GoodSubstat] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def validate_substat_shape(self) -> GoodArtifact:
        non_empty = [
            item.key
            for item in [*self.substats, *self.unactivatedSubstats]
            if item.key
        ]
        if len(non_empty) > 4:
            raise ValueError("GOOD artifact exposes more than four substats")
        if len(non_empty) != len(set(non_empty)):
            raise ValueError("GOOD artifact repeats an active or unactivated substat")
        return self


class GoodTalent(BaseModel):
    model_config = ConfigDict(extra="allow")

    auto: Annotated[int, Field(ge=1, le=15)]
    skill: Annotated[int, Field(ge=1, le=15)]
    burst: Annotated[int, Field(ge=1, le=15)]


class GoodCharacter(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    level: Annotated[int, Field(ge=1, le=100)]
    constellation: Annotated[int, Field(ge=0, le=6)]
    ascension: Annotated[int, Field(ge=0, le=6)]
    talent: GoodTalent


class GoodWeapon(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    level: Annotated[int, Field(ge=1, le=90)]
    ascension: Annotated[int, Field(ge=0, le=6)]
    refinement: Annotated[int, Field(ge=1, le=5)]
    location: str = ""
    lock: bool = False


class GoodDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    format: Literal["GOOD"]
    version: Literal[1, 2, 3]
    source: str
    artifacts: list[GoodArtifact] = Field(default_factory=list)
    characters: list[GoodCharacter] = Field(default_factory=list)
    weapons: list[GoodWeapon] = Field(default_factory=list)
    materials: dict[str, Annotated[int, Field(ge=0)]] = Field(default_factory=dict)


class GoodImportReport(BaseModel):
    source: str
    version: int
    artifacts_imported: int
    characters_seen: int
    weapons_seen: int
    equipped_artifacts_seen: int = 0
    equipped_weapons_seen: int = 0
    inactive_substats_imported: int = 0
    skipped_empty_substats: int = 0
    warnings: list[str] = Field(default_factory=list)


class GoodInventory(BaseModel):
    artifacts: list[Artifact]
    characters: list[CharacterProfile] = Field(default_factory=list)
    weapons: list[WeaponProfile] = Field(default_factory=list)
    report: GoodImportReport

    @property
    def character_keys(self) -> list[str]:
        return [item.name for item in self.characters]

    def character(self, name: str) -> CharacterProfile | None:
        return next((item for item in self.characters if item.name == name), None)

    def equipped_weapon(self, character: str) -> WeaponProfile | None:
        return next(
            (item for item in self.weapons if item.equipped_by == character),
            None,
        )

    def to_account_state(
        self,
        character: str,
        *,
        protected_characters: set[str] | None = None,
    ) -> AccountState:
        profile = self.character(character)
        if profile is None:
            raise ValueError(
                f"GOOD has no complete equipped build for {character}; "
                "missing character profile"
            )
        equipped = [item for item in self.artifacts if item.equipped_by == character]
        by_slot: dict[Slot, Artifact] = {}
        for artifact in equipped:
            if artifact.slot in by_slot:
                raise ValueError(
                    f"GOOD contains more than one {artifact.slot.value} equipped by {character}"
                )
            by_slot[artifact.slot] = artifact

        missing = [slot.value for slot in Slot if slot not in by_slot]
        if missing:
            raise ValueError(
                f"GOOD has no complete equipped build for {character}; missing: "
                + ", ".join(missing)
            )

        return AccountState(
            character=profile.model_copy(
                update={
                    "equipped_artifact_ids": {
                        slot: item.id for slot, item in by_slot.items()
                    },
                }
            ),
            artifacts=self.artifacts,
            protected_characters=protected_characters or set(),
        )


def load_good(path: str | Path) -> GoodInventory:
    file_path = Path(path)
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid GOOD JSON: {exc}") from exc
    return import_good(payload)


def import_good(payload: dict[str, Any]) -> GoodInventory:
    document = GoodDocument.model_validate(payload)
    warnings: list[str] = []

    character_keys = [item.key for item in document.characters]
    if len(character_keys) != len(set(character_keys)):
        raise ValueError("GOOD contains duplicate character profiles")

    equipped_weapon_locations = [
        item.location for item in document.weapons if item.location
    ]
    if len(equipped_weapon_locations) != len(set(equipped_weapon_locations)):
        raise ValueError("GOOD contains more than one weapon equipped by a character")

    occurrences: Counter[str] = Counter()
    artifacts: list[Artifact] = []
    skipped_empty = 0
    inactive_substats = 0
    equipped_slots: set[tuple[str, Slot]] = set()
    for source_index, raw in enumerate(document.artifacts, start=1):
        try:
            slot = Slot(raw.slotKey)
        except ValueError as exc:
            raise ValueError(f"unknown GOOD slotKey: {raw.slotKey!r}") from exc
        main_stat = _map_stat(raw.mainStatKey, field="mainStatKey")

        substats: list[Substat] = []
        for substat in raw.substats:
            if substat.key == "":
                skipped_empty += 1
                continue
            substats.append(
                Substat(
                    stat=_map_stat(substat.key, field="substats[].key"),
                    value=substat.value,
                    initial_value=substat.initialValue,
                )
            )

        unactivated_substats: list[Substat] = []
        for substat in raw.unactivatedSubstats:
            if substat.key == "":
                skipped_empty += 1
                continue
            inactive_substats += 1
            unactivated_substats.append(
                Substat(
                    stat=_map_stat(
                        substat.key,
                        field="unactivatedSubstats[].key",
                    ),
                    value=substat.value,
                    initial_value=substat.initialValue,
                )
            )

        if raw.location:
            equipped_slot = (raw.location, slot)
            if equipped_slot in equipped_slots:
                raise ValueError(
                    f"GOOD contains more than one {slot.value} equipped by {raw.location}"
                )
            equipped_slots.add(equipped_slot)

        canonical = json.dumps(
            raw.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        occurrences[digest] += 1
        artifact_id = f"good:{digest}:{occurrences[digest]}"
        artifacts.append(
            Artifact(
                id=artifact_id,
                set_name=raw.setKey,
                slot=slot,
                rarity=raw.rarity,
                level=raw.level,
                main_stat=main_stat,
                main_value=None,
                substats=substats,
                unactivated_substats=unactivated_substats,
                total_rolls=raw.totalRolls,
                astral_mark=raw.astralMark,
                elixir_crafted=raw.elixirCrafted,
                equipped_by=raw.location or None,
                locked=raw.lock,
                source=f"good:{document.source}",
                confidence=1.0,
                source_index=source_index,
            )
        )

    if skipped_empty:
        warnings.append(
            f"skipped {skipped_empty} empty substat placeholders reported by the exporter"
        )

    weapon_occurrences: Counter[str] = Counter()
    weapons: list[WeaponProfile] = []
    for source_index, raw in enumerate(document.weapons, start=1):
        canonical = json.dumps(
            raw.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        weapon_occurrences[digest] += 1
        weapons.append(
            WeaponProfile(
                id=f"good-weapon:{digest}:{weapon_occurrences[digest]}",
                key=raw.key,
                level=raw.level,
                ascension=raw.ascension,
                refinement=raw.refinement,
                equipped_by=raw.location or None,
                locked=raw.lock,
                source=f"good:{document.source}",
                source_index=source_index,
            )
        )

    weapon_by_character = {
        item.equipped_by: item.id for item in weapons if item.equipped_by
    }
    artifacts_by_character: dict[str, dict[Slot, str]] = {}
    for artifact in artifacts:
        if artifact.equipped_by:
            artifacts_by_character.setdefault(artifact.equipped_by, {})[
                artifact.slot
            ] = artifact.id

    characters = [
        CharacterProfile(
            name=raw.key,
            level=raw.level,
            constellation=raw.constellation,
            ascension=raw.ascension,
            talents=CharacterTalents(
                auto=raw.talent.auto,
                skill=raw.talent.skill,
                burst=raw.talent.burst,
            ),
            equipped_weapon_id=weapon_by_character.get(raw.key),
            equipped_artifact_ids=artifacts_by_character.get(raw.key, {}),
        )
        for raw in document.characters
    ]

    referenced_characters = {
        item.equipped_by
        for item in [*artifacts, *weapons]
        if item.equipped_by
    }
    missing_profiles = sorted(referenced_characters - set(character_keys))
    if missing_profiles:
        warnings.append(
            "equipped locations without character profiles: "
            + ", ".join(missing_profiles)
        )

    return GoodInventory(
        artifacts=artifacts,
        characters=characters,
        weapons=weapons,
        report=GoodImportReport(
            source=document.source,
            version=document.version,
            artifacts_imported=len(artifacts),
            characters_seen=len(document.characters),
            weapons_seen=len(document.weapons),
            equipped_artifacts_seen=sum(item.equipped_by is not None for item in artifacts),
            equipped_weapons_seen=sum(item.equipped_by is not None for item in weapons),
            inactive_substats_imported=inactive_substats,
            skipped_empty_substats=skipped_empty,
            warnings=warnings,
        ),
    )


def _map_stat(key: str, *, field: str) -> Stat:
    try:
        return GOOD_STAT_KEYS[key]
    except KeyError as exc:
        raise ValueError(f"unknown GOOD {field}: {key!r}") from exc
