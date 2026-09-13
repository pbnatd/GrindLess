from __future__ import annotations

import os
import platform as platform_module
import shutil
import subprocess
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence


EXPECTED_WIDTH = 1920
EXPECTED_HEIGHT = 1080
DEFAULT_WINDOW_NAME = "Genshin Impact"
INPUT_ENABLE_ENV = "GRINDLESS_ENABLE_GAME_INPUT"


class LinuxGameStatus(StrEnum):
    UNSUPPORTED = "unsupported"
    SETUP_REQUIRED = "setup_required"
    GAME_NOT_RUNNING = "game_not_running"
    NEEDS_ATTENTION = "needs_attention"
    READY = "ready"


class LinuxGameControlError(RuntimeError):
    """The input boundary could not prove that an action is safe to issue."""


class EmergencyStopRequested(LinuxGameControlError):
    """The operator requested a fail-safe stop."""


@dataclass(frozen=True)
class ProbeCheck:
    code: str
    ok: bool
    required: bool
    message: str


@dataclass(frozen=True)
class WindowGeometry:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class LinuxGameReadiness:
    status: LinuxGameStatus
    input_enabled: bool
    session_type: str
    display: str | None
    window_id: str | None
    window_geometry: WindowGeometry | None
    checks: tuple[ProbeCheck, ...]
    next_action: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    def run(self, command: Sequence[str]) -> CommandResult: ...


class SubprocessCommandRunner:
    def run(self, command: Sequence[str]) -> CommandResult:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _parse_geometry(output: str) -> WindowGeometry:
    values: dict[str, int] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in {"X", "Y", "WIDTH", "HEIGHT"}:
            try:
                values[key] = int(value)
            except ValueError as exc:
                raise LinuxGameControlError(
                    f"xdotool returned a non-numeric {key}: {value!r}"
                ) from exc
    missing = {"X", "Y", "WIDTH", "HEIGHT"} - values.keys()
    if missing:
        raise LinuxGameControlError(
            "xdotool geometry is incomplete: " + ", ".join(sorted(missing))
        )
    return WindowGeometry(
        x=values["X"],
        y=values["Y"],
        width=values["WIDTH"],
        height=values["HEIGHT"],
    )


def _binary_available(
    name: str, *, which: Callable[[str], str | None] = shutil.which
) -> bool:
    return bool(which(name))


def probe_linux_game(
    *,
    system_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    runner: CommandRunner | None = None,
    which: Callable[[str], str | None] = shutil.which,
    window_name: str = DEFAULT_WINDOW_NAME,
) -> LinuxGameReadiness:
    """Inspect Linux/X11 readiness without focusing the game or sending input."""

    environment = os.environ if environ is None else environ
    observed_system = (system_name or platform_module.system()).strip().lower()
    session_type = environment.get("XDG_SESSION_TYPE", "unknown").strip().lower()
    display = environment.get("DISPLAY") or None
    input_enabled = environment.get(INPUT_ENABLE_ENV) == "1"
    checks: list[ProbeCheck] = []

    is_linux = observed_system == "linux"
    checks.append(
        ProbeCheck("linux_host", is_linux, True, "Linux обнаружен" if is_linux else "Этот режим доступен только на Linux")
    )
    if not is_linux:
        return LinuxGameReadiness(
            status=LinuxGameStatus.UNSUPPORTED,
            input_enabled=False,
            session_type=session_type,
            display=display,
            window_id=None,
            window_geometry=None,
            checks=tuple(checks),
            next_action="Откройте GrindLess на Linux-компьютере, где запущена игра.",
        )

    is_x11 = session_type == "x11"
    checks.append(
        ProbeCheck(
            "x11_session",
            is_x11,
            True,
            "Сеанс X11 активен" if is_x11 else f"Нужен X11; сейчас используется {session_type or 'неизвестный сеанс'}",
        )
    )
    checks.append(
        ProbeCheck(
            "display_available",
            bool(display),
            True,
            f"Экран найден: DISPLAY={display}" if display else "Переменная DISPLAY не задана",
        )
    )

    xdotool_available = _binary_available("xdotool", which=which)
    maim_available = _binary_available("maim", which=which)
    checks.extend(
        (
            ProbeCheck(
                "xdotool_installed",
                xdotool_available,
                True,
                "xdotool установлен" if xdotool_available else "Установите xdotool",
            ),
            ProbeCheck(
                "maim_installed",
                maim_available,
                True,
                "maim установлен" if maim_available else "Установите maim",
            ),
        )
    )

    if not all(item.ok for item in checks if item.required):
        return LinuxGameReadiness(
            status=LinuxGameStatus.SETUP_REQUIRED,
            input_enabled=input_enabled,
            session_type=session_type,
            display=display,
            window_id=None,
            window_geometry=None,
            checks=tuple(checks),
            next_action="Исправьте отмеченные пункты и повторите проверку.",
        )

    command_runner = runner or SubprocessCommandRunner()
    window_search = command_runner.run(
        ("xdotool", "search", "--onlyvisible", "--name", window_name)
    )
    window_ids = tuple(
        line.strip() for line in window_search.stdout.splitlines() if line.strip()
    )
    exactly_one_window = window_search.returncode == 0 and len(window_ids) == 1
    checks.append(
        ProbeCheck(
            "single_game_window",
            exactly_one_window,
            True,
            "Найдено одно окно Genshin"
            if exactly_one_window
            else (
                "Окно Genshin не найдено"
                if not window_ids
                else f"Нужно оставить одно окно Genshin; сейчас найдено {len(window_ids)}"
            ),
        )
    )
    if not window_ids:
        return LinuxGameReadiness(
            status=LinuxGameStatus.GAME_NOT_RUNNING,
            input_enabled=input_enabled,
            session_type=session_type,
            display=display,
            window_id=None,
            window_geometry=None,
            checks=tuple(checks),
            next_action="Запустите Genshin, войдите в игру и оставьте открытым одно окно.",
        )
    if not exactly_one_window:
        return LinuxGameReadiness(
            status=LinuxGameStatus.NEEDS_ATTENTION,
            input_enabled=input_enabled,
            session_type=session_type,
            display=display,
            window_id=None,
            window_geometry=None,
            checks=tuple(checks),
            next_action="Закройте лишние подходящие окна перед включением управления.",
        )

    window_id = window_ids[0]
    geometry_result = command_runner.run(
        ("xdotool", "getwindowgeometry", "--shell", window_id)
    )
    try:
        geometry = (
            _parse_geometry(geometry_result.stdout)
            if geometry_result.returncode == 0
            else None
        )
    except LinuxGameControlError:
        geometry = None
    expected_geometry = bool(
        geometry
        and geometry.width == EXPECTED_WIDTH
        and geometry.height == EXPECTED_HEIGHT
    )
    checks.append(
        ProbeCheck(
            "expected_game_size",
            expected_geometry,
            True,
            f"Размер игрового окна: {EXPECTED_WIDTH}×{EXPECTED_HEIGHT}"
            if expected_geometry
            else (
                f"Нужен размер {EXPECTED_WIDTH}×{EXPECTED_HEIGHT}; сейчас {geometry.width}×{geometry.height}"
                if geometry
                else "Не удалось определить размер окна игры"
            ),
        )
    )

    active_result = command_runner.run(("xdotool", "getactivewindow"))
    active_window = active_result.stdout.strip() if active_result.returncode == 0 else ""
    focused = active_window == window_id
    checks.append(
        ProbeCheck(
            "game_has_focus",
            focused,
            False,
            "Окно Genshin активно" if focused else "Перед тестом переключитесь на окно Genshin",
        )
    )

    status = LinuxGameStatus.READY if expected_geometry else LinuxGameStatus.NEEDS_ATTENTION
    next_action = (
        "Наблюдение готово. Управление останется выключенным, пока вы не включите его вручную."
        if status is LinuxGameStatus.READY
        else "Переключите Genshin в безрамочный режим 1920×1080 и повторите проверку."
    )
    return LinuxGameReadiness(
        status=status,
        input_enabled=input_enabled,
        session_type=session_type,
        display=display,
        window_id=window_id,
        window_geometry=geometry,
        checks=tuple(checks),
        next_action=next_action,
    )


class LinuxX11GameControl:
    """Minimal guarded X11 capture/input driver; it does not own game decisions."""

    _ALLOWED_KEYS = frozenset(
        {"w", "a", "s", "d", "e", "q", "f", "space", "escape", "return", "1", "2", "3", "4"}
    )

    def __init__(
        self,
        readiness: LinuxGameReadiness,
        *,
        runner: CommandRunner | None = None,
        stop_file: Path | None = None,
    ) -> None:
        if readiness.status is not LinuxGameStatus.READY or not readiness.window_id:
            raise LinuxGameControlError(
                f"Linux game control is not ready: {readiness.status.value}"
            )
        self.readiness = readiness
        self.runner = runner or SubprocessCommandRunner()
        self.stop_file = stop_file or Path.home() / ".grindless" / "STOP_GAME_INPUT"

    def _run_required(self, command: Sequence[str]) -> CommandResult:
        result = self.runner.run(command)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise LinuxGameControlError(f"Command failed: {' '.join(command)}: {detail}")
        return result

    def _assert_verified_window(self) -> None:
        active = self._run_required(("xdotool", "getactivewindow")).stdout.strip()
        if active != self.readiness.window_id:
            raise LinuxGameControlError("Genshin lost focus; the window was not observed")
        geometry = _parse_geometry(
            self._run_required(
                ("xdotool", "getwindowgeometry", "--shell", self.readiness.window_id)
            ).stdout
        )
        if geometry.width != EXPECTED_WIDTH or geometry.height != EXPECTED_HEIGHT:
            raise LinuxGameControlError(
                "Genshin window size changed; the window was not observed"
            )

    def _assert_safe_input_state(self) -> None:
        if not self.readiness.input_enabled:
            raise LinuxGameControlError(
                f"Game input is disarmed; set {INPUT_ENABLE_ENV}=1 only for a supervised test"
            )
        if self.stop_file.exists():
            raise EmergencyStopRequested(
                f"Emergency stop file exists: {self.stop_file}"
            )
        try:
            self._assert_verified_window()
        except LinuxGameControlError as exc:
            raise LinuxGameControlError(
                str(exc).replace("the window was not observed", "no input was sent")
            ) from exc
        pointer = self._run_required(("xdotool", "getmouselocation", "--shell")).stdout
        pointer_values = {
            key: int(value)
            for key, value in (line.split("=", 1) for line in pointer.splitlines() if "=" in line)
            if key in {"X", "Y"} and value.lstrip("-").isdigit()
        }
        if pointer_values.get("X", 999) <= 5 and pointer_values.get("Y", 999) <= 5:
            raise EmergencyStopRequested("Pointer is in the top-left fail-safe corner")

    def capture_png(self) -> bytes:
        self._assert_verified_window()
        result = subprocess.run(
            ("maim", "--format=png", "--window", self.readiness.window_id),
            check=False,
            capture_output=True,
        )
        if result.returncode != 0 or not result.stdout.startswith(b"\x89PNG"):
            detail = result.stderr.decode(errors="replace").strip() or "invalid PNG output"
            raise LinuxGameControlError(f"Could not capture the Genshin window: {detail}")
        return result.stdout

    def click(self, x: int, y: int) -> None:
        if not (0 <= x < EXPECTED_WIDTH and 0 <= y < EXPECTED_HEIGHT):
            raise ValueError("click coordinates must be inside the 1920x1080 game area")
        self._assert_safe_input_state()
        self._run_required(
            (
                "xdotool",
                "mousemove",
                "--window",
                self.readiness.window_id,
                str(x),
                str(y),
                "click",
                "1",
            )
        )

    def press(self, key: str) -> None:
        normalized = key.strip().lower()
        if normalized not in self._ALLOWED_KEYS:
            raise ValueError(f"key is not in the game-control allowlist: {key!r}")
        self._assert_safe_input_state()
        self._run_required(("xdotool", "key", "--clearmodifiers", normalized))
