// Single place every network call goes through, so error handling lives in one spot and
// swapping the base URL is a one-file change. Requests are same-origin (the dev proxy
// locally, Caddy in production), so a session cookie rides along without any CORS setup.
import type {
  AnswerGrade, Attempt, AttemptIn, AttemptResult, BlindWriteResult, Credit,
  ComplexityStats, DailyQueue, FollowUp, InterviewQuestion, Me, MockStart,
  PatternStat, Problem, ProblemDetail, Stats, TemplateSummary,
} from './types'
import { aiHeaders } from './aiKey'

// vite.config.ts proxies /api/* to http://localhost:8000/* during development
const BASE = '/api'

/** A failed request, with its HTTP status so callers can tell "signed out" from "broken". */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })
  if (!res.ok) {
    // The session ended (expired or signed out elsewhere): the app swaps to the login page
    if (res.status === 401) window.dispatchEvent(new Event('auth:expired'))
    const detail = await res.json().catch(() => ({}))
    throw new ApiError(detail.detail ?? `Request failed (${res.status})`, res.status)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const qs = (params: Record<string, unknown>) => {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (Array.isArray(v)) v.forEach((x) => p.append(k, String(x)))   // ?skip=1&skip=2
    else if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  })
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  health: () => request<{ status: string; llm_enabled: boolean; llm_provider: string }>('/health'),
  me: () => request<Me>('/auth/me'),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  // null puts a setting back to the server's default
  updateMe: (body: { timezone?: string | null; daily_review_cap?: number | null;
                     daily_new_cap?: number | null }) =>
    request<Me>('/auth/me', { method: 'PATCH', body: JSON.stringify(body) }),

  // --- daily queue and attempts ---
  today: (opts?: { review_cap?: number; new_cap?: number; shuffle?: number; skip?: number[] }) =>
    request<DailyQueue>(`/review/today${qs(opts ?? {})}`),
  forecast: (days = 14) =>
    request<{ date: string; count: number; overdue: number }[]>(`/review/forecast${qs({ days })}`),
  suggestGrade: (p: { seconds: number; looked_at_solution: boolean; had_bugs: boolean; difficulty: string }) =>
    request<{ grade: string; reason: string }>(`/review/suggest-grade${qs(p)}`),
  submitAttempt: (number: number, body: AttemptIn) =>
    request<AttemptResult>(`/review/${number}/attempt`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  attempts: (number: number) => request<Attempt[]>(`/review/${number}/attempts`),
  complexityChoices: () => request<string[]>('/review/complexity-choices'),
  // Slow on purpose-built models with thinking on (can take tens of seconds)
  aiComplexity: (attemptId: number) =>
    request<Attempt>(`/review/attempts/${attemptId}/complexity-ai`,
                     { method: 'POST', headers: aiHeaders() }),

  // --- problem library ---
  problems: (f?: { chapter?: number; difficulty?: string; status?: string; q?: string;
                   pattern?: string; kind?: string }) =>
    request<Problem[]>(`/problems${qs(f ?? {})}`),
  problem: (number: number) => request<ProblemDetail>(`/problems/${number}`),
  updateProblem: (number: number, body: { notes?: string; code?: string }) =>
    request<ProblemDetail>(`/problems/${number}`, { method: 'PATCH', body: JSON.stringify(body) }),

  // --- template blind-write drills ---
  templates: () => request<TemplateSummary[]>('/templates'),
  checkBlindWrite: (number: number, code: string) =>
    request<BlindWriteResult>(`/templates/${number}/check`, {
      method: 'POST', body: JSON.stringify({ code }),
    }),
  templateReference: (number: number) =>
    request<{ number: number; name: string; reference: string }>(`/templates/${number}/reference`),

  // --- stats ---
  stats: () => request<Stats>('/stats'),
  patterns: () => request<PatternStat[]>('/stats/patterns'),
  complexityStats: () => request<ComplexityStats>('/stats/complexity'),
  credit: (refresh = false) => request<Credit>(`/stats/credit${qs({ refresh: refresh || undefined })}`),
  heatmap: (days = 90) => request<{ date: string; count: number }[]>(`/stats/heatmap${qs({ days })}`),

  // --- mock interview ---
  mockStart: (f?: { difficulty?: string; chapter?: number; only_solved?: boolean }) =>
    request<MockStart>(`/mock/start${qs(f ?? {})}`, { method: 'POST', headers: aiHeaders() }),
  followups: (number: number, regenerate = false) =>
    request<FollowUp[]>(`/mock/${number}/followups${qs({ regenerate })}`,
                        { headers: aiHeaders() }),
  // Questions about the code written in this session; answers graded one by one
  startInterview: (number: number, body: { code: string; time_complexity: string; space_complexity: string }) =>
    request<InterviewQuestion[]>(`/mock/${number}/interview`, {
      method: 'POST', body: JSON.stringify(body), headers: aiHeaders(),
    }),
  answerQuestion: (qaId: number, answer: string) =>
    request<AnswerGrade>(`/mock/qa/${qaId}/answer`, {
      method: 'POST', body: JSON.stringify({ answer }), headers: aiHeaders(),
    }),
}
