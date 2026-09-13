export type Slot = 'flower' | 'plume' | 'sands' | 'goblet' | 'circlet';
export type FarmPolicy = 'economy' | 'spend_all';
export type LLMBackend = 'offline' | 'openai_luna' | 'openai_terra' | 'openai_sol' | 'local_qwen';
export type ReasoningEffort = 'low' | 'medium' | 'high';
export type TeamMode = 'manual' | 'auto';
export type DomainTeamMode = 'same' | 'manual' | 'auto';
export type TeamObjective = 'max_dps' | 'comfort' | 'stable_rotation';

export interface CharacterDefinition {
  key: string;
  name_ru: string;
  avatar_id: number;
  alternate_avatar_ids: number[];
  rarity: 4 | 5;
  availability: 'limited' | 'starter' | 'standard' | 'collab' | 'unknown';
  element: string;
  role: string;
  primary_set: string;
  secondary_set: string;
  full_target_support: boolean;
}

export interface CharacterCatalogResponse {
  targets: CharacterDefinition[];
  roster: CharacterDefinition[];
  roster_count: number;
  roster_provenance: {
    game_version: string;
    retrieved_at: string;
    source_url: string;
  };
  target_profile_provenance: {
    game_version: string;
    retrieved_at: string;
    target_rule: string;
    primary_source: string;
  };
}

export interface TeamIntent {
  target_key: string;
  target_objective: TeamObjective;
  target_team_mode: TeamMode;
  target_team: string[];
  domain_team_mode: DomainTeamMode;
  domain_objective: TeamObjective;
  domain_team: string[];
  candidate_pool: string[];
}

export interface TeamPlan {
  target_key: string;
  target_team_mode: TeamMode;
  target_team: string[];
  target_objective: TeamObjective;
  domain_team_mode: DomainTeamMode;
  domain_team: string[];
  domain_objective: TeamObjective;
  candidate_pool: string[];
  expected_showcase_keys: string[];
  target_team_status: 'confirmed' | 'pending_optimizer';
  domain_team_status: 'confirmed' | 'pending_optimizer' | 'same_as_target';
}

export interface TeamStrategyResult {
  decision_owner: 'llm_plus_team_evaluator';
  execution_status: 'shadow_only';
  target_team: string[];
  domain_team: string[];
  target_strategy_ru: string;
  domain_strategy_ru: string;
  synergies_ru: string[];
  weak_points_ru: string[];
  recommendations_ru: string[];
  preference_handling_ru: string;
  assumptions_ru: string[];
  confidence: 'high' | 'medium' | 'low';
  evaluation: {
    evaluator: 'deterministic_rubric_v1';
    exact_dps_claimed: false;
    target: TeamEvaluationReport;
    domain: TeamEvaluationReport;
  };
  validated_team_plan: TeamPlan;
  validation: {
    passed: true;
    checks: string[];
    knowledge_coverage: 'curated' | 'partial' | 'identity_only' | 'web_researched';
  };
  evidence: {
    target_key: string;
    candidates: Array<{
      character_key: string;
      name_ru: string;
      element: string;
      role: string;
      role_evidence: 'curated' | 'identity_only';
      character_level: number | null;
      constellation: number;
      weapon_id: number | null;
      weapon_level: number | null;
      weapon_refinement: number | null;
    }>;
    knowledge_limitations: string[];
    privacy_notice: string;
  };
  llm_audit: NarrationReport;
}

export type TeamMetric = 'damage_potential' | 'reaction_coherence' | 'rotation_stability' | 'energy_feasibility' | 'comfort' | 'account_readiness' | 'domain_compatibility';

export interface TeamEvaluationReport {
  scope: 'target' | 'domain';
  objective: TeamObjective;
  acceptance_threshold: number;
  selected_proposal_id: string | null;
  gate_errors_ru: string[];
  excluded_by_preference: string[];
  candidates: Array<{
    proposal_id: string;
    team: string[];
    score: number;
    accepted: boolean;
    rejection_reasons_ru: string[];
    breakdown: {
      raw_scores: Record<TeamMetric, number>;
      weighted_points: Record<TeamMetric, number>;
      total: number;
    };
    evidence_ru: string[];
  }>;
}

export interface EnkaCharacterProfile {
  character_key: string;
  name_ru: string;
  avatar_id: number;
  captured_at: string;
  character_level: number | null;
  character_ascension: number | null;
  constellation: number;
  skill_levels: Record<string, number>;
  weapon_id: number | null;
  weapon_icon: string | null;
  weapon_level: number | null;
  weapon_ascension: number | null;
  weapon_refinement: number | null;
}

export interface EnkaCollection {
  collection_id: string;
  mode: 'planned' | 'discovery';
  finalized: boolean;
  uid_last4: string;
  profiles: EnkaCharacterProfile[];
  observed_keys: string[];
  missing_keys: string[];
  complete: boolean;
  ttl_seconds: number;
  cache_hit: boolean;
  retention_seconds: number;
  privacy_notice: string;
}

export interface BackendStatus {
  backend: LLMBackend;
  label: string;
  configured: boolean;
  model: string | null;
  reason: string | null;
}

export interface QuotaSnapshot {
  daily_limit: number;
  monthly_limit: number;
  used_today: number;
  used_this_month: number;
  attempts_today: number;
  input_tokens_this_month: number;
  output_tokens_this_month: number;
  resets_at_utc: string;
}

export interface LLMStatusResponse {
  backends: BackendStatus[];
  quota: QuotaSnapshot;
  quota_scope: 'single_local_user';
}

export interface LLMCallAudit {
  purpose: string;
  backend: LLMBackend;
  model: string;
  reasoning_effort: ReasoningEffort;
  status: 'succeeded' | 'failed' | 'invalid_output';
  provider_called: boolean;
  transmitted_text: string;
  output_text: string | null;
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens: number;
  response_id: string | null;
  estimated_cost_usd: number | null;
  web_search_used: boolean;
  web_sources: Array<{ url: string; title: string | null }>;
  error: string | null;
}

export interface NarrationReport {
  backend: LLMBackend;
  model: string | null;
  status: 'offline' | 'succeeded' | 'degraded';
  external_data_sent: boolean;
  successful_calls: number;
  failed_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
  pricing_note: string;
  calls: LLMCallAudit[];
}

export interface VideoImportStatus {
  job_id: string;
  status: 'queued' | 'scanning' | 'succeeded' | 'failed';
  filename: string;
  created_at: string;
  message: string;
  good: Record<string, unknown> | null;
  extraction_audit: Record<string, unknown> | null;
  error: string | null;
}

export interface SessionSummary {
  session_id: string;
  created_at: string;
  backend: LLMBackend;
  model: string | null;
  policy: FarmPolicy;
  target_slots: Slot[];
  resin_budget: number;
  seed: number;
  decision: string;
  reason: string;
  runs: number;
  resin_spent: number;
  resin_remaining: number;
  narration_status: string;
}

export interface BuildContext {
  character: string;
  constellation: number;
  weapon: string;
  weapon_refinement: number;
  target_team: string[];
  farming_team: string[];
}

export interface SlotGoal {
  slot: Slot;
  allowed_sets: string[];
  allowed_main_stats: string[];
  main_stat_priorities: Record<string, number>;
  substat_priorities: Record<string, number>;
  min_useful_substats: number;
}

export interface ResolvedArtifactGoal {
  character: string;
  targets: Array<SlotGoal & {
    min_content_score_gain: number;
    min_gain: number;
  }>;
  policy: FarmPolicy;
  constraints: {
    stat_weights: Record<string, number>;
    minimum_stats: Record<string, number>;
    set_requirements: Array<{
      set_name: string;
      pieces: 2 | 4;
    }>;
  };
  resin_budget: number;
  reward_cost: number;
  baseline_mode: 'empty' | 'equipped';
}

export interface ArtifactGoalStrategyResult {
  decision_owner: 'llm';
  execution_status: 'shadow_only';
  draft: {
    build_role_ru: string;
    selected_set_option_id: string;
    slots: Array<{
      slot: Slot;
      allowed_main_stats: string[];
      min_useful_substats: number;
      rationale_ru: string;
    }>;
    substat_priority_order: string[];
    slot_priority_order: Slot[];
    farming_plan_ru: string;
    alternative_upgrade_ru: string;
    preference_handling_ru: string;
    assumptions_ru: string[];
    confidence: 'high' | 'medium' | 'low';
  };
  resolved_goal: ResolvedArtifactGoal;
  inventory_audit: AnalysisResponse['audit'];
  validation: {
    passed: true;
    checks: string[];
    evaluation_mode: 'content_only';
    off_piece_status: 'optimized_locally';
  };
  evidence: {
    target: {
      character_key: string;
      name_ru: string;
      element: string;
      role: string;
      weapon_key: string | null;
      weapon_level: number | null;
      weapon_refinement: number | null;
    };
    target_team: string[];
    domain_team: string[];
    inventory_artifact_count: number;
    allowed_set_options: Array<{
      option_id: string;
      label_ru: string;
      requirements: Array<{ set_name: string; pieces: 2 | 4 }>;
    }>;
    curated_set_counts: Record<string, number>;
    knowledge_limitations: string[];
    privacy_notice: string;
  };
  llm_audit: NarrationReport;
}

export type RotationAction = 'skill' | 'burst' | 'normal_attack' | 'charged_attack' | 'dodge';

export interface RotationStepDraft {
  character_key: string;
  action: RotationAction;
  repetitions: number;
  purpose_ru: string;
}

export interface CompiledRotationState {
  state_id: string;
  character_key: string;
  action: RotationAction;
  repetitions: number;
  on_success: string;
  on_failure: 'safe_stop';
  on_burst_unavailable: string | null;
  source_step: number;
  recovery: boolean;
  purpose_ru: string;
  fallback_rationale_ru: string | null;
}

export interface ValidatedRotation {
  domain_team: string[];
  opening_ru: string;
  rationale_ru: string;
  stop_conditions_ru: string[];
  assumptions_ru: string[];
  states: CompiledRotationState[];
  entry_state: string;
  repeat_state: string;
  terminal_states: Array<'rotation_complete' | 'safe_stop'>;
  validation_level: 'structural_only';
  input_authority: 'none';
  plan_fingerprint: string;
}

export interface RotationStrategyResult {
  decision_owner: 'llm';
  execution_status: 'shadow_only';
  draft: {
    domain_team: string[];
    opening_ru: string;
    steps: RotationStepDraft[];
    burst_fallbacks: Array<{
      at_step: number;
      response: 'use_skill_then_retry' | 'skip_step' | 'restart_rotation' | 'safe_stop';
      rationale_ru: string;
    }>;
    repeat_from_step: number;
    stop_conditions_ru: string[];
    preference_handling_ru: string;
    assumptions_ru: string[];
    rationale_ru: string;
    confidence: 'high' | 'medium' | 'low';
  };
  validated_rotation: ValidatedRotation;
  validation: {
    passed: true;
    checks: string[];
    knowledge_coverage: 'curated' | 'partial' | 'identity_only' | 'web_researched';
    timing_status: 'unverified' | 'web_researched';
    energy_status: 'unverified' | 'web_researched';
    execution_status: 'blocked';
  };
  evidence: {
    domain_team: string[];
    knowledge_limitations: string[];
    privacy_notice: string;
  };
  llm_audit: NarrationReport;
}

export interface ArtifactCandidate {
  artifact_id: string;
  source_index: number | null;
  slot: Slot;
  set_name: string;
  main_stat: string;
  main_stat_priority: number;
  substats: string[];
  matched_substats: string[];
  content_score: number;
  useful_substat_count: number;
  observed_substat_count: number;
  closes_goal: boolean;
}

export interface MavuikaPresetResponse {
  preset: BuildContext;
  policy: FarmPolicy;
  goals: SlotGoal[];
}

export interface AnalysisResponse extends MavuikaPresetResponse {
  character?: CharacterDefinition;
  profile?: EnkaCharacterProfile;
  team_plan?: TeamPlan;
  import_report: {
    source: string;
    version: number;
    artifacts_imported: number;
    characters_seen: number;
    weapons_seen: number;
    equipped_artifacts_seen?: number;
    equipped_weapons_seen?: number;
    inactive_substats_imported?: number;
    skipped_empty_substats: number;
    warnings: string[];
  };
  inventory: {
    artifacts: number;
    five_star_artifacts: number;
    level_zero_artifacts: number;
    equipped_artifacts: number;
    locked_artifacts: number;
    sets: Record<string, number>;
  };
  audit: {
    character: string;
    baseline_mode: 'empty';
    candidates: Record<Slot, ArtifactCandidate[]>;
    selected_artifact_ids: Partial<Record<Slot, string>>;
    selected_set_counts: Record<string, number>;
    set_composition_met: boolean;
    off_piece_artifact_id: string | null;
    pending_slots: Slot[];
    starter_build_available: boolean;
  };
}

export interface HealthResponse {
  status: 'ok';
  version: string;
  platform: {
    host: string;
    architecture: string;
  };
  llm_backends: BackendStatus[];
}

export interface GameAdapterCheck {
  code: string;
  ok: boolean;
  required: boolean;
  message: string;
}

export interface GameAdapterStatus {
  status: 'unsupported' | 'setup_required' | 'game_not_running' | 'needs_attention' | 'ready';
  input_enabled: boolean;
  session_type: string;
  display: string | null;
  window_id: string | null;
  window_geometry: { x: number; y: number; width: number; height: number } | null;
  checks: GameAdapterCheck[];
  next_action: string;
}

export interface SimulationArtifact {
  artifact_id: string;
  slot: Slot;
  set_name: string;
  main_stat: string;
  substats: string[];
  relevant: boolean;
  promising: boolean;
  baseline_eligible: boolean;
  matched_substats: string[];
  content_score: number | null;
  baseline_content_score: number | null;
}

export interface SimulationRun {
  run: number;
  resin_spent_total: number;
  resin_remaining: number;
  analyzed: boolean;
  accepted_slots_after: Slot[];
  artifacts: SimulationArtifact[];
  stop_here: boolean;
}

export interface SlotProgress {
  slot: Slot;
  baseline_artifact_id: string | null;
  best_artifact_id: string | null;
  evaluation_mode: 'content_only' | 'enhanced_values';
  baseline_content_score: number;
  candidate_content_score: number;
  content_score_gain: number;
  matched_substats: string[];
  relative_gain: number | null;
  accepted: boolean;
  reason: string;
}

export interface SimulationResponse {
  session_id: string;
  policy: FarmPolicy;
  target_slots: Slot[];
  resin_budget: number;
  reward_cost: number;
  seed: number;
  baseline_artifact_ids: Partial<Record<Slot, string>>;
  checkpoint_strategy: 'after_each_reward' | 'after_final_reward';
  probability_notice: string;
  enhancement_notice: string;
  artifact_goal_source?: 'profile' | 'llm';
  rotation_plan_source?: 'none' | 'llm';
  rotation_execution_status?: 'not_executed';
  validated_rotation?: ValidatedRotation | null;
  result: {
    decision: 'repeat' | 'stop' | 'change_goal' | 'safe_stop';
    reason: 'full_budget_spent' | 'all_slot_goals_met' | 'resin_exhausted' | 'guaranteed_upgrade_is_better' | 'unknown_state' | 'reward_not_confirmed';
    runs: number;
    resin_spent: number;
    resin_remaining: number;
    model_checkpoints: number;
    slot_progress: SlotProgress[];
    recommendation: string;
  };
  runs: SimulationRun[];
  narration: NarrationReport;
  quota: QuotaSnapshot;
  character?: CharacterDefinition;
  profile?: EnkaCharacterProfile;
  team_plan?: TeamPlan;
}
