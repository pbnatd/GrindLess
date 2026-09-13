from __future__ import annotations

import unittest

from grindless.platform_support import (
    HostPlatform,
    SupportStatus,
    detect_host,
    platform_support,
)


class PlatformSupportTests(unittest.TestCase):
    def test_detects_supported_desktop_operating_systems(self) -> None:
        self.assertEqual(detect_host("Darwin"), HostPlatform.MACOS)
        self.assertEqual(detect_host("Windows"), HostPlatform.WINDOWS)
        self.assertEqual(detect_host("Linux"), HostPlatform.LINUX)

    def test_macos_keeps_analysis_even_without_game_execution(self) -> None:
        support = platform_support(system_name="Darwin", architecture="arm64")

        self.assertEqual(support.host, HostPlatform.MACOS)
        self.assertEqual(support.good_import.status, SupportStatus.AVAILABLE)
        self.assertEqual(support.video_import.status, SupportStatus.EXPERIMENTAL)
        self.assertEqual(support.game_execution.status, SupportStatus.UNAVAILABLE)
        self.assertIn("Metal", support.local_qwen.reason)

    def test_windows_is_only_a_planned_executor_target(self) -> None:
        support = platform_support(system_name="Windows", architecture="AMD64")

        self.assertEqual(support.game_execution.status, SupportStatus.PLANNED)
        self.assertNotEqual(support.game_execution.status, SupportStatus.AVAILABLE)

    def test_linux_exposes_only_the_experimental_guarded_control_foundation(self) -> None:
        support = platform_support(system_name="Linux", architecture="x86_64")

        self.assertEqual(support.game_execution.status, SupportStatus.EXPERIMENTAL)
        self.assertIn("1920×1080", support.game_execution.reason)
        self.assertIn("пока не реализованы", support.game_execution.reason)

    def test_unknown_host_fails_capabilities_loudly(self) -> None:
        support = platform_support(system_name="Plan9", architecture="mystery")

        self.assertEqual(support.host, HostPlatform.UNKNOWN)
        self.assertTrue(
            all(
                getattr(support, name).status is SupportStatus.UNAVAILABLE
                for name in (
                    "simulator",
                    "good_import",
                    "video_import",
                    "local_qwen",
                    "cloud_luna",
                    "game_execution",
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
