from __future__ import annotations

from collections.abc import Iterable
from collections import Counter
from itertools import product

from .models import (
    AccountState,
    Artifact,
    ArtifactCandidate,
    Build,
    FarmGoal,
    InitialBuildAudit,
    Slot,
    SlotGoal,
    SlotProgress,
    Stat,
)


class BruteForceBuildOptimizer:
    """Exact optimizer for small MVP inventories.

    The interface is deliberately replaceable: a production inventory can use a
    pruned or mixed-integer implementation without changing the agent.
    """

    def evaluate(self, build: Build, goal: FarmGoal) -> Build:
        totals: dict[Stat, float] = dict(build.base_stats)
        for stat, value in goal.constraints.minimum_stats.items():
            totals.setdefault(stat, 0.0)
        for artifact in build.artifacts.values():
            if artifact.main_value is not None:
                totals[artifact.main_stat] = (
                    totals.get(artifact.main_stat, 0.0) + artifact.main_value
                )
            for substat in artifact.substats:
                totals[substat.stat] = totals.get(substat.stat, 0.0) + substat.value

        constraints_met = all(
            totals.get(stat, 0.0) >= minimum
            for stat, minimum in goal.constraints.minimum_stats.items()
        )
        constraints_met = constraints_met and self.set_requirements_met(
            build.artifacts.values(), goal
        )

        score = sum(
            totals.get(stat, 0.0) * weight
            for stat, weight in goal.constraints.stat_weights.items()
        )
        return build.model_copy(
            update={"score": score, "stat_totals": totals, "constraints_met": constraints_met}
        )

    def optimize(self, state: AccountState, goal: FarmGoal) -> Build:
        slots = list(Slot)
        candidates: list[list[Artifact]] = []
        for slot in slots:
            eligible = [
                artifact
                for artifact in state.artifacts
                if artifact.slot == slot
                and (
                    artifact.equipped_by is None
                    or artifact.equipped_by == goal.character
                    or artifact.equipped_by not in state.protected_characters
                )
            ]
            if not eligible:
                raise ValueError(f"no eligible artifacts for slot {slot}")
            candidates.append(eligible)

        best_valid: Build | None = None
        best_any: Build | None = None
        for combination in product(*candidates):
            build = self.evaluate(
                Build(
                    artifacts={slot: artifact for slot, artifact in zip(slots, combination)},
                    base_stats=state.character.base_stats,
                ),
                goal,
            )
            if best_any is None or build.score > best_any.score:
                best_any = build
            if build.constraints_met and (best_valid is None or build.score > best_valid.score):
                best_valid = build

        if best_valid is not None:
            return best_valid
        if best_any is None:
            raise ValueError("optimizer could not construct a build")
        return best_any

    def assess_targets(
        self, state: AccountState, baseline: Build, goal: FarmGoal
    ) -> list[SlotProgress]:
        if not goal.enhancement.enabled:
            return self._assess_content_targets(state, baseline, goal)

        return self._assess_enhanced_targets(state, baseline, goal)

    def audit_initial_build(
        self,
        artifacts: list[Artifact],
        goal: FarmGoal,
        *,
        top_per_slot: int = 5,
    ) -> InitialBuildAudit:
        """Rank an inventory when the character has no equipped baseline.

        Only observed main-stat/set/substat types and the number of visible
        starting substats are used. Numeric substat values are not tie-breakers.
        """

        if goal.baseline_mode.value != "empty":
            raise ValueError("initial-build audit requires baseline_mode=empty")
        if top_per_slot < 1:
            raise ValueError("top_per_slot must be positive")

        candidates: dict[Slot, list[ArtifactCandidate]] = {}
        ranked_by_slot: dict[Slot, list[tuple[ArtifactCandidate, Artifact]]] = {}

        targets = {target.slot: target for target in goal.targets}
        for slot in Slot:
            target = targets.get(slot)
            if target is None:
                candidates[slot] = []
                ranked_by_slot[slot] = []
                continue

            ranked: list[tuple[ArtifactCandidate, Artifact]] = []
            for artifact in artifacts:
                if artifact.slot != slot:
                    continue
                if target.allowed_sets and artifact.set_name not in target.allowed_sets:
                    continue
                if (
                    target.allowed_main_stats
                    and artifact.main_stat not in target.allowed_main_stats
                ):
                    continue

                score, matched = self.content_score(artifact, target)
                main_priority = target.main_stat_priorities.get(artifact.main_stat, 1)
                closes_goal = (
                    main_priority == max(target.main_stat_priorities.values(), default=1)
                    and len(matched) >= target.min_useful_substats
                )
                ranked.append(
                    (
                        ArtifactCandidate(
                            artifact_id=artifact.id,
                            source_index=artifact.source_index,
                            slot=artifact.slot,
                            set_name=artifact.set_name,
                            main_stat=artifact.main_stat,
                            main_stat_priority=main_priority,
                            substats=[item.stat for item in artifact.known_substats],
                            matched_substats=matched,
                            content_score=score,
                            useful_substat_count=len(matched),
                            observed_substat_count=len(artifact.known_substats),
                            closes_goal=closes_goal,
                        ),
                        artifact,
                    )
                )

            ranked.sort(
                key=lambda pair: (
                    -pair[0].main_stat_priority,
                    -pair[0].content_score,
                    -pair[0].useful_substat_count,
                    -pair[0].observed_substat_count,
                    pair[0].source_index or 10**9,
                )
            )
            ranked_by_slot[slot] = ranked

        selected_artifacts, composition_met = self._select_initial_build(
            ranked_by_slot, goal
        )
        selected = {
            slot: artifact.id for slot, artifact in selected_artifacts.items()
        }
        pending = [
            slot
            for slot in Slot
            if slot not in selected_artifacts
            or not next(
                candidate.closes_goal
                for candidate, artifact in ranked_by_slot[slot]
                if artifact.id == selected_artifacts[slot].id
            )
        ]

        for slot in Slot:
            visible = [pair[0] for pair in ranked_by_slot[slot][:top_per_slot]]
            selected_id = selected.get(slot)
            if selected_id and all(item.artifact_id != selected_id for item in visible):
                chosen = next(
                    pair[0]
                    for pair in ranked_by_slot[slot]
                    if pair[1].id == selected_id
                )
                visible = [chosen, *visible[: max(0, top_per_slot - 1)]]
            candidates[slot] = visible

        selected_counts = Counter(
            artifact.set_name for artifact in selected_artifacts.values()
        )
        off_piece_id = (
            self._off_piece_artifact_id(selected_artifacts, goal)
            if composition_met
            else None
        )

        return InitialBuildAudit(
            character=goal.character,
            candidates=candidates,
            selected_artifact_ids=selected,
            selected_set_counts=dict(sorted(selected_counts.items())),
            set_composition_met=composition_met,
            off_piece_artifact_id=off_piece_id,
            pending_slots=pending,
            starter_build_available=len(selected) == len(Slot) and composition_met,
        )

    @staticmethod
    def set_requirements_met(
        artifacts: Iterable[Artifact], goal: FarmGoal
    ) -> bool:
        counts = Counter(item.set_name for item in artifacts)
        return all(
            counts[requirement.set_name] >= requirement.pieces
            for requirement in goal.constraints.set_requirements
        )

    def _select_initial_build(
        self,
        ranked_by_slot: dict[Slot, list[tuple[ArtifactCandidate, Artifact]]],
        goal: FarmGoal,
    ) -> tuple[dict[Slot, Artifact], bool]:
        """Choose five items jointly while tracking the exact set composition."""

        if any(not ranked_by_slot[slot] for slot in Slot):
            return (
                {
                    slot: ranked_by_slot[slot][0][1]
                    for slot in Slot
                    if ranked_by_slot[slot]
                },
                False,
            )

        requirements = goal.constraints.set_requirements
        initial_signature = tuple(0 for _ in requirements)
        # signature -> (additive quality tuple, artifacts by slot)
        states: dict[
            tuple[int, ...],
            tuple[tuple[float, ...], dict[Slot, Artifact]],
        ] = {initial_signature: ((0, 0, 0, 0, 0, 0), {})}

        for slot in Slot:
            next_states: dict[
                tuple[int, ...],
                tuple[tuple[float, ...], dict[Slot, Artifact]],
            ] = {}
            for signature, (score, selected) in states.items():
                for candidate, artifact in ranked_by_slot[slot]:
                    new_signature = tuple(
                        min(
                            requirement.pieces,
                            signature[index]
                            + int(artifact.set_name == requirement.set_name),
                        )
                        for index, requirement in enumerate(requirements)
                    )
                    item_score = (
                        float(candidate.closes_goal),
                        float(candidate.main_stat_priority),
                        candidate.content_score,
                        float(candidate.useful_substat_count),
                        float(candidate.observed_substat_count),
                        -float(candidate.source_index or 10**9),
                    )
                    new_score = tuple(
                        score[index] + item_score[index]
                        for index in range(len(score))
                    )
                    current = next_states.get(new_signature)
                    if current is None or new_score > current[0]:
                        next_states[new_signature] = (
                            new_score,
                            {**selected, slot: artifact},
                        )
            states = next_states

        required_signature = tuple(item.pieces for item in requirements)
        if required_signature in states:
            return states[required_signature][1], True
        return max(states.values(), key=lambda item: item[0])[1], not requirements

    @staticmethod
    def _off_piece_artifact_id(
        selected: dict[Slot, Artifact], goal: FarmGoal
    ) -> str | None:
        if sum(item.pieces for item in goal.constraints.set_requirements) != 4:
            return None
        requirements = {
            item.set_name: item.pieces for item in goal.constraints.set_requirements
        }
        counts = Counter(item.set_name for item in selected.values())
        removable = [
            artifact
            for artifact in selected.values()
            if all(
                counts[name] - int(artifact.set_name == name) >= pieces
                for name, pieces in requirements.items()
            )
        ]
        outside = [item for item in removable if item.set_name not in requirements]
        chosen = (outside or removable)[-1] if (outside or removable) else None
        return chosen.id if chosen else None

    @staticmethod
    def content_score(
        artifact: Artifact, goal_target: SlotGoal
    ) -> tuple[float, list[Stat]]:
        """Score substat *types* only; numeric artifact values are ignored."""

        present = {item.stat for item in artifact.known_substats}
        matched = [
            stat for stat in goal_target.substat_priorities if stat in present
        ]
        score = sum(goal_target.substat_priorities[stat] for stat in matched)
        return score, matched

    @staticmethod
    def content_eligible(
        artifact: Artifact, target: SlotGoal, state: AccountState
    ) -> bool:
        if artifact.slot != target.slot:
            return False
        if target.allowed_main_stats and artifact.main_stat not in target.allowed_main_stats:
            return False
        if target.allowed_sets and artifact.set_name not in target.allowed_sets:
            return False
        return not (
            artifact.equipped_by in state.protected_characters
            and artifact.equipped_by != state.character.name
        )

    def _best_joint_replacements(
        self,
        state: AccountState,
        baseline: Build,
        goal: FarmGoal,
        *,
        enhanced: bool,
    ) -> dict[Slot, Artifact]:
        """Optimize targeted replacements, including a partial/empty baseline.

        A missing slot is represented by absence from the returned mapping, not
        by a synthetic artifact.  If the complete set requirement cannot yet be
        reached, keep the state with the greatest progress toward it so farming
        can build the composition incrementally.
        """

        targets = {target.slot: target for target in goal.targets}
        requirements = goal.constraints.set_requirements
        initial_signature = tuple(0 for _ in requirements)
        states: dict[
            tuple[int, ...],
            tuple[tuple[float, ...], dict[Slot, Artifact]],
        ] = {initial_signature: ((0, 0, 0, 0, 0), {})}

        for slot in Slot:
            target = targets.get(slot)
            baseline_artifact = baseline.artifacts.get(slot)
            options: list[Artifact | None] = [baseline_artifact]
            if target is not None:
                options.extend(
                    artifact
                    for artifact in state.artifacts
                    if (
                        baseline_artifact is None
                        or artifact.id != baseline_artifact.id
                    )
                    and self.content_eligible(artifact, target, state)
                    and (not enhanced or artifact.level >= goal.enhancement.target_level)
                )

            next_states: dict[
                tuple[int, ...],
                tuple[tuple[float, ...], dict[Slot, Artifact]],
            ] = {}
            for signature, (score, selected) in states.items():
                for artifact in options:
                    if artifact is None:
                        new_signature = signature
                        item_score = (0.0, 0.0, 0.0, 0.0, 0.0)
                        new_selected = selected
                    else:
                        new_signature = tuple(
                            min(
                                requirement.pieces,
                                signature[index]
                                + int(artifact.set_name == requirement.set_name),
                            )
                            for index, requirement in enumerate(requirements)
                        )
                        if target is None:
                            item_score = (0.0, 0.0, 0.0, 0.0, 0.0)
                        elif enhanced:
                            item_score = (
                                self._observed_substat_value_score(artifact, target),
                                0.0,
                                0.0,
                                float(len(artifact.known_substats)),
                                -float(artifact.source_index or 10**9),
                            )
                        else:
                            content, matched = self.content_score(artifact, target)
                            item_score = (
                                float(target.main_stat_priorities.get(artifact.main_stat, 1)),
                                content,
                                float(len(matched)),
                                float(len(artifact.known_substats)),
                                -float(artifact.source_index or 10**9),
                            )
                        new_selected = {**selected, slot: artifact}
                    new_score = tuple(
                        score[index] + item_score[index]
                        for index in range(len(score))
                    )
                    current = next_states.get(new_signature)
                    if current is None or new_score > current[0]:
                        next_states[new_signature] = (
                            new_score,
                            new_selected,
                        )
            states = next_states

        required_signature = tuple(item.pieces for item in requirements)
        selected = states.get(required_signature)
        if selected is not None:
            return selected[1]
        # The full 4pc/2pc+2pc composition may be impossible at the start.
        # Prefer observed progress toward it instead of refusing to simulate.
        return max(
            states.items(),
            key=lambda item: (sum(item[0]), item[1][0]),
        )[1][1]

    def _assess_content_targets(
        self, state: AccountState, baseline: Build, goal: FarmGoal
    ) -> list[SlotProgress]:
        progress: list[SlotProgress] = []
        selected_build = self._best_joint_replacements(
            state, baseline, goal, enhanced=False
        )
        for target in goal.targets:
            baseline_artifact = baseline.artifacts.get(target.slot)
            baseline_score = (
                self.content_score(baseline_artifact, target)[0]
                if baseline_artifact is not None
                else 0.0
            )
            baseline_eligible = (
                baseline_artifact is not None
                and self.content_eligible(baseline_artifact, target, state)
                and self.set_requirements_met(baseline.artifacts.values(), goal)
            )

            best_artifact = selected_build.get(target.slot)
            if best_artifact is None:
                progress.append(
                    SlotProgress(
                        slot=target.slot,
                        baseline_artifact_id=(
                            baseline_artifact.id if baseline_artifact else None
                        ),
                        best_artifact_id=None,
                        evaluation_mode="content_only",
                        baseline_content_score=baseline_score,
                        candidate_content_score=0.0,
                        content_score_gain=0.0,
                        matched_substats=[],
                        accepted=False,
                        reason=(
                            "no eligible candidate has been observed for the empty "
                            "baseline slot"
                        ),
                    )
                )
                continue

            best_score, best_matched = self.content_score(best_artifact, target)
            composition_allows_candidate = self._candidate_allowed_while_incomplete(
                best_artifact, selected_build, goal
            )

            gain = best_score - baseline_score
            accepted = (
                (baseline_artifact is None or best_artifact.id != baseline_artifact.id)
                and len(best_matched) >= target.min_useful_substats
                and composition_allows_candidate
                and (
                    not baseline_eligible
                    or gain >= target.min_content_score_gain
                )
            )
            if accepted:
                reason = (
                    "first suitable candidate for a slot without a valid baseline; "
                    "rolled values were not used"
                    if not baseline_eligible
                    else (
                        "promising candidate: suitable main/set and better desired "
                        f"substat content ({best_score:g} vs {baseline_score:g}); "
                        "rolled values were not used"
                    )
                )
            elif not composition_allows_candidate:
                reason = (
                    "candidate does not advance the incomplete required set "
                    "composition"
                )
            elif baseline_artifact is not None and best_artifact.id == baseline_artifact.id:
                reason = (
                    "no candidate has better desired substat content than the baseline; "
                    "rolled values were not used"
                )
            else:
                reason = (
                    f"content gain {gain:g} is below required "
                    f"{target.min_content_score_gain:g}"
                )
            progress.append(
                SlotProgress(
                    slot=target.slot,
                    baseline_artifact_id=(baseline_artifact.id if baseline_artifact else None),
                    best_artifact_id=best_artifact.id,
                    evaluation_mode="content_only",
                    baseline_content_score=baseline_score,
                    candidate_content_score=best_score,
                    content_score_gain=gain,
                    matched_substats=best_matched,
                    accepted=accepted,
                    reason=reason,
                )
            )
        return progress

    def _assess_enhanced_targets(
        self, state: AccountState, baseline: Build, goal: FarmGoal
    ) -> list[SlotProgress]:
        progress: list[SlotProgress] = []
        selected_build = self._best_joint_replacements(
            state, baseline, goal, enhanced=True
        )
        for target in goal.targets:
            baseline_artifact = baseline.artifacts.get(target.slot)
            best_artifact = selected_build.get(target.slot)
            baseline_value_score = (
                self._observed_substat_value_score(baseline_artifact, target)
                if baseline_artifact is not None
                else 0.0
            )
            if best_artifact is None:
                progress.append(
                    SlotProgress(
                        slot=target.slot,
                        baseline_artifact_id=(
                            baseline_artifact.id if baseline_artifact else None
                        ),
                        best_artifact_id=None,
                        evaluation_mode="enhanced_values",
                        baseline_content_score=(
                            self.content_score(baseline_artifact, target)[0]
                            if baseline_artifact is not None
                            else 0.0
                        ),
                        candidate_content_score=0.0,
                        content_score_gain=0.0,
                        matched_substats=[],
                        relative_gain=None,
                        accepted=False,
                        reason=(
                            "no authorized enhanced candidate has been observed "
                            "for the empty baseline slot"
                        ),
                    )
                )
                continue
            best_value_score = self._observed_substat_value_score(
                best_artifact, target
            )

            relative_gain = (
                None
                if baseline_artifact is None
                else (best_value_score - baseline_value_score)
                / max(abs(baseline_value_score), 1e-9)
            )
            candidate_content, matched = self.content_score(best_artifact, target)
            composition_allows_candidate = self._candidate_allowed_while_incomplete(
                best_artifact, selected_build, goal
            )
            accepted = (
                len(matched) >= target.min_useful_substats
                and composition_allows_candidate
                if baseline_artifact is None
                else (
                    best_artifact.id != baseline_artifact.id
                    and relative_gain is not None
                    and relative_gain >= target.min_gain
                    and composition_allows_candidate
                )
            )
            baseline_content = (
                self.content_score(baseline_artifact, target)[0]
                if baseline_artifact is not None
                else 0.0
            )
            if accepted:
                reason = (
                    "first suitable authorized enhanced candidate for an empty "
                    "baseline slot"
                    if baseline_artifact is None
                    else (
                        f"observed weighted substat gain {relative_gain:.2%} >= "
                        f"target {target.min_gain:.2%} after authorized enhancement"
                    )
                )
            elif not composition_allows_candidate:
                reason = (
                    "candidate does not advance the incomplete required set "
                    "composition"
                )
            elif baseline_artifact is not None and best_artifact.id == baseline_artifact.id:
                reason = "no authorized enhanced candidate beats the baseline"
            else:
                reason = (
                    "candidate does not meet the minimum useful-substat contract"
                    if relative_gain is None
                    else (
                        f"observed weighted substat gain {relative_gain:.2%} < "
                        f"target {target.min_gain:.2%}"
                    )
                )
            progress.append(
                SlotProgress(
                    slot=target.slot,
                    baseline_artifact_id=(baseline_artifact.id if baseline_artifact else None),
                    best_artifact_id=best_artifact.id,
                    evaluation_mode="enhanced_values",
                    baseline_content_score=baseline_content,
                    candidate_content_score=candidate_content,
                    content_score_gain=candidate_content - baseline_content,
                    matched_substats=matched,
                    relative_gain=relative_gain,
                    accepted=accepted,
                    reason=reason,
                )
            )
        return progress

    def _candidate_allowed_while_incomplete(
        self,
        candidate: Artifact,
        selected_build: dict[Slot, Artifact],
        goal: FarmGoal,
    ) -> bool:
        """Allow off-set candidates only after the required composition exists."""

        requirements = goal.constraints.set_requirements
        if not requirements or self.set_requirements_met(selected_build.values(), goal):
            return True
        return candidate.set_name in {
            requirement.set_name for requirement in requirements
        }

    @staticmethod
    def _observed_substat_value_score(
        artifact: Artifact, target: SlotGoal
    ) -> float:
        return sum(
            substat.value * target.substat_priorities.get(substat.stat, 0.0)
            for substat in artifact.substats
        )
