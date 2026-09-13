from __future__ import annotations

from .models import (
    AccountState,
    Artifact,
    ArtifactSetRequirement,
    BaselineMode,
    BuildContext,
    BuildConstraints,
    CharacterProfile,
    FarmGoal,
    FarmPolicy,
    Slot,
    SlotGoal,
    Stat,
    Substat,
)


def mavuika_goal(policy: FarmPolicy) -> FarmGoal:
    """Content-only demo preset for an unequipped C2 Mavuika.

    ATK% and Elemental Mastery sands deliberately have equal main-stat priority.
    Their final ordering needs an observed leveled build and rotation calculator.
    """

    priorities = {
        Stat.CRIT_RATE: 3,
        Stat.CRIT_DMG: 3,
        Stat.ELEMENTAL_MASTERY: 2,
        Stat.ATK_PCT: 2,
    }

    def target(
        slot: Slot,
        allowed_main_stats: set[Stat],
        main_stat_priorities: dict[Stat, int] | None = None,
    ) -> SlotGoal:
        return SlotGoal(
            slot=slot,
            allowed_main_stats=allowed_main_stats,
            main_stat_priorities=main_stat_priorities or {
                stat: 2 for stat in allowed_main_stats
            },
            substat_priorities=priorities,
            min_useful_substats=2,
            min_content_score_gain=1,
            min_gain=0.01,
        )

    return FarmGoal(
        character="Mavuika",
        policy=policy,
        baseline_mode=BaselineMode.EMPTY,
        build_context=BuildContext(
            character="Mavuika",
            constellation=2,
            weapon="WolfsGravestone",
            weapon_refinement=1,
            target_team=["Mavuika", "Citlali", "Xilonen", "Bennett"],
            farming_team=["Nefer", "Lauma", "Columbina", "Sucrose"],
        ),
        targets=[
            target(Slot.FLOWER, {Stat.HP_FLAT}),
            target(Slot.PLUME, {Stat.ATK_FLAT}),
            target(
                Slot.SANDS,
                {Stat.ATK_PCT, Stat.ELEMENTAL_MASTERY},
                {Stat.ATK_PCT: 2, Stat.ELEMENTAL_MASTERY: 2},
            ),
            target(
                Slot.GOBLET,
                {Stat.PYRO_DMG, Stat.ATK_PCT},
                {Stat.PYRO_DMG: 2, Stat.ATK_PCT: 1},
            ),
            target(
                Slot.CIRCLET,
                {Stat.CRIT_RATE, Stat.CRIT_DMG},
                {Stat.CRIT_RATE: 2, Stat.CRIT_DMG: 2},
            ),
        ],
        constraints=BuildConstraints(
            stat_weights=priorities,
            set_requirements=[
                ArtifactSetRequirement(set_name="ObsidianCodex", pieces=4)
            ],
        ),
    )


def xiangling_account() -> AccountState:
    artifacts = [
        _artifact("base-flower", Slot.FLOWER, Stat.HP_FLAT, 4780, [(Stat.CRIT_RATE, 7.0), (Stat.CRIT_DMG, 14.0), (Stat.ENERGY_RECHARGE, 10.4)]),
        _artifact("base-plume", Slot.PLUME, Stat.ATK_FLAT, 311, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 12.4), (Stat.ENERGY_RECHARGE, 11.0)]),
        _artifact("base-sands", Slot.SANDS, Stat.ENERGY_RECHARGE, 51.8, [(Stat.CRIT_RATE, 6.2), (Stat.CRIT_DMG, 13.2), (Stat.ATK_PCT, 5.8)]),
        _artifact("base-goblet", Slot.GOBLET, Stat.PYRO_DMG, 46.6, [(Stat.CRIT_RATE, 6.6), (Stat.CRIT_DMG, 12.4), (Stat.ENERGY_RECHARGE, 5.2)]),
        _artifact("base-circlet", Slot.CIRCLET, Stat.CRIT_RATE, 31.1, [(Stat.CRIT_DMG, 13.2), (Stat.ENERGY_RECHARGE, 5.8), (Stat.ATK_PCT, 4.7)]),
    ]
    return AccountState(
        character=CharacterProfile(
            name="Xiangling",
            base_stats={Stat.ENERGY_RECHARGE: 100.0},
            equipped_artifact_ids={artifact.slot: artifact.id for artifact in artifacts},
        ),
        artifacts=artifacts,
    )


def xiangling_goal(policy: FarmPolicy) -> FarmGoal:
    return FarmGoal(
        character="Xiangling",
        policy=policy,
        targets=[
            SlotGoal(
                slot=Slot.PLUME,
                substat_priorities={
                    Stat.ENERGY_RECHARGE: 4,
                    Stat.CRIT_RATE: 3,
                    Stat.CRIT_DMG: 3,
                    Stat.ATK_PCT: 1,
                    Stat.ELEMENTAL_MASTERY: 1,
                },
                min_useful_substats=3,
                min_content_score_gain=1,
                min_gain=0.01,
            ),
            SlotGoal(
                slot=Slot.CIRCLET,
                allowed_main_stats={Stat.CRIT_RATE, Stat.CRIT_DMG},
                substat_priorities={
                    Stat.ENERGY_RECHARGE: 4,
                    Stat.CRIT_RATE: 3,
                    Stat.CRIT_DMG: 3,
                    Stat.ATK_PCT: 1,
                    Stat.ELEMENTAL_MASTERY: 1,
                },
                min_useful_substats=3,
                min_content_score_gain=1,
                min_gain=0.01,
            ),
        ],
        constraints=BuildConstraints(
            stat_weights={
                Stat.CRIT_RATE: 2.0,
                Stat.CRIT_DMG: 1.0,
                Stat.ENERGY_RECHARGE: 0.65,
                Stat.ATK_PCT: 0.7,
                Stat.ATK_FLAT: 0.025,
                Stat.PYRO_DMG: 1.0,
            },
            minimum_stats={Stat.ENERGY_RECHARGE: 70.0},
            set_requirements=[
                ArtifactSetRequirement(set_name="EmblemOfSeveredFate", pieces=4)
            ],
        ),
    )


def _artifact(
    artifact_id: str,
    slot: Slot,
    main_stat: Stat,
    main_value: float,
    substats: list[tuple[Stat, float]],
) -> Artifact:
    return Artifact(
        id=artifact_id,
        set_name="EmblemOfSeveredFate",
        slot=slot,
        level=20,
        main_stat=main_stat,
        main_value=main_value,
        substats=[Substat(stat=stat, value=value) for stat, value in substats],
        equipped_by="Xiangling",
        locked=True,
        source="fixture",
    )
