// Settings: where your AI requests get their key.
import { useState, type FormEvent } from 'react'
import { clearAiKey, loadAiKey, saveAiKey, type AiKey } from '../lib/aiKey'
import { useAuth } from '../lib/auth'

const field = 'w-full mt-1 text-sm p-2 rounded-lg border border-slate-200 bg-white'

export default function Settings() {
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Settings</h1>
      <AiSection />
    </div>
  )
}

function AiSection() {
  const { me } = useAuth()
  if (!me) return null

  // Local mode and the owner use the server's key from backend/.env; nothing to set here.
  if (me.provider === 'local' || me.ai_enabled) {
    return (
      <section className="card space-y-1">
        <h2 className="font-medium">🤖 AI</h2>
        <p className="text-sm text-slate-500">
          {me.ai_enabled
            ? "AI features use this server's key (backend/.env)."
            : 'AI features are off. Set LLM_PROVIDER and a key in backend/.env to turn them on.'}
        </p>
      </section>
    )
  }
  return <KeyForm />
}

const EMPTY: AiKey = { provider: 'openai', key: '', baseUrl: '', model: '' }

function KeyForm() {
  const [form, setForm] = useState<AiKey>(() => loadAiKey() ?? EMPTY)
  const [saved, setSaved] = useState(() => loadAiKey() !== null)
  const [note, setNote] = useState('')

  const set = (patch: Partial<AiKey>) => { setForm((f) => ({ ...f, ...patch })); setNote('') }

  const save = (e: FormEvent) => {
    e.preventDefault()
    const ok = saveAiKey({ ...form, key: form.key.trim(), model: form.model.trim(),
                           baseUrl: form.baseUrl.trim() })
    setSaved(ok)
    setNote(ok ? 'Saved in this browser.' : "This browser won't let the page save it (private window?).")
  }

  const remove = () => {
    clearAiKey()
    setForm({ ...EMPTY, provider: form.provider })
    setSaved(false)
    setNote('Removed from this browser.')
  }

  return (
    <section className="card space-y-4">
      <div>
        <h2 className="font-medium">🤖 Your AI key</h2>
        <p className="text-sm text-slate-500">
          Complexity checks and mock interviews run on your own API key, so you pay your
          provider directly.
        </p>
      </div>
      <p className="text-sm rounded-lg border border-slate-200 bg-slate-50 p-3">
        🔒 Your key is saved in this browser only. It's sent with each AI request and passed
        through to the provider; our server never stores or logs it.
      </p>

      <form onSubmit={save} className="space-y-3 max-w-md">
        <label className="block text-sm">
          Provider
          <select value={form.provider} className={field}
                  onChange={(e) => set({ provider: e.target.value as AiKey['provider'] })}>
            <option value="openai">OpenAI-compatible (DeepSeek, OpenAI, OpenRouter …)</option>
            <option value="anthropic">Anthropic (Claude)</option>
          </select>
        </label>
        {form.provider === 'openai' && (
          <label className="block text-sm">
            Base URL <span className="text-slate-400">(blank = DeepSeek)</span>
            <input type="url" value={form.baseUrl} placeholder="https://api.deepseek.com"
                   onChange={(e) => set({ baseUrl: e.target.value })} className={field} />
          </label>
        )}
        <label className="block text-sm">
          Model
          <input required value={form.model} spellCheck={false}
                 placeholder={form.provider === 'openai' ? 'deepseek-chat' : 'claude-sonnet-5-5'}
                 onChange={(e) => set({ model: e.target.value })} className={field} />
        </label>
        <label className="block text-sm">
          API key
          <input required type="password" value={form.key} autoComplete="off" spellCheck={false}
                 onChange={(e) => set({ key: e.target.value })} className={field} />
        </label>
        <div className="flex items-center gap-2">
          <button type="submit" className="btn btn-primary">Save</button>
          {saved && <button type="button" onClick={remove} className="btn">Remove key</button>}
          {note && <span className="text-sm text-slate-500">{note}</span>}
        </div>
      </form>
    </section>
  )
}
