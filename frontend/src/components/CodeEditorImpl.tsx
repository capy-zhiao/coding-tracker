// Monaco (the editor behind VS Code) in place of a bare <textarea>.
//
// Loaded lazily through CodeEditor.tsx — Monaco is ~3 MB, and Today / Patterns / Stats
// never need it, so it must not sit in the entry chunk.
//
// The textarea was the single biggest daily friction point: Enter returned the caret to
// column 0, so every line of Python needed its indentation typed by hand, and Tab moved
// focus out of the field entirely. Monaco gives auto-indent, bracket matching and syntax
// highlighting, and lets us bind Cmd/Ctrl+Enter to submit from inside the editor — a
// document-level key handler never sees keys Monaco has swallowed.
import Editor, { type BeforeMount, type OnMount } from '@monaco-editor/react'
import { useRef } from 'react'
import '../lib/monaco-setup'
import { useTheme } from '../lib/theme'

// Tokyo Night and Tokyo Night Day, to match the rest of the app
const defineThemes: BeforeMount = (monaco) => {
  monaco.editor.defineTheme('tokyo-night', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'comment', foreground: '565f89', fontStyle: 'italic' },
      { token: 'keyword', foreground: 'bb9af7' },
      { token: 'string', foreground: '9ece6a' },
      { token: 'number', foreground: 'ff9e64' },
      { token: 'type', foreground: '2ac3de' },
      { token: 'delimiter', foreground: '89ddff' },
      { token: 'identifier', foreground: 'c0caf5' },
    ],
    colors: {
      'editor.background': '#1a1b26',
      'editor.foreground': '#c0caf5',
      'editorLineNumber.foreground': '#3b4261',
      'editorLineNumber.activeForeground': '#737aa2',
      'editor.lineHighlightBackground': '#1e2030',
      'editor.selectionBackground': '#364a8288',
      'editorCursor.foreground': '#c0caf5',
      'editorIndentGuide.background1': '#292e42',
      'editorBracketMatch.background': '#3d59a155',
      'editorBracketMatch.border': '#7aa2f7',
    },
  })
  monaco.editor.defineTheme('tokyo-day', {
    base: 'vs',
    inherit: true,
    rules: [
      { token: 'comment', foreground: '848cb5', fontStyle: 'italic' },
      { token: 'keyword', foreground: '9854f1' },
      { token: 'string', foreground: '587539' },
      { token: 'number', foreground: 'b15c00' },
      { token: 'type', foreground: '007197' },
      { token: 'delimiter', foreground: '006a83' },
      { token: 'identifier', foreground: '3760bf' },
    ],
    colors: {
      'editor.background': '#f6f7fb',
      'editor.foreground': '#3760bf',
      'editorLineNumber.foreground': '#a8aecb',
      'editorLineNumber.activeForeground': '#68709a',
      'editor.lineHighlightBackground': '#eceef5',
      'editor.selectionBackground': '#b7c1e3aa',
      'editorCursor.foreground': '#3760bf',
    },
  })
}

interface Props {
  value: string
  onChange: (v: string) => void
  onSubmit?: () => void          // bound to Cmd/Ctrl+Enter inside the editor
  height?: number
  language?: string
  readOnly?: boolean
  /** Shown over an empty editor, since Monaco has no placeholder of its own. */
  placeholder?: string
}

export default function CodeEditor({
  value, onChange, onSubmit, height = 320,
  language = 'python', readOnly = false, placeholder,
}: Props) {
  // A ref, not state: changing it must not re-render (that would remount the editor).
  const submitRef = useRef(onSubmit)
  submitRef.current = onSubmit
  const theme = useTheme()

  const handleMount: OnMount = (editor, monaco) => {
    editor.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter,
      () => submitRef.current?.(),
    )
    if (!readOnly) editor.focus()
    // Monaco measures glyphs once; measure again when the web font has arrived
    document.fonts?.ready.then(() => monaco.editor.remeasureFonts())
  }

  return (
    <div className="relative rounded-lg border border-slate-200 overflow-hidden">
      <Editor
        height={height}
        language={language}
        theme={theme === 'dark' ? 'tokyo-night' : 'tokyo-day'}
        beforeMount={defineThemes}
        value={value}
        onChange={(v) => onChange(v ?? '')}
        onMount={handleMount}
        loading={<div className="p-4 text-sm text-slate-400">Loading editor…</div>}
        options={{
          readOnly,
          fontSize: 13,
          fontFamily: '"JetBrains Mono Variable", ui-monospace, SFMono-Regular, Menlo, monospace',
          fontLigatures: true,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          lineNumbers: 'on',
          tabSize: 4,
          insertSpaces: true,
          automaticLayout: true,       // re-measure when the pane resizes
          renderWhitespace: 'selection',
          padding: { top: 10, bottom: 10 },
          scrollbar: { alwaysConsumeMouseWheel: false },
          overviewRulerLanes: 0,
          folding: false,
        }}
      />
      {placeholder && !value && (
        <div className="pointer-events-none absolute top-[10px] left-[60px] text-sm
                        text-slate-400 font-mono">
          {placeholder}
        </div>
      )}
    </div>
  )
}
