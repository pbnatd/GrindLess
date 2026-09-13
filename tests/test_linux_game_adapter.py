from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Sequence

from grindless.linux_game_adapter import (
    CommandResult,
    LinuxGameControlError,
    LinuxGameStatus,
    LinuxX11GameControl,
    probe_linux_game,
)


GEOMETRY = "WINDOW=42\nX=0\nY=0\nWIDTH=1920\nHEIGHT=1080\nSCREEN=0\n"


class FakeRunner:
    def __init__(self, active_window: str = "42") -> None:
        self.active_window = active_window
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: Sequence[str]) -> CommandResult:
        observed = tuple(command)
        self.commands.append(observed)
        if observed[:3] == ("xdotool", "search", "--onlyvisible"):
            return CommandResult(0, "42\n")
        if observed[:3] == ("xdotool", "getwindowgeometry", "--shell"):
            return CommandResult(0, GEOMETRY)
        if observed == ("xdotool", "getactivewindow"):
            return CommandResult(0, f"{self.active_window}\n")
        if observed == ("xdotool", "getmouselocation", "--shell"):
            return CommandResult(0, "X=700\nY=500\nSCREEN=0\nWINDOW=42\n")
        return CommandResult(0)


def all_binaries(_: str) -> str:
    return "/usr/bin/tool"


class LinuxGameProbeTests(unittest.TestCase):
    def test_non_linux_host_is_explicitly_unsupported(self) -> None:
        report = probe_linux_game(system_name="Darwin", environ={}, which=all_binaries)

        self.assertEqual(report.status, LinuxGameStatus.UNSUPPORTED)
        self.assertIsNone(report.window_id)

    def test_wayland_blocks_control_before_window_search(self) -> None:
        runner = FakeRunner()
        report = probe_linux_game(
            system_name="Linux",
            environ={"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":1"},
            runner=runner,
            which=all_binaries,
        )

        self.assertEqual(report.status, LinuxGameStatus.SETUP_REQUIRED)
        self.assertEqual(runner.commands, [])
        self.assertFalse(next(item for item in report.checks if item.code == "x11_session").ok)

    def test_ready_probe_records_window_geometry_without_sending_input(self) -> None:
        runner = FakeRunner()
        report = probe_linux_game(
            system_name="Linux",
            environ={"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"},
            runner=runner,
            which=all_binaries,
        )

        self.assertEqual(report.status, LinuxGameStatus.READY)
        self.assertEqual(report.window_id, "42")
        self.assertEqual(report.window_geometry.width, 1920)
        self.assertFalse(report.input_enabled)
        self.assertFalse(any("click" in command for command in runner.commands))

    def test_input_requires_both_ready_probe_and_explicit_arm(self) -> None:
        runner = FakeRunner()
        report = probe_linux_game(
            system_name="Linux",
            environ={"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"},
            runner=runner,
            which=all_binaries,
        )
        commands_before = len(runner.commands)
        control = LinuxX11GameControl(report, runner=runner)

        with self.assertRaisesRegex(LinuxGameControlError, "disarmed"):
            control.click(100, 100)

        self.assertEqual(len(runner.commands), commands_before)

    def test_focus_loss_stops_before_click(self) -> None:
        probe_runner = FakeRunner()
        report = probe_linux_game(
            system_name="Linux",
            environ={
                "XDG_SESSION_TYPE": "x11",
                "DISPLAY": ":0",
                "GRINDLESS_ENABLE_GAME_INPUT": "1",
            },
            runner=probe_runner,
            which=all_binaries,
        )
        action_runner = FakeRunner(active_window="99")
        with tempfile.TemporaryDirectory() as directory:
            control = LinuxX11GameControl(
                report,
                runner=action_runner,
                stop_file=Path(directory) / "stop",
            )
            with self.assertRaisesRegex(LinuxGameControlError, "lost focus"):
                control.press("e")

        self.assertFalse(any("key" in command for command in action_runner.commands))

    def test_armed_input_rechecks_state_and_sends_only_allowlisted_key(self) -> None:
        runner = FakeRunner()
        report = probe_linux_game(
            system_name="Linux",
            environ={
                "XDG_SESSION_TYPE": "x11",
                "DISPLAY": ":0",
                "GRINDLESS_ENABLE_GAME_INPUT": "1",
            },
            runner=runner,
            which=all_binaries,
        )
        with tempfile.TemporaryDirectory() as directory:
            control = LinuxX11GameControl(
                report,
                runner=runner,
                stop_file=Path(directory) / "stop",
            )
            control.press("E")

        self.assertEqual(
            runner.commands[-1],
            ("xdotool", "key", "--clearmodifiers", "e"),
        )
        self.assertIn(("xdotool", "getactivewindow"), runner.commands)
        self.assertIn(("xdotool", "getmouselocation", "--shell"), runner.commands)

    def test_stop_file_prevents_input_without_querying_the_window(self) -> None:
        runner = FakeRunner()
        report = probe_linux_game(
            system_name="Linux",
            environ={
                "XDG_SESSION_TYPE": "x11",
                "DISPLAY": ":0",
                "GRINDLESS_ENABLE_GAME_INPUT": "1",
            },
            runner=runner,
            which=all_binaries,
        )
        with tempfile.TemporaryDirectory() as directory:
            stop_file = Path(directory) / "stop"
            stop_file.touch()
            control = LinuxX11GameControl(report, runner=runner, stop_file=stop_file)
            commands_before = len(runner.commands)
            with self.assertRaisesRegex(LinuxGameControlError, "stop file"):
                control.click(10, 10)

        self.assertEqual(len(runner.commands), commands_before)


if __name__ == "__main__":
    unittest.main()
