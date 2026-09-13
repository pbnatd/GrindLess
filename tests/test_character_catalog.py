from __future__ import annotations

import unittest
from pathlib import Path
from struct import unpack

from pydantic import ValidationError

from grindless.character_catalog import (
    CHARACTERS,
    CHARACTER_BY_AVATAR_ID,
    ROSTER_PROVENANCE,
    TARGET_CHARACTER_KEYS,
    TARGET_PROFILES,
    TARGET_PROFILE_PROVENANCE,
    TeamIntent,
    build_team_plan,
    character_goal,
)
from grindless.models import FarmPolicy, Slot, Stat


class CharacterCatalogTests(unittest.TestCase):
    def test_version_7_roster_contains_every_current_team_candidate(self) -> None:
        self.assertEqual(len(CHARACTERS), 116)
        self.assertEqual(ROSTER_PROVENANCE["game_version"], "7.0")
        for key in ("Alyosha", "Odette", "Columbina", "Varka", "Traveler", "Aloy"):
            self.assertIn(key, CHARACTERS)
        for unreleased_or_internal in ("Nicole", "Prune", "Sandrone", "Manekin"):
            self.assertNotIn(unreleased_or_internal, CHARACTERS)

    def test_both_traveler_avatar_ids_resolve_to_one_team_candidate(self) -> None:
        self.assertEqual(CHARACTER_BY_AVATAR_ID[10000005].key, "Traveler")
        self.assertEqual(CHARACTER_BY_AVATAR_ID[10000007].key, "Traveler")

    def test_catalog_covers_every_limited_five_star_and_four_starter_targets(self) -> None:
        limited = set("""
            KamisatoAyaka Venti Xiao Klee Zhongli Tartaglia Ganyu Albedo HuTao Kazuha
            Yoimiya Eula RaidenShogun SangonomiyaKokomi AratakiItto YaeMiko Yelan
            Shenhe KamisatoAyato Nilou Cyno Nahida Wanderer Alhaitham Baizhu Lyney
            Wriothesley Neuvillette Furina Navia Xianyun Chiori Sigewinne Arlecchino
            Clorinde Emilie Kinich Mualani Xilonen Chasca Mavuika Citlali Varesa
            Escoffier Skirk Ineffa Lauma Flins Nefer Durin Columbina Zibai Varka
            Lohen Linnea Odette
        """.split())
        starters = {"Xiangling", "Noelle", "Kaeya", "Lisa"}
        self.assertEqual(
            {key for key, item in TARGET_PROFILES.items() if item.target_kind == "limited"},
            limited,
        )
        self.assertEqual(set(TARGET_CHARACTER_KEYS), limited | starters)
        self.assertEqual(TARGET_PROFILE_PROVENANCE["game_version"], "7.0")
        for key in limited:
            self.assertEqual(CHARACTERS[key].rarity, 5)
            self.assertEqual(CHARACTERS[key].availability, "limited")
            self.assertTrue(CHARACTERS[key].profile_source_url.startswith("https://"))
        for excluded in ("Jean", "Diluc", "Tighnari", "Dehya", "YumemizukiMizuki", "Aloy"):
            self.assertNotIn(excluded, TARGET_CHARACTER_KEYS)

    def test_every_target_profile_builds_a_five_slot_goal(self) -> None:
        for key in TARGET_CHARACTER_KEYS:
            with self.subTest(key=key):
                goal = character_goal(key, FarmPolicy.ECONOMY)
                self.assertEqual({item.slot for item in goal.targets}, set(Slot))
                self.assertEqual(
                    goal.constraints.set_requirements[0].set_name,
                    CHARACTERS[key].primary_set,
                )
                self.assertEqual(goal.constraints.set_requirements[0].pieces, 4)

    def test_every_target_has_a_bundled_square_avatar(self) -> None:
        avatar_directory = Path(__file__).resolve().parents[1] / "frontend" / "public" / "avatars"
        for key in TARGET_CHARACTER_KEYS:
            with self.subTest(key=key):
                icon = avatar_directory / f"{CHARACTERS[key].avatar_id}.png"
                self.assertTrue(icon.is_file(), f"missing avatar for {key}: {icon.name}")
                header = icon.read_bytes()[:24]
                self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(unpack(">II", header[16:24]), (256, 256))

    def test_nilou_profile_exposes_a_valid_two_plus_two_option(self) -> None:
        option = next(
            item
            for item in TARGET_PROFILES["Nilou"].set_options
            if item.option_id == "double_hp_2pc"
        )
        self.assertEqual(
            {(item.set_name, item.pieces) for item in option.requirements},
            {
                ("TenacityOfTheMillelith", 2),
                ("VourukashasGlow", 2),
            },
        )

    def test_separate_teams_keep_separate_objectives(self) -> None:
        plan = build_team_plan(TeamIntent(
            target_key="Mavuika",
            target_objective="comfort",
            target_team_mode="manual",
            target_team=["Mavuika", "Citlali", "Xilonen", "Bennett"],
            domain_team_mode="manual",
            domain_objective="max_dps",
            domain_team=["Nahida", "Xingqiu", "KukiShinobu", "Zhongli"],
        ))
        self.assertEqual(plan.target_objective, "comfort")
        self.assertEqual(plan.domain_objective, "max_dps")
        self.assertEqual(len(plan.expected_showcase_keys), 8)

    def test_same_team_preserves_two_independent_objectives(self) -> None:
        plan = build_team_plan(TeamIntent(
            target_key="Mavuika",
            target_objective="max_dps",
            target_team_mode="manual",
            target_team=["Mavuika", "Citlali", "Xilonen", "Bennett"],
            domain_team_mode="same",
            domain_objective="stable_rotation",
        ))
        self.assertEqual(plan.target_objective, "max_dps")
        self.assertEqual(plan.domain_objective, "stable_rotation")
        self.assertEqual(plan.domain_team, plan.target_team)

    def test_domain_auto_accepts_target_plus_three_teammates(self) -> None:
        intent = TeamIntent(
            target_key="Mavuika",
            target_team_mode="auto",
            domain_team_mode="auto",
            candidate_pool=["Citlali", "Xilonen", "Bennett"],
        )
        self.assertEqual(len(intent.candidate_pool), 3)

    def test_auto_mode_requires_an_explicit_candidate_pool(self) -> None:
        with self.assertRaises(ValidationError):
            TeamIntent(target_key="Nahida", target_team_mode="auto")

    def test_candidate_pool_can_contain_the_complete_roster_except_target(self) -> None:
        candidate_pool = [key for key in CHARACTERS if key != "Nahida"]
        intent = TeamIntent(
            target_key="Nahida",
            target_team_mode="auto",
            domain_team_mode="auto",
            candidate_pool=candidate_pool,
        )
        self.assertEqual(len(intent.candidate_pool), 115)

    def test_target_profiles_are_content_only_and_character_specific(self) -> None:
        mavuika = character_goal("Mavuika", FarmPolicy.ECONOMY)
        noelle = character_goal("Noelle", FarmPolicy.ECONOMY)
        mavuika_sands = next(item for item in mavuika.targets if item.slot is Slot.SANDS)
        noelle_sands = next(item for item in noelle.targets if item.slot is Slot.SANDS)
        self.assertEqual(mavuika.baseline_mode.value, "empty")
        self.assertIn(Stat.ELEMENTAL_MASTERY, mavuika_sands.allowed_main_stats)
        self.assertEqual(noelle_sands.allowed_main_stats, {Stat.DEF_PCT})


if __name__ == "__main__":
    unittest.main()
