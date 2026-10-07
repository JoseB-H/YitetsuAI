import { useEffect, useState, type FormEvent } from 'react'
import './App.css'

type AuthMode = 'register' | 'login'
type MessageRole = 'user' | 'assistant'

type User = {
  user_id: string
  email: string
  full_name: string
}

type Conversation = {
  conversation_id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

type Source = { attachment_id: string; filename: string; locator: string; excerpt: string }
type Attachment = { attachment_id: string; conversation_id: string; filename: string; kind: string; size_bytes: number; warnings: string[] }

type Message = {
  sources?: Source[]
  message_id?: string
  role: MessageRole
  content: string
  created_at?: string
}

type PromptCorrection = {
  original: string
  corrected: string
}

type AICapability = {
  id: string
  name: string
  function: string
  implementation: string
  availability: string
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001'

const samplePrompts = [
  '¿Cómo mejorar la experiencia de onboarding sin reemplazar al equipo?',
  '¿Qué pasos seguir para implementar IA de forma responsable en una empresa?',
  '¿Qué métricas debe revisar un equipo antes de escalar una solución de IA?',
]

function isCapabilityList(value: unknown): value is { components: AICapability[] } {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('components' in value) ||
    !Array.isArray(value.components)
  ) {
    return false
  }
  return value.components.every(
    (component: unknown) =>
      typeof component === 'object' &&
      component !== null &&
      'id' in component &&
      typeof component.id === 'string' &&
      'name' in component &&
      typeof component.name === 'string' &&
      'function' in component &&
      typeof component.function === 'string' &&
      'implementation' in component &&
      typeof component.implementation === 'string' &&
      'availability' in component &&
      typeof component.availability === 'string',
  )
}

async function fetchAICapabilities(): Promise<AICapability[]> {
  const response = await fetch(`${API_BASE}/ai/capabilities`)
  const data: unknown = await response.json()
  if (!response.ok) {
    throw new Error('No se pudieron cargar los componentes de IA')
  }
  if (!isCapabilityList(data)) {
    throw new Error('La API devolvió una lista de componentes de IA inválida')
  }
  return data.components
}

function App() {
  const [authMode, setAuthMode] = useState<AuthMode>('register')
  const [token, setToken] = useState<string | null>(localStorage.getItem('yitetsuai_token'))
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState('Conectando con la API...')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [registerForm, setRegisterForm] = useState({ email: '', password: '', full_name: '' })
  const [loginForm, setLoginForm] = useState({ email: '', password: '' })
  const [chatPrompt, setChatPrompt] = useState(samplePrompts[0])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [interpretation, setInterpretation] = useState<{
    prompt: string
    corrections: PromptCorrection[]
  } | null>(null)

  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [selectedAttachments, setSelectedAttachments] = useState<string[]>([])
  const [aiCapabilities, setAiCapabilities] = useState<AICapability[]>([])
  const [capabilityError, setCapabilityError] = useState('')

  useEffect(() => {
    let active = true
    setAttachments([]); setSelectedAttachments([])
    if (token && activeConversationId) fetchJson<Attachment[]>(`${API_BASE}/attachments?conversation_id=${activeConversationId}`)
      .then(items => { if (active) { setAttachments(items); setSelectedAttachments(items.map(item => item.attachment_id)) } })
      .catch(err => { if (active) setError(String(err.message)) })
    return () => { active = false }
  }, [token, activeConversationId])

  const fetchJson = async <T,>(url: string, options: RequestInit = {}): Promise<T> => {
    const headers = new Headers(options.headers)
    if (!(options.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`)

    const response = await fetch(url, { ...options, headers })
    const data: unknown = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail =
        typeof data === 'object' && data !== null && 'detail' in data
          ? String(data.detail)
          : 'La petición falló'
      throw new Error(detail)
    }
    return data as T
  }

  const setAuthToken = (newToken: string | null) => {
    setToken(newToken)
    if (newToken) {
      localStorage.setItem('yitetsuai_token', newToken)
    } else {
      localStorage.removeItem('yitetsuai_token')
      setUser(null)
      setConversations([])
      setActiveConversationId(null)
      setMessages([])
      setInterpretation(null)
    }
  }

  useEffect(() => {
    let mounted = true
    fetchJson<{ status: string }>(`${API_BASE}/health`)
      .then((data) => {
        if (mounted) setStatus(`API conectada: ${data.status}`)
      })
      .catch(() => {
        if (mounted) setStatus(`La API no responde en ${API_BASE}`)
      })
    return () => {
      mounted = false
    }
  }, [])

  useEffect(() => {
    let mounted = true
    fetchAICapabilities()
      .then(setAiCapabilities)
      .catch((requestError: unknown) => {
        if (mounted) {
          setCapabilityError(
            requestError instanceof Error
              ? requestError.message
              : 'No se pudieron cargar los componentes de IA',
          )
        }
      })
    return () => {
      mounted = false
    }
  }, [])

  useEffect(() => {
    let mounted = true
    if (!token) {
      setUser(null)
      setConversations([])
      setActiveConversationId(null)
      setMessages([])
      setInterpretation(null)
      return
    }

    Promise.all([
      fetchJson<User>(`${API_BASE}/users/me`),
      fetchJson<Conversation[]>(`${API_BASE}/conversations`),
    ])
      .then(([currentUser, history]) => {
        if (!mounted) return
        setUser(currentUser)
        setConversations(history)
      })
      .catch((requestError: unknown) => {
        if (!mounted) return
        setAuthToken(null)
        setError(requestError instanceof Error ? requestError.message : 'No se pudo cargar la sesión')
      })
    return () => {
      mounted = false
    }
  }, [token])

  const handleRegister = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await fetchJson<User & { token: string }>(`${API_BASE}/auth/register`, {
        method: 'POST',
        body: JSON.stringify(registerForm),
      })
      setAuthToken(data.token)
      setUser(data)
      setRegisterForm({ email: '', password: '', full_name: '' })
      setStatus(`Registro exitoso para ${data.email}`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'No se pudo registrar')
    } finally {
      setLoading(false)
    }
  }

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await fetchJson<User & { token: string }>(`${API_BASE}/auth/login`, {
        method: 'POST',
        body: JSON.stringify(loginForm),
      })
      setAuthToken(data.token)
      setUser(data)
      setLoginForm({ email: '', password: '' })
      setStatus(`Sesión iniciada para ${data.email}`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Credenciales inválidas')
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = async () => {
    setError('')
    setLoading(true)
    try {
      await fetchJson<{ status: string }>(`${API_BASE}/auth/logout`, { method: 'POST' })
      setAuthToken(null)
      setStatus('Sesión cerrada')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'No se pudo cerrar la sesión')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateConversation = async () => {
    setError('')
    setLoading(true)
    try {
      const created = await fetchJson<{
        conversation_id: string
        title: string
        created_at: string
      }>(`${API_BASE}/conversations`, {
        method: 'POST',
        body: JSON.stringify({ title: 'Nueva conversación' }),
      })
      setConversations((current) => [
        {
          ...created,
          updated_at: created.created_at,
          message_count: 0,
        },
        ...current,
      ])
      setActiveConversationId(created.conversation_id)
      setMessages([])
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'No se pudo crear la conversación')
    } finally {
      setLoading(false)
    }
  }

  const handleSelectConversation = async (conversationId: string) => {
    setError('')
    setLoading(true)
    setInterpretation(null)
    try {
      const history = await fetchJson<Message[]>(
        `${API_BASE}/conversations/${conversationId}/messages`,
      )
      setActiveConversationId(conversationId)
      setMessages(history)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'No se pudo cargar el historial')
    } finally {
      setLoading(false)
    }
  }

  const handleFiles = async (files: FileList | null) => {
    if (!files?.length || !token) return
    setLoading(true); setError('')
    let conversationId = activeConversationId
    const uploaded: Attachment[] = []
    const failures: string[] = []
    try {
      for (const file of Array.from(files)) {
        setStatus(`Extrayendo ${file.name}…`)
        const form = new FormData(); form.append('file', file)
        if (conversationId) form.append('conversation_id', conversationId)
        try {
          const item = await fetchJson<Attachment>(`${API_BASE}/attachments`, { method: 'POST', body: form })
          conversationId = item.conversation_id; uploaded.push(item)
        } catch (err) { failures.push(`${file.name}: ${err instanceof Error ? err.message : 'Error de extracción'}`) }
      }
      if (conversationId !== activeConversationId) {
        setMessages([]); setActiveConversationId(conversationId)
      } else {
        setAttachments(current => [...current, ...uploaded])
        setSelectedAttachments(current => [...current, ...uploaded.map(item => item.attachment_id)])
      }
      setConversations(await fetchJson<Conversation[]>(`${API_BASE}/conversations`))
      setStatus(`${uploaded.length} adjunto(s) procesado(s)`)
      setError(failures.join(' · '))
    } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo actualizar el historial') }
    finally { setLoading(false) }
  }

  const removeAttachment = async (id: string) => {
    setLoading(true); setError('')
    try {
      await fetchJson(`${API_BASE}/attachments/${id}`, { method: 'DELETE' })
      setAttachments(current => current.filter(item => item.attachment_id !== id))
      setSelectedAttachments(current => current.filter(value => value !== id))
    } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo eliminar') }
    finally { setLoading(false) }
  }

  const downloadAttachment = async (item: Attachment) => {
    try {
      const response = await fetch(`${API_BASE}/attachments/${item.attachment_id}/download`, { headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error('No se pudo descargar el archivo')
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a'); link.href = url; link.download = item.filename; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo descargar') }
  }

  const handleChat = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await fetchJson<{
        response: string
        conversation_id: string | null
        messages: Message[]
        interpreted_prompt: string
        corrections: PromptCorrection[]
        warnings: string[]
      }>(`${API_BASE}/chat`, {
        method: 'POST',
        body: JSON.stringify({
          prompt: chatPrompt,
          conversation_id: activeConversationId,
          attachment_ids: selectedAttachments,
        }),
      })
      setMessages((current) => [...current, ...data.messages])
      setInterpretation(
        data.corrections.length
          ? { prompt: data.interpreted_prompt, corrections: data.corrections }
          : null,
      )
      if (data.warnings?.length) setError(data.warnings.join(' · '))
      setChatPrompt('')
      if (data.conversation_id) {
        setActiveConversationId(data.conversation_id)
        const history = await fetchJson<Conversation[]>(`${API_BASE}/conversations`)
        setConversations(history)
      }
      setStatus(
        data.conversation_id
          ? 'Respuesta guardada en tu historial'
          : 'Inicia sesión para guardar el historial',
      )
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'No se pudo consultar la IA')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">AI para potenciar personas</p>
          <h1>YitetsuAI</h1>
        </div>
        <div className="status-pill">{status}</div>
      </header>

      <main className="grid-layout">
        <section className="panel auth-panel">
          <div className="panel-header">
            <h2>Cuenta</h2>
            {token ? (
              <button className="ghost-button" onClick={handleLogout} type="button" disabled={loading}>
                Cerrar sesión
              </button>
            ) : null}
          </div>

          {!token ? (
            <>
              <div className="segmented-control">
                <button
                  type="button"
                  className={authMode === 'register' ? 'active' : ''}
                  onClick={() => setAuthMode('register')}
                >
                  Registrarse
                </button>
                <button
                  type="button"
                  className={authMode === 'login' ? 'active' : ''}
                  onClick={() => setAuthMode('login')}
                >
                  Iniciar sesión
                </button>
              </div>

              {authMode === 'register' ? (
                <form onSubmit={handleRegister} className="form-stack">
                  <label>
                    Nombre completo
                    <input
                      required
                      minLength={2}
                      value={registerForm.full_name}
                      onChange={(event) =>
                        setRegisterForm((current) => ({ ...current, full_name: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    Email
                    <input
                      required
                      type="email"
                      value={registerForm.email}
                      onChange={(event) =>
                        setRegisterForm((current) => ({ ...current, email: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    Contraseña (mínimo 8 caracteres)
                    <input
                      required
                      minLength={8}
                      type="password"
                      value={registerForm.password}
                      onChange={(event) =>
                        setRegisterForm((current) => ({ ...current, password: event.target.value }))
                      }
                    />
                  </label>
                  <button className="primary-button" type="submit" disabled={loading}>
                    {loading ? 'Creando...' : 'Crear cuenta'}
                  </button>
                </form>
              ) : (
                <form onSubmit={handleLogin} className="form-stack">
                  <label>
                    Email
                    <input
                      required
                      type="email"
                      value={loginForm.email}
                      onChange={(event) =>
                        setLoginForm((current) => ({ ...current, email: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    Contraseña
                    <input
                      required
                      type="password"
                      value={loginForm.password}
                      onChange={(event) =>
                        setLoginForm((current) => ({ ...current, password: event.target.value }))
                      }
                    />
                  </label>
                  <button className="primary-button" type="submit" disabled={loading}>
                    {loading ? 'Ingresando...' : 'Iniciar sesión'}
                  </button>
                </form>
              )}
            </>
          ) : (
            <div className="user-card">
              <div className="avatar">{user?.full_name?.[0]?.toUpperCase() || 'U'}</div>
              <div>
                <p className="label">Usuario autenticado</p>
                <strong>{user?.full_name || 'Usuario'}</strong>
                <p>{user?.email}</p>
              </div>
            </div>
          )}
          {error ? <p className="error-box">{error}</p> : null}
        </section>

        <section className="panel history-panel">
          <div className="panel-header">
            <h2>Historial</h2>
            {token ? (
              <button
                className="ghost-button"
                onClick={handleCreateConversation}
                type="button"
                disabled={loading}
              >
                + Nueva
              </button>
            ) : null}
          </div>
          {!token ? (
            <p className="empty-history">Inicia sesión para guardar y consultar tus conversaciones.</p>
          ) : conversations.length === 0 ? (
            <p className="empty-history">Aún no tienes conversaciones guardadas.</p>
          ) : (
            <ul className="conversation-list">
              {conversations.map((conversation) => (
                <li key={conversation.conversation_id}>
                  <button
                    type="button"
                    className={`conversation-item ${
                      activeConversationId === conversation.conversation_id ? 'selected' : ''
                    }`}
                    onClick={() => handleSelectConversation(conversation.conversation_id)}
                    disabled={loading}
                  >
                    <strong>{conversation.title}</strong>
                    <span>
                      {conversation.message_count} mensajes ·{' '}
                      {new Date(conversation.updated_at).toLocaleDateString()}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel chat-panel">
          <div className="panel-header">
            <h2>Asistente IA</h2>
          </div>

          <details className="capability-panel">
            <summary>
              {aiCapabilities.length
                ? `${aiCapabilities.length} componentes especializados`
                : capabilityError
                  ? 'Componentes de IA no disponibles'
                  : 'Cargando componentes de IA...'}
            </summary>
            {capabilityError ? <p className="capability-error">{capabilityError}</p> : null}
            <ol className="capability-list">
              {aiCapabilities.map((capability) => (
                <li key={capability.id}>
                  <div>
                    <strong>{capability.name}</strong>
                    <span>{capability.function}</span>
                    <small>{capability.implementation}</small>
                    <small>{capability.availability}</small>
                  </div>
                </li>
              ))}
            </ol>
          </details>

          <div className="prompt-list">
            {samplePrompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                className="prompt-chip"
                onClick={() => setChatPrompt(prompt)}
              >
                {prompt}
              </button>
            ))}
          </div>

          <section className="attachments-panel" aria-label="Adjuntos">
            <h3>Datos de esta conversación</h3>
            <p>PDF, Word, Excel, CSV, JSON, texto, imágenes, audio y video. Hasta 25 MB por archivo; audio/video hasta 10 minutos. Selecciona los archivos que usará la IA.</p>
            <label className="upload-label">Adjuntar archivos
              <input type="file" multiple disabled={!token || loading} accept=".pdf,.docx,.xlsx,.csv,.tsv,.json,.txt,.md,.log,.html,.htm,.xml,.png,.jpg,.jpeg,.webp,.gif,.wav,.mp3,.m4a,.ogg,.flac,.mp4,.mov,.webm,.mkv" onChange={event => { void handleFiles(event.target.files); event.target.value = '' }} />
            </label>
            {!token && <p>Inicia sesión para adjuntar y conservar tus archivos.</p>}
            {attachments.map(item => <article className="attachment-item" key={item.attachment_id}>
              <label><input type="checkbox" disabled={loading} checked={selectedAttachments.includes(item.attachment_id)} onChange={event => setSelectedAttachments(current => event.target.checked ? [...current, item.attachment_id] : current.filter(id => id !== item.attachment_id))} /> {item.filename} · {item.kind} · {Math.ceil(item.size_bytes / 1024)} KB</label>
              {item.warnings.map((warning, index) => <p key={index}>{warning}</p>)}
              <button type="button" disabled={loading} onClick={() => void downloadAttachment(item)}>Descargar</button>
              <button type="button" disabled={loading} onClick={() => void removeAttachment(item.attachment_id)}>Eliminar</button>
            </article>)}
          </section>

          <div className="message-list" aria-live="polite">
            {messages.length === 0 ? (
              <p className="empty-history">Tu conversación aparecerá aquí.</p>
            ) : (
              messages.map((message, index) => (
                <article
                  className={`message ${message.role}`}
                  key={message.message_id || `${message.role}-${index}`}
                >
                  <p className="label">{message.role === 'user' ? 'Tú' : 'YitetsuAI'}</p>
                  <p>{message.content}</p>
                  {!!message.sources?.length && <details><summary>Fuentes aportadas al modelo ({message.sources.length})</summary>{message.sources.map((source, sourceIndex) => <div className="source" key={sourceIndex}><strong>{source.filename} — {source.locator}</strong><p>{source.excerpt}</p></div>)}</details>}
                </article>
              ))
            )}
          </div>

          {interpretation?.corrections.length ? (
            <div className="interpretation-notice" role="status">
              <p className="label">Interpreté tu consulta como</p>
              <p>{interpretation.prompt}</p>
              <p className="correction-details">
                Correcciones: {interpretation.corrections
                  .map(({ original, corrected }) => `${original} → ${corrected}`)
                  .join(', ')}
              </p>
            </div>
          ) : null}

          <form onSubmit={handleChat} className="chat-form">
            <textarea
              value={chatPrompt}
              onChange={(event) => setChatPrompt(event.target.value)}
              rows={4}
              placeholder="Escribe una pregunta para YitetsuAI..."
            />
            <button className="primary-button" type="submit" disabled={loading || !chatPrompt.trim()}>
              {loading ? 'Consultando...' : 'Consultar IA'}
            </button>
          </form>
        </section>
      </main>
    </div>
  )
}

export default App
