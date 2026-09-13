from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock, Timer
from time import monotonic
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, model_validator

from .character_catalog import CHARACTER_BY_AVATAR_ID, CHARACTERS, TeamIntent, build_team_plan

ENKA_UID_URL = "https://enka.network/api/uid/{uid}/"
USER_AGENT = "GrindLess-Agent/0.28 (local educational prototype)"
COLLECTION_TTL_SECONDS = 30 * 60
EnkaCollectionMode = Literal["planned", "discovery"]


class EnkaError(RuntimeError):
    """An Enka lookup failed without producing usable showcase data."""


class EnkaCharacterProfile(BaseModel):
    character_key: str
    name_ru: str
    avatar_id: int
    captured_at: datetime
    character_level: int | None = None
    character_ascension: int | None = None
    constellation: int = Field(ge=0, le=6)
    skill_levels: dict[str, int] = Field(default_factory=dict)
    weapon_id: int | None = None
    weapon_icon: str | None = None
    weapon_level: int | None = None
    weapon_ascension: int | None = None
    weapon_refinement: int | None = Field(default=None, ge=1, le=5)


class EnkaShowcase(BaseModel):
    uid_last4: str
    ttl_seconds: int = Field(ge=0)
    cache_hit: bool = False
    captured_at: datetime
    profiles: list[EnkaCharacterProfile]


class EnkaSnapshotRequest(BaseModel):
    uid: str
    consent: bool = False
    mode: EnkaCollectionMode = "planned"
    team_intent: TeamIntent | None = None
    collection_id: str | None = None

    @model_validator(mode="after")
    def validate_mode(self) -> EnkaSnapshotRequest:
        if self.mode == "planned" and self.team_intent is None:
            raise ValueError("planned Enka collection requires team_intent")
        if self.mode == "discovery" and self.team_intent is not None:
            raise ValueError("discovery Enka collection must not predeclare team_intent")
        return self


class EnkaCollectionFinalizeRequest(BaseModel):
    team_intent: TeamIntent


class EnkaCollectionView(BaseModel):
    collection_id: str
    mode: EnkaCollectionMode
    finalized: bool
    uid_last4: str
    profiles: list[EnkaCharacterProfile]
    observed_keys: list[str]
    missing_keys: list[str]
    complete: bool
    ttl_seconds: int
    cache_hit: bool
    retention_seconds: int = COLLECTION_TTL_SECONDS
    privacy_notice: str = (
        "В Enka отправлен только UID; видео и GOOD не отправлялись. "
        "Снимки хранятся только в памяти локального процесса."
    )


@dataclass
class _CacheEntry:
    showcase: EnkaShowcase
    expires_at: float


@dataclass
class _Collection:
    uid_proof: bytes
    uid_last4: str
    mode: EnkaCollectionMode
    profiles: dict[str, EnkaCharacterProfile]
    expected_keys: set[str]
    finalized: bool
    expires_at: float


class EnkaClient:
    def __init__(self, fetch_json: Callable[[str], dict[str, Any]] | None = None) -> None:
        self._fetch_json = fetch_json or self._request_json
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = RLock()

    def fetch_showcase(self, uid: str, *, consent: bool) -> EnkaShowcase:
        normalized = uid.strip()
        if not consent:
            raise ValueError("нужно явно разрешить отправку UID в Enka.Network")
        if not re.fullmatch(r"[1-9][0-9]{8,9}", normalized):
            raise ValueError("UID должен содержать 9 или 10 цифр")
        now = monotonic()
        with self._lock:
            cached = self._cache.get(normalized)
            if cached is not None and cached.expires_at > now:
                return cached.showcase.model_copy(update={"cache_hit": True})
            self._cache.pop(normalized, None)

        payload = self._fetch_json(normalized)
        avatars = payload.get("avatarInfoList")
        if not isinstance(avatars, list):
            raise EnkaError("витрина закрыта или в ней нет персонажей")
        captured_at = datetime.now(timezone.utc)
        profiles = [
            profile
            for raw in avatars
            if isinstance(raw, dict)
            and (profile := _parse_profile(raw, captured_at)) is not None
        ]
        if not profiles:
            raise EnkaError("в витрине нет персонажей, известных текущему каталогу")
        ttl = max(0, int(payload.get("ttl", 0) or 0))
        showcase = EnkaShowcase(
            uid_last4=normalized[-4:],
            ttl_seconds=ttl,
            captured_at=captured_at,
            profiles=profiles,
        )
        if ttl > 0:
            entry = _CacheEntry(showcase=showcase, expires_at=now + ttl)
            with self._lock:
                self._cache[normalized] = entry
            timer = Timer(ttl, self._expire, args=(normalized, entry.expires_at))
            timer.daemon = True
            timer.start()
        return showcase

    def _expire(self, uid: str, expires_at: float) -> None:
        with self._lock:
            entry = self._cache.get(uid)
            if entry is not None and entry.expires_at == expires_at:
                self._cache.pop(uid, None)

    @staticmethod
    def _request_json(uid: str) -> dict[str, Any]:
        request = Request(
            ENKA_UID_URL.format(uid=uid),
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urlopen(request, timeout=20) as response:  # noqa: S310 - pinned HTTPS
                payload = json.load(response)
        except HTTPError as exc:
            messages = {
                400: "неверный формат UID",
                404: "игрок не найден",
                424: "Genshin или Enka находятся на обслуживании",
                429: "лимит Enka исчерпан; дождитесь окончания TTL",
            }
            raise EnkaError(messages.get(exc.code, f"Enka вернул HTTP {exc.code}")) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise EnkaError(f"Enka недоступен: {exc}") from exc
        if not isinstance(payload, dict):
            raise EnkaError("Enka вернул ответ неизвестного формата")
        return payload


class EnkaCollectionRegistry:
    def __init__(self) -> None:
        self._secret = secrets.token_bytes(32)
        self._collections: dict[str, _Collection] = {}
        self._lock = RLock()

    def merge(
        self,
        uid: str,
        showcase: EnkaShowcase,
        intent: TeamIntent | None,
        collection_id: str | None = None,
        *,
        mode: EnkaCollectionMode = "planned",
    ) -> EnkaCollectionView:
        if mode == "planned" and intent is None:
            raise ValueError("planned Enka collection requires team_intent")
        if mode == "discovery" and intent is not None:
            raise ValueError("discovery Enka collection must not predeclare team_intent")
        proof = hmac.digest(self._secret, uid.strip().encode(), hashlib.sha256)
        now = monotonic()
        with self._lock:
            if collection_id is None:
                collection_id = secrets.token_urlsafe(24)
                collection = _Collection(
                    uid_proof=proof,
                    uid_last4=showcase.uid_last4,
                    mode=mode,
                    profiles={},
                    expected_keys=set(),
                    finalized=False,
                    expires_at=now + COLLECTION_TTL_SECONDS,
                )
            else:
                collection = self._collections.get(collection_id)
                if collection is None or collection.expires_at <= now:
                    self._collections.pop(collection_id, None)
                    raise ValueError("коллекция Enka не найдена или истекла")
                if not hmac.compare_digest(collection.uid_proof, proof):
                    raise ValueError("UID не совпадает с ранее загруженной коллекцией")
                if collection.mode != mode:
                    raise ValueError("режим коллекции Enka нельзя менять после первого снимка")
            for profile in showcase.profiles:
                previous = collection.profiles.get(profile.character_key)
                if previous is None or profile.captured_at >= previous.captured_at:
                    collection.profiles[profile.character_key] = profile
            if mode == "planned":
                assert intent is not None
                collection.expected_keys = set(build_team_plan(intent).expected_showcase_keys)
                collection.finalized = collection.expected_keys <= set(collection.profiles)
            else:
                collection.expected_keys = set()
                collection.finalized = False
            collection.expires_at = now + COLLECTION_TTL_SECONDS
            self._collections[collection_id] = collection
        self._schedule_expiry(collection_id, collection.expires_at)
        return self.view(collection_id, showcase)

    def view(
        self,
        collection_id: str,
        showcase: EnkaShowcase | None = None,
    ) -> EnkaCollectionView:
        with self._lock:
            collection = self._collections.get(collection_id)
            if collection is None or collection.expires_at <= monotonic():
                self._collections.pop(collection_id, None)
                raise ValueError("коллекция Enka не найдена или истекла")
            profiles = sorted(collection.profiles.values(), key=lambda item: item.name_ru)
            observed = {profile.character_key for profile in profiles}
            missing = sorted(collection.expected_keys - observed)
            return EnkaCollectionView(
                collection_id=collection_id,
                mode=collection.mode,
                finalized=collection.finalized,
                uid_last4=collection.uid_last4,
                profiles=profiles,
                observed_keys=sorted(observed),
                missing_keys=missing,
                complete=collection.finalized and not missing,
                ttl_seconds=showcase.ttl_seconds if showcase is not None else 0,
                cache_hit=showcase.cache_hit if showcase is not None else False,
            )

    def finalize(
        self,
        collection_id: str,
        intent: TeamIntent,
    ) -> EnkaCollectionView:
        plan = build_team_plan(intent)
        with self._lock:
            collection = self._collections.get(collection_id)
            if collection is None or collection.expires_at <= monotonic():
                self._collections.pop(collection_id, None)
                raise ValueError("коллекция Enka не найдена или истекла")
            if collection.mode != "discovery":
                raise ValueError("явное завершение доступно только для discovery-коллекции")
            expected = set(plan.expected_showcase_keys)
            missing = sorted(expected - set(collection.profiles))
            if missing:
                raise ValueError(
                    "в собранных витринах не хватает выбранных персонажей: "
                    + ", ".join(missing)
                )
            collection.expected_keys = expected
            collection.finalized = True
        return self.view(collection_id)

    def target_profile(self, collection_id: str | None, target_key: str) -> EnkaCharacterProfile | None:
        if collection_id is None:
            return None
        with self._lock:
            collection = self._collections.get(collection_id)
            if collection is None or collection.expires_at <= monotonic():
                self._collections.pop(collection_id, None)
                raise ValueError("коллекция Enka не найдена или истекла")
            return collection.profiles.get(target_key)

    def profiles(self, collection_id: str) -> list[EnkaCharacterProfile]:
        with self._lock:
            collection = self._collections.get(collection_id)
            if collection is None or collection.expires_at <= monotonic():
                self._collections.pop(collection_id, None)
                raise ValueError("коллекция Enka не найдена или истекла")
            return list(collection.profiles.values())

    def _schedule_expiry(self, collection_id: str, expires_at: float) -> None:
        timer = Timer(
            COLLECTION_TTL_SECONDS,
            self._expire,
            args=(collection_id, expires_at),
        )
        timer.daemon = True
        timer.start()

    def _expire(self, collection_id: str, expires_at: float) -> None:
        with self._lock:
            collection = self._collections.get(collection_id)
            if collection is not None and collection.expires_at == expires_at:
                self._collections.pop(collection_id, None)


def _parse_profile(raw: dict[str, Any], captured_at: datetime) -> EnkaCharacterProfile | None:
    definition = CHARACTER_BY_AVATAR_ID.get(int(raw.get("avatarId", 0) or 0))
    if definition is None:
        return None
    props = raw.get("propMap") or {}
    equipment = raw.get("equipList") or []
    weapon = next(
        (item for item in equipment if isinstance(item, dict) and "weapon" in item),
        None,
    )
    weapon_data = weapon.get("weapon", {}) if isinstance(weapon, dict) else {}
    affixes = weapon_data.get("affixMap") or {}
    flat = weapon.get("flat", {}) if isinstance(weapon, dict) else {}
    return EnkaCharacterProfile(
        character_key=definition.key,
        name_ru=definition.name_ru,
        avatar_id=int(raw.get("avatarId", 0) or 0),
        captured_at=captured_at,
        character_level=_prop_int(props, "4001"),
        character_ascension=_prop_int(props, "1002"),
        constellation=len(raw.get("talentIdList") or []),
        skill_levels={
            str(key): int(value)
            for key, value in (raw.get("skillLevelMap") or {}).items()
        },
        weapon_id=int(weapon.get("itemId", 0) or 0) if isinstance(weapon, dict) else None,
        weapon_icon=str(flat.get("icon")) if flat.get("icon") else None,
        weapon_level=int(weapon_data.get("level", 0) or 0) or None,
        weapon_ascension=int(weapon_data.get("promoteLevel", 0) or 0),
        weapon_refinement=(
            max((int(value) for value in affixes.values()), default=0) + 1
            if weapon is not None
            else None
        ),
    )


def _prop_int(props: dict[str, Any], key: str) -> int | None:
    item = props.get(key)
    if not isinstance(item, dict) or item.get("val") is None:
        return None
    return int(item["val"])
