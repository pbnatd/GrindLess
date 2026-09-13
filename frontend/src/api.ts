import type {
  AnalysisResponse,
  FarmPolicy,
  HealthResponse,
  LLMBackend,
  LLMStatusResponse,
  ReasoningEffort,
  MavuikaPresetResponse,
  SimulationResponse,
  SessionSummary,
  Slot,
  VideoImportStatus,
  GameAdapterStatus,
  CharacterCatalogResponse,
  EnkaCollection,
  TeamIntent,
  TeamPlan,
  TeamStrategyResult,
  ArtifactGoalStrategyResult,
  ResolvedArtifactGoal,
  RotationStrategyResult,
  ValidatedRotation,
} from './types';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message;
    throw new Error(message || `Локальный API вернул ошибку ${response.status}`);
  }
  return payload as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request('/api/v1/health');
}

export function getLLMStatus(): Promise<LLMStatusResponse> {
  return request('/api/v1/llm/status');
}

export function getGameAdapterStatus(): Promise<GameAdapterStatus> {
  return request('/api/v1/game-adapter/status');
}

export function getCharacters(): Promise<CharacterCatalogResponse> {
  return request('/api/v1/characters');
}

export function planTeams(intent: TeamIntent): Promise<TeamPlan> {
  return request('/api/v1/team-plans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(intent),
  });
}

export function createTeamStrategy(
  teamIntent: TeamIntent,
  collectionId: string,
  llmBackend: LLMBackend,
  reasoningEffort: ReasoningEffort,
  preferences: string,
): Promise<TeamStrategyResult> {
  return request('/api/v1/team-strategies', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      team_intent: teamIntent,
      enka_collection_id: collectionId,
      llm_backend: llmBackend,
      reasoning_effort: reasoningEffort,
      preferences,
    }),
  });
}

export function createArtifactGoalStrategy(
  inventory: Record<string, unknown>,
  teamIntent: TeamIntent,
  collectionId: string,
  llmBackend: LLMBackend,
  reasoningEffort: ReasoningEffort,
  policy: FarmPolicy,
  preferences: string,
): Promise<ArtifactGoalStrategyResult> {
  return request('/api/v1/artifact-goal-strategies', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      inventory,
      team_intent: teamIntent,
      enka_collection_id: collectionId,
      llm_backend: llmBackend,
      reasoning_effort: reasoningEffort,
      policy,
      preferences,
    }),
  });
}

export function createRotationStrategy(
  teamIntent: TeamIntent,
  collectionId: string,
  llmBackend: LLMBackend,
  reasoningEffort: ReasoningEffort,
  artifactGoal: ResolvedArtifactGoal | null,
  preferences: string,
): Promise<RotationStrategyResult> {
  return request('/api/v1/rotation-strategies', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      team_intent: teamIntent,
      enka_collection_id: collectionId,
      llm_backend: llmBackend,
      reasoning_effort: reasoningEffort,
      artifact_goal: artifactGoal,
      preferences,
    }),
  });
}

export function loadEnkaSnapshot(
  uid: string,
  consent: boolean,
  mode: 'planned' | 'discovery',
  teamIntent?: TeamIntent,
  collectionId?: string,
): Promise<EnkaCollection> {
  return request('/api/v1/profiles/enka/snapshots', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-GrindLess-Local': '1' },
    body: JSON.stringify({
      uid,
      consent,
      mode,
      team_intent: teamIntent || null,
      collection_id: collectionId || null,
    }),
  });
}

export function finalizeEnkaCollection(
  collectionId: string,
  teamIntent: TeamIntent,
): Promise<EnkaCollection> {
  return request(`/api/v1/profiles/enka/collections/${collectionId}/finalize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-GrindLess-Local': '1' },
    body: JSON.stringify({ team_intent: teamIntent }),
  });
}

export function getSessions(): Promise<{ sessions: SessionSummary[] }> {
  return request('/api/v1/sessions');
}

export function getSession(sessionId: string): Promise<{ payload: SimulationResponse }> {
  return request(`/api/v1/sessions/${sessionId}`);
}

export function getMavuikaPreset(policy: FarmPolicy): Promise<MavuikaPresetResponse> {
  return request(`/api/v1/presets/mavuika?policy=${policy}`);
}

export function analyzeMavuika(
  payload: Record<string, unknown>,
  policy: FarmPolicy,
): Promise<AnalysisResponse> {
  return request(`/api/v1/audits/mavuika?policy=${policy}&top=5`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function analyzeCharacter(
  characterKey: string,
  payload: Record<string, unknown>,
  policy: FarmPolicy,
  teamIntent: TeamIntent,
  collectionId: string,
): Promise<AnalysisResponse> {
  return request(`/api/v1/characters/${characterKey}/audit?policy=${policy}&top=5`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      inventory: payload,
      team_intent: teamIntent,
      enka_collection_id: collectionId,
    }),
  });
}

export function startVideoImport(video: File): Promise<{ job_id: string; status: string }> {
  const body = new FormData();
  body.append('video', video, video.name);
  return request('/api/v1/video-imports', {
    method: 'POST',
    headers: { 'X-GrindLess-Local': '1' },
    body,
  });
}

export function getVideoImport(jobId: string): Promise<VideoImportStatus> {
  return request(`/api/v1/video-imports/${jobId}`);
}

export function simulateMavuika(
  inventory: Record<string, unknown>,
  policy: FarmPolicy,
  targetSlots: Slot[],
  resinBudget: number,
  seed: number,
  llmBackend: LLMBackend,
): Promise<SimulationResponse> {
  return request('/api/v1/simulations/mavuika', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      inventory,
      policy,
      target_slots: targetSlots,
      resin_budget: resinBudget,
      seed,
      llm_backend: llmBackend,
    }),
  });
}

export function simulateCharacter(
  characterKey: string,
  inventory: Record<string, unknown>,
  policy: FarmPolicy,
  targetSlots: Slot[],
  resinBudget: number,
  seed: number,
  llmBackend: LLMBackend,
  teamIntent: TeamIntent,
  collectionId: string,
  artifactGoal: ResolvedArtifactGoal | null,
  rotationPlan: ValidatedRotation | null,
): Promise<SimulationResponse> {
  return request(`/api/v1/characters/${characterKey}/simulation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      inventory,
      policy,
      target_slots: targetSlots,
      resin_budget: resinBudget,
      seed,
      llm_backend: llmBackend,
      team_intent: teamIntent,
      enka_collection_id: collectionId,
      artifact_goal: artifactGoal,
      rotation_plan: rotationPlan,
    }),
  });
}
