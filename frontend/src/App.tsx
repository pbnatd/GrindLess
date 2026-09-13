import { useEffect, useMemo, useRef, useState } from 'react';
import {
  analyzeCharacter, createArtifactGoalStrategy, createRotationStrategy, createTeamStrategy, finalizeEnkaCollection, getCharacters, getGameAdapterStatus, getHealth, getLLMStatus, getSession,
  getSessions, getVideoImport, loadEnkaSnapshot, planTeams, simulateCharacter, startVideoImport,
} from './api';
import type {
  AnalysisResponse, ArtifactCandidate, ArtifactGoalStrategyResult, CharacterCatalogResponse, CharacterDefinition, DomainTeamMode, EnkaCollection,
  FarmPolicy, HealthResponse, GameAdapterStatus, LLMBackend, LLMStatusResponse, SessionSummary,
  ReasoningEffort, RotationAction, RotationStrategyResult, SimulationResponse, Slot, TeamEvaluationReport, TeamIntent, TeamMetric, TeamMode, TeamObjective, TeamPlan, TeamStrategyResult, VideoImportStatus,
} from './types';

type View = 'onboarding' | 'strategy' | 'inventory' | 'build' | 'artifact-plan' | 'rotation' | 'goals' | 'simulation' | 'history' | 'control';
type TeamInputMethod = 'showcase' | 'roster';

const slots: Slot[] = ['flower', 'plume', 'sands', 'goblet', 'circlet'];
const slotLabels: Record<Slot, string> = {
  flower: 'Цветок', plume: 'Перо', sands: 'Часы', goblet: 'Кубок', circlet: 'Корона',
};
const slotGlyphs: Record<Slot, string> = {
  flower: '✦', plume: '〆', sands: '◈', goblet: '♢', circlet: '✧',
};
const statLabels: Record<string, string> = {
  hp_flat: 'HP', atk_flat: 'Сила атаки', def_flat: 'Защита', hp_pct: 'HP%',
  atk_pct: 'Сила атаки%', def_pct: 'Защита%', elemental_mastery: 'Мастерство стихий',
  energy_recharge: 'Восст. энергии', crit_rate: 'Шанс крита', crit_dmg: 'Крит. урон',
  pyro_dmg: 'Пиро-урон', physical_dmg: 'Физ. урон', anemo_dmg: 'Анемо-урон',
  geo_dmg: 'Гео-урон', electro_dmg: 'Электро-урон', hydro_dmg: 'Гидро-урон',
  cryo_dmg: 'Крио-урон', dendro_dmg: 'Дендро-урон', healing_bonus: 'Бонус лечения',
};
const characterLabels: Record<string, string> = {
  Mavuika: 'Мавуика', Citlali: 'Ситлали', Xilonen: 'Шилонен', Bennett: 'Беннет',
  Neuvillette: 'Нёвиллет', Arlecchino: 'Арлекино', Nahida: 'Нахида', Xiangling: 'Сян Лин',
  Noelle: 'Ноэлль', Kaeya: 'Кэйа', Lisa: 'Лиза', Furina: 'Фурина', Zhongli: 'Чжун Ли',
  Kazuha: 'Кадзуха', Sucrose: 'Сахароза', Fischl: 'Фишль', Xingqiu: 'Син Цю',
  Yelan: 'Е Лань', KukiShinobu: 'Куки Синобу', Chevreuse: 'Шеврёз',
};
const actionLabels: Record<RotationAction, string> = {
  skill: 'Навык',
  burst: 'Взрыв стихий',
  normal_attack: 'Обычная атака',
  charged_attack: 'Заряженная атака',
  dodge: 'Уклонение',
};
const teamObjectives: Array<{ key: TeamObjective; label: string; description: string }> = [
  { key: 'max_dps', label: 'Максимальный DPS', description: 'Самый высокий потолок урона; сложная ротация допустима.' },
  { key: 'comfort', label: 'Комфорт', description: 'Лечение, щит и простое исполнение важнее рекордного урона.' },
  { key: 'stable_rotation', label: 'Стабильный DPS и ротация', description: 'Повторяемые циклы, готовность ресурсов и восстановление после ошибки.' },
];
const viewCodes: Record<View, string> = {
  onboarding: '01', strategy: '02', inventory: '03', build: '04', 'artifact-plan': '05',
  rotation: '06', goals: '07', simulation: '08', history: '09', control: '10',
};
const navigationIcons: Record<View, string[]> = {
  onboarding: ['M12 3.5a3.2 3.2 0 1 1 0 6.4 3.2 3.2 0 0 1 0-6.4Z', 'M5.5 20c.5-4 2.7-6.1 6.5-6.1s6 2.1 6.5 6.1'],
  strategy: ['M12 2.8 14 8l5.2 2-5.2 2-2 5.2-2-5.2-5.2-2L10 8l2-5.2Z', 'M18.5 15.5 19.4 18l2.6 1-2.6 1-.9 2.5-.9-2.5-2.6-1 2.6-1 .9-2.5Z'],
  inventory: ['M4 6.5 12 3l8 3.5-8 3.5-8-3.5Z', 'M4 6.5V17l8 4 8-4V6.5', 'M12 10v11'],
  build: ['M4 4h6v6H4V4Z', 'M14 4h6v6h-6V4Z', 'M4 14h6v6H4v-6Z', 'M14 14h6v6h-6v-6Z'],
  'artifact-plan': ['M12 3v3', 'M12 18v3', 'M3 12h3', 'M18 12h3', 'M8 12a4 4 0 1 0 8 0 4 4 0 0 0-8 0Z'],
  rotation: ['M18.5 8A7 7 0 0 0 6 5.5L4 8', 'M5.5 16A7 7 0 0 0 18 18.5L20 16', 'M4 4.5V8h3.5', 'M20 19.5V16h-3.5'],
  goals: ['M5 21V4', 'M5 5h11l-2.5 4L16 13H5'],
  simulation: ['M4 19V9', 'M9 19V5', 'M14 19v-7', 'M19 19V3', 'M2.5 19.5h19'],
  history: ['M12 5a7 7 0 1 1-6.2 3.7', 'M3.5 4.5v5h5', 'M12 8.5V12l2.5 2'],
  control: ['M12 3 19 6v5c0 4.5-2.8 8-7 10-4.2-2-7-5.5-7-10V6l7-3Z', 'm9 12 2 2 4-5'],
};

function StepIcon({ view }: { view: View }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true">{navigationIcons[view].map((path) => <path d={path} key={path} />)}</svg>;
}

function CharacterAvatar({ character, className }: { character: CharacterDefinition | null | undefined; className?: string }) {
  if (!character) return null;
  return <img className={className} src={`/avatars/${character.avatar_id}.png`} alt="" aria-hidden="true" draggable={false} />;
}
const objectiveLabels: Record<TeamObjective, string> = Object.fromEntries(
  teamObjectives.map((item) => [item.key, item.label]),
) as Record<TeamObjective, string>;
const reasoningOptions: Array<{ key: ReasoningEffort; label: string; description: string }> = [
  { key: 'low', label: 'Low', description: 'Быстрее, для простого повторного анализа.' },
  { key: 'medium', label: 'Medium', description: 'Баланс скорости и глубины.' },
  { key: 'high', label: 'High', description: 'Глубокий поиск механик и сравнение команд.' },
];
const teamMetricLabels: Record<TeamMetric, string> = {
  damage_potential: 'Урон',
  reaction_coherence: 'Реакции',
  rotation_stability: 'Ротация',
  energy_feasibility: 'Энергия',
  comfort: 'Комфорт',
  account_readiness: 'Готовность',
  domain_compatibility: 'Домен',
};
const adapterCheckLabels: Record<string, string> = {
  linux_host: 'Linux',
  x11_session: 'Сеанс X11',
  display_available: 'Экран',
  xdotool_installed: 'xdotool',
  maim_installed: 'maim',
  single_game_window: 'Окно Genshin',
  expected_game_size: 'Размер окна',
  game_has_focus: 'Фокус окна',
};

function StrategicModelPicker({
  status, backend, effort, onBackend, onEffort,
}: {
  status: LLMStatusResponse | null;
  backend: LLMBackend;
  effort: ReasoningEffort;
  onBackend: (value: LLMBackend) => void;
  onEffort: (value: ReasoningEffort) => void;
}) {
  const models = status?.backends.filter((item) => item.backend.startsWith('openai_')) || [];
  return <div className="strategic-model-control">
    <div className="model-picker strategy-models">
      <div className="model-heading"><span>Модель для анализа</span><small>Luna / Terra / Sol</small></div>
      {models.map((item) => <button key={item.backend} className={`model-option ${backend === item.backend ? 'active' : ''}`} disabled={!item.configured} onClick={() => onBackend(item.backend)} title={item.reason || undefined}><span>{item.backend.replace('openai_', '').toUpperCase()}</span><div><b>{item.label}</b><small>{item.configured ? item.model : item.reason}</small></div></button>)}
    </div>
    <div className="reasoning-picker">
      <div className="model-heading"><span>Глубина анализа</span><small>Low / Medium / High</small></div>
      <div>{reasoningOptions.map((item) => <button key={item.key} className={effort === item.key ? 'active' : ''} onClick={() => onEffort(item.key)} title={item.description}><b>{item.label}</b><small>{item.description}</small></button>)}</div>
    </div>
  </div>;
}

function WebResearchSources({ report }: { report: TeamStrategyResult['llm_audit'] }) {
  const sources = Array.from(new Map(
    report.calls.flatMap((call) => call.web_sources || []).map((source) => [source.url, source]),
  ).values());
  if (!sources.length) return <p className="web-research-empty">Ссылки на источники не загрузились. Попробуйте запустить анализ ещё раз.</p>;
  return <div className="web-research-sources"><b>Источники</b><div>{sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title || new URL(source.url).hostname}</a>)}</div></div>;
}

function TeamEvaluationView({
  report, title, characterName,
}: {
  report: TeamEvaluationReport;
  title: string;
  characterName: (key: string) => string;
}) {
  return <article className="team-evaluation-group">
    <header><div><span className="section-kicker">{title}</span><h3>Порог {report.acceptance_threshold.toFixed(0)} / 100</h3></div><small>{report.candidates.length} {report.candidates.length === 1 ? 'вариант' : 'варианта'}</small></header>
    {report.gate_errors_ru.map((reason) => <p className="evaluation-gate-error" key={reason}>{reason}</p>)}
    <div className="team-candidate-list">{report.candidates.map((candidate) => {
      const selected = candidate.proposal_id === report.selected_proposal_id;
      return <section className={`team-candidate-score ${selected ? 'selected' : candidate.accepted ? 'accepted' : 'rejected'}`} key={candidate.proposal_id}>
        <div className="candidate-score-head"><div><small>{selected ? 'Выбран' : candidate.accepted ? 'Прошёл' : 'Отклонён'}</small><b>{candidate.team.map(characterName).join(' · ')}</b></div><strong>{candidate.score.toFixed(1)}</strong></div>
        <div className="score-breakdown">{(Object.keys(teamMetricLabels) as TeamMetric[]).map((metric) => <span key={metric}><small>{teamMetricLabels[metric]}</small><b>{candidate.breakdown.raw_scores[metric]}/5</b><i>+{candidate.breakdown.weighted_points[metric].toFixed(1)}</i></span>)}</div>
        {candidate.rejection_reasons_ru.length > 0 && <ul className="candidate-rejections">{candidate.rejection_reasons_ru.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
        <details><summary>Почему такая оценка</summary><ul>{candidate.evidence_ru.map((item) => <li key={item}>{item}</li>)}</ul></details>
      </section>;
    })}</div>
  </article>;
}
const reasonLabels: Record<string, { title: string; text: string }> = {
  all_slot_goals_met: {
    title: 'Цель достигнута',
    text: 'Для каждого выбранного слота найден первый предмет, который лучше зафиксированной базы по заданным признакам.',
  },
  full_budget_spent: {
    title: 'Весь выбранный бюджет потрачен',
    text: 'Режим полного расхода не прерывает фарм после раннего улучшения: лучший дроп выбран из всей пачки.',
  },
  resin_exhausted: {
    title: 'Бюджет закончился раньше цели',
    text: 'Не все выбранные слоты удалось закрыть. Они останутся целями следующей сессии.',
  },
  guaranteed_upgrade_is_better: {
    title: 'Выгоднее сменить цель',
    text: 'Ожидаемый прирост от артефактов ниже гарантированного улучшения оружия или таланта.',
  },
  unknown_state: { title: 'Сессия остановлена', text: 'Не удалось уверенно определить, что сейчас происходит в игре.' },
  reward_not_confirmed: { title: 'Сессия остановлена', text: 'Не удалось убедиться, что награда получена.' },
};

function label(value: string): string {
  return statLabels[value] || characterLabels[value] || value;
}

function selectedCandidate(analysis: AnalysisResponse, slot: Slot): ArtifactCandidate | undefined {
  return selectedAuditCandidate(analysis.audit, slot);
}

function selectedAuditCandidate(audit: AnalysisResponse['audit'], slot: Slot): ArtifactCandidate | undefined {
  const selectedId = audit.selected_artifact_ids[slot];
  return audit.candidates[slot].find((item) => item.artifact_id === selectedId);
}

function artifactCompositionLabel(goal: ArtifactGoalStrategyResult): string {
  return goal.evidence.allowed_set_options.find(
    (option) => option.option_id === goal.draft.selected_set_option_id,
  )?.label_ru || goal.resolved_goal.constraints.set_requirements
    .map((item) => `${item.pieces}pc ${item.set_name}`)
    .join(' + ');
}

function offPieceLabel(goal: ArtifactGoalStrategyResult): string {
  const artifactId = goal.inventory_audit.off_piece_artifact_id;
  if (!artifactId) return 'не найден';
  const candidate = Object.values(goal.inventory_audit.candidates)
    .flat()
    .find((item) => item.artifact_id === artifactId);
  return candidate ? `${slotLabels[candidate.slot]} · ${candidate.set_name}` : artifactId;
}

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [catalog, setCatalog] = useState<CharacterCatalogResponse | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [simulation, setSimulation] = useState<SimulationResponse | null>(null);
  const [llmStatus, setLLMStatus] = useState<LLMStatusResponse | null>(null);
  const [gameAdapter, setGameAdapter] = useState<GameAdapterStatus | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [llmBackend, setLLMBackend] = useState<LLMBackend>('offline');
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>('high');
  const [view, setView] = useState<View>('onboarding');
  const [targetKey, setTargetKey] = useState('Mavuika');
  const [teamInputMethod, setTeamInputMethod] = useState<TeamInputMethod>('showcase');
  const [targetTeamMode, setTargetTeamMode] = useState<TeamMode>('auto');
  const [targetObjective, setTargetObjective] = useState<TeamObjective>('max_dps');
  const [targetTeam, setTargetTeam] = useState<string[]>(['Mavuika']);
  const [domainTeamMode, setDomainTeamMode] = useState<DomainTeamMode>('auto');
  const [domainObjective, setDomainObjective] = useState<TeamObjective>('stable_rotation');
  const [domainTeam, setDomainTeam] = useState<string[]>([]);
  const [candidatePool, setCandidatePool] = useState<string[]>([]);
  const [targetQuery, setTargetQuery] = useState('');
  const [rosterQuery, setRosterQuery] = useState('');
  const [teamPlan, setTeamPlan] = useState<TeamPlan | null>(null);
  const [strategy, setStrategy] = useState<TeamStrategyResult | null>(null);
  const [strategyPreferences, setStrategyPreferences] = useState('');
  const [artifactGoal, setArtifactGoal] = useState<ArtifactGoalStrategyResult | null>(null);
  const [artifactPreferences, setArtifactPreferences] = useState('');
  const [rotation, setRotation] = useState<RotationStrategyResult | null>(null);
  const [rotationPreferences, setRotationPreferences] = useState('');
  const [showcaseFits, setShowcaseFits] = useState<'yes' | 'no' | null>(null);
  const [uid, setUid] = useState('');
  const [enkaConsent, setEnkaConsent] = useState(false);
  const [enkaCollection, setEnkaCollection] = useState<EnkaCollection | null>(null);
  const [enkaCooldown, setEnkaCooldown] = useState(0);
  const [policy, setPolicy] = useState<FarmPolicy>('economy');
  const [targetSlots, setTargetSlots] = useState<Slot[]>(['sands', 'goblet', 'circlet']);
  const [resinBudget, setResinBudget] = useState(200);
  const [seed, setSeed] = useState(386);
  const [selectedSlot, setSelectedSlot] = useState<Slot>('flower');
  const [fileName, setFileName] = useState('');
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [videoImport, setVideoImport] = useState<VideoImportStatus | null>(null);
  const [error, setError] = useState('');
  const payloadRef = useRef<Record<string, unknown> | null>(null);
  const targetMenuRef = useRef<HTMLDetailsElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const videoInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
    getCharacters().then(setCatalog).catch((reason: Error) => setError(reason.message));
    getGameAdapterStatus().then(setGameAdapter).catch(() => setGameAdapter(null));
    void refreshOperationalState();
  }, []);
  useEffect(() => {
    if (!enkaCooldown) return;
    const timer = window.setInterval(() => setEnkaCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [enkaCooldown > 0]);

  const currentPreset = analysis;
  const selectedCharacter = catalog?.targets.find((item) => item.key === targetKey);
  const targetProfile = enkaCollection?.profiles.find((item) => item.character_key === targetKey);
  const visibleRoster = useMemo(() => {
    const query = rosterQuery.trim().toLocaleLowerCase('ru');
    if (!query) return catalog?.roster || [];
    return (catalog?.roster || []).filter((item) =>
      item.name_ru.toLocaleLowerCase('ru').includes(query)
      || item.key.toLocaleLowerCase().includes(query),
    );
  }, [catalog, rosterQuery]);
  const visibleTargets = useMemo(() => {
    const query = targetQuery.trim().toLocaleLowerCase('ru');
    if (!query) return catalog?.targets || [];
    return (catalog?.targets || []).filter((item) =>
      item.name_ru.toLocaleLowerCase('ru').includes(query)
      || item.key.toLocaleLowerCase().includes(query)
      || item.element.toLocaleLowerCase().includes(query),
    );
  }, [catalog, targetQuery]);
  const discoveredRoster = enkaCollection?.profiles || [];
  const teamIntent: TeamIntent = {
    target_key: targetKey,
    target_objective: targetObjective,
    target_team_mode: targetTeamMode,
    target_team: targetTeamMode === 'manual' ? targetTeam : [],
    domain_team_mode: domainTeamMode,
    domain_objective: domainObjective,
    domain_team: domainTeamMode === 'manual' ? domainTeam : [],
    candidate_pool: candidatePool,
  };
  const selected = useMemo(
    () => analysis && selectedCandidate(analysis, selectedSlot),
    [analysis, selectedSlot],
  );
  const activeGoals = artifactGoal?.resolved_goal.targets || analysis?.goals || [];
  const characterName = (key: string) => catalog?.roster.find((item) => item.key === key)?.name_ru || characterLabels[key] || key;
  const maxRuns = resinBudget / 20;
  const projectedCheckpoints = policy === 'economy' ? maxRuns + 1 : 1;
  const isStrategicBackend = llmBackend.startsWith('openai_');

  async function refreshOperationalState() {
    const [statusResult, sessionsResult] = await Promise.allSettled([
      getLLMStatus(), getSessions(),
    ]);
    if (statusResult.status === 'fulfilled') {
      setLLMStatus(statusResult.value);
      const preferred = statusResult.value.backends.find(
        (item) => item.backend === 'openai_sol' && item.configured,
      ) || statusResult.value.backends.find(
        (item) => item.backend.startsWith('openai_') && item.configured,
      );
      if (preferred) {
        setLLMBackend((current) => current === 'offline' ? preferred.backend : current);
      }
    }
    if (sessionsResult.status === 'fulfilled') setSessions(sessionsResult.value.sessions);
  }

  async function runAudit(payload: Record<string, unknown>) {
    setBusy(true);
    setError('');
    try {
      if (!enkaCollection) throw new Error('Сначала загрузите профиль целевого персонажа из Enka');
      const result = await analyzeCharacter(
        targetKey, payload, policy, teamIntent, enkaCollection.collection_id,
      );
      setAnalysis(result);
      setArtifactGoal(null);
      setRotation(null);
      const defaults = result.audit.pending_slots.length ? result.audit.pending_slots : slots;
      setTargetSlots(defaults);
      setSelectedSlot(defaults[0] || 'flower');
      setView('build');
    } catch (reason) {
      setAnalysis(null);
      setError(reason instanceof Error ? reason.message : 'Не удалось разобрать файл');
    } finally { setBusy(false); }
  }

  function selectTarget(key: string) {
    setTargetKey(key);
    setTargetTeam([key]);
    setDomainTeam([]);
    setCandidatePool([]);
    setTeamPlan(null);
    setStrategy(null);
    setArtifactGoal(null);
    setRotation(null);
    setShowcaseFits(null);
    setEnkaCollection(null);
    targetMenuRef.current?.removeAttribute('open');
  }

  function selectTeamMethod(method: TeamInputMethod) {
    setTeamInputMethod(method);
    setTargetTeamMode(method === 'showcase' ? 'auto' : 'manual');
    setTargetTeam(method === 'showcase' ? [] : [targetKey]);
    setDomainTeamMode('auto');
    setDomainTeam([]);
    setCandidatePool([]);
    setTeamPlan(null);
    setStrategy(null);
    setArtifactGoal(null);
    setRotation(null);
    setShowcaseFits(null);
    setEnkaCollection(null);
  }

  function selectObjective(scope: 'target' | 'domain', objective: TeamObjective) {
    if (scope === 'target') setTargetObjective(objective);
    else setDomainObjective(objective);
    setTeamPlan(null);
    setStrategy(null);
    setArtifactGoal(null);
    setRotation(null);
  }

  function selectDiscoveredTargetMode(mode: TeamMode) {
    setTargetTeamMode(mode);
    setTargetTeam(mode === 'manual' ? [targetKey] : []);
    setTeamPlan(null);
    setStrategy(null);
    setArtifactGoal(null);
    setRotation(null);
    setEnkaCollection((current) => current
      ? { ...current, complete: false, finalized: false }
      : current);
  }

  function selectDiscoveredDomainMode(mode: DomainTeamMode) {
    setDomainTeamMode(mode);
    setDomainTeam([]);
    setTeamPlan(null);
    setStrategy(null);
    setArtifactGoal(null);
    setRotation(null);
    setEnkaCollection((current) => current
      ? { ...current, complete: false, finalized: false }
      : current);
  }

  function toggleCharacter(key: string, scope: 'target' | 'domain' | 'pool') {
    if (scope === 'target') {
      if (key === targetKey) return;
      setTargetTeam((current) => current.includes(key)
        ? current.filter((item) => item !== key)
        : current.length < 4 ? [...current, key] : current);
    } else if (scope === 'domain') {
      setDomainTeam((current) => current.includes(key)
        ? current.filter((item) => item !== key)
        : current.length < 4 ? [...current, key] : current);
    } else {
      setCandidatePool((current) => current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key]);
    }
    setTeamPlan(null);
    setStrategy(null);
    setArtifactGoal(null);
    setRotation(null);
    if (teamInputMethod === 'showcase') {
      setEnkaCollection((current) => current
        ? { ...current, complete: false, finalized: false }
        : current);
    } else {
      setEnkaCollection(null);
    }
  }

  async function prepareShowcase() {
    setError('');
    try {
      const plan = await planTeams(teamIntent);
      setTeamPlan(plan);
      setStrategy(null);
      setArtifactGoal(null);
      setRotation(null);
      setShowcaseFits(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Проверьте составы команд');
    }
  }

  async function refreshEnka() {
    setBusy(true);
    setError('');
    try {
      const result = await loadEnkaSnapshot(
        uid,
        enkaConsent,
        teamInputMethod === 'showcase' ? 'discovery' : 'planned',
        teamInputMethod === 'showcase' ? undefined : teamIntent,
        enkaCollection?.collection_id,
      );
      setEnkaCollection(result);
      if (teamInputMethod === 'showcase') {
        setCandidatePool(result.observed_keys.filter((key) => key !== targetKey));
      }
      setStrategy(null);
      setArtifactGoal(null);
      setRotation(null);
      setEnkaCooldown(result.ttl_seconds);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось загрузить витрину Enka');
    } finally { setBusy(false); }
  }

  async function finalizeDiscoveredTeams() {
    if (!enkaCollection || enkaCollection.mode !== 'discovery') {
      setError('Сначала загрузите хотя бы одну витрину Enka');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const plan = await planTeams(teamIntent);
      const finalized = await finalizeEnkaCollection(
        enkaCollection.collection_id,
        teamIntent,
      );
      setTeamPlan(plan);
      setEnkaCollection(finalized);
      setStrategy(null);
      setArtifactGoal(null);
      setRotation(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Проверьте выбранные команды');
    } finally { setBusy(false); }
  }

  async function runTeamStrategy() {
    if (!enkaCollection?.complete) {
      setError('Сначала соберите все профили из витрины Enka');
      return;
    }
    if (!isStrategicBackend) {
      setError('Для стратегического решения выберите Luna, Terra или Sol');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const result = await createTeamStrategy(
        teamIntent,
        enkaCollection.collection_id,
        llmBackend,
        reasoningEffort,
        strategyPreferences,
      );
      setStrategy(result);
      setArtifactGoal(null);
      setRotation(null);
      setTeamPlan(result.validated_team_plan);
      setTargetTeamMode('manual');
      setTargetTeam(result.target_team);
      if (result.validated_team_plan.domain_team_status === 'same_as_target') {
        setDomainTeamMode('same');
        setDomainTeam([]);
      } else {
        setDomainTeamMode('manual');
        setDomainTeam(result.domain_team);
      }
      setCandidatePool([]);
      setView('strategy');
      await refreshOperationalState();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось подобрать команды');
    } finally { setBusy(false); }
  }

  async function runArtifactGoalStrategy() {
    if (!payloadRef.current || !analysis) {
      setError('Сначала загрузите и проверьте инвентарь');
      return;
    }
    if (!enkaCollection) {
      setError('Коллекция Enka истекла — обновите профиль');
      return;
    }
    if (!isStrategicBackend) {
      setError('Для выбора целей артефактов выберите Luna, Terra или Sol');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const result = await createArtifactGoalStrategy(
        payloadRef.current,
        teamIntent,
        enkaCollection.collection_id,
        llmBackend,
        reasoningEffort,
        policy,
        artifactPreferences,
      );
      setArtifactGoal(result);
      setRotation(null);
      const pending = result.draft.slot_priority_order.filter((slot) =>
        result.inventory_audit.pending_slots.includes(slot),
      );
      setTargetSlots(pending.length ? pending : result.draft.slot_priority_order);
      setSelectedSlot(result.draft.slot_priority_order[0]);
      setView('artifact-plan');
      await refreshOperationalState();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось подобрать сборку');
    } finally { setBusy(false); }
  }

  async function runRotationStrategy() {
    if (!analysis || !enkaCollection) {
      setError('Сначала загрузите Enka и проверьте инвентарь');
      return;
    }
    if (!isStrategicBackend) {
      setError('Для построения ротации выберите Luna, Terra или Sol');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const result = await createRotationStrategy(
        teamIntent,
        enkaCollection.collection_id,
        llmBackend,
        reasoningEffort,
        artifactGoal?.resolved_goal || null,
        rotationPreferences,
      );
      setRotation(result);
      setView('rotation');
      await refreshOperationalState();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось составить ротацию');
    } finally { setBusy(false); }
  }

  async function acceptJSON(file?: File) {
    if (!file) return;
    setFileName(file.name);
    setError('');
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('В корне JSON должен находиться объект GOOD');
      }
      const payload = parsed as Record<string, unknown>;
      if (payload.format !== 'GOOD') throw new Error('Это JSON, но не GOOD: отсутствует format = "GOOD"');
      payloadRef.current = payload;
      await runAudit(payload);
    } catch (reason) {
      payloadRef.current = null;
      setAnalysis(null);
      setArtifactGoal(null);
      setRotation(null);
      setError(reason instanceof Error ? reason.message : 'Файл невозможно прочитать');
    }
  }

  async function acceptVideo(file?: File) {
    if (!file) return;
    setFileName(file.name);
    setVideoImport(null);
    setBusy(true);
    setError('');
    try {
      const started = await startVideoImport(file);
      for (;;) {
        const status = await getVideoImport(started.job_id);
        setVideoImport(status);
        if (status.status === 'failed') {
          throw new Error(status.error || status.message);
        }
        if (status.status === 'succeeded') {
          if (!status.good) throw new Error('Artiscan завершился без GOOD-инвентаря');
          payloadRef.current = status.good;
          await runAudit(status.good);
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
    } catch (reason) {
      payloadRef.current = null;
      setAnalysis(null);
      setArtifactGoal(null);
      setRotation(null);
      setError(reason instanceof Error ? reason.message : 'Не удалось распознать видео');
    } finally {
      setBusy(false);
    }
  }

  function acceptInventoryFile(file?: File) {
    if (!file) return;
    const suffix = file.name.split('.').pop()?.toLowerCase();
    if (suffix && ['mp4', 'mov', 'mkv', 'webm'].includes(suffix)) {
      void acceptVideo(file);
      return;
    }
    void acceptJSON(file);
  }

  function resetImport() {
    payloadRef.current = null;
    setAnalysis(null);
    setSimulation(null);
    setArtifactGoal(null);
    setRotation(null);
    setFileName('');
    setVideoImport(null);
    setError('');
    setView('inventory');
    if (inputRef.current) inputRef.current.value = '';
    if (videoInputRef.current) videoInputRef.current.value = '';
  }

  function toggleTarget(slot: Slot) {
    setTargetSlots((current) => current.includes(slot)
      ? current.filter((item) => item !== slot)
      : slots.filter((item) => item === slot || current.includes(item)));
  }

  async function runSimulation(nextSeed = seed) {
    if (!payloadRef.current || !analysis) return;
    if (!targetSlots.length) {
      setError('Выберите хотя бы один целевой слот');
      return;
    }
    setBusy(true);
    setError('');
    try {
      if (!enkaCollection) throw new Error('Коллекция Enka истекла — обновите профиль');
      const result = await simulateCharacter(
        targetKey, payloadRef.current, policy, targetSlots, resinBudget, nextSeed,
        llmBackend, teamIntent, enkaCollection.collection_id,
        artifactGoal?.resolved_goal || null,
        rotation?.validated_rotation || null,
      );
      setSeed(nextSeed);
      setSimulation(result);
      setView('simulation');
      await refreshOperationalState();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось запустить симуляцию');
    } finally { setBusy(false); }
  }

  async function openSession(sessionId: string) {
    setBusy(true);
    setError('');
    try {
      const stored = await getSession(sessionId);
      setSimulation(stored.payload);
      setPolicy(stored.payload.policy);
      setTargetSlots(stored.payload.target_slots);
      setSeed(stored.payload.seed);
      setView('simulation');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось открыть сессию');
    } finally { setBusy(false); }
  }

  return (
    <div className={`app-shell view-${view}`}>
      <div className="ambient-field" aria-hidden="true"><i /><i /><i /><b className="ambient-wordmark">GRIND / LESS</b></div>
      <header className="app-navigation">
        <button className="brand app-brand" aria-label="Открыть первый шаг" onClick={() => setView('onboarding')}><span className="brand-mark">✦</span><div><b>GrindLess</b><small>план прокачки</small></div></button>
        <nav aria-label="Этапы настройки">
          <button className={`nav-item ${view === 'onboarding' ? 'active' : enkaCollection?.complete ? 'ready' : ''}`} onClick={() => setView('onboarding')}><span className="nav-icon"><StepIcon view="onboarding" /><i>01</i></span><div><b>Персонаж и команды</b><small>Enka · витрина</small></div></button>
          <button className={`nav-item ${view === 'strategy' ? 'active' : strategy ? 'ready' : ''}`} disabled={!strategy} onClick={() => setView('strategy')}><span className="nav-icon"><StepIcon view="strategy" /><i>02</i></span><div><b>План команд</b><small>составы и приоритеты</small></div></button>
          <button className={`nav-item ${view === 'inventory' ? 'active' : analysis ? 'ready' : ''}`} disabled={!enkaCollection?.complete} onClick={() => setView('inventory')}><span className="nav-icon"><StepIcon view="inventory" /><i>03</i></span><div><b>Инвентарь</b><small>GOOD / Artiscan</small></div></button>
          <button className={`nav-item ${view === 'build' ? 'active' : analysis ? 'ready' : ''}`} disabled={!analysis} onClick={() => setView('build')}><span className="nav-icon"><StepIcon view="build" /><i>04</i></span><div><b>Сборка</b><small>лучшие кандидаты</small></div></button>
          <button className={`nav-item ${view === 'artifact-plan' ? 'active' : artifactGoal ? 'ready' : ''}`} disabled={!artifactGoal} onClick={() => setView('artifact-plan')}><span className="nav-icon"><StepIcon view="artifact-plan" /><i>05</i></span><div><b>Цели сборки</b><small>сеты и характеристики</small></div></button>
          <button className={`nav-item ${view === 'rotation' ? 'active' : rotation ? 'ready' : ''}`} disabled={!analysis} onClick={() => setView('rotation')}><span className="nav-icon"><StepIcon view="rotation" /><i>06</i></span><div><b>Ротация</b><small>порядок действий</small></div></button>
          <button className={`nav-item ${view === 'goals' ? 'active' : simulation ? 'ready' : ''}`} disabled={!analysis} onClick={() => setView('goals')}><span className="nav-icon"><StepIcon view="goals" /><i>07</i></span><div><b>Цели фарма</b><small>слоты и смола</small></div></button>
          <button className={`nav-item ${view === 'simulation' ? 'active' : ''}`} disabled={!simulation} onClick={() => setView('simulation')}><span className="nav-icon"><StepIcon view="simulation" /><i>08</i></span><div><b>Симуляция</b><small>результаты фарма</small></div></button>
          <button className={`nav-item ${view === 'history' ? 'active' : sessions.length ? 'ready' : ''}`} onClick={() => setView('history')}><span className="nav-icon"><StepIcon view="history" /><i>09</i></span><div><b>История</b><small>{sessions.length} локальных сессий</small></div></button>
          <button className={`nav-item ${view === 'control' ? 'active' : gameAdapter?.status === 'ready' ? 'ready' : ''}`} onClick={() => setView('control')}><span className="nav-icon"><StepIcon view="control" /><i>10</i></span><div><b>Управление</b><small>Linux · X11</small></div></button>
        </nav>
        <div className="local-state"><span className={`status-dot ${health ? 'online' : ''}`} /><div><b>{health ? 'Приложение готово' : 'Приложение не запущено'}</b><small>{health ? `${health.platform.host} · v${health.version}` : 'Запустите grindless-app'}</small></div></div>
      </header>

      <main>
        <header className="topbar">
          <div><span className="eyebrow">Персональный план прокачки</span><h1>{view === 'onboarding' ? 'Кого прокачиваем и кто пойдёт в домен?' : view === 'strategy' ? 'Какие команды подходят лучше?' : view === 'artifact-plan' ? 'Какую сборку будем искать?' : view === 'rotation' ? 'В каком порядке использовать навыки?' : view === 'goals' ? 'Какие артефакты будем искать?' : view === 'simulation' ? 'Результаты сессии' : view === 'history' ? 'История решений на этом компьютере' : view === 'control' ? 'Готов ли Linux к управлению игрой?' : `Соберём ${selectedCharacter?.name_ru || 'персонажа'} из того, что уже есть`}</h1></div>
          <div className="topbar-meta"><span className="view-code">GL / {viewCodes[view]}</span><div className="privacy-pill"><span>✦</span>{llmBackend === 'offline' ? ' Данные остаются на компьютере' : view === 'strategy' ? ' Для подбора отправим данные персонажей и ваш комментарий' : view === 'artifact-plan' ? ' Для расчёта отправим сводку сборки и ваш комментарий' : view === 'rotation' ? ' Для ротации отправим состав команды и ваши пожелания' : ' Для объяснения отправим только журнал сессии'}</div></div>
        </header>

        <section className="profile-strip">
          <span className="profile-watermark" aria-hidden="true">LESS</span>
          <div className="avatar-orbit"><CharacterAvatar character={selectedCharacter} /></div>
          <div className="profile-title"><small>{targetProfile ? 'Данные загружены из Enka' : 'Выбранная цель'}</small><h2>{selectedCharacter?.name_ru || 'Выберите персонажа'} {targetProfile && <i>C{targetProfile.constellation}</i>}</h2><p>{targetProfile ? `оружие #${targetProfile.weapon_id || '—'} · R${targetProfile.weapon_refinement || 1}` : selectedCharacter?.primary_set || '—'}</p></div>
          <div className="team-block"><small>Целевая команда · {objectiveLabels[teamPlan?.target_objective || targetObjective]}</small><div>{strategy ? strategy.target_team.map((item) => <span key={item}>{characterName(item)}</span>) : teamIntent.target_team_mode === 'manual' ? teamIntent.target_team.map((item) => <span key={item}>{characterName(item)}</span>) : <span>подбор по кандидатам</span>}</div></div>
          <div className="team-block"><small>Команда домена · {objectiveLabels[teamPlan?.domain_objective || domainObjective]}</small><div>{strategy ? strategy.domain_team.map((item) => <span key={item}>{characterName(item)}</span>) : teamIntent.domain_team_mode === 'same' ? <span>та же команда</span> : teamIntent.domain_team_mode === 'manual' ? teamIntent.domain_team.map((item) => <span key={item}>{characterName(item)}</span>) : <span>подбор по кандидатам</span>}</div></div>
        </section>

        {view === 'onboarding' && (
          <section className="onboarding-panel">
            <div className="onboarding-section target-picker-section">
              <span className="section-kicker">1 · целевой персонаж</span>
              <h2>Выберите персонажа для прокачки</h2>
              <p className="lead-copy">В базе {catalog?.targets.length || 0} подробных профилей. Полный список и поиск находятся в компактном меню.</p>
              <details
                className="target-picker"
                ref={targetMenuRef}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') targetMenuRef.current?.removeAttribute('open');
                }}
              >
                <summary className="target-picker-summary">
                  <span className="target-picker-avatar" aria-hidden="true"><CharacterAvatar character={selectedCharacter} /></span>
                  <span className="target-picker-current">
                    <small>Текущая цель</small>
                    <b>{selectedCharacter?.name_ru || 'Выберите персонажа'}</b>
                    <em>{selectedCharacter ? `${selectedCharacter.element} · ${selectedCharacter.rarity}★ · ${selectedCharacter.role}` : 'Откройте список доступных целей'}</em>
                  </span>
                  <span className="target-picker-action"><span>Изменить</span><i aria-hidden="true">⌄</i></span>
                </summary>
                <div className="target-picker-menu">
                  <div className="target-picker-toolbar">
                    <label className="search-field target-search"><span>Найти цель</span><input value={targetQuery} placeholder="Имя, ключ или элемент" onChange={(event) => setTargetQuery(event.target.value)} /></label>
                    <p className="target-result-count">Показано {visibleTargets.length} из {catalog?.targets.length || 0}</p>
                  </div>
                  {visibleTargets.length > 0
                    ? <div className="character-grid">{visibleTargets.map((item) => <button type="button" key={item.key} className={`character-card ${targetKey === item.key ? 'selected' : ''}`} onClick={() => selectTarget(item.key)}><span className="character-card-avatar"><CharacterAvatar character={item} /></span><span className="character-card-element">{item.element}</span><b>{item.name_ru}</b><small>{item.rarity}★ · {item.role}</small><em>{item.primary_set}</em></button>)}</div>
                    : <p className="target-picker-empty">По этому запросу персонажи не найдены.</p>}
                </div>
              </details>
            </div>

            <div className="onboarding-section team-config">
              <span className="section-kicker">2 · как собрать персонажей</span>
              <h2>Начать с витрины или выбрать вручную?</h2>
              <p className="lead-copy">Витрина избавляет от поиска среди всего ростера: приложение само распознает показанных героев. Ручной список остаётся для тех, кто заранее знает весь состав.</p>
              <div className="method-grid">
                <button className={teamInputMethod === 'showcase' ? 'selected' : ''} onClick={() => selectTeamMethod('showcase')}><span>Рекомендуется</span><b>Сначала витрина Enka</b><small>Покажите желаемых героев в игре, загрузите витрину и при необходимости повторите.</small></button>
                <button className={teamInputMethod === 'roster' ? 'selected' : ''} onClick={() => selectTeamMethod('roster')}><span>Альтернатива</span><b>Выбрать из полного списка</b><small>Найдите персонажей вручную среди всех {catalog?.roster_count || 0} записей ростера.</small></button>
              </div>
            </div>

            {teamInputMethod === 'showcase' && <>
              <div className="onboarding-section showcase-card discovery-card">
                <span className="section-kicker">3 · первая витрина</span>
                <h2>Поставьте желаемых персонажей в Character Showcase</h2>
                <p>Добавьте {selectedCharacter?.name_ru || 'целевого персонажа'} и союзников, которых готовы использовать в итоговой или доменной команде. Имена заранее указывать не нужно — приложение получит их из открытой витрины.</p>
                <div className="truth-note"><b>Если все не помещаются</b><p>Загрузите первую часть, замените персонажей в витрине и после окончания TTL Enka нажмите «Добавить следующую витрину». Уже найденные профили сохранятся в локальной коллекции.</p></div>
                <div className="enka-form"><label><span>UID</span><input value={uid} inputMode="numeric" placeholder="9–10 цифр" onChange={(event) => setUid(event.target.value.replace(/\D/g, ''))} /></label><label className="consent-check"><input type="checkbox" checked={enkaConsent} onChange={(event) => setEnkaConsent(event.target.checked)} /><span>Разрешаю запрос UID к Enka.Network. Видео и GOOD туда не отправляются.</span></label><button className="primary-button" disabled={busy || !enkaConsent || uid.length < 9 || enkaCooldown > 0} onClick={() => void refreshEnka()}>{busy ? 'Загружаем…' : enkaCooldown > 0 ? `Следующая витрина через ${enkaCooldown} сек.` : enkaCollection ? 'Добавить следующую витрину' : 'Загрузить первую витрину'}</button></div>
                {enkaCollection && <div className="collection-result discovery-result"><b>Найдено персонажей: {enkaCollection.observed_keys.length}</b><div className="showcase-list">{enkaCollection.profiles.map((profile) => <span key={profile.character_key}>{profile.name_ru}</span>)}</div><p>Коллекция хранится в памяти 30 минут и не содержит полный UID. Отсутствие героя означает только, что он ещё не был замечен в загруженных витринах.</p>{!enkaCollection.observed_keys.includes(targetKey) && <p><strong>Нужно добавить {selectedCharacter?.name_ru}:</strong> целевой персонаж пока не найден.</p>}</div>}
              </div>

              {enkaCollection && <div className="onboarding-section team-config discovered-team-config">
                <span className="section-kicker">4 · команды из найденных героев</span>
                <h2>Выберите составы или включите автоподбор</h2>

                <div className="discovered-team-section">
                  <h3>Итоговая команда</h3>
                  <div className="objective-grid">{teamObjectives.map((item) => <button key={item.key} className={targetObjective === item.key ? 'selected' : ''} onClick={() => selectObjective('target', item.key)}><b>{item.label}</b><small>{item.description}</small></button>)}</div>
                  <div className="segmented compact"><button className={targetTeamMode === 'auto' ? 'active' : ''} onClick={() => selectDiscoveredTargetMode('auto')}>Подобрать из найденных</button><button className={targetTeamMode === 'manual' ? 'active' : ''} onClick={() => selectDiscoveredTargetMode('manual')}>Укажу точный состав</button></div>
                  {targetTeamMode === 'auto' ? <p>GrindLess выберет {selectedCharacter?.name_ru} и трёх союзников из этих {candidatePool.length} найденных кандидатов.</p> : <div className="roster-grid compact-roster">{discoveredRoster.filter((item) => item.character_key !== targetKey).map((item) => { const active = targetTeam.includes(item.character_key); return <button key={item.character_key} className={active ? 'selected' : ''} onClick={() => toggleCharacter(item.character_key, 'target')}><span>{active ? '✓' : '+'}</span>{item.name_ru}</button>; })}</div>}
                </div>

                <div className="discovered-team-section">
                  <h3>Команда домена</h3>
                  <p className="domain-independence-note"><b>Независимый состав:</b> целевой герой здесь не обязателен. Автоподбор рассматривает всех найденных персонажей и оптимизирует только прохождение домена.</p>
                  <div className="objective-grid">{teamObjectives.map((item) => <button key={item.key} className={domainObjective === item.key ? 'selected' : ''} onClick={() => selectObjective('domain', item.key)}><b>{item.label}</b><small>{item.description}</small></button>)}</div>
                  <div className="segmented compact"><button className={domainTeamMode === 'same' ? 'active' : ''} onClick={() => selectDiscoveredDomainMode('same')}>Та же команда</button><button className={domainTeamMode === 'auto' ? 'active' : ''} onClick={() => selectDiscoveredDomainMode('auto')}>Подобрать из найденных</button><button className={domainTeamMode === 'manual' ? 'active' : ''} onClick={() => selectDiscoveredDomainMode('manual')}>Укажу точный состав</button></div>
                  {domainTeamMode === 'manual' && <div className="roster-grid compact-roster">{discoveredRoster.map((item) => { const active = domainTeam.includes(item.character_key); return <button key={item.character_key} className={active ? 'selected' : ''} onClick={() => toggleCharacter(item.character_key, 'domain')}><span>{active ? '✓' : '+'}</span>{item.name_ru}</button>; })}</div>}
                </div>

                <button className="primary-button" disabled={busy} onClick={() => void finalizeDiscoveredTeams()}>{busy ? 'Проверяем…' : 'Все нужные герои собраны — проверить команды →'}</button>
                {enkaCollection.complete && <div className="collection-result complete"><b>Команды готовы к подбору</b><p>В подборе участвуют только найденные и выбранные персонажи. Чтобы добавить ещё одного, загрузите следующую витрину и снова проверьте составы.</p></div>}
              </div>}

              {enkaCollection?.complete && <div className="onboarding-section strategy-launch">
                <div><span className="section-kicker">5 · подбор команд</span><h3>Подобрать и сравнить команды</h3><p>GrindLess учтёт персонажей, оружие, выбранные приоритеты и ваши пожелания. Затем сравнит допустимые варианты.</p></div>
                <label className="strategy-preferences"><span>Обязательные ограничения и пожелания — необязательно</span><textarea value={strategyPreferences} maxLength={2000} placeholder="Например: не использовать Беннета или сохранить Фурину для второй команды" onChange={(event) => setStrategyPreferences(event.target.value)} /></label>
                <StrategicModelPicker status={llmStatus} backend={llmBackend} effort={reasoningEffort} onBackend={setLLMBackend} onEffort={setReasoningEffort} />
                <div className="strategy-actions"><button className="primary-button" disabled={busy || !isStrategicBackend} onClick={() => void runTeamStrategy()}>{busy ? 'Подбираем команды…' : 'Подобрать команды →'}</button><button className="secondary-button" onClick={() => setView('inventory')}>Продолжить без подбора</button></div>
              </div>}
            </>}

            {teamInputMethod === 'roster' && <>

            <div className="onboarding-section team-config">
              <span className="section-kicker">2 · целевая команда</span>
              <h2>У вас уже есть желаемый состав?</h2>
              <div className="objective-heading"><b>Какой результат важнее?</b><small>Критерий применяется и к ручному составу, и к автоподбору.</small></div>
              <div className="objective-grid">{teamObjectives.map((item) => <button key={item.key} className={targetObjective === item.key ? 'selected' : ''} onClick={() => selectObjective('target', item.key)}><b>{item.label}</b><small>{item.description}</small></button>)}</div>
              <div className="segmented compact"><button className={targetTeamMode === 'manual' ? 'active' : ''} onClick={() => { setTargetTeamMode('manual'); setTargetTeam([targetKey]); setTeamPlan(null); setStrategy(null); setArtifactGoal(null); setRotation(null); setEnkaCollection(null); }}>Да, укажу состав</button><button className={targetTeamMode === 'auto' ? 'active' : ''} onClick={() => { setTargetTeamMode('auto'); setTargetTeam([]); setTeamPlan(null); setStrategy(null); setArtifactGoal(null); setRotation(null); setEnkaCollection(null); }}>Нет, подобрать</button></div>
              <p>{targetTeamMode === 'manual' ? `Выберите ещё трёх героев. Состав будет оценён по критерию «${objectiveLabels[targetObjective]}».` : `Отметьте хотя бы трёх доступных кандидатов. Подбор по критерию «${objectiveLabels[targetObjective]}» будет ограничен этим списком.`}</p>
              <div className="roster-toolbar"><label><span>Поиск среди {catalog?.roster_count || 0} персонажей</span><input type="search" value={rosterQuery} placeholder="Например, Фурина" onChange={(event) => setRosterQuery(event.target.value)} /></label><small>Найдено: {visibleRoster.filter((item) => item.key !== targetKey).length}</small></div>
              <div className="roster-grid">{visibleRoster.filter((item) => item.key !== targetKey).map((item) => { const active = targetTeamMode === 'manual' ? targetTeam.includes(item.key) : candidatePool.includes(item.key); return <button key={item.key} className={active ? 'selected' : ''} onClick={() => toggleCharacter(item.key, targetTeamMode === 'manual' ? 'target' : 'pool')}><span>{active ? '✓' : '+'}</span>{item.name_ru}</button>; })}</div>
            </div>

            <div className="onboarding-section team-config">
              <span className="section-kicker">3 · команда домена</span>
              <h2>Как должна проходить домен?</h2>
              <div className="objective-heading"><b>Отдельный критерий домена</b><small>Он не переписывает цель итоговой команды, даже если состав один.</small></div>
              <p className="domain-independence-note"><b>По умолчанию это независимая команда.</b> Целевой герой не обязан входить в неё: автоподбор использует любых отмеченных персонажей аккаунта.</p>
              <div className="objective-grid">{teamObjectives.map((item) => <button key={item.key} className={domainObjective === item.key ? 'selected' : ''} onClick={() => selectObjective('domain', item.key)}><b>{item.label}</b><small>{item.description}</small></button>)}</div>
              <div className="segmented compact"><button className={domainTeamMode === 'same' ? 'active' : ''} onClick={() => { setDomainTeamMode('same'); setDomainTeam([]); setTeamPlan(null); setStrategy(null); setArtifactGoal(null); setRotation(null); setEnkaCollection(null); }}>Та же команда</button><button className={domainTeamMode === 'manual' ? 'active' : ''} onClick={() => { setDomainTeamMode('manual'); setDomainTeam([]); setTeamPlan(null); setStrategy(null); setArtifactGoal(null); setRotation(null); setEnkaCollection(null); }}>Другой состав</button><button className={domainTeamMode === 'auto' ? 'active' : ''} onClick={() => { setDomainTeamMode('auto'); setDomainTeam([]); setTeamPlan(null); setStrategy(null); setArtifactGoal(null); setRotation(null); setEnkaCollection(null); }}>Подобрать</button></div>
              <p>{domainTeamMode === 'same' ? `Состав будет один, а в результате будет отдельно показан компромисс между «${objectiveLabels[targetObjective]}» и «${objectiveLabels[domainObjective]}».` : domainTeamMode === 'manual' ? `Выберите ровно четырёх любых героев; они будут оценены по критерию «${objectiveLabels[domainObjective]}».` : `GrindLess независимо выберет четырёх героев из всего отмеченного пула; ${selectedCharacter?.name_ru || 'целевой персонаж'} в эту команду не добавляется автоматически. Критерий — «${objectiveLabels[domainObjective]}».`}</p>
              {domainTeamMode === 'manual' && <><div className="roster-toolbar"><label><span>Поиск по общему ростеру</span><input type="search" value={rosterQuery} placeholder="Например, Чжун Ли" onChange={(event) => setRosterQuery(event.target.value)} /></label><small>Найдено: {visibleRoster.length}</small></div><div className="roster-grid">{visibleRoster.map((item) => { const active = domainTeam.includes(item.key); return <button key={item.key} className={active ? 'selected' : ''} onClick={() => toggleCharacter(item.key, 'domain')}><span>{active ? '✓' : '+'}</span>{item.name_ru}</button>; })}</div></>}
              {domainTeamMode === 'auto' && targetTeamMode === 'manual' && <><div className="roster-toolbar"><label><span>Доступные персонажи аккаунта</span><input type="search" value={rosterQuery} placeholder="Например, Чжун Ли" onChange={(event) => setRosterQuery(event.target.value)} /></label><small>Отмечено: {candidatePool.length}</small></div><div className="roster-grid">{visibleRoster.map((item) => { const active = candidatePool.includes(item.key); return <button key={item.key} className={active ? 'selected' : ''} onClick={() => toggleCharacter(item.key, 'pool')}><span>{active ? '✓' : '+'}</span>{item.name_ru}</button>; })}</div></>}
              <button className="primary-button" onClick={() => void prepareShowcase()}>Составить список витрины →</button>
            </div>

            {teamPlan && <div className="onboarding-section showcase-card">
              <span className="section-kicker">4 · витрина Genshin</span>
              <h2>Поставьте этих персонажей в Character Showcase</h2>
              <div className="showcase-list">{teamPlan.expected_showcase_keys.map((key) => <span key={key}>{characterName(key)}</span>)}</div>
              <p>Витрина Enka частичная: отсутствие героя не означает, что его нет на аккаунте. Поэтому можно собрать несколько снимков.</p>
              <b>Все поместились одновременно?</b>
              <div className="button-row"><button className={showcaseFits === 'yes' ? 'primary-button' : 'secondary-button'} onClick={() => setShowcaseFits('yes')}>Да</button><button className={showcaseFits === 'no' ? 'primary-button' : 'secondary-button'} onClick={() => setShowcaseFits('no')}>Нет, нужны замены</button></div>
              {showcaseFits === 'no' && <div className="truth-note"><b>Снимки объединятся</b><p>Поставьте первую часть списка, загрузите Enka, затем замените персонажей в витрине. После окончания TTL нажмите «Обновить и добавить» — уже найденные профили сохранятся в этой локальной коллекции.</p></div>}
              {showcaseFits && <div className="enka-form"><label><span>UID</span><input value={uid} inputMode="numeric" placeholder="9–10 цифр" onChange={(event) => setUid(event.target.value.replace(/\D/g, ''))} /></label><label className="consent-check"><input type="checkbox" checked={enkaConsent} onChange={(event) => setEnkaConsent(event.target.checked)} /><span>Разрешаю один запрос UID к Enka.Network. Видео и GOOD туда не отправляются.</span></label><button className="primary-button" disabled={busy || !enkaConsent || uid.length < 9 || enkaCooldown > 0} onClick={() => void refreshEnka()}>{busy ? 'Загружаем…' : enkaCooldown > 0 ? `Повтор через ${enkaCooldown} сек.` : enkaCollection ? 'Обновить и добавить' : 'Загрузить витрину'}</button></div>}
              {enkaCollection && <div className={`collection-result ${enkaCollection.complete ? 'complete' : ''}`}><b>{enkaCollection.complete ? 'Все нужные профили собраны' : `Не хватает: ${enkaCollection.missing_keys.map(characterName).join(', ')}`}</b><p>Собрано: {enkaCollection.observed_keys.map(characterName).join(', ')}. Коллекция живёт в памяти 30 минут и не хранит полный UID.</p>{enkaCollection.missing_keys.length > 0 && <p>Обновите витрину недостающими героями, дождитесь окончания TTL и загрузите следующий снимок.</p>}</div>}
              {enkaCollection?.complete && <div className="strategy-launch">
                <div><span className="section-kicker">5 · подбор команд</span><h3>Подобрать и сравнить команды</h3><p>GrindLess учтёт персонажей, оружие, выбранные приоритеты и ваши пожелания. Затем сравнит допустимые варианты.</p></div>
                <label className="strategy-preferences"><span>Обязательные ограничения и пожелания — необязательно</span><textarea value={strategyPreferences} maxLength={2000} placeholder="Например: не использовать Беннета или сохранить Фурину для второй команды" onChange={(event) => setStrategyPreferences(event.target.value)} /></label>
                <StrategicModelPicker status={llmStatus} backend={llmBackend} effort={reasoningEffort} onBackend={setLLMBackend} onEffort={setReasoningEffort} />
                <div className="strategy-actions"><button className="primary-button" disabled={busy || !isStrategicBackend} onClick={() => void runTeamStrategy()}>{busy ? 'Подбираем команды…' : 'Подобрать команды →'}</button><button className="secondary-button" onClick={() => setView('inventory')}>Продолжить без подбора</button></div>
              </div>}
            </div>}
            </>}
          </section>
        )}

        {view === 'strategy' && strategy && (
          <section className="strategy-page">
            <div className="strategy-hero">
              <div><span className="section-kicker">Подбор завершён</span><h2>План команд готов</h2><p>Составы сравнены по выбранным приоритетам. Управление игрой пока не подключено, поэтому план остаётся рекомендацией.</p></div>
              <div className="strategy-status"><b>ПЛАН</b><span>уверенность: {strategy.confidence}</span></div>
            </div>

            <div className="strategy-team-grid">
              <article className="strategy-team-card"><span>Целевая команда · {objectiveLabels[strategy.validated_team_plan.target_objective]}</span><h2>{strategy.target_team.map(characterName).join(' · ')}</h2><p>{strategy.target_strategy_ru}</p></article>
              <article className="strategy-team-card"><span>Команда домена · {objectiveLabels[strategy.validated_team_plan.domain_objective]}</span><h2>{strategy.domain_team.map(characterName).join(' · ')}</h2><p>{strategy.domain_strategy_ru}</p></article>
            </div>

            <section className="team-evaluator-panel">
              <div className="team-evaluator-heading"><div><span className="section-kicker">Сравнение вариантов</span><h2>Почему выбраны именно эти команды</h2></div><p>Каждый состав оценён по одной шкале: урон, реакции, энергия, удобство и стабильность ротации.</p></div>
              <div className="team-evaluator-grid">
                <TeamEvaluationView report={strategy.evaluation.target} title="Целевая команда" characterName={characterName} />
                <TeamEvaluationView report={strategy.evaluation.domain} title="Команда домена" characterName={characterName} />
              </div>
            </section>

            <div className="strategy-detail-grid">
              <article><span className="section-kicker">Синергия</span><ul>{strategy.synergies_ru.map((item) => <li key={item}>{item}</li>)}</ul></article>
              <article><span className="section-kicker">Что может помешать</span>{strategy.weak_points_ru.length ? <ul>{strategy.weak_points_ru.map((item) => <li key={item}>{item}</li>)}</ul> : <p>Критических проблем не найдено.</p>}</article>
              <article><span className="section-kicker">Что улучшить</span>{strategy.recommendations_ru.length ? <ul>{strategy.recommendations_ru.map((item) => <li key={item}>{item}</li>)}</ul> : <p>Дополнительных рекомендаций нет.</p>}</article>
              {strategy.preference_handling_ru && <article className="preference-result"><span className="section-kicker">Как учтён ваш комментарий</span><p>{strategy.preference_handling_ru}</p></article>}
            </div>

            <section className="strategy-validation">
              <div><span className="section-kicker">Проверка пройдена</span><h2>Составы подходят под выбранные условия</h2>{strategy.validation.checks.map((check) => <p key={check}><span>✓</span>{check}</p>)}</div>
              <aside><small>Проверенные механики</small><b>{strategy.validation.knowledge_coverage}</b><small>Персонажей в подборе</small><b>{strategy.evidence.candidates.length}</b>{strategy.assumptions_ru.length > 0 && <><small>Что стоит учесть</small>{strategy.assumptions_ru.map((item) => <p key={item}>{item}</p>)}</>}</aside>
            </section>

            <section className={`narration-panel ${strategy.llm_audit.status}`}>
              <div className="narration-summary"><div><span className="section-kicker">Расчёт и источники · {strategy.llm_audit.backend}</span><h2>Подробности подбора</h2><p>{strategy.evidence.privacy_notice}</p></div><div className="narration-count"><b>{strategy.llm_audit.successful_calls}/{strategy.llm_audit.calls.length}</b><small>выполненных запросов</small></div></div>
              <div className="llm-totals"><span><small>Модель</small><b>{strategy.llm_audit.model}</b></span><span><small>Всего токенов</small><b>{strategy.llm_audit.total_tokens.toLocaleString('ru-RU')}</b></span><span><small>Вход / выход</small><b>{strategy.llm_audit.total_input_tokens.toLocaleString('ru-RU')} / {strategy.llm_audit.total_output_tokens.toLocaleString('ru-RU')}</b></span><span><small>Оценка стоимости</small><b>{strategy.llm_audit.estimated_cost_usd == null ? 'не рассчитана' : `$${strategy.llm_audit.estimated_cost_usd.toFixed(6)}`}</b></span></div>
              <WebResearchSources report={strategy.llm_audit} />
              <div className="call-audit-list">{strategy.llm_audit.calls.map((call, index) => <details key={`${call.purpose}-${index}`}><summary><span>{call.status === 'succeeded' ? '✓' : '!'}</span><b>{call.purpose}</b><small>{call.input_tokens} на входе · {call.output_tokens} на выходе</small></summary><div className="audit-content"><div className="response-meta"><span>Модель: {call.model}</span><span>ID ответа: {call.response_id || 'не получен'}</span></div><b>Что было отправлено</b><pre>{call.transmitted_text}</pre>{call.output_text && <><b>Полученный ответ</b><pre>{call.output_text}</pre></>}{call.error && <p className="audit-error">{call.error}</p>}</div></details>)}</div>
            </section>

            <div className="strategy-footer"><button className="primary-button" onClick={() => setView('inventory')}>Перейти к видео артефактов →</button><button className="secondary-button" onClick={() => setView('onboarding')}>Изменить ввод и построить заново</button></div>
          </section>
        )}

        {view === 'inventory' && (
          <section className="import-layout">
            <div className={`drop-card ${dragging ? 'dragging' : ''} ${busy ? 'busy' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); acceptInventoryFile(event.dataTransfer.files[0]); }}>
              <input ref={videoInputRef} type="file" accept=".mp4,.mov,.mkv,.webm,video/*" onChange={(event) => void acceptVideo(event.target.files?.[0])} hidden />
              <input ref={inputRef} type="file" accept=".json,.good,application/json" onChange={(event) => void acceptJSON(event.target.files?.[0])} hidden />
              <div className="file-glyph"><span>{videoImport ? 'SCAN' : 'VIDEO'}</span><i>{busy ? '···' : '▶'}</i></div>
              <span className="section-kicker">Предпочтительный вход · видео</span><h2>{videoImport ? videoImport.message : analysis ? 'Инвентарь уже загружен' : 'Покажите все артефакты одним видео'}</h2>
              <p>{analysis ? `${fileName}: ${analysis.inventory.artifacts} артефактов. Можно продолжить или заменить файл.` : videoImport ? 'Оставьте приложение открытым: Artiscan сам отклонит перекодирование и остановит скан на чёрном хвосте или в конце видео.' : 'Перетащите запись инвентаря сюда. Распознавание идёт локально; после проверки приложение само откроет сборку.'}</p>
              {videoImport?.status === 'scanning' && <div className="scan-checkpoints"><span><b>1</b> Transcode: <strong>No, если вопрос появился</strong></span><span><b>2</b> Чёрный хвост: <strong>Stop Scan автоматически</strong></span></div>}
              {analysis ? <div className="button-row"><button className="primary-button" onClick={() => setView('build')}>Продолжить</button><button className="secondary-button" onClick={resetImport}>Заменить</button></div> : <div className="import-actions"><button className="primary-button" onClick={() => videoInputRef.current?.click()} disabled={busy}>{busy ? 'Artiscan работает…' : 'Выбрать видео'}</button><button className="secondary-button" onClick={() => inputRef.current?.click()} disabled={busy}>У меня уже есть GOOD JSON</button></div>}
              <small>Видео: MP4, MOV, MKV или WebM · резервный вход: GOOD JSON</small>
            </div>
            <div className="process-card"><span className="section-kicker">Что происходит</span><ol><li><span>1</span><div><b>Локальный Artiscan</b><small>распознаёт запись прямо на этом компьютере</small></div></li><li><span>2</span><div><b>Проверка файла GOOD</b><small>неполный файл не загрузится</small></div></li><li><span>3</span><div><b>Готовая база сборки</b><small>после загрузки сразу покажем подходящие предметы</small></div></li></ol><div className="video-note"><span>⌁</span><div><b>Временный файл удаляется</b><small>После успеха или ошибки видео не остаётся в данных GrindLess.</small></div></div></div>
          </section>
        )}

        {view === 'build' && analysis && (
          <>
            <section className="summary-row"><article><small>Файл</small><b>{fileName}</b><span>{analysis.import_report.source} · GOOD v{analysis.import_report.version} · персонажи {analysis.import_report.characters_seen} · оружие {analysis.import_report.weapons_seen}</span></article><article><small>Артефактов</small><b>{analysis.inventory.artifacts}</b><span>{analysis.inventory.five_star_artifacts} пятизвёздочных{analysis.import_report.inactive_substats_imported ? ` · ${analysis.import_report.inactive_substats_imported} скрытых характеристик` : ''}</span></article><article className={analysis.audit.set_composition_met ? 'success-metric' : 'warning-metric'}><small>Подходящая база</small><b>{Object.keys(analysis.audit.selected_artifact_ids).length} / 5</b><span>{analysis.audit.set_composition_met ? 'комплект и свободный предмет подобраны' : 'остальные слоты начнутся пустыми'}</span></article><article className={analysis.audit.pending_slots.length || !analysis.audit.set_composition_met ? 'warning-metric' : 'success-metric'}><small>Нужно улучшить</small><b>{analysis.audit.pending_slots.length}</b><span>{analysis.audit.pending_slots.map((item) => slotLabels[item]).join(', ') || 'базовые цели закрыты'}</span></article></section>
            <section className="workspace-grid">
              <div className="build-panel">
                <div className="panel-heading"><div><span className="section-kicker">Черновая сборка</span><h2>Лучшие предметы без улучшения</h2></div><button className="text-button" onClick={resetImport}>Заменить файл</button></div>
                <div className="slot-grid">{slots.map((slot) => { const candidate = selectedCandidate(analysis, slot); const pending = analysis.audit.pending_slots.includes(slot); return <button key={slot} className={`artifact-card ${selectedSlot === slot ? 'selected' : ''} ${pending ? 'pending' : 'complete'}`} onClick={() => setSelectedSlot(slot)}><div className="artifact-head"><span>{slotGlyphs[slot]}</span><small>{pending ? 'цель открыта' : 'цель закрыта'}</small></div><h3>{slotLabels[slot]}</h3>{candidate ? <><b>{label(candidate.main_stat)}</b><p>{candidate.matched_substats.slice(0, 3).map(label).join(' · ') || 'нет полезных дополнительных характеристик'}</p><footer><span>#{candidate.source_index ?? '—'}</span><strong>{candidate.useful_substat_count}/{candidate.observed_substat_count}</strong></footer></> : <p>Подходящий предмет не найден</p>}</button>; })}</div>
                <div className="conflict-note"><span>✦</span><div><b>Это черновая сборка</b><p>На следующем шаге GrindLess учтёт команду, оружие и пожелания, а затем ещё раз проверит все пять слотов.</p></div></div>
              </div>
              <aside className="details-panel">
                <span className="section-kicker">Почему выбран предмет</span><h2>{slotLabels[selectedSlot]}</h2>
                {selected ? <><div className="candidate-number">Артефакт #{selected.source_index ?? '—'} <span>{selected.set_name}</span></div><dl><div><dt>Главная характеристика</dt><dd>{label(selected.main_stat)}</dd></div><div><dt>Полезных дополнительных</dt><dd>{selected.useful_substat_count} из {selected.observed_substat_count}</dd></div><div><dt>Оценка</dt><dd>{selected.content_score}</dd></div></dl><div className="substat-list">{selected.substats.map((item) => <span key={item} className={selected.matched_substats.includes(item) ? 'matched' : ''}>{label(item)}</span>)}</div><p className={`verdict ${selected.closes_goal ? 'good' : ''}`}><b>{selected.closes_goal ? 'Предмет закрывает стартовую цель.' : 'Это временный лучший вариант.'}</b>Сейчас сравниваем главную характеристику и состав дополнительных.</p></> : <p>В этом слоте нет подходящего кандидата.</p>}
                <label className="strategy-preferences artifact-preferences"><span>Пожелания к сборке — необязательно</span><textarea value={artifactPreferences} maxLength={2000} placeholder="Например: сначала собрать стабильную сборку" onChange={(event) => setArtifactPreferences(event.target.value)} /></label>
                <StrategicModelPicker status={llmStatus} backend={llmBackend} effort={reasoningEffort} onBackend={setLLMBackend} onEffort={setReasoningEffort} />
                <button className="primary-button full" onClick={() => void runArtifactGoalStrategy()} disabled={busy || !isStrategicBackend}>{busy ? 'Подбираем сборку…' : 'Подобрать сборку →'}</button>
                <button className="secondary-button full" onClick={() => { setArtifactGoal(null); setRotation(null); setView('rotation'); }}>Использовать базовый профиль</button>
              </aside>
            </section>
          </>
        )}

        {view === 'artifact-plan' && artifactGoal && (
          <section className="artifact-plan-page">
            <div className="strategy-hero artifact-plan-hero">
              <div><span className="section-kicker">План сборки</span><h2>{artifactGoal.draft.build_role_ru}</h2><p>{artifactGoal.draft.farming_plan_ru}</p></div>
              <div className="strategy-status"><b>ГОТОВО</b><span>уверенность: {artifactGoal.draft.confidence}</span></div>
            </div>

            <div className="artifact-plan-metrics">
              <article><small>Композиция сетов</small><b>{artifactCompositionLabel(artifactGoal)}</b><span>off-piece: {offPieceLabel(artifactGoal)}</span></article>
              <article><small>Оружие из GOOD</small><b>{artifactGoal.evidence.target.weapon_key || 'не распознано'}</b><span>{artifactGoal.evidence.target.weapon_level ? `ур. ${artifactGoal.evidence.target.weapon_level} · R${artifactGoal.evidence.target.weapon_refinement || 1}` : 'название не указано'}</span></article>
              <article><small>Инвентарь</small><b>{artifactGoal.evidence.inventory_artifact_count}</b><span>использована краткая сводка без полного файла</span></article>
              <article className={artifactGoal.inventory_audit.pending_slots.length || !artifactGoal.inventory_audit.set_composition_met ? 'warning-metric' : 'success-metric'}><small>Открыто целей</small><b>{artifactGoal.inventory_audit.pending_slots.length}</b><span>{!artifactGoal.inventory_audit.set_composition_met ? 'симуляция достроит сет с пустой базы' : artifactGoal.inventory_audit.pending_slots.map((slot) => slotLabels[slot]).join(', ') || 'все базовые цели закрыты'}</span></article>
            </div>

            <div className="artifact-goal-grid">
              {artifactGoal.draft.slot_priority_order.map((slot, index) => {
                const goal = artifactGoal.draft.slots.find((item) => item.slot === slot);
                const candidate = selectedAuditCandidate(artifactGoal.inventory_audit, slot);
                const pending = artifactGoal.inventory_audit.pending_slots.includes(slot);
                return <article key={slot} className={pending ? 'pending' : 'complete'}><header><i>{slotGlyphs[slot]}</i><span>приоритет {index + 1}</span></header><h3>{slotLabels[slot]}</h3><b>{goal?.allowed_main_stats.map(label).join(' / ')}</b><p>{goal?.rationale_ru}</p><footer>{candidate ? `База: #${candidate.source_index ?? '—'} · ${label(candidate.main_stat)}` : 'Подходящей базы нет'}</footer></article>;
              })}
            </div>

            <div className="artifact-plan-detail-grid">
              <article><span className="section-kicker">Дополнительные характеристики</span><ol>{artifactGoal.draft.substat_priority_order.map((stat, index) => <li key={stat}><b>{index + 1}</b>{label(stat)}</li>)}</ol></article>
              <article><span className="section-kicker">Альтернатива артефактам</span><p>{artifactGoal.draft.alternative_upgrade_ru}</p><small>Позже здесь появится сравнение с оружием и талантами.</small></article>
              <article><span className="section-kicker">Что стоит учесть</span>{artifactGoal.evidence.knowledge_limitations.map((item) => <p key={item}>{item}</p>)}{artifactGoal.draft.assumptions_ru.map((item) => <p key={item}>{item}</p>)}</article>
              {artifactGoal.draft.preference_handling_ru && <article className="preference-result"><span className="section-kicker">Как учтён ваш комментарий</span><p>{artifactGoal.draft.preference_handling_ru}</p></article>}
            </div>

            <section className="strategy-validation artifact-validation"><div><span className="section-kicker">Проверка пройдена</span><h2>Сборка готова к симуляции</h2>{artifactGoal.validation.checks.map((check) => <p key={check}><span>✓</span>{check}</p>)}</div><aside><small>Сравнение</small><b>по характеристикам</b><small>Свободный предмет</small><b>подобран локально</b><small>Статус</small><b>готово</b></aside></section>

            <section className={`narration-panel ${artifactGoal.llm_audit.status}`}>
              <div className="narration-summary"><div><span className="section-kicker">Расчёт и источники · {artifactGoal.llm_audit.backend}</span><h2>Подробности подбора</h2><p>{artifactGoal.evidence.privacy_notice}</p></div><div className="narration-count"><b>{artifactGoal.llm_audit.successful_calls}/{artifactGoal.llm_audit.calls.length}</b><small>выполненных запросов</small></div></div>
              <div className="llm-totals"><span><small>Модель</small><b>{artifactGoal.llm_audit.model}</b></span><span><small>Всего токенов</small><b>{artifactGoal.llm_audit.total_tokens.toLocaleString('ru-RU')}</b></span><span><small>Вход / выход</small><b>{artifactGoal.llm_audit.total_input_tokens.toLocaleString('ru-RU')} / {artifactGoal.llm_audit.total_output_tokens.toLocaleString('ru-RU')}</b></span><span><small>Оценка стоимости</small><b>{artifactGoal.llm_audit.estimated_cost_usd == null ? 'не рассчитана' : `$${artifactGoal.llm_audit.estimated_cost_usd.toFixed(6)}`}</b></span></div>
              <WebResearchSources report={artifactGoal.llm_audit} />
              <div className="call-audit-list">{artifactGoal.llm_audit.calls.map((call, index) => <details key={`${call.purpose}-${index}`}><summary><span>{call.status === 'succeeded' ? '✓' : '!'}</span><b>{call.purpose}</b><small>{call.input_tokens} на входе · {call.output_tokens} на выходе</small></summary><div className="audit-content"><b>Что было отправлено</b><pre>{call.transmitted_text}</pre>{call.output_text && <><b>Полученный ответ</b><pre>{call.output_text}</pre></>}{call.error && <p className="audit-error">{call.error}</p>}</div></details>)}</div>
            </section>

            <div className="strategy-footer"><button className="primary-button" onClick={() => setView('rotation')}>Построить ротацию →</button><button className="secondary-button" onClick={() => setView('build')}>Изменить пожелания и построить заново</button></div>
          </section>
        )}

        {view === 'rotation' && analysis && (
          <section className="rotation-page">
            {!rotation ? <>
              <div className="strategy-hero rotation-hero">
                <div><span className="section-kicker">Ротация команды</span><h2>Настроим порядок навыков и атак</h2><p>GrindLess подберёт последовательность действий и запасной вариант на случай, если ульта не готова. Пока это только план без управления игрой.</p></div>
                <div className="strategy-status"><b>ПЛАН</b><span>без управления</span></div>
              </div>
              <div className="rotation-setup-grid">
                <article><span className="section-kicker">Команда домена</span><h3>{(teamPlan?.domain_team || teamIntent.target_team).map(characterName).join(' · ')}</h3><p>Используем выбранный состав без замен.</p></article>
                <article><span className="section-kicker">Контекст сборки</span><h3>{artifactGoal ? artifactCompositionLabel(artifactGoal) : 'Базовый профиль'}</h3><p>{artifactGoal ? 'Учитываем общие цели сборки. Полный файл GOOD и список артефактов не отправляются.' : 'Используем состав из Enka и базовые цели персонажа.'}</p></article>
                <article><span className="section-kicker">Управление игрой</span><h3>Пока выключено</h3><p>Если следующий шаг нельзя определить уверенно, сессия остановится.</p></article>
              </div>
              <section className="rotation-launch">
                <label className="strategy-preferences"><span>Пожелания к ротации — необязательно</span><textarea value={rotationPreferences} maxLength={2000} placeholder="Например: безопасный цикл, без сложных отмен анимаций" onChange={(event) => setRotationPreferences(event.target.value)} /></label>
                <div className="rotation-boundary"><b>Используем свежие гайды</b><span>Перед составлением ротации GrindLess проверит навыки, реакции, энергию и актуальные примеры командных циклов.</span></div>
                <StrategicModelPicker status={llmStatus} backend={llmBackend} effort={reasoningEffort} onBackend={setLLMBackend} onEffort={setReasoningEffort} />
                <div className="strategy-actions"><button className="primary-button" disabled={busy || !isStrategicBackend} onClick={() => void runRotationStrategy()}>{busy ? 'Составляем ротацию…' : 'Составить ротацию →'}</button><button className="secondary-button" onClick={() => setView('goals')}>Продолжить без ротации</button></div>
              </section>
            </> : <>
              <div className="strategy-hero rotation-hero">
                <div><span className="section-kicker">Ротация готова</span><h2>{rotation.draft.opening_ru}</h2><p>{rotation.draft.rationale_ru}</p></div>
                <div className="strategy-status"><b>ПЛАН</b><span>уверенность: {rotation.draft.confidence}</span></div>
              </div>

              <div className="rotation-metrics">
                <article><small>Шагов в ротации</small><b>{rotation.draft.steps.length}</b><span>навыки и атаки</span></article>
                <article><small>Состояний</small><b>{rotation.validated_rotation.states.length}</b><span>включая запасные переходы</span></article>
                <article><small>Запасных вариантов</small><b>{rotation.draft.burst_fallbacks.length}</b><span>для каждой ульты</span></article>
                <article><small>Управление</small><b>выкл.</b><span>игра не управляется</span></article>
              </div>

              <div className="rotation-sequence">
                {rotation.draft.steps.map((step, index) => {
                  const fallback = rotation.draft.burst_fallbacks.find((item) => item.at_step === index + 1);
                  return <article key={`${index}-${step.character_key}-${step.action}`}><span className="rotation-index">{index + 1}</span><div><small>{characterName(step.character_key)}</small><h3>{actionLabels[step.action]}{step.repetitions > 1 ? ` × ${step.repetitions}` : ''}</h3><p>{step.purpose_ru}</p>{fallback && <footer><b>Если ульта не готова:</b> {fallback.response.replaceAll('_', ' ')} · {fallback.rationale_ru}</footer>}</div><i>→</i></article>;
                })}
              </div>

              <div className="rotation-detail-grid">
                <article><span className="section-kicker">Условия остановки</span>{rotation.draft.stop_conditions_ru.map((item) => <p key={item}>{item}</p>)}</article>
                <article><span className="section-kicker">Что стоит учесть</span>{rotation.draft.assumptions_ru.map((item) => <p key={item}>{item}</p>)}</article>
                <article><span className="section-kicker">Что нужно перепроверить</span>{rotation.evidence.knowledge_limitations.map((item) => <p key={item}>{item}</p>)}</article>
                {rotation.draft.preference_handling_ru && <article className="preference-result"><span className="section-kicker">Как учтён ваш комментарий</span><p>{rotation.draft.preference_handling_ru}</p></article>}
              </div>

              <section className="strategy-validation rotation-validation"><div><span className="section-kicker">Проверка пройдена</span><h2>Ротация собрана, управление выключено</h2>{rotation.validation.checks.map((check) => <p key={check}><span>✓</span>{check}</p>)}</div><aside><small>Покрытие знаний</small><b>{rotation.validation.knowledge_coverage}</b><small>Энергия / тайминги</small><b>{rotation.validation.energy_status} / {rotation.validation.timing_status}</b><small>ID плана</small><code>{rotation.validated_rotation.plan_fingerprint.slice(0, 16)}…</code></aside></section>

              <section className={`narration-panel ${rotation.llm_audit.status}`}>
                <div className="narration-summary"><div><span className="section-kicker">Расчёт и источники · {rotation.llm_audit.backend}</span><h2>Подробности ротации</h2><p>{rotation.evidence.privacy_notice}</p></div><div className="narration-count"><b>{rotation.llm_audit.successful_calls}/{rotation.llm_audit.calls.length}</b><small>выполненных запросов</small></div></div>
                <div className="llm-totals"><span><small>Модель</small><b>{rotation.llm_audit.model}</b></span><span><small>Всего токенов</small><b>{rotation.llm_audit.total_tokens.toLocaleString('ru-RU')}</b></span><span><small>Вход / выход</small><b>{rotation.llm_audit.total_input_tokens.toLocaleString('ru-RU')} / {rotation.llm_audit.total_output_tokens.toLocaleString('ru-RU')}</b></span><span><small>Оценка стоимости</small><b>{rotation.llm_audit.estimated_cost_usd == null ? 'не рассчитана' : `$${rotation.llm_audit.estimated_cost_usd.toFixed(6)}`}</b></span></div>
                <WebResearchSources report={rotation.llm_audit} />
                <div className="call-audit-list">{rotation.llm_audit.calls.map((call, index) => <details key={`${call.purpose}-${index}`}><summary><span>{call.status === 'succeeded' ? '✓' : '!'}</span><b>{call.purpose}</b><small>{call.input_tokens} на входе · {call.output_tokens} на выходе</small></summary><div className="audit-content"><b>Что было отправлено</b><pre>{call.transmitted_text}</pre>{call.output_text && <><b>Полученный ответ</b><pre>{call.output_text}</pre></>}{call.error && <p className="audit-error">{call.error}</p>}</div></details>)}</div>
              </section>

              <div className="strategy-footer"><button className="primary-button" onClick={() => setView('goals')}>Выбрать слоты и смолу →</button><button className="secondary-button" onClick={() => { setRotation(null); setView('rotation'); }}>Изменить пожелания и построить заново</button></div>
            </>}
          </section>
        )}

        {view === 'goals' && analysis && (
          <section className="goal-layout">
            <div className="goal-main">
              <div className="panel-heading"><div><span className="section-kicker">Шаг 3 · цель</span><h2>Выберите слоты для улучшения</h2></div><span className="selection-count">{targetSlots.length} выбрано</span></div>
              <p className="lead-copy">За отправную точку берём лучшие подходящие предметы с прошлого экрана. Если нужного предмета или полного комплекта ещё нет, слот останется пустым до первого подходящего дропа. Улучшение артефактов внутри симуляции выключено.</p>
              <div className="target-grid">{slots.map((slot) => { const goal = activeGoals.find((item) => item.slot === slot); const candidate = artifactGoal ? selectedAuditCandidate(artifactGoal.inventory_audit, slot) : selectedCandidate(analysis, slot); const active = targetSlots.includes(slot); return <button key={slot} className={`target-card ${active ? 'selected' : ''}`} onClick={() => toggleTarget(slot)}><span className="check">{active ? '✓' : ''}</span><div className="target-title"><i>{slotGlyphs[slot]}</i><div><b>{slotLabels[slot]}</b><small>База: {candidate ? label(candidate.main_stat) : 'нет предмета'}</small></div></div><dl><div><dt>Главная характеристика</dt><dd>{goal?.allowed_main_stats.map(label).join(' / ')}</dd></div><div><dt>Минимум</dt><dd>{goal?.min_useful_substats} полезных дополнительных</dd></div></dl></button>; })}</div>
              <div className="decision-rule"><span>STOP</span><div><b>{policy === 'economy' ? 'Когда остановимся' : 'Почему не остановимся раньше'}</b><p>{policy === 'economy' ? 'После очередной награды, если для каждого выбранного слота уже найден первый предмет лучше замороженной базы. Следующий потенциальный дроп может быть сильнее, поэтому экономию смолы выбирает пользователь заранее.' : `Проведём все ${maxRuns} получений награды и только затем выберем лучшие предметы. Ранний хороший дроп не сокращает сессию.`}</p></div></div>
              <div className="future-gate"><span>Следующий этап</span><b>Если заметное улучшение маловероятно, переключиться на оружие или талант</b><p>Позже GrindLess сможет сравнивать эти варианты автоматически. Для этого ещё нужно откалибровать вероятность дропа и прирост от гарантированных улучшений.</p></div>
            </div>
            <aside className="control-panel">
              <span className="section-kicker">Параметры сессии</span><h2>Как тратить смолу?</h2>
              <div className="segmented"><button className={policy === 'economy' ? 'active' : ''} onClick={() => setPolicy('economy')}>Экономить</button><button className={policy === 'spend_all' ? 'active' : ''} onClick={() => setPolicy('spend_all')}>Весь бюджет</button></div>
              <p className="control-explain">{policy === 'economy' ? 'Одна проверка после каждого получения награды; ранняя остановка разрешена.' : 'Дроп накапливается без проверки; один пакетный анализ в конце.'}</p>
              <label className="range-label"><span><b>Бюджет смолы</b><strong>{resinBudget}</strong></span><input type="range" min="20" max="200" step="20" value={resinBudget} onChange={(event) => setResinBudget(Number(event.target.value))} /><small>{maxRuns} × 20 смолы = максимум {maxRuns} получений награды</small></label>
              <label className="seed-field"><span>Вариант симуляции</span><input type="number" min="0" max="2147483647" value={seed} onChange={(event) => setSeed(Math.max(0, Number(event.target.value) || 0))} /></label>
              <div className="model-picker">
                <div className="model-heading"><span>Формат объяснения</span><small>На расчёты это не влияет</small></div>
                {llmStatus?.backends.map((backend) => (
                  <button
                    key={backend.backend}
                    className={`model-option ${llmBackend === backend.backend ? 'active' : ''}`}
                    disabled={!backend.configured}
                    onClick={() => setLLMBackend(backend.backend)}
                    title={backend.reason || undefined}
                  >
                    <span>{backend.backend === 'offline' ? 'LOCAL' : backend.backend.startsWith('openai_') ? 'API' : 'GPU'}</span>
                    <div><b>{backend.label}</b><small>{backend.configured ? (backend.model || backend.reason) : backend.reason}</small></div>
                  </button>
                ))}
                {llmStatus && <p className="quota-line">Локальный лимит: {llmStatus.quota.used_today}/{llmStatus.quota.daily_limit} сегодня · {llmStatus.quota.used_this_month}/{llmStatus.quota.monthly_limit} в месяце</p>}
              </div>
              <div className="call-budget"><small>Проверки результата</small><b>до {projectedCheckpoints}</b><p>{policy === 'economy' ? `${maxRuns} возможных проверок награды и одно итоговое объяснение.` : 'Одно итоговое объяснение после всей сессии.'} {llmBackend === 'offline' ? 'Внешние сервисы не используются.' : 'Каждая выполненная проверка учитывается в лимите; подробности появятся в журнале.'}</p></div>
              <div className="no-rolls"><span>⊘</span><p><b>Без улучшения до +20</b>Артефакты оцениваются на том уровне, на котором были получены.</p></div>
              <button className="primary-button full" disabled={busy || !targetSlots.length} onClick={() => void runSimulation()}>{busy ? 'Запускаем сессию…' : 'Запустить симуляцию →'}</button>
            </aside>
          </section>
        )}

        {view === 'simulation' && simulation && (
          <section className="simulation-layout">
            <div className="result-hero"><div><span className="section-kicker">Результат · вариант {simulation.seed}</span><h2>{reasonLabels[simulation.result.reason]?.title}</h2><p>{reasonLabels[simulation.result.reason]?.text}</p><small className="simulation-plan-source">Сборка: {simulation.artifact_goal_source === 'llm' ? 'персональный план' : 'базовый профиль'} · ротация: {simulation.rotation_plan_source === 'llm' ? 'учтена в плане' : 'не задана'} · стартовая база: {Object.keys(simulation.baseline_artifact_ids).length}/5</small></div><div className="result-badge">СТОП</div></div>
            <div className="result-metrics"><article><small>Получений награды</small><b>{simulation.result.runs}</b><span>из {simulation.resin_budget / simulation.reward_cost} возможных</span></article><article><small>Потрачено смолы</small><b>{simulation.result.resin_spent}</b><span>осталось {simulation.result.resin_remaining}</span></article><article><small>Проверок результата</small><b>{simulation.result.model_checkpoints}</b><span>{simulation.checkpoint_strategy === 'after_each_reward' ? 'после каждой награды и в конце' : 'одна итоговая проверка'}</span></article><article><small>Закрыто целей</small><b>{simulation.result.slot_progress.filter((item) => item.accepted).length}/{simulation.target_slots.length}</b><span>{simulation.result.slot_progress.filter((item) => !item.accepted).map((item) => slotLabels[item.slot]).join(', ') || 'все выбранные слоты'}</span></article></div>
            <section className={`narration-panel ${simulation.narration.status}`}>
              <div className="narration-summary"><div><span className="section-kicker">Подробности объяснения · {simulation.narration.backend}</span><h2>{simulation.narration.status === 'offline' ? 'Локальное объяснение' : simulation.narration.status === 'succeeded' ? 'Объяснение готово' : 'Показано стандартное объяснение'}</h2><p>{simulation.narration.external_data_sent ? 'Для объяснения отправлен журнал сессии. Полный файл GOOD остался на компьютере.' : 'Все расчёты и данные остались на этом компьютере.'}</p></div><div className="narration-count"><b>{simulation.narration.successful_calls}/{simulation.narration.successful_calls + simulation.narration.failed_calls}</b><small>успешных запросов</small></div></div>
              {simulation.narration.calls.length > 0 && <div className="llm-totals"><span><small>Модель</small><b>{simulation.narration.model}</b></span><span><small>Всего токенов</small><b>{(simulation.narration.total_tokens ?? simulation.narration.calls.reduce((sum, call) => sum + call.input_tokens + call.output_tokens, 0)).toLocaleString('ru-RU')}</b></span><span><small>Вход / выход</small><b>{(simulation.narration.total_input_tokens ?? simulation.narration.calls.reduce((sum, call) => sum + call.input_tokens, 0)).toLocaleString('ru-RU')} / {(simulation.narration.total_output_tokens ?? simulation.narration.calls.reduce((sum, call) => sum + call.output_tokens, 0)).toLocaleString('ru-RU')}</b></span><span><small>Оценка стоимости</small><b>{simulation.narration.estimated_cost_usd == null ? 'не рассчитана' : `$${simulation.narration.estimated_cost_usd.toFixed(6)}`}</b></span></div>}
              {simulation.narration.calls.length > 0 && <div className="call-audit-list">{simulation.narration.calls.map((call, index) => <details key={`${call.purpose}-${index}`}><summary><span>{call.status === 'succeeded' ? '✓' : '!'}</span><b>{call.purpose}</b><small>{call.input_tokens} на входе · {call.output_tokens} на выходе</small></summary><div className="audit-content"><div className="response-meta"><span>Модель: {call.model}</span><span>ID ответа: {call.response_id || 'не получен'}</span><span>Стоимость: {call.estimated_cost_usd == null ? 'не рассчитана' : `$${call.estimated_cost_usd.toFixed(6)}`}</span></div><b>Что было отправлено</b><pre>{call.transmitted_text}</pre>{call.output_text && <><b>Полученный ответ</b><p>{call.output_text}</p></>}{call.error && <p className="audit-error">{call.error}</p>}</div></details>)}</div>}
              <footer>Способ объяснения не влияет на оценку предметов и условие остановки. Стоимость показывается только для моделей с указанными тарифами. Использовано сегодня: {simulation.quota.used_today} из {simulation.quota.daily_limit} запросов.</footer>
            </section>
            <div className="result-grid"><div className="timeline-panel"><div className="panel-heading"><div><span className="section-kicker">Награды и решения</span><h2>Журнал сессии</h2></div><span className="sim-label">Учебная симуляция</span></div><div className="run-timeline">{simulation.runs.map((run) => <article className={`run-card ${run.stop_here ? 'last' : ''}`} key={run.run}><div className="run-marker"><span>{run.run}</span><i /></div><div className="run-body"><header><div><b>Получение награды #{run.run}</b><small>{run.resin_spent_total} потрачено · {run.resin_remaining} осталось</small></div><em className={run.analyzed ? 'analyzed' : ''}>{run.analyzed ? 'проверено' : 'отложено'}</em></header><div className="drop-list">{run.artifacts.map((artifact) => <div className={`drop-item ${artifact.promising ? 'promising' : ''}`} key={artifact.artifact_id}><span className="drop-slot">{slotGlyphs[artifact.slot]}</span><div><b>{slotLabels[artifact.slot]} · {label(artifact.main_stat)}</b><small>{artifact.set_name}</small><p>{artifact.substats.map(label).join(' · ')}</p></div><strong>{artifact.promising ? (artifact.baseline_eligible ? 'Лучше базы' : 'Первый подходящий') : artifact.relevant ? 'Цель не закрыта' : 'Вне цели'}</strong></div>)}</div>{run.analyzed && <footer>{run.accepted_slots_after.length ? <>Закрыты: {run.accepted_slots_after.map((slot) => slotLabels[slot]).join(', ')}</> : <>Ни один выбранный слот пока не закрыт</>}</footer>}{!run.analyzed && <footer>Проверка отложена до конца выбранного бюджета</footer>}</div></article>)}</div></div>
              <aside className="decision-panel"><span className="section-kicker">Итог по выбранным слотам</span><h2>Сравнение с базой</h2><div className="progress-list">{simulation.result.slot_progress.map((item) => <article className={item.accepted ? 'accepted' : ''} key={item.slot}><span>{item.accepted ? '✓' : '·'}</span><div><b>{slotLabels[item.slot]}</b><small>{item.baseline_artifact_id == null ? 'пустой слот' : `оценка базы ${item.baseline_content_score}`} → {item.best_artifact_id == null ? 'кандидата нет' : item.candidate_content_score}</small><p>{item.accepted ? `Полезные дополнительные: ${item.matched_substats.map(label).join(', ')}` : 'Подходящего улучшения не выпало.'}</p></div></article>)}</div><div className="truth-note"><b>Что используется в расчёте</b><p>Стартовая база, выбранные критерии и правило остановки берутся из вашего плана. Награды в этом режиме генерируются для учебной симуляции.</p></div><div className="button-stack"><button className="primary-button full" onClick={() => void runSimulation(seed + 1)} disabled={busy || !payloadRef.current}>{busy ? 'Новый прогон…' : payloadRef.current ? 'Повторить с другим вариантом' : 'Для повтора загрузите GOOD'}</button><button className="secondary-button full" onClick={() => analysis ? setView('goals') : setView('inventory')}>{analysis ? 'Изменить цели' : 'Загрузить инвентарь'}</button></div></aside>
            </div>
          </section>
        )}

        {view === 'history' && (
          <section className="history-panel">
            <div className="panel-heading"><div><span className="section-kicker">SQLite · только этот компьютер</span><h2>Последние сессии</h2></div><span className="selection-count">{sessions.length} сохранено</span></div>
            <p className="lead-copy">Хранятся результаты, цели, журнал объяснений и расход смолы. Исходный GOOD-инвентарь и API-ключ в историю не записываются.</p>
            {sessions.length ? <div className="history-list">{sessions.map((item) => <button key={item.session_id} onClick={() => void openSession(item.session_id)} disabled={busy}><span className={`history-backend ${item.backend}`}>{item.backend === 'offline' ? 'LOCAL' : item.backend === 'openai_luna' ? 'LUNA' : 'QWEN'}</span><div><b>{reasonLabels[item.reason]?.title || item.reason}</b><small>{new Date(item.created_at).toLocaleString('ru-RU')} · вариант {item.seed} · {item.target_slots.map((slot) => slotLabels[slot]).join(', ')}</small></div><strong>{item.resin_spent} смолы</strong></button>)}</div> : <div className="empty-history"><span>◇</span><h3>История пока пустая</h3><p>После первой симуляции здесь появятся результат и выбранные настройки.</p></div>}
          </section>
        )}

        {view === 'control' && (
          <section className="control-readiness">
            <div className="readiness-main">
              <div className="panel-heading"><div><span className="section-kicker">Проверка Linux</span><h2>{gameAdapter?.status === 'ready' ? 'Окно игры готово к наблюдению' : 'Проверка окружения'}</h2></div><span className={`readiness-badge ${gameAdapter?.status || 'unknown'}`}>{gameAdapter?.status || 'нет связи'}</span></div>
              <p className="lead-copy">GrindLess видит окно Genshin через Wine. Сейчас маршрут проходит человек, а приложение только сверяет семь экранов и записывает результат. Автономная навигация и бой пока не подключены. Приложение не читает память игры и не перехватывает трафик, но риск санкций за автоматизацию всё равно остаётся.</p>
              <div className="readiness-list">
                {gameAdapter?.checks.map((check) => <article className={check.ok ? 'passed' : check.required ? 'blocked' : 'notice'} key={check.code}><span>{check.ok ? '✓' : check.required ? '!' : '·'}</span><div><b>{adapterCheckLabels[check.code] || check.code.replaceAll('_', ' ')}</b><p>{check.message}</p></div></article>)}
                {!gameAdapter && <article className="blocked"><span>!</span><div><b>Локальный сервис</b><p>Запустите приложение GrindLess.</p></div></article>}
              </div>
              {gameAdapter && <div className="next-action"><small>Что сделать дальше</small><b>{gameAdapter.next_action}</b></div>}
              <div className="next-action"><small>Проверка без управления</small><b>Откалибруйте 7 состояний командой grindless-linux-game --record-state, затем запустите --shadow-run.</b></div>
            </div>
            <aside className="readiness-aside">
              <span className="section-kicker">Настройки теста</span><h2>Текущее окружение</h2>
              <dl><div><dt>Система</dt><dd>Linux · X11</dd></div><div><dt>Запуск игры</dt><dd>An Anime Game Launcher</dd></div><div><dt>Режим</dt><dd>Безрамочный</dd></div><div><dt>Размер окна</dt><dd>1920 × 1080</dd></div><div><dt>Язык игры</dt><dd>English</dd></div><div><dt>Управление</dt><dd>{gameAdapter?.input_enabled ? 'явно разрешено' : 'выключено'}</dd></div></dl>
              <div className="safety-boundary"><b>Ввод по умолчанию выключен</b><p>Сначала проверяется изображение и окно. Разрешение на мышь и клавиатуру включается отдельно только для наблюдаемого теста.</p></div>
              <div className="emergency-list"><span>Аварийная остановка</span><p>Переместить курсор в левый верхний угол или создать файл <code>~/.grindless/STOP_GAME_INPUT</code>.</p></div>
            </aside>
          </section>
        )}

        {error && <div className="error-toast" role="alert"><b>Не получилось продолжить</b><span>{error}</span><button aria-label="Закрыть сообщение" onClick={() => setError('')}>×</button></div>}
      </main>
    </div>
  );
}

export default App;
