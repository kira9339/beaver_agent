<template>
  <view class="browse-page">
    <view class="header">
      <text class="back" @click="goBack">‹ 返回</text>
      <text class="title">浏览</text>
      <text class="placeholder"></text>
    </view>

    <scroll-view scroll-y class="body">
      <!-- agents -->
      <view class="card">
        <view class="card-title">Agent</view>
        <view class="hint">主 Agent 可以调度下列专家；对话中说"切换到 XX"即可调用。</view>

        <view class="agent main-agent">
          <view class="agent-head">
            <text class="agent-name">{{ agents.main.class_name || '—' }}</text>
            <text class="agent-badge">当前</text>
          </view>
          <text class="agent-desc">{{ agents.main.description || '主对话 Agent' }}</text>
          <view class="tool-chips">
            <text v-for="t in agents.main.tools" :key="t" class="chip">{{ t }}</text>
          </view>
        </view>

        <view v-for="a in agents.experts" :key="a.name" class="agent">
          <view class="agent-head">
            <text class="agent-name">{{ a.class_name }}</text>
            <text class="agent-key">{{ a.name }}</text>
          </view>
          <text class="agent-desc">{{ a.description || '（无描述）' }}</text>
          <view v-if="a.error" class="agent-error">加载失败：{{ a.error }}</view>
          <view v-else class="tool-chips">
            <text v-for="t in a.tools" :key="t" class="chip">{{ t }}</text>
          </view>
        </view>
        <view v-if="!agents.experts.length" class="hint">暂无专家 Agent</view>
      </view>

      <!-- knowledge base -->
      <view class="card">
        <view class="card-title">
          知识库
          <text class="count">（{{ documents.length }} 份）</text>
        </view>
        <view class="hint">上传的文档会切块、向量化后存到这里，对话中可以直接提问其内容。</view>

        <view v-for="d in documents" :key="d.id" class="doc-row">
          <view class="doc-main">
            <text class="doc-name">{{ d.file_name }}</text>
            <text class="doc-meta">{{ d.chunks }} 个分块 · {{ shortDate(d.created_at) }}</text>
          </view>
          <text class="doc-del" @click="onDeleteDoc(d)">删除</text>
        </view>
        <view v-if="!documents.length" class="hint">知识库还是空的，在聊天页点 📎 上传文档</view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { chatStore } from '../../store/chat.js'
import { apiDelete, apiGet } from '../../utils/api.js'

const agents = reactive({ main: {}, experts: [] })
const documents = ref([])

async function loadAgents() {
  try {
    const res = await apiGet('/api/agents')
    agents.main = (res && res.main) || {}
    agents.experts = (res && res.experts) || []
  } catch (e) {
    uni.showToast({ title: e.message || '读取 Agent 失败', icon: 'none' })
  }
}

async function loadDocuments() {
  if (!chatStore.username) return
  try {
    const res = await apiGet(`/api/documents?username=${encodeURIComponent(chatStore.username)}`)
    documents.value = (res && res.items) || []
  } catch (e) {
    uni.showToast({ title: e.message || '读取知识库失败', icon: 'none' })
  }
}

function onDeleteDoc(doc) {
  uni.showModal({
    title: '删除文档',
    content: `确认从知识库中删除「${doc.file_name}」及其全部分块？`,
    confirmText: '删除',
    confirmColor: '#f56c6c',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await apiDelete(
          `/api/documents/${encodeURIComponent(doc.id)}?username=${encodeURIComponent(chatStore.username)}`
        )
        await loadDocuments()
        uni.showToast({ title: '已删除', icon: 'none' })
      } catch (e) {
        uni.showToast({ title: e.message || '删除失败', icon: 'none', duration: 3000 })
      }
    },
  })
}

function shortDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function goBack() {
  uni.navigateBack()
}

onLoad(() => {
  loadAgents()
  loadDocuments()
})
</script>

<style lang="scss" scoped>
.browse-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f6f8;
}
.header {
  height: 52px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e8eaef;
}
.back {
  font-size: 14px;
  color: #4f6df5;
  width: 60px;
}
.title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}
.placeholder {
  width: 60px;
}
.body {
  flex: 1;
  min-height: 0;
  padding: 16px;
  box-sizing: border-box;
}
.card {
  background: #fff;
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 16px;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}
.count {
  font-size: 12px;
  font-weight: 400;
  color: #999;
}
.hint {
  margin: 6px 0 10px;
  font-size: 12px;
  color: #999;
  line-height: 1.6;
}

/* agents */
.agent {
  padding: 12px 0;
  border-top: 1px solid #f2f3f6;
}
.agent.main-agent {
  border-top: none;
}
.agent-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.agent-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}
.agent-badge {
  padding: 1px 8px;
  background: #eef1ff;
  color: #4f6df5;
  border-radius: 8px;
  font-size: 11px;
}
.agent-key {
  font-size: 12px;
  color: #aaa;
}
.agent-desc {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #777;
  line-height: 1.6;
}
.agent-error {
  margin-top: 6px;
  font-size: 12px;
  color: #f56c6c;
}
.tool-chips {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  padding: 2px 8px;
  background: #f3f4f7;
  color: #666;
  border-radius: 6px;
  font-size: 11px;
}

/* documents */
.doc-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-top: 1px solid #f2f3f6;
}
.doc-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.doc-name {
  font-size: 14px;
  color: #333;
  word-break: break-all;
}
.doc-meta {
  margin-top: 3px;
  font-size: 12px;
  color: #aaa;
}
.doc-del {
  flex-shrink: 0;
  padding: 6px 12px;
  font-size: 13px;
  color: #f56c6c;
}
</style>
