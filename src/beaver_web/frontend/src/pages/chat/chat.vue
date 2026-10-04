<template>
  <view class="chat-page">
    <!-- agent confirmation dialog, shown over everything else -->
    <view v-if="chatStore.pendingConfirm" class="confirm-mask">
      <view class="confirm-box">
        <text class="confirm-title">{{ chatStore.pendingConfirm.title }}</text>
        <text class="confirm-sub">Agent 请求执行：{{ chatStore.pendingConfirm.tool_name }}</text>
        <pre class="confirm-body">{{ chatStore.pendingConfirm.summary }}</pre>
        <textarea
          v-model="rejectReason"
          class="confirm-reason"
          placeholder="拒绝理由（可选，会反馈给 Agent）"
        ></textarea>
        <view class="confirm-actions">
          <button class="confirm-reject" @click="onConfirmReject">拒绝</button>
          <button class="confirm-approve" @click="onConfirmApprove">同意</button>
        </view>
      </view>
    </view>

    <!-- username login overlay -->
    <view v-if="!username" class="login-mask">
      <view class="login-box">
        <text class="login-title">Beaver</text>
        <text class="login-sub">输入用户名开始对话</text>
        <input v-model="usernameInput" class="login-input" placeholder="username" @confirm="confirmUsername" />
        <button class="login-btn" @click="confirmUsername">进入</button>
      </view>
    </view>

    <view v-else class="layout">
      <!-- tapping outside the sidebar closes it (phone layout only) -->
      <view v-if="chatStore.sidebarOpen" class="sidebar-backdrop" @click="closeSidebar"></view>

      <!-- sidebar -->
      <view class="sidebar" :class="{ open: chatStore.sidebarOpen }">
        <view class="sidebar-header">
          <text class="brand">Beaver</text>
          <view class="new-btn" @click="onNewChat">+ 新建</view>
        </view>
        <scroll-view scroll-y class="session-list">
          <view
            v-for="s in chatStore.sessions"
            :key="s.id"
            class="session-item"
            :class="{ active: s.id === chatStore.sessionId }"
            @click="onSelectSession(s.id)"
          >
            <view class="session-title">{{ s.title }}</view>
            <view class="session-meta">{{ shortDate(s.updated_at) }}</view>
            <view class="session-del" @click.stop="onDeleteSession(s)">✕</view>
          </view>
          <view v-if="chatStore.sessions.length === 0" class="session-empty">暂无会话</view>
        </scroll-view>
      </view>

      <!-- main -->
      <view class="main">
        <view class="topbar">
          <view class="topbar-left">
            <text class="icon-btn" @click="toggleSidebar">☰</text>
            <text class="topbar-title">{{ chatStore.title }}</text>
          </view>
          <view class="topbar-right">
            <text class="agent-tag hide-narrow">{{ chatStore.agentName }}</text>
            <text
              class="conn-dot"
              :class="chatStore.connected ? 'online' : 'offline'"
            >{{ chatStore.connected ? '在线' : '重连中' }}</text>
            <text class="icon-btn" @click="onOpenBrowse">📚</text>
            <text class="icon-btn" @click="onOpenSettings">⚙</text>
          </view>
        </view>
        <view v-if="chatStore.banner" class="banner">{{ chatStore.banner }}</view>

        <scroll-view scroll-y class="messages" :scroll-top="scrollTop" @scroll="onScroll">
          <view v-for="(m, i) in chatStore.messages" :key="i" class="msg-row" :class="m.role">
            <view v-if="m.role === 'user'" class="bubble user">
              <view class="avatar user-avatar">我</view>
              <view class="bubble-body user">{{ m.content }}</view>
            </view>
            <view v-else class="bubble assistant">
              <view class="avatar assistant-avatar">Beaver</view>
              <view class="bubble-body assistant">
                <view class="assistant-text">
                  {{ m.content }}<text v-if="m.streaming" class="cursor">▍</text>
                </view>
                <view
                  v-for="(card, ci) in m.toolCards"
                  :key="ci"
                  class="tool-card"
                  @click="toggleCard(card)"
                >
                  <view class="tool-card-head">
                    <text class="tool-icon">{{ card.status === 'running' ? '⏳' : (card.status === 'awaiting' ? '❓' : '🔧') }}</text>
                    <text class="tool-name">{{ card.name }}</text>
                    <text class="tool-status" :class="card.status">
                      {{ card.status === 'running' ? '运行中' : (card.status === 'awaiting' ? '等待确认' : '完成') }}
                    </text>
                    <text v-if="card.duration_ms" class="tool-dur">{{ card.duration_ms }}ms</text>
                    <text class="tool-toggle">{{ card.expanded ? '▾' : '▸' }}</text>
                  </view>
                  <view v-if="card.expanded" class="tool-card-body">
                    <view class="tool-label">参数</view>
                    <pre class="tool-pre">{{ JSON.stringify(card.arguments, null, 2) }}</pre>
                    <view class="tool-label">结果</view>
                    <pre class="tool-pre">{{ card.result || (card.status === 'running' ? '运行中…' : '') }}</pre>
                  </view>
                </view>
              </view>
            </view>
          </view>
          <view v-if="chatStore.messages.length === 0" class="messages-empty">
            输入消息开始与 Agent 对话
          </view>
        </scroll-view>

        <view class="input-bar">
          <view v-if="!chatStore.connected" class="conn-hint">未连接，正在重连…（消息会暂存，重连后自动发送）</view>
          <textarea
            v-model="inputText"
            class="input-area"
            placeholder="输入消息，Enter 发送，Shift+Enter 换行"
            @keydown="onKeydown"
          ></textarea>
          <view class="input-actions">
            <button class="attach-btn" @click="onUpload">📎 上传文档</button>
            <button v-if="chatStore.streaming" class="stop-btn" @click="onInterrupt">⏹ 停止</button>
            <button class="send-btn" @click="onSend">发送</button>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { onLoad, onUnload } from '@dcloudio/uni-app'
import { chatStore } from '../../store/chat.js'
import {
  closeSocket,
  loadSessions,
  pushLocalNotice,
  selectSession,
  sendConfirmResponse,
  sendInterrupt,
  sendText,
} from '../../utils/ws.js'
import { apiUploadFile } from '../../utils/api.js'

// Keep in sync with beaver_core/utils/file_parsers.py::SUPPORTED_SUFFIXES.
const ACCEPTED_DOC_EXTENSIONS = [
  '.md', '.markdown', '.txt', '.text', '.log',
  '.pdf', '.docx', '.xlsx', '.xlsm', '.xls', '.csv', '.tsv', '.pptx',
]

const usernameInput = ref('')
const inputText = ref('')
const scrollTop = ref(0)
const rejectReason = ref('')

const username = computed(() => chatStore.username)

function bootstrap() {
  loadSessions().then(() => selectSession('new'))
}

function confirmUsername() {
  const name = usernameInput.value.trim()
  if (!name) {
    uni.showToast({ title: '请输入用户名', icon: 'none' })
    return
  }
  uni.setStorageSync('username', name)
  chatStore.username = name
  // Ensure the user exists on the backend, then initialize regardless of the result.
  ensureUser(name).finally(() => bootstrap())
}

function ensureUser(name) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: `/api/users/by-username/${encodeURIComponent(name)}`,
      method: 'GET',
      success: resolve,
      fail: (err) => {
        console.error('ensureUser failed', err)
        reject(err)
      },
    })
  })
}

function toggleSidebar() {
  chatStore.sidebarOpen = !chatStore.sidebarOpen
}

function closeSidebar() {
  chatStore.sidebarOpen = false
}

// On a phone the sidebar covers the chat, so it should get out of the way once
// the user has picked something. On a wide screen it stays where it is.
function closeSidebarOnNarrow() {
  if ((uni.getSystemInfoSync().windowWidth || 1024) <= 768) closeSidebar()
}

function onNewChat() {
  selectSession('new')
  closeSidebarOnNarrow()
}

function onSelectSession(id) {
  if (id !== chatStore.sessionId) selectSession(id)
  closeSidebarOnNarrow()
}

function onDeleteSession(session) {
  uni.showModal({
    title: '删除会话',
    content: `确认删除「${session.title}」及其全部消息？`,
    confirmText: '删除',
    confirmColor: '#f56c6c',
    success: (res) => {
      if (!res.confirm) return
      uni.request({
        url: `/api/sessions/${session.id}?username=${encodeURIComponent(chatStore.username)}`,
        method: 'DELETE',
        success: (r) => {
          // uni.request routes 4xx/5xx through success as well, so the status has
          // to be checked explicitly — otherwise a failed delete looks like a
          // successful no-op.
          if (r.statusCode >= 200 && r.statusCode < 300) {
            if (chatStore.sessionId === session.id) selectSession('new')
            else loadSessions()
          } else {
            const detail = r.data && r.data.detail
            uni.showToast({ title: detail || `删除失败 (${r.statusCode})`, icon: 'none', duration: 3000 })
          }
        },
        fail: () => uni.showToast({ title: '删除失败：网络错误', icon: 'none' }),
      })
    },
  })
}

function onSend() {
  const text = inputText.value.trim()
  if (!text || chatStore.streaming) return
  inputText.value = ''
  sendText(text)
  scrollToBottom()
}

function onInterrupt() {
  sendInterrupt()
}

// -- agent confirmation -----------------------------------------------------

function onConfirmApprove() {
  const pending = chatStore.pendingConfirm
  if (!pending) return
  sendConfirmResponse(pending.confirm_id, true)
  rejectReason.value = ''
}

function onConfirmReject() {
  const pending = chatStore.pendingConfirm
  if (!pending) return
  sendConfirmResponse(pending.confirm_id, false, rejectReason.value.trim())
  rejectReason.value = ''
}

function onOpenSettings() {
  uni.navigateTo({ url: '/pages/settings/settings' })
}

function onOpenBrowse() {
  uni.navigateTo({ url: '/pages/browse/browse' })
}

// -- document upload --------------------------------------------------------

function onUpload() {
  if (!chatStore.username) {
    uni.showToast({ title: '请先登录', icon: 'none' })
    return
  }
  if (typeof uni.chooseFile === 'function') {
    uni.chooseFile({
      count: 1,
      extension: ACCEPTED_DOC_EXTENSIONS,
      success: (res) => {
        const picked = res.tempFiles && res.tempFiles[0]
        if (picked) doUpload(picked.path, picked.name || '')
      },
      fail: () => {},
    })
    return
  }
  // Fallback for H5 builds without uni.chooseFile: a native file input.
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = ACCEPTED_DOC_EXTENSIONS.join(',')
  input.onchange = (event) => {
    const file = event.target.files && event.target.files[0]
    if (file) doUpload(URL.createObjectURL(file), file.name)
  }
  input.click()
}

async function doUpload(filePath, name, overwrite = false) {
  if (!filePath) return
  uni.showLoading({ title: '上传并入库中…', mask: true })
  try {
    const res = await apiUploadFile({
      url: '/api/documents/upload',
      filePath,
      name: 'file',
      formData: {
        username: chatStore.username,
        collection: 'default',
        overwrite: overwrite ? 'true' : 'false',
      },
    })
    uni.hideLoading()
    pushLocalNotice(
      `📎 已上传「${res.file_name}」并写入知识库，共 ${res.chunks_count} 个分块。` +
      '可以直接向我提问，或让我整理这份文档。'
    )
    scrollToBottom()
  } catch (e) {
    uni.hideLoading()
    const message = (e && e.message) || '上传失败'
    if (message.includes('已存在')) {
      uni.showModal({
        title: '文件已存在',
        content: message,
        success: (r) => {
          if (r.confirm) doUpload(filePath, name, true)
        },
      })
      return
    }
    uni.showToast({ title: message, icon: 'none', duration: 4000 })
  }
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    onSend()
  }
}

function toggleCard(card) {
  card.expanded = !card.expanded
}

function scrollToBottom() {
  scrollTop.value += 10000
}

function onScroll() {
  // placeholder; scrollTop is controlled to stay at the bottom on new content
}

function shortDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

watch(
  () => {
    const last = chatStore.messages[chatStore.messages.length - 1]
    return last ? last.content : ''
  },
  () => scrollToBottom()
)

onLoad(() => {
  if (chatStore.username) bootstrap()
})

onUnload(() => {
  chatStore.intentionalClose = true
  closeSocket()
})
</script>

<style lang="scss" scoped>
.chat-page {
  height: 100vh;
  display: flex;
}

/* login overlay */
.login-mask {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #4f6df5 0%, #6e8cff 100%);
}
.login-box {
  width: 320px;
  padding: 32px 28px;
  background: #fff;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
}
.login-title {
  font-size: 40px;
  font-weight: 700;
  color: #4f6df5;
}
.login-sub {
  margin: 8px 0 20px;
  color: #888;
  font-size: 14px;
}
.login-input {
  width: 100%;
  height: 44px;
  border: 1px solid #dfe3ec;
  border-radius: 8px;
  padding: 0 12px;
  font-size: 16px;
  box-sizing: border-box;
}
.login-btn {
  margin-top: 20px;
  width: 100%;
  height: 44px;
  line-height: 44px;
  text-align: center;
  color: #fff;
  background: #4f6df5;
  border-radius: 8px;
  font-size: 16px;
}

/* layout */
.layout {
  flex: 1;
  display: flex;
  min-height: 0;
}

/* sidebar — overlay on a phone, docked column on a wide screen */
.sidebar {
  position: fixed;
  top: 0;
  bottom: 0;
  left: 0;
  z-index: 60;
  width: 260px;
  background: #fff;
  border-right: 1px solid #e8eaef;
  display: flex;
  flex-direction: column;
  transform: translateX(-100%);
  transition: transform 0.2s ease;
}
.sidebar.open {
  transform: translateX(0);
}
.sidebar-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(0, 0, 0, 0.28);
}

@media (min-width: 769px) {
  .sidebar {
    position: static;
    transform: none;
    flex-shrink: 0;
  }
  .sidebar:not(.open) {
    display: none;
  }
  .sidebar-backdrop {
    display: none;
  }
}
@media (max-width: 768px) {
  .hide-narrow {
    display: none;
  }
}
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 12px;
}
.brand {
  font-size: 22px;
  font-weight: 700;
  color: #4f6df5;
}
.new-btn {
  padding: 6px 12px;
  background: #4f6df5;
  color: #fff;
  border-radius: 6px;
  font-size: 13px;
}
.session-list {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.session-item {
  position: relative;
  padding: 12px 14px;
  border-bottom: 1px solid #f2f3f6;
  cursor: pointer;
}
.session-item.active {
  background: #eef1ff;
  border-left: 3px solid #4f6df5;
}
.session-title {
  font-size: 14px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 38px;
}
.session-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #aaa;
}
/* Big enough to be a comfortable touch target on a phone (was 18px). */
.session-del {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  width: 32px;
  height: 32px;
  line-height: 32px;
  text-align: center;
  color: #bbb;
  font-size: 13px;
  border-radius: 50%;
}
.session-del:hover,
.session-del:active {
  color: #f56c6c;
  background: #fdeaea;
}
.session-empty {
  padding: 30px 0;
  text-align: center;
  color: #bbb;
  font-size: 13px;
}

/* main */
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #f5f6f8;
}
.topbar {
  height: 52px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e8eaef;
}
.topbar-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.agent-tag {
  padding: 3px 10px;
  background: #eef1ff;
  color: #4f6df5;
  border-radius: 12px;
  font-size: 12px;
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.conn-dot {
  flex-shrink: 0;
  font-size: 12px;
}
.conn-dot.online {
  color: #67c23a;
}
.conn-dot.offline {
  color: #e6a23c;
}
.banner {
  margin: 8px 20px 0;
  padding: 8px 12px;
  background: #eef1ff;
  color: #4f6df5;
  border-radius: 8px;
  font-size: 13px;
}

/* messages */
.messages {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 16px 20px;
  box-sizing: border-box;
}
.messages-empty {
  margin-top: 80px;
  text-align: center;
  color: #bbb;
  font-size: 14px;
}
.msg-row {
  display: flex;
  margin-bottom: 16px;
}
.msg-row.user {
  justify-content: flex-end;
}
.bubble {
  display: flex;
  max-width: 80%;
}
.avatar {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  line-height: 34px;
  text-align: center;
  border-radius: 50%;
  font-size: 13px;
  color: #fff;
}
.assistant-avatar {
  background: #4f6df5;
  margin-right: 10px;
}
.user-avatar {
  background: #2bb673;
  margin-left: 10px;
  order: 2;
}
.bubble-body {
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.bubble-body.user {
  background: #4f6df5;
  color: #fff;
  border-top-right-radius: 2px;
}
.bubble-body.assistant {
  background: #fff;
  color: #333;
  border: 1px solid #eceef2;
  border-top-left-radius: 2px;
}
.assistant-text {
  white-space: pre-wrap;
  word-break: break-word;
}
.cursor {
  color: #4f6df5;
  animation: blink 1s step-end infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}

/* tool card */
.tool-card {
  margin-top: 10px;
  border: 1px solid #e0e4ec;
  border-radius: 8px;
  background: #fafbfd;
  overflow: hidden;
}
.tool-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  font-size: 13px;
  cursor: pointer;
}
.tool-name {
  font-weight: 600;
  color: #444;
}
.tool-status {
  font-size: 12px;
}
.tool-status.running {
  color: #e6a23c;
}
.tool-status.done {
  color: #67c23a;
}
.tool-dur {
  color: #999;
  font-size: 12px;
  margin-left: auto;
}
.tool-toggle {
  color: #999;
  font-size: 12px;
}
.tool-card-body {
  border-top: 1px dashed #e0e4ec;
  padding: 8px 10px;
}
.tool-label {
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
}
.tool-pre {
  margin: 0 0 8px;
  padding: 8px;
  background: #f3f4f7;
  border-radius: 6px;
  font-size: 12px;
  color: #555;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow: auto;
}

/* input bar */
.input-bar {
  padding: 12px 20px 16px;
  border-top: 1px solid #e8eaef;
  background: #fff;
}
.conn-hint {
  margin-bottom: 8px;
  padding: 6px 10px;
  background: #fdf6ec;
  border: 1px solid #f5d9ab;
  color: #e6a23c;
  border-radius: 6px;
  font-size: 12px;
}
.input-area {
  width: 100%;
  min-height: 60px;
  max-height: 140px;
  padding: 10px 12px;
  border: 1px solid #dfe3ec;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.5;
  box-sizing: border-box;
  resize: none;
}
.input-actions {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.send-btn {
  width: 88px;
  height: 38px;
  line-height: 38px;
  text-align: center;
  color: #fff;
  background: #4f6df5;
  border-radius: 8px;
  font-size: 14px;
}
.send-btn[disabled] {
  background: #c3cae8;
  color: #fff;
}
.stop-btn {
  width: 88px;
  height: 38px;
  line-height: 38px;
  text-align: center;
  color: #e6a23c;
  background: #fdf6ec;
  border: 1px solid #f5d9ab;
  border-radius: 8px;
  font-size: 14px;
}
.attach-btn {
  height: 38px;
  line-height: 38px;
  padding: 0 14px;
  text-align: center;
  color: #4f6df5;
  background: #eef1ff;
  border: 1px solid #ccd4f7;
  border-radius: 8px;
  font-size: 13px;
  margin-right: auto;
}

/* topbar icon buttons (browse / settings) and the sidebar toggle */
.icon-btn {
  flex-shrink: 0;
  padding: 5px 8px;
  line-height: 1;
  font-size: 16px;
  color: #666;
  border-radius: 8px;
}
.icon-btn:hover,
.icon-btn:active {
  color: #4f6df5;
  background: #f2f3f6;
}

/* awaiting-confirmation tool card */
.tool-status.awaiting {
  color: #4f6df5;
}

/* confirmation dialog */
.confirm-mask {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
}
.confirm-box {
  width: 460px;
  max-width: calc(100vw - 40px);
  padding: 20px 22px;
  background: #fff;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.22);
}
.confirm-title {
  font-size: 17px;
  font-weight: 600;
  color: #333;
}
.confirm-sub {
  margin-top: 4px;
  font-size: 12px;
  color: #999;
}
.confirm-body {
  margin: 12px 0 0;
  padding: 10px;
  max-height: 220px;
  overflow: auto;
  background: #f3f4f7;
  border-radius: 6px;
  font-size: 12px;
  color: #555;
  white-space: pre-wrap;
  word-break: break-word;
}
.confirm-reason {
  width: 100%;
  min-height: 56px;
  margin-top: 12px;
  padding: 8px 10px;
  border: 1px solid #dfe3ec;
  border-radius: 8px;
  font-size: 13px;
  box-sizing: border-box;
}
.confirm-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.confirm-reject,
.confirm-approve {
  width: 96px;
  height: 38px;
  line-height: 38px;
  text-align: center;
  border-radius: 8px;
  font-size: 14px;
}
.confirm-reject {
  color: #666;
  background: #f2f3f6;
}
.confirm-approve {
  color: #fff;
  background: #4f6df5;
}
</style>
