import { chatStore, resetMessages } from '../store/chat.js'
import { apiGet } from './api.js'

// The SocketTask is a native browser object; keep it OUT of the Vue reactive store
// (a reactive proxy can interfere with its internal state / event dispatch).
let socketTask = null
let reconnectAttempts = 0
let pendingText = ''

function wsUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://'
  const host = window.location.host
  const sid = chatStore.sessionId || 'new'
  return `${proto}${host}/ws/chat/${sid}?username=${encodeURIComponent(chatStore.username)}`
}

export function connect() {
  closeSocket()
  chatStore.intentionalClose = false
  // uni-app H5 returns a Promise when no callback is passed; an empty `complete`
  // callback forces it to return the SocketTask (with onOpen/onMessage/.../send).
  const task = uni.connectSocket({
    url: wsUrl(),
    complete: () => {},
  })
  socketTask = task

  // Every handler below ignores itself once `socketTask` has moved on. Closing a
  // socket fires its onClose *asynchronously*, so without this guard the handler
  // of a socket we deliberately replaced would see intentionalClose === false and
  // schedule a reconnect — which replaces the next socket, whose handler does the
  // same, and the page ends up reconnecting forever (and reloading its messages
  // on each cycle).
  const isCurrent = () => task === socketTask

  task.onOpen(() => {
    if (!isCurrent()) return
    chatStore.connected = true
    reconnectAttempts = 0
    startHeartbeat()
    if (pendingText) {
      const text = pendingText
      pendingText = ''
      pushAndSend(text)
    }
  })
  task.onMessage((res) => {
    if (!isCurrent()) return
    try {
      handleMessage(JSON.parse(res.data))
    } catch (e) {
      console.error('[ws] message parse error', e)
    }
  })
  task.onClose((res) => {
    if (!isCurrent()) return
    console.warn('[ws] connection closed', (res && res.code) || '', (res && res.reason) || '')
    chatStore.connected = false
    stopHeartbeat()
    if (!chatStore.intentionalClose) scheduleReconnect()
  })
  task.onError(() => {
    if (!isCurrent()) return
    if (!chatStore.intentionalClose) scheduleReconnect()
  })
}

export function closeSocket() {
  stopHeartbeat()
  if (chatStore.reconnectTimer) {
    clearTimeout(chatStore.reconnectTimer)
    chatStore.reconnectTimer = null
  }
  const task = socketTask
  // Drop the reference *before* closing so the task's own handlers already see
  // themselves as stale when they fire.
  socketTask = null
  if (task) {
    try {
      task.close({ code: 1000 })
    } catch (e) {
      /* ignore */
    }
  }
}

function scheduleReconnect() {
  if (chatStore.intentionalClose) return
  if (chatStore.reconnectTimer) return
  reconnectAttempts += 1
  if (reconnectAttempts > 60) {
    console.warn('[ws] giving up reconnect after many attempts')
    return
  }
  const delay = Math.min(15000, 2000 * reconnectAttempts)
  chatStore.reconnectTimer = setTimeout(() => {
    chatStore.reconnectTimer = null
    connect()
  }, delay)
}

function startHeartbeat() {
  stopHeartbeat()
  chatStore.heartbeatTimer = setInterval(() => {
    if (socketTask) {
      send({ type: 'ping', data: {} })
    }
  }, 30000)
}

function stopHeartbeat() {
  if (chatStore.heartbeatTimer) {
    clearInterval(chatStore.heartbeatTimer)
    chatStore.heartbeatTimer = null
  }
}

function send(payload) {
  if (socketTask) {
    try {
      socketTask.send({ data: JSON.stringify(payload) })
    } catch (e) {
      console.error('[ws] send error', e)
    }
  }
}

// -- message handling -------------------------------------------------------

function handleMessage(msg) {
  const data = msg.data || {}
  switch (msg.type) {
    case 'session_created': {
      const previousId = chatStore.sessionId
      // Empty for a chat that has not been used yet: the server creates the
      // conversation on the first message and announces the real id then.
      chatStore.sessionId = data.session_id || ''
      chatStore.title = data.title || chatStore.title || 'new chat'
      if (data.created) loadSessions()
      // Pull the transcript only when we have nothing on screen. Reconnecting to
      // the session already showing — or being handed the id of the chat we are
      // already in — must not replace it (that is what made the page flicker).
      const isDifferent = !!data.session_id && data.session_id !== previousId
      if (isDifferent && chatStore.messages.length === 0) {
        loadMessages(data.session_id)
      }
      break
    }
    case 'token':
      appendToken(data.content || '')
      break
    case 'tool_start':
      pushToolCard(data)
      break
    case 'tool_result':
      updateToolCard(data)
      break
    case 'confirm_request':
      chatStore.pendingConfirm = data
      markToolCardAwaiting(data.tool_call_id)
      break
    case 'agent_switch':
      chatStore.agentName = data.to || chatStore.agentName
      chatStore.banner = `已切换至 ${data.to}`
      setTimeout(() => {
        chatStore.banner = ''
      }, 3000)
      break
    case 'message_complete':
      finalizeMessage(data)
      break
    case 'summary':
      uni.showToast({ title: '会话摘要已保存', icon: 'none' })
      break
    case 'error':
      // A timed-out confirmation also arrives as an error carrying its id.
      if (data.confirm_id && chatStore.pendingConfirm
          && chatStore.pendingConfirm.confirm_id === data.confirm_id) {
        chatStore.pendingConfirm = null
      }
      uni.showToast({ title: data.message || '出错了', icon: 'none', duration: 3000 })
      break
    case 'pong':
      break
    default:
      break
  }
}

function ensureAssistantBubble() {
  const list = chatStore.messages
  const last = list[list.length - 1]
  if (!last || last.role !== 'assistant' || last.streaming !== true) {
    const bubble = { role: 'assistant', content: '', streaming: true, toolCards: [] }
    list.push(bubble)
    chatStore.streaming = true
    return bubble
  }
  return last
}

function appendToken(text) {
  const bubble = ensureAssistantBubble()
  bubble.content += text
}

function pushToolCard(data) {
  const bubble = ensureAssistantBubble()
  bubble.toolCards.push({
    tool_call_id: data.tool_call_id,
    name: data.name,
    arguments: data.arguments || {},
    result: '',
    duration_ms: 0,
    status: 'running',
    expanded: true,
  })
}

function updateToolCard(data) {
  const list = chatStore.messages
  for (let i = list.length - 1; i >= 0; i--) {
    const cards = list[i].toolCards
    if (cards) {
      const card = cards.find((c) => c.tool_call_id === data.tool_call_id)
      if (card) {
        card.status = 'done'
        card.result = data.result || ''
        card.duration_ms = data.duration_ms || 0
        return
      }
    }
  }
}

function finalizeMessage(data) {
  const bubble = ensureAssistantBubble()
  bubble.streaming = false
  chatStore.streaming = false
}

function markToolCardAwaiting(toolCallId) {
  if (!toolCallId) return
  const list = chatStore.messages
  for (let i = list.length - 1; i >= 0; i--) {
    const cards = list[i].toolCards
    if (cards) {
      const card = cards.find((c) => c.tool_call_id === toolCallId)
      if (card) {
        card.status = 'awaiting'
        return
      }
    }
  }
}

// -- REST helpers -----------------------------------------------------------

// Re-exported for existing consumers; new code should import from api.js.
export { apiGet }

export async function loadSessions() {
  if (!chatStore.username) return
  try {
    const res = await apiGet(`/api/sessions?username=${encodeURIComponent(chatStore.username)}`)
    chatStore.sessions = (res && res.items) || []
  } catch (e) {
    console.error('[ws] loadSessions failed', e)
  }
}

export async function loadMessages(sessionId) {
  if (!sessionId || !chatStore.username) return
  try {
    const res = await apiGet(`/api/sessions/${sessionId}/messages?username=${encodeURIComponent(chatStore.username)}`)
    const items = (res && res.items) || []
    const messages = []
    for (const it of items) {
      if (it.role === 'user') {
        messages.push({ role: 'user', content: it.content, streaming: false, toolCards: [] })
      } else if (it.role === 'assistant') {
        const toolCalls = (it.metadata && it.metadata.tool_calls) || []
        const cards = (toolCalls || []).map((tc) => {
          const fn = tc.function || {}
          let args = {}
          try {
            args = JSON.parse(fn.arguments || '{}')
          } catch (e) {
            args = fn.arguments || {}
          }
          return { tool_call_id: tc.id, name: fn.name, arguments: args, result: '', duration_ms: 0, status: 'done', expanded: false }
        })
        messages.push({ role: 'assistant', content: it.content, streaming: false, toolCards: cards })
      } else if (it.role === 'tool') {
        const last = messages[messages.length - 1]
        const card = last && last.toolCards && last.toolCards.find((c) => c.tool_call_id === (it.metadata && it.metadata.tool_call_id))
        if (card) {
          card.result = it.content
          card.status = 'done'
        }
      }
    }
    chatStore.messages = messages
    chatStore.streaming = false
  } catch (e) {
    console.error('[ws] loadMessages failed', e)
  }
}

// -- actions used by the page ----------------------------------------------

export function selectSession(id) {
  closeSocket()
  if (id === 'new') {
    chatStore.sessionId = ''
    resetMessages()
  } else {
    chatStore.sessionId = id
    loadMessages(id)
  }
  connect()
}

export function sendText(text) {
  const content = text.trim()
  if (!content) return
  if (!socketTask || !chatStore.connected) {
    pendingText = pendingText ? `${pendingText}\n${content}` : content
    uni.showToast({ title: '未连接，消息已暂存，重连后自动发送', icon: 'none' })
    connect()
    return
  }
  pushAndSend(content)
}

function pushAndSend(content) {
  chatStore.messages.push({ role: 'user', content, streaming: false, toolCards: [] })
  chatStore.streaming = true
  send({ type: 'user_message', data: { content } })
}

export function sendInterrupt() {
  send({ type: 'interrupt', data: {} })
}

export function sendConfirmResponse(confirmId, approved, reason = '') {
  send({ type: 'confirm_response', data: { confirm_id: confirmId, approved, reason } })
  chatStore.pendingConfirm = null
}

// Local-only bubble: shown in the transcript but never sent to the model.
export function pushLocalNotice(text) {
  chatStore.messages.push({ role: 'notice', content: text, streaming: false, toolCards: [] })
}
