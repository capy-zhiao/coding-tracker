// Mirrors the backend's schemas.py. TypeScript types exist only at compile time —
// their job is to let the editor catch typos in field names before you run anything.

export type Grade = 'again' | 'hard' | 'good' | 'easy'
export type Difficulty = 'Easy' | 'Medium' | 'Hard'

/** The signed-in user (in local mode, the one local user) and deployment facts. */
export interface Me {
  id: number
  login: string
  display_name: string
  avatar_url: string
  provider: 'local' | 'github' | 'demo'
  is_owner: boolean
  is_demo: boolean
  ai_enabled: boolean
  timezone: string | null
  daily_review_cap: number
  daily_new_cap: number
  auth_mode: 'local' | 'github'
  today: string
}

export interface ReviewStateT {
  interval_days: number
  ease: number
  reps: number
  lapses: number
  due: string | null
  total_attempts: number
  best_seconds: number | null
}

export interface Problem {
  id: number
  number: number
  title: string
  difficulty: Difficulty
  chapter_num: number
  chapter: string
  url: string
  in_neetcode150: boolean
  in_top150: boolean
  in_lc75: boolean
  kind: 'problem' | 'template'
  patterns: string[]
  state: ReviewStateT | null
}

export interface ProblemDetail extends Problem {
  notes: string
  code: string
}

export interface QueueItem {
  problem: Problem
  reason: 'due' | 'new' | 'template'
  priority_score: number
  overdue_days: number
}

export interface DailyQueue {
  date: string
  reviews: QueueItem[]
  new_problems: QueueItem[]
  templates: QueueItem[]
  total_due: number
  deferred: number
  review_cap: number
}


export interface AttemptIn {
  grade: Grade
  seconds: number
  looked_at_solution: boolean
  had_bugs: boolean
  code: string
  note: string
  mode: 'practice' | 'mock' | 'drill'
  time_complexity: string
  space_complexity: string
  blindwrite_score?: number | null
}

export interface Attempt {
  id: number
  problem_id: number
  created_at: string
  grade: Grade
  seconds: number
  note: string
  mode: string
  code: string
  time_complexity: string
  space_complexity: string
  complexity_ok: boolean | null
  complexity_ai: ComplexityVerdict | null
}

/** The LLM's analysis of the code actually submitted (backend llm.ComplexityVerdict). */
export interface ComplexityVerdict {
  actual_time: string
  actual_space: string
  time_correct: boolean
  space_correct: boolean
  why_wrong?: string        // only when an answer is wrong
  optimal_time: string
  optimal_space: string
  time_optimal?: boolean
  space_optimal?: boolean
  optimal_how?: string      // only when time or space is not optimal
  optimized_code?: string   // validated rewrite of the submitted code; "" when already optimal
  optimized_diff?: string[] // unified diff: submitted code -> optimized
  model?: string            // which model judged it
  // Verdicts stored before the four-part layout
  explanation?: string
  is_optimal?: boolean
}

export interface ComplexityCheck {
  graded: boolean
  time_ok: boolean
  space_ok: boolean
  expected_time: string
  expected_space: string
  accepted_time: string[]
  accepted_space: string[]
}

export interface AttemptResult {
  attempt: Attempt
  state: ReviewStateT
  next_due_in_days: number
  complexity: ComplexityCheck | null
}

export interface ChapterStat {
  chapter_num: number; chapter: string
  total: number; started: number; mastered: number
}

export interface Stats {
  total_problems: number; started: number; mastered: number
  due_today: number; attempts_total: number; attempts_7d: number
  streak_days: number; avg_seconds: number
  by_chapter: ChapterStat[]
}

export interface FollowUp { id: number; question: string; hint: string }
export interface MockStart { problem: ProblemDetail; minutes: number; followups_ready: boolean }

// --- template blind-write drills ---

export interface TemplateSummary {
  number: number
  title: string
  chapter: string
  check_count: number
  state: ReviewStateT | null
}

export interface BlindWriteCheck {
  id: string
  label: string
  why: string
  passed: boolean
}

export interface BlindWriteResult {
  number: number
  name: string
  passed: boolean
  similarity: number
  checks: BlindWriteCheck[]
  missing: string[]
  diff: string[]
  verdict: string
  suggested_grade: Grade
  reference: string
}

// --- pattern proficiency ---

export interface PatternStat {
  id: string
  label: string
  description: string
  total: number
  started: number
  mastered: number
  attempts: number
  avg_seconds: number
  again_rate: number
  weakness: number
  template_number: number | null
}

export interface ComplexityStats {
  answered: number
  graded: number
  time_correct: number
  space_correct: number
  both_correct: number
  accuracy: number
  worst: { number: number; title: string; wrong: number; attempts: number }[]
}

// --- code-aware mock interview ---

export interface InterviewQuestion { id: number; question: string }

export interface AnswerGrade {
  id: number
  question: string
  answer: string
  key_points: string
  score: 1 | 2 | 3 | 4          // weak · partial · good · strong
  feedback: string
  missing: string[]
  model_answer: string
}

/** Remaining API credit reported by the LLM provider (GET /stats/credit). */
export interface Credit {
  source: 'relay' | 'deepseek'
  currency: string
  granted: number | null
  used: number | null
  available: number
  unlimited: boolean
  expires_at: number        // unix seconds, 0 = never
}
