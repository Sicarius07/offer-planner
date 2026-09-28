import type {
  AdvertiserProfile, CampaignConfig, ClarifyingQuestion, Creative, PersonaPlan, PlanEvent,
  PublisherPlan, StageName, StageStatus, StageTrace,
} from "@/api/types"

export const STAGES: { key: StageName; label: string }[] = [
  { key: "understand", label: "Brief" },
  { key: "publishers", label: "Where to run" },
  { key: "personas", label: "Who to reach" },
  { key: "creative", label: "What to say" },
  { key: "campaign", label: "Campaign" },
]

export type StageState = { status: StageStatus | "idle"; ms?: number | null }

export type PlanState = {
  status: "idle" | "running" | "done"
  source: "live" | "cached" | null
  brief: string
  stages: Record<StageName, StageState>
  profile: AdvertiserProfile | null
  needsInput: { reason: string; questions: ClarifyingQuestion[] } | null
  publishers: PublisherPlan | null
  personas: PersonaPlan | null
  creatives: Record<string, Creative>
  config: CampaignConfig | null
  errors: { stage: string; message: string; retryable: boolean }[]
  run: { id: string; totalMs: number; costUsd: number; trace: StageTrace[] } | null
}

const idleStages = () =>
  Object.fromEntries(STAGES.map((s) => [s.key, { status: "idle" }])) as Record<StageName, StageState>

export const initialPlan: PlanState = {
  status: "idle",
  source: null,
  brief: "",
  stages: idleStages(),
  profile: null,
  needsInput: null,
  publishers: null,
  personas: null,
  creatives: {},
  config: null,
  errors: [],
  run: null,
}

export type Action =
  | { type: "start"; brief: string; source: "live" | "cached" }
  | { type: "event"; event: PlanEvent }
  | { type: "fail"; message: string }
  | { type: "reset" }

export function reducer(state: PlanState, action: Action): PlanState {
  switch (action.type) {
    case "start":
      return { ...initialPlan, stages: idleStages(), status: "running", brief: action.brief, source: action.source }
    case "reset":
      return initialPlan
    case "fail":
      return {
        ...state,
        status: "done",
        errors: [...state.errors, { stage: "run", message: action.message, retryable: true }],
      }
    case "event":
      return applyEvent(state, action.event)
  }
}

function applyEvent(s: PlanState, e: PlanEvent): PlanState {
  switch (e.type) {
    case "stage":
      return { ...s, stages: { ...s.stages, [e.stage]: { status: e.status, ms: e.ms } } }
    case "profile":
      return { ...s, profile: e.profile }
    case "needs_input":
      return { ...s, needsInput: { reason: e.reason, questions: e.questions } }
    case "publishers":
      return { ...s, publishers: e.plan }
    case "personas":
      return { ...s, personas: e.plan }
    case "creative":
      return { ...s, creatives: { ...s.creatives, [e.creative.persona_id]: e.creative } }
    case "config":
      return { ...s, config: e.config }
    case "error":
      return { ...s, errors: [...s.errors, { stage: e.stage, message: e.message, retryable: e.retryable ?? true }] }
    case "done":
      return {
        ...s,
        status: "done",
        run: { id: e.run_id, totalMs: e.total_ms, costUsd: e.cost_usd, trace: e.trace },
      }
  }
}
