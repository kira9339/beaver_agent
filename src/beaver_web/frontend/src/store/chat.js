import { reactive } from 'vue'

// Reactive chat state shared between the page and the WebSocket helper.
// NOTE: the WebSocket SocketTask is intentionally NOT stored here — keeping a native
// task object inside a Vue reactive proxy can interfere with its internal state.
// ws.js holds it in a plain module-level variable instead.
export const chatStore = reactive({
  username: uni.getStorageSync('username') || '',
  sessions: [],
  sessionId: '',
  title: 'new chat',
  // messages: [{ role: 'user'|'assistant', content, streaming, toolCards }]
  messages: [],
  streaming: false,
  connected: false,
  // Sidebar starts open on a wide screen and collapsed on a phone, where it
  // overlays the chat instead of sharing the row.
  sidebarOpen: (uni.getSystemInfoSync().windowWidth || 1024) > 768,
  agentName: 'MainAgent',
  banner: '',
  // {confirm_id, tool_call_id, tool_name, title, summary, arguments, timeout_ms}
  // when the agent is waiting for the user to approve a write/delete operation.
  pendingConfirm: null,
  reconnectTimer: null,
  heartbeatTimer: null,
  intentionalClose: false,
})

export function resetMessages() {
  chatStore.messages = []
  chatStore.streaming = false
  chatStore.title = 'new chat'
}
