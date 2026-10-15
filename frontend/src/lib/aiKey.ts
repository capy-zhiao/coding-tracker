// Your own AI key, for accounts that don't use the server's (everyone but the owner).
// It lives in this browser's localStorage until you remove it, and goes out only with AI
// requests; the server passes it to the provider and never stores or logs it.
import { useEffect, useState } from 'react'
import { useAuth } from './auth'

export interface AiKey {
  provider: 'openai' | 'anthropic'    // openai = any OpenAI-compatible API (DeepSeek, ...)
  key: string
  baseUrl: string                     // OpenAI-compatible only; blank = DeepSeek's
  model: string
}

const STORAGE = 'ai-key'
const CHANGED = 'ai-key:changed'

export function loadAiKey(): AiKey | null {
  try {
    const k = JSON.parse(localStorage.getItem(STORAGE) ?? 'null')
    return k && typeof k.key === 'string' && k.key ? k : null
  } catch {
    return null                       // storage blocked (private window): no saved key
  }
}

export function saveAiKey(k: AiKey): boolean {
  try {
    localStorage.setItem(STORAGE, JSON.stringify(k))
  } catch {
    return false
  }
  window.dispatchEvent(new Event(CHANGED))
  return true
}

export function clearAiKey() {
  try { localStorage.removeItem(STORAGE) } catch { /* nothing saved */ }
  window.dispatchEvent(new Event(CHANGED))
}

/** Headers for an AI request: the saved key, or nothing (then the server decides). */
export function aiHeaders(): Record<string, string> {
  const k = loadAiKey()
  if (!k) return {}
  const h: Record<string, string> = {
    'X-LLM-Provider': k.provider, 'X-LLM-Key': k.key, 'X-LLM-Model': k.model,
  }
  if (k.provider === 'openai' && k.baseUrl) h['X-LLM-Base-URL'] = k.baseUrl
  return h
}

/** Whether AI features can run for you: the server's key (owner) or one saved here. */
export function useAiAvailable(): boolean {
  const { me } = useAuth()
  const [hasKey, setHasKey] = useState(() => loadAiKey() !== null)
  useEffect(() => {
    const update = () => setHasKey(loadAiKey() !== null)
    window.addEventListener(CHANGED, update)
    return () => window.removeEventListener(CHANGED, update)
  }, [])
  return Boolean(me?.ai_enabled) || hasKey
}
