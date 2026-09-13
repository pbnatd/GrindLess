from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from grindless.character_catalog import TeamIntent
from grindless.enka import EnkaCharacterProfile, EnkaClient, EnkaCollectionRegistry, EnkaShowcase


INTENT = TeamIntent(
    target_key="Mavuika",
    target_team_mode="manual",
    target_team=["Mavuika", "Citlali", "Xilonen", "Bennett"],
    domain_team_mode="same",
)


def profile(key: str, avatar_id: int, captured_at: datetime) -> EnkaCharacterProfile:
    return EnkaCharacterProfile(
        character_key=key,
        name_ru={"Mavuika": "Мавуика", "Citlali": "Ситлали", "Xilonen": "Шилонен", "Bennett": "Беннет"}[key],
        avatar_id=avatar_id,
        captured_at=captured_at,
        constellation=0,
    )


class EnkaTests(unittest.TestCase):
    def test_female_traveler_showcase_maps_to_shared_traveler_candidate(self) -> None:
        client = EnkaClient(lambda uid: {
            "ttl": 0,
            "avatarInfoList": [{"avatarId": 10000007, "talentIdList": [], "equipList": []}],
        })

        result = client.fetch_showcase("700123456", consent=True)

        self.assertEqual(result.profiles[0].character_key, "Traveler")
        self.assertEqual(result.profiles[0].avatar_id, 10000007)

    def test_client_requires_consent_and_honors_ttl_cache(self) -> None:
        calls = []
        payload = {
            "ttl": 60,
            "avatarInfoList": [{
                "avatarId": 10000106,
                "propMap": {"4001": {"val": "90"}},
                "talentIdList": [1, 2],
                "skillLevelMap": {"1": 6},
                "equipList": [{"itemId": 12510, "weapon": {"level": 90, "affixMap": {"1": 0}}, "flat": {"icon": "weapon"}}],
            }],
        }
        client = EnkaClient(lambda uid: calls.append(uid) or payload)
        with self.assertRaises(ValueError):
            client.fetch_showcase("700123456", consent=False)
        first = client.fetch_showcase("700123456", consent=True)
        second = client.fetch_showcase("700123456", consent=True)
        self.assertEqual(calls, ["700123456"])
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(first.profiles[0].constellation, 2)
        self.assertEqual(first.profiles[0].weapon_refinement, 1)

    def test_snapshots_merge_and_newest_repeated_profile_wins(self) -> None:
        registry = EnkaCollectionRegistry()
        now = datetime.now(timezone.utc)
        first = EnkaShowcase(
            uid_last4="3456", ttl_seconds=0, captured_at=now,
            profiles=[profile("Mavuika", 10000106, now), profile("Citlali", 10000107, now)],
        )
        view = registry.merge("700123456", first, INTENT)
        self.assertEqual(set(view.missing_keys), {"Xilonen", "Bennett"})
        newer = profile("Mavuika", 10000106, now + timedelta(seconds=1)).model_copy(update={"constellation": 2})
        second = EnkaShowcase(
            uid_last4="3456", ttl_seconds=0, captured_at=now,
            profiles=[newer, profile("Xilonen", 10000103, now), profile("Bennett", 10000032, now)],
        )
        merged = registry.merge("700123456", second, INTENT, view.collection_id)
        self.assertTrue(merged.complete)
        self.assertEqual(len(merged.profiles), 4)
        self.assertEqual(registry.target_profile(view.collection_id, "Mavuika").constellation, 2)

    def test_collection_is_bound_to_the_same_uid(self) -> None:
        registry = EnkaCollectionRegistry()
        now = datetime.now(timezone.utc)
        showcase = EnkaShowcase(uid_last4="3456", ttl_seconds=0, captured_at=now, profiles=[profile("Mavuika", 10000106, now)])
        view = registry.merge("700123456", showcase, INTENT)
        with self.assertRaisesRegex(ValueError, "UID"):
            registry.merge("800123456", showcase, INTENT, view.collection_id)

    def test_discovery_collects_unknown_plan_then_requires_explicit_finalize(self) -> None:
        registry = EnkaCollectionRegistry()
        now = datetime.now(timezone.utc)
        first = EnkaShowcase(
            uid_last4="3456",
            ttl_seconds=0,
            captured_at=now,
            profiles=[
                profile("Mavuika", 10000106, now),
                profile("Citlali", 10000107, now),
                profile("Xilonen", 10000103, now),
                profile("Bennett", 10000032, now),
            ],
        )

        discovered = registry.merge(
            "700123456",
            first,
            None,
            mode="discovery",
        )

        self.assertEqual(discovered.mode, "discovery")
        self.assertFalse(discovered.finalized)
        self.assertFalse(discovered.complete)
        self.assertEqual(set(discovered.observed_keys), set(INTENT.target_team))

        finalized = registry.finalize(discovered.collection_id, INTENT)
        self.assertTrue(finalized.finalized)
        self.assertTrue(finalized.complete)
        self.assertEqual(finalized.missing_keys, [])

    def test_discovery_finalize_fails_loudly_for_unobserved_selection(self) -> None:
        registry = EnkaCollectionRegistry()
        now = datetime.now(timezone.utc)
        discovered = registry.merge(
            "700123456",
            EnkaShowcase(
                uid_last4="3456",
                ttl_seconds=0,
                captured_at=now,
                profiles=[profile("Mavuika", 10000106, now)],
            ),
            None,
            mode="discovery",
        )

        with self.assertRaisesRegex(ValueError, "не хватает"):
            registry.finalize(discovered.collection_id, INTENT)

    def test_collection_mode_cannot_change_midstream(self) -> None:
        registry = EnkaCollectionRegistry()
        now = datetime.now(timezone.utc)
        showcase = EnkaShowcase(
            uid_last4="3456",
            ttl_seconds=0,
            captured_at=now,
            profiles=[profile("Mavuika", 10000106, now)],
        )
        discovered = registry.merge(
            "700123456",
            showcase,
            None,
            mode="discovery",
        )

        with self.assertRaisesRegex(ValueError, "режим"):
            registry.merge(
                "700123456",
                showcase,
                INTENT,
                discovered.collection_id,
                mode="planned",
            )


if __name__ == "__main__":
    unittest.main()
