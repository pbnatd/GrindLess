from __future__ import annotations

import unittest

from grindless.simulator import ArtifactDomainSimulator


class SimulatorTests(unittest.TestCase):
    def test_same_seed_produces_same_reward(self) -> None:
        first = ArtifactDomainSimulator(seed=7).claim_reward(20)
        second = ArtifactDomainSimulator(seed=7).claim_reward(20)
        self.assertEqual(
            [item.model_dump() for item in first.artifacts],
            [item.model_dump() for item in second.artifacts],
        )

    def test_enhancement_reaches_twenty_in_five_checkpoints(self) -> None:
        simulator = ArtifactDomainSimulator(seed=11)
        artifact = simulator.claim_reward(20).artifacts[0]
        result = simulator.enhance_artifact(artifact, 20)
        self.assertEqual(result.artifact.level, 20)
        self.assertEqual([event.to_level for event in result.events], [4, 8, 12, 16, 20])
        self.assertEqual(len(result.artifact.substats), 4)


if __name__ == "__main__":
    unittest.main()
