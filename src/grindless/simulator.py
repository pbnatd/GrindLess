from __future__ import annotations

import random

from .models import (
    Artifact,
    EnhancementEvent,
    EnhancementResult,
    RewardBatch,
    Slot,
    Stat,
    Substat,
)


MAIN_STATS: dict[Slot, tuple[Stat, ...]] = {
    Slot.FLOWER: (Stat.HP_FLAT,),
    Slot.PLUME: (Stat.ATK_FLAT,),
    Slot.SANDS: (
        Stat.HP_PCT,
        Stat.ATK_PCT,
        Stat.DEF_PCT,
        Stat.ENERGY_RECHARGE,
        Stat.ELEMENTAL_MASTERY,
    ),
    Slot.GOBLET: (
        Stat.HP_PCT,
        Stat.ATK_PCT,
        Stat.DEF_PCT,
        Stat.ELEMENTAL_MASTERY,
        Stat.PYRO_DMG,
    ),
    Slot.CIRCLET: (
        Stat.HP_PCT,
        Stat.ATK_PCT,
        Stat.DEF_PCT,
        Stat.ELEMENTAL_MASTERY,
        Stat.CRIT_RATE,
        Stat.CRIT_DMG,
        Stat.HEALING_BONUS,
    ),
}

MAIN_STAT_VALUES: dict[Stat, tuple[float, float]] = {
    Stat.HP_FLAT: (717.0, 4780.0),
    Stat.ATK_FLAT: (47.0, 311.0),
    Stat.HP_PCT: (7.0, 46.6),
    Stat.ATK_PCT: (7.0, 46.6),
    Stat.DEF_PCT: (8.7, 58.3),
    Stat.ENERGY_RECHARGE: (7.8, 51.8),
    Stat.ELEMENTAL_MASTERY: (28.0, 187.0),
    Stat.PYRO_DMG: (7.0, 46.6),
    Stat.CRIT_RATE: (4.7, 31.1),
    Stat.CRIT_DMG: (9.3, 62.2),
    Stat.HEALING_BONUS: (5.4, 35.9),
}

SUBSTAT_ROLLS: dict[Stat, tuple[float, ...]] = {
    Stat.HP_FLAT: (209.0, 239.0, 269.0, 299.0),
    Stat.ATK_FLAT: (14.0, 16.0, 18.0, 19.0),
    Stat.DEF_FLAT: (16.0, 19.0, 21.0, 23.0),
    Stat.HP_PCT: (4.1, 4.7, 5.3, 5.8),
    Stat.ATK_PCT: (4.1, 4.7, 5.3, 5.8),
    Stat.DEF_PCT: (5.1, 5.8, 6.6, 7.3),
    Stat.ELEMENTAL_MASTERY: (16.0, 19.0, 21.0, 23.0),
    Stat.ENERGY_RECHARGE: (4.5, 5.2, 5.8, 6.5),
    Stat.CRIT_RATE: (2.7, 3.1, 3.5, 3.9),
    Stat.CRIT_DMG: (5.4, 6.2, 7.0, 7.8),
}


class ArtifactDomainSimulator:
    """Seeded, configurable simulator behind the future GameAdapter boundary.

    The probabilities are intentionally a teaching approximation, not an
    authoritative drop-rate table. They live in this adapter so they can be
    calibrated without changing the agent or stop-policy.
    """

    def __init__(
        self,
        *,
        seed: int = 42,
        resin: int = 200,
        domain_sets: tuple[str, str] = ("EmblemOfSeveredFate", "ShimenawasReminiscence"),
        bonus_drop_chance: float = 0.10,
    ) -> None:
        self._rng = random.Random(seed)
        self._resin = resin
        self._domain_sets = domain_sets
        self._bonus_drop_chance = bonus_drop_chance
        self._run_number = 0
        self._artifact_number = 0

    @property
    def resin_remaining(self) -> int:
        return self._resin

    def claim_reward(self, cost: int) -> RewardBatch:
        if cost <= 0:
            raise ValueError("reward cost must be positive")
        if self._resin < cost:
            raise ValueError("not enough resin to claim reward")
        self._resin -= cost
        self._run_number += 1
        count = 2 if self._rng.random() < self._bonus_drop_chance else 1
        return RewardBatch(
            run_number=self._run_number,
            artifacts=[self._generate_artifact() for _ in range(count)],
            resin_spent=cost,
        )

    def enhance_artifact(self, artifact: Artifact, target_level: int = 20) -> EnhancementResult:
        if target_level not in {4, 8, 12, 16, 20}:
            raise ValueError("target_level must be one of 4, 8, 12, 16, 20")
        if artifact.level > target_level:
            raise ValueError("cannot lower artifact level")

        current = artifact.model_copy(deep=True)
        events: list[EnhancementEvent] = []
        while current.level < target_level:
            next_level = current.level + 4
            substats = [item.model_copy() for item in current.substats]
            added = False
            if len(substats) < 4:
                existing = {item.stat for item in substats}
                choices = [
                    stat
                    for stat in SUBSTAT_ROLLS
                    if stat != current.main_stat and stat not in existing
                ]
                changed_stat = self._rng.choice(choices)
                substats.append(
                    Substat(stat=changed_stat, value=self._rng.choice(SUBSTAT_ROLLS[changed_stat]))
                )
                added = True
            else:
                index = self._rng.randrange(len(substats))
                changed_stat = substats[index].stat
                substats[index] = Substat(
                    stat=changed_stat,
                    value=round(
                        substats[index].value + self._rng.choice(SUBSTAT_ROLLS[changed_stat]), 1
                    ),
                )

            start_value, max_value = MAIN_STAT_VALUES[current.main_stat]
            main_value = start_value + (max_value - start_value) * (next_level / 20)
            current = Artifact.model_validate(
                {
                    **current.model_dump(),
                    "level": next_level,
                    "main_value": round(main_value, 1),
                    "substats": substats,
                }
            )
            events.append(
                EnhancementEvent(
                    artifact_id=current.id,
                    from_level=next_level - 4,
                    to_level=next_level,
                    changed_stat=changed_stat,
                    added_new_substat=added,
                )
            )
        return EnhancementResult(artifact=current, events=events)

    def _generate_artifact(self) -> Artifact:
        self._artifact_number += 1
        slot = self._rng.choice(list(Slot))
        main_stat = self._rng.choice(MAIN_STATS[slot])
        substat_count = 4 if self._rng.random() < 0.20 else 3
        choices = [stat for stat in SUBSTAT_ROLLS if stat != main_stat]
        selected = self._rng.sample(choices, substat_count)
        return Artifact(
            id=f"sim-{self._artifact_number:04d}",
            set_name=self._rng.choice(self._domain_sets),
            slot=slot,
            main_stat=main_stat,
            main_value=MAIN_STAT_VALUES[main_stat][0],
            substats=[
                Substat(stat=stat, value=self._rng.choice(SUBSTAT_ROLLS[stat]))
                for stat in selected
            ],
            level=0,
            source="simulator",
        )
