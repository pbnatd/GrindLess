from __future__ import annotations

from types import SimpleNamespace
import sys
import unittest

from grindless.resource_monitor import ProcessTreeProfiler, ResourceMeasurement


class FakeNoSuchProcess(Exception):
    pass


class FakeZombieProcess(Exception):
    pass


class FakeAccessDenied(Exception):
    pass


class FakeProcess:
    def __init__(
        self,
        rss: int,
        *,
        children: list["FakeProcess"] | None = None,
        executable: str = sys.executable,
    ) -> None:
        self.rss = rss
        self._children = children or []
        self.executable = executable

    def exe(self) -> str:
        return self.executable

    def memory_info(self) -> SimpleNamespace:
        return SimpleNamespace(rss=self.rss)

    def children(self, *, recursive: bool) -> list["FakeProcess"]:
        self.last_recursive = recursive
        return self._children


class FakePsutil:
    NoSuchProcess = FakeNoSuchProcess
    ZombieProcess = FakeZombieProcess
    AccessDenied = FakeAccessDenied

    def __init__(self, root: FakeProcess) -> None:
        self.root = root

    def Process(self, pid: int) -> FakeProcess:
        self.requested_pid = pid
        return self.root


class ProcessTreeProfilerTests(unittest.TestCase):
    def test_rejects_a_process_namespace_that_points_at_another_executable(self) -> None:
        profiler = ProcessTreeProfiler(
            psutil_module=FakePsutil(FakeProcess(100, executable="/bin/false"))
        )

        with self.assertRaisesRegex(RuntimeError, "current Python process"):
            profiler.start()

    def test_sums_python_and_descendant_rss(self) -> None:
        root = FakeProcess(
            100_000_000,
            children=[FakeProcess(200_000_000), FakeProcess(300_000_000)],
        )
        profiler = ProcessTreeProfiler(
            sampling_interval_ms=25,
            psutil_module=FakePsutil(root),
        )
        profiler.start()
        measurement = profiler.stop()

        self.assertTrue(measurement.complete)
        self.assertGreaterEqual(measurement.samples, 2)
        self.assertGreater(measurement.wall_time_seconds, 0)
        self.assertEqual(measurement.peak_python_rss_bytes, 100_000_000)
        self.assertEqual(measurement.peak_process_tree_rss_bytes, 600_000_000)

    def test_serialized_measurement_names_the_rss_contract(self) -> None:
        measurement = ResourceMeasurement(
            wall_time_seconds=1.23456,
            peak_python_rss_bytes=10,
            peak_process_tree_rss_bytes=20,
            sampling_interval_ms=100,
            samples=11,
            complete=False,
            warnings=("partial",),
        )

        self.assertEqual(measurement.as_dict()["wall_time_seconds"], 1.235)
        self.assertEqual(
            measurement.as_dict()["memory_metric"],
            "sampled sum of RSS for Python and descendant processes",
        )
        self.assertEqual(measurement.as_dict()["warnings"], ["partial"])


if __name__ == "__main__":
    unittest.main()
