// Mock interview: random problem, countdown, then interviewer follow-ups.
//
// With an LLM configured and code written, the follow-ups are about THAT code, and each
// written answer is graded. Otherwise it falls back to per-problem questions with key
// points to self-check against.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bot, Lightbulb, Mic, MicOff } from 'lucide-react'
import SectionTitle from '../components/SectionTitle'
import CodeEditor from '../components/CodeEditor'
import Timer, { useTimer } from '../components/Timer'
import { useAiAvailable } from '../lib/aiKey'
import { api } from '../lib/api'
import type { AnswerGrade, FollowUp, InterviewQuestion, MockStart } from '../lib/types'

export default function Mock() {
  const [session, setSession] = useState<MockStart | null>(null)
  const [followups, setFollowups] = useState<FollowUp[]>([])
  const [phase, setPhase] = useState<'idle' | 'solving' | 'followup'>('idle')
  const [difficulty, setDifficulty] = useState('')
  const [onlySolved, setOnlySolved] = useState(false)
  const [answered, setAnswered] = useState<number[]>([])
  const [code, setCode] = useState('')
  // Asked before the follow-ups, because that is the order a real interview uses.
  const [timeComplexity, setTimeComplexity] = useState('')
  const [spaceComplexity, setSpaceComplexity] = useState('')
  const [loading, setLoading] = useState(false)
  const aiEnabled = useAiAvailable()
  const [questions, setQuestions] = useState<InterviewQuestion[]>([])
  const [interviewNote, setInterviewNote] = useState('')
  const timer = useTimer()


  const start = async () => {
    setLoading(true)
    try {
      const s = await api.mockStart({ difficulty: difficulty || undefined, only_solved: onlySolved })
      setSession(s); setFollowups([]); setAnswered([]); setQuestions([]); setPhase('solving')
      setInterviewNote('')
      setCode(''); setTimeComplexity(''); setSpaceComplexity('')
      timer.reset(); timer.start()
    } catch (e) { alert((e as Error).message) } finally { setLoading(false) }
  }

  const toFollowup = async () => {
    timer.pause(); setPhase('followup'); setLoading(true)
    const number = session!.problem.number
    try {
      if (aiEnabled && code.trim()) {
        try {
          setQuestions(await api.startInterview(number, {
            code, time_complexity: timeComplexity, space_complexity: spaceComplexity,
          }))
          return
        } catch (e) {
          // Never strand the interview: fall back to the per-problem questions
          setInterviewNote(`Couldn't generate questions about your code (${(e as Error).message}) — using general ones.`)
        }
      } else if (aiEnabled) {
        setInterviewNote('No code written, so these are general questions about the problem.')
      }
      setFollowups(await api.followups(number))
    } finally { setLoading(false) }
  }

  // A real interview doesn't show you your own notes, so this page deliberately hides them.
  if (phase === 'idle') {
    return (
      <div className="card space-y-4 max-w-lg">
        <div>
          <SectionTitle as="h1" icon={Mic} tone="rose" className="text-lg font-semibold">Mock interview</SectionTitle>
          <p className="text-sm text-slate-500 mt-1">
            Random problem, a clock, and no notes. Follow-ups come after — that is where
            real interviews are won or lost.
          </p>
          {aiEnabled && (
            <p className="text-sm text-indigo-700 mt-1">
              <Bot size={14} className="inline -mt-0.5 mr-1" />The interviewer reads the code you write and asks about it. Answer each
              question in writing and it gets graded.
            </p>
          )}
        </div>
        <div className="flex gap-2 items-center">
          <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)} className="btn">
            <option value="">Any difficulty</option>
            <option>Easy</option><option>Medium</option><option>Hard</option>
          </select>
          <label className="text-sm flex items-center gap-1.5">
            <input type="checkbox" checked={onlySolved} onChange={(e) => setOnlySolved(e.target.checked)} />
            only problems I've solved (practise explaining)
          </label>
        </div>
        <button className="btn btn-primary w-full" onClick={start} disabled={loading}>
          {loading ? 'Drawing a problem…' : 'Start interview'}
        </button>
      </div>
    )
  }

  const p = session!.problem
  return (
    <div className="space-y-4">
      <div className="card flex items-center gap-4">
        <div className="flex-1">
          <h1 className="text-lg font-semibold">{p.number}. {p.title}</h1>
          <p className="text-sm text-slate-500">{p.difficulty} · {p.chapter}</p>
        </div>
        <Timer running={timer.running} seconds={timer.seconds}
               onTick={timer.onTick} limitMinutes={session!.minutes} />
      </div>

      {phase === 'solving' && (
        <div className="card space-y-3">
          <p className="text-sm text-slate-500">
            <MicOff size={14} className="inline -mt-0.5 mr-1" />Interview mode: notes and past solutions are hidden. Talk through the approach
            first, then code, then state the complexity.
          </p>
          {p.url && <a href={p.url} target="_blank" rel="noreferrer" className="btn inline-block">
            Open the problem ↗
          </a>}
          <CodeEditor value={code} onChange={setCode} onSubmit={toFollowup} height={300}
                      placeholder="Code it here, under the clock…" />
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-xs text-slate-500">Time complexity</span>
              <input value={timeComplexity} onChange={(e) => setTimeComplexity(e.target.value)}
                     placeholder="O(n log n)" spellCheck={false}
                     className="w-full mt-0.5 text-sm font-mono p-2 rounded-lg border border-slate-200" />
            </label>
            <label className="block">
              <span className="text-xs text-slate-500">Space complexity</span>
              <input value={spaceComplexity} onChange={(e) => setSpaceComplexity(e.target.value)}
                     placeholder="O(1)" spellCheck={false}
                     className="w-full mt-0.5 text-sm font-mono p-2 rounded-lg border border-slate-200" />
            </label>
          </div>
          <button className="btn btn-primary w-full" onClick={toFollowup}>
            Done coding — go to follow-ups →
          </button>
        </div>
      )}

      {phase === 'followup' && (
        <div className="card space-y-3">
          <h2 className="font-medium">
            Interviewer follow-ups
            {questions.length > 0 && <span className="text-xs text-slate-400 ml-2">about your code · answer in writing, AI grades each one</span>}
          </h2>
          {loading && (
            <p className="text-sm text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-lg p-3 thinking">
              <Bot size={14} className="inline -mt-0.5 mr-1.5" />
              {aiEnabled && code.trim()
                ? 'The interviewer is reading your code… this can take about a minute.'
                : 'Loading questions…'}
            </p>
          )}
          {interviewNote && <p className="text-xs text-slate-500">{interviewNote}</p>}

          {questions.map((q, i) => <QuestionCard key={q.id} q={q} index={i} />)}

          {questions.length === 0 && followups.map((f, i) => {
            const open = answered.includes(f.id)
            return (
              <div key={f.id} className="rounded-lg border border-slate-200 p-3">
                <p className="font-medium text-sm">Q{i + 1}. {f.question}</p>
                {open
                  ? <p className="mt-2 text-sm text-slate-600 bg-slate-50 rounded p-2"><Lightbulb size={14} className="inline -mt-0.5 mr-1 text-amber-500" />{f.hint}</p>
                  : <button className="btn text-xs mt-2"
                            onClick={() => setAnswered([...answered, f.id])}>
                      I've answered — show the key points
                    </button>}
              </div>
            )
          })}
          <div className="flex gap-2">
            {/* Carry the session through so the solve page starts from what you just wrote */}
            <Link
              to={`/solve/${p.number}`}
              state={{ code, timeComplexity, spaceComplexity, fromMock: true }}
              className="btn flex-1 text-center"
            >
              Record this attempt
            </Link>
            <button className="btn flex-1" onClick={() => { setPhase('idle'); setSession(null) }}>
              Another one
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

const SCORE: Record<number, { label: string; tone: string }> = {
  4: { label: 'Strong',  tone: 'bg-emerald-100 text-emerald-800' },
  3: { label: 'Good',    tone: 'bg-sky-100 text-sky-800' },
  2: { label: 'Partial', tone: 'bg-amber-100 text-amber-800' },
  1: { label: 'Weak',    tone: 'bg-rose-100 text-rose-800' },
}

/** One question: its own answer box and grading state, so several can be graded at once. */
function QuestionCard({ q, index }: { q: InterviewQuestion; index: number }) {
  const [answer, setAnswer] = useState('')
  const [grading, setGrading] = useState(false)
  const [grade, setGrade] = useState<AnswerGrade | null>(null)
  const [error, setError] = useState('')

  const submit = async () => {
    if (!answer.trim() || grading) return
    setGrading(true); setError('')
    try { setGrade(await api.answerQuestion(q.id, answer)) }
    catch (e) { setError((e as Error).message) }
    finally { setGrading(false) }
  }

  const s = grade ? SCORE[grade.score] : null
  return (
    <div className="rounded-lg border border-slate-200 p-3 space-y-2">
      <p className="font-medium text-sm">Q{index + 1}. {q.question}</p>
      <textarea
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') submit() }}
        disabled={grading}
        rows={3}
        placeholder="Answer as you would out loud — in English, for practice"
        className="w-full text-sm p-2 rounded-lg border border-slate-200 disabled:bg-slate-50"
      />
      <div className="flex items-center gap-2">
        <button className="btn btn-primary text-xs" onClick={submit} disabled={grading || !answer.trim()}>
          {grading ? 'Grading…' : grade ? 'Answer again' : 'Submit answer'}
          {!grading && <kbd className="ml-1 text-[10px] opacity-60">⌘↵</kbd>}
        </button>
        {grading && <span className="text-xs text-slate-400">the interviewer is thinking — you can answer the next one meanwhile</span>}
        {error && <span className="text-xs text-red-600">{error}</span>}
      </div>

      {grade && s && (
        <div className="rounded-lg bg-slate-50 p-3 text-sm space-y-2">
          <div className="flex items-baseline gap-2">
            <span className={`chip ${s.tone}`}>{s.label} · {grade.score}/4</span>
            <span className="text-slate-700">{grade.feedback}</span>
          </div>
          {grade.missing.length > 0 && (
            <div>
              <p className="text-xs font-medium text-slate-500">Missed</p>
              <ul className="list-disc list-inside text-slate-700 space-y-0.5">
                {grade.missing.map((m, k) => <li key={k}>{m}</li>)}
              </ul>
            </div>
          )}
          <details>
            <summary className="text-xs text-slate-500 cursor-pointer">Model answer and key points</summary>
            <p className="mt-1 text-slate-700">{grade.model_answer}</p>
            <p className="mt-1 text-xs text-slate-500"><Lightbulb size={12} className="inline -mt-0.5 mr-1 text-amber-500" />{grade.key_points}</p>
          </details>
        </div>
      )}
    </div>
  )
}
