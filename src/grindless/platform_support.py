from __future__ import annotations

import platform as platform_module
from dataclasses import asdict, dataclass
from enum import StrEnum


class HostPlatform(StrEnum):
    MACOS = "macos"
    WINDOWS = "windows"
    LINUX = "linux"
    UNKNOWN = "unknown"


class SupportStatus(StrEnum):
    AVAILABLE = "available"
    EXPERIMENTAL = "experimental"
    PLANNED = "planned"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CapabilitySupport:
    status: SupportStatus
    reason: str


@dataclass(frozen=True)
class PlatformSupport:
    host: HostPlatform
    architecture: str
    simulator: CapabilitySupport
    good_import: CapabilitySupport
    video_import: CapabilitySupport
    local_qwen: CapabilitySupport
    cloud_luna: CapabilitySupport
    game_execution: CapabilitySupport

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_host(system_name: str | None = None) -> HostPlatform:
    observed = (system_name or platform_module.system()).strip().lower()
    return {
        "darwin": HostPlatform.MACOS,
        "windows": HostPlatform.WINDOWS,
        "linux": HostPlatform.LINUX,
    }.get(observed, HostPlatform.UNKNOWN)


def platform_support(
    *, system_name: str | None = None, architecture: str | None = None
) -> PlatformSupport:
    host = detect_host(system_name)
    observed_architecture = (
        (architecture or platform_module.machine() or "unknown").strip().lower()
    )

    portable = host is not HostPlatform.UNKNOWN
    simulator = CapabilitySupport(
        SupportStatus.AVAILABLE if portable else SupportStatus.UNAVAILABLE,
        "Симуляция работает независимо от игрового клиента."
        if portable
        else "Эта операционная система не поддерживается.",
    )
    good_import = CapabilitySupport(
        SupportStatus.AVAILABLE if portable else SupportStatus.UNAVAILABLE,
        "Импорт GOOD и подбор артефактов доступны на этой системе."
        if portable
        else "Импорт GOOD доступен только на поддерживаемых настольных системах.",
    )
    video_import = CapabilitySupport(
        SupportStatus.EXPERIMENTAL if portable else SupportStatus.UNAVAILABLE,
        "Импорт через Artiscan работает в тестовом режиме."
        if portable
        else "Импорт видео доступен только на поддерживаемых настольных системах.",
    )

    if host is HostPlatform.MACOS:
        local_qwen_reason = (
            "Можно подключить внешний совместимый сервис с Metal на Apple Silicon; "
            "встроенный запуск пока не готов."
        )
        execution_reason = (
            "Управление игрой на macOS пока недоступно; анализ продолжает работать."
        )
        execution_status = SupportStatus.UNAVAILABLE
    elif host is HostPlatform.WINDOWS:
        local_qwen_reason = (
            "Можно подключить внешний совместимый сервис на CUDA или CPU; "
            "встроенный запуск пока не готов."
        )
        execution_reason = "Поддержка наблюдения за игрой в Windows запланирована, но пока не реализована."
        execution_status = SupportStatus.PLANNED
    elif host is HostPlatform.LINUX:
        local_qwen_reason = (
            "Можно подключить внешний совместимый сервис на CUDA или CPU; "
            "встроенный запуск пока не готов."
        )
        execution_reason = (
            "На Linux/X11 приложение умеет находить одно окно Genshin размером 1920×1080, "
            "делать снимки и распознавать состояние экрана. Управление включается отдельно; "
            "автономная навигация, бой и получение наград пока не реализованы."
        )
        execution_status = SupportStatus.EXPERIMENTAL
    else:
        local_qwen_reason = (
            "Для этой операционной системы нет готового локального пакета."
        )
        execution_reason = (
            "Управление игрой на этой операционной системе не поддерживается."
        )
        execution_status = SupportStatus.UNAVAILABLE

    local_qwen = CapabilitySupport(
        SupportStatus.EXPERIMENTAL if portable else SupportStatus.UNAVAILABLE,
        local_qwen_reason,
    )
    cloud_luna = CapabilitySupport(
        SupportStatus.EXPERIMENTAL if portable else SupportStatus.UNAVAILABLE,
        "Для облачного анализа нужны API-ключ и доступная модель."
        if portable
        else "Настольное приложение для этой операционной системы не собрано.",
    )
    game_execution = CapabilitySupport(execution_status, execution_reason)

    return PlatformSupport(
        host=host,
        architecture=observed_architecture,
        simulator=simulator,
        good_import=good_import,
        video_import=video_import,
        local_qwen=local_qwen,
        cloud_luna=cloud_luna,
        game_execution=game_execution,
    )
