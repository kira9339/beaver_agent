<template>
  <view class="settings-page">
    <view class="header">
      <text class="back" @click="goBack">‹ 返回</text>
      <text class="title">设置</text>
      <text class="placeholder"></text>
    </view>

    <scroll-view scroll-y class="body">
      <!-- model provider -->
      <view class="card">
        <view class="card-title">模型服务</view>
        <view class="hint">这是服务器全局配置，所有浏览器共用。</view>

        <view class="field">
          <text class="label">provider</text>
          <picker :range="modelProviders" :value="modelProviderIndex" @change="onModelProviderChange">
            <view class="picker">{{ form.model_provider.provider }}</view>
          </picker>
        </view>

        <view class="field">
          <text class="label">model</text>
          <input v-model="form.model_provider.model" class="input" placeholder="例如 deepseek-chat" />
        </view>

        <view class="field">
          <text class="label">base url</text>
          <input v-model="form.model_provider.base_url" class="input" placeholder="例如 https://api.deepseek.com/v1" />
        </view>

        <view class="field">
          <text class="label">api key</text>
          <input
            v-model="form.model_provider.api_key"
            class="input"
            password
            :placeholder="apiKeyPlaceholder(modelInfo)"
          />
        </view>
      </view>

      <!-- embedding -->
      <view class="card">
        <view class="card-title">Embedding（知识库向量化）</view>

        <view class="field">
          <text class="label">provider</text>
          <picker :range="embeddingProviders" :value="embeddingProviderIndex" @change="onEmbeddingProviderChange">
            <view class="picker">{{ form.embedding.provider }}</view>
          </picker>
        </view>

        <view class="field">
          <text class="label">model</text>
          <input v-model="form.embedding.model" class="input" placeholder="例如 embedding-3 / BAAI/bge-m3" />
        </view>

        <view class="field">
          <text class="label">base url</text>
          <input v-model="form.embedding.base_url" class="input" placeholder="例如 https://open.bigmodel.cn/api/paas/v4" />
        </view>

        <view class="field">
          <text class="label">api key</text>
          <input
            v-model="form.embedding.api_key"
            class="input"
            password
            :placeholder="apiKeyPlaceholder(embeddingInfo)"
          />
        </view>

        <view v-if="form.embedding.provider === 'local'" class="field">
          <text class="label">model path</text>
          <input v-model="form.embedding.model_path" class="input" placeholder="本地 HuggingFace 缓存目录" />
        </view>

        <view class="hint warn">
          使用 mock_embedding_provider 时无法向知识库写入文档，请切换到 openai 或 local。
        </view>
      </view>

      <view class="save-row">
        <button class="save-btn" :disabled="saving" @click="onSave">
          {{ saving ? '保存中…' : '保存配置' }}
        </button>
      </view>

      <!-- user management -->
      <view class="card">
        <view class="card-title">用户管理</view>

        <view v-for="u in users" :key="u.id" class="user-row">
          <view class="user-main">
            <text class="user-name">
              {{ u.username }}
              <text v-if="u.username === chatStore.username" class="user-current">当前</text>
            </text>
            <text class="user-meta">{{ u.display_name || '（未设置显示名）' }} · {{ u.email || '无邮箱' }} · {{ u.timezone }}</text>
          </view>
          <view class="user-actions">
            <text class="link" @click="onSwitchUser(u.username)">切换</text>
            <text class="link" @click="onEditUser(u)">编辑</text>
            <text class="link danger" @click="onDeleteUser(u)">删除</text>
          </view>
        </view>
        <view v-if="users.length === 0" class="hint">暂无用户</view>

        <view class="create-user">
          <input v-model="newUser.username" class="input" placeholder="新用户名" />
          <button class="small-btn" @click="onCreateUser">新建用户</button>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { onLoad, onUnload } from '@dcloudio/uni-app'
import { chatStore } from '../../store/chat.js'
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '../../utils/api.js'
import { closeSocket } from '../../utils/ws.js'

const MODEL_PROVIDERS = ['mock_provider', 'openai']
const EMBEDDING_PROVIDERS = ['mock_embedding_provider', 'openai', 'local']

const modelProviders = MODEL_PROVIDERS
const embeddingProviders = EMBEDDING_PROVIDERS

const modelInfo = ref({ api_key_set: false, api_key_masked: null })
const embeddingInfo = ref({ api_key_set: false, api_key_masked: null })
const users = ref([])
const saving = ref(false)
const newUser = reactive({ username: '' })

// api_key is never sent back in plaintext: leave the field empty to keep the
// stored key, type a new one to replace it, or clear it and save to remove it.
const form = reactive({
  model_provider: { provider: 'mock_provider', model: '', base_url: '', api_key: '' },
  embedding: { provider: 'mock_embedding_provider', model: '', base_url: '', api_key: '', model_path: '' },
})

const modelProviderIndex = computed(() => Math.max(0, MODEL_PROVIDERS.indexOf(form.model_provider.provider)))
const embeddingProviderIndex = computed(() => Math.max(0, EMBEDDING_PROVIDERS.indexOf(form.embedding.provider)))

function apiKeyPlaceholder(info) {
  if (!info) return '留空表示不修改'
  return info.api_key_set ? `已设置（${info.api_key_masked}），留空不修改` : '未设置，留空不修改'
}

function applySnapshot(data) {
  const mp = data.model_provider || {}
  const em = data.embedding || {}
  form.model_provider.provider = mp.provider || 'mock_provider'
  form.model_provider.model = mp.model || ''
  form.model_provider.base_url = mp.base_url || ''
  form.model_provider.api_key = ''
  modelInfo.value = { api_key_set: !!mp.api_key_set, api_key_masked: mp.api_key_masked }

  form.embedding.provider = em.provider || 'mock_embedding_provider'
  form.embedding.model = em.model || ''
  form.embedding.base_url = em.base_url || ''
  form.embedding.model_path = em.model_path || ''
  form.embedding.api_key = ''
  embeddingInfo.value = { api_key_set: !!em.api_key_set, api_key_masked: em.api_key_masked }
}

async function loadConfig() {
  try {
    applySnapshot(await apiGet('/api/config'))
  } catch (e) {
    uni.showToast({ title: e.message || '读取配置失败', icon: 'none' })
  }
}

async function loadUsers() {
  try {
    const res = await apiGet('/api/users')
    users.value = (res && res.items) || []
  } catch (e) {
    console.error('[settings] loadUsers failed', e)
  }
}

function onModelProviderChange(e) {
  form.model_provider.provider = MODEL_PROVIDERS[Number(e.detail.value)]
}

function onEmbeddingProviderChange(e) {
  form.embedding.provider = EMBEDDING_PROVIDERS[Number(e.detail.value)]
}

async function onSave() {
  saving.value = true
  try {
    const body = {
      model_provider: {
        provider: form.model_provider.provider,
        model: form.model_provider.model,
        base_url: form.model_provider.base_url,
      },
      embedding: {
        provider: form.embedding.provider,
        model: form.embedding.model,
        base_url: form.embedding.base_url,
        model_path: form.embedding.model_path,
      },
    }
    // Only send api_key when the user actually typed one; "" clears it.
    if (form.model_provider.api_key !== '') body.model_provider.api_key = form.model_provider.api_key
    if (form.embedding.api_key !== '') body.embedding.api_key = form.embedding.api_key

    applySnapshot(await apiPut('/api/config', body))
    uni.showToast({ title: '已保存并重建模型连接', icon: 'none' })
  } catch (e) {
    uni.showToast({ title: e.message || '保存失败', icon: 'none', duration: 4000 })
  } finally {
    saving.value = false
  }
}

async function onCreateUser() {
  const username = newUser.username.trim()
  if (!username) {
    uni.showToast({ title: '请输入用户名', icon: 'none' })
    return
  }
  try {
    await apiPost('/api/users', { username })
    newUser.username = ''
    await loadUsers()
    uni.showToast({ title: '用户已创建', icon: 'none' })
  } catch (e) {
    uni.showToast({ title: e.message || '创建失败', icon: 'none' })
  }
}

function onEditUser(user) {
  uni.showModal({
    title: `编辑 ${user.username}`,
    editable: true,
    placeholderText: '显示名',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await apiPatch(`/api/users/${encodeURIComponent(user.username)}`, {
          display_name: (res.content || '').trim() || null,
        })
        await loadUsers()
      } catch (e) {
        uni.showToast({ title: e.message || '更新失败', icon: 'none' })
      }
    },
  })
}

function onDeleteUser(user) {
  if (user.username === chatStore.username) {
    uni.showToast({ title: '不能删除当前用户', icon: 'none' })
    return
  }
  uni.showModal({
    title: '删除用户',
    content: `确认删除用户「${user.username}」及其全部数据？`,
    success: async (res) => {
      if (!res.confirm) return
      try {
        await apiDelete(`/api/users/${encodeURIComponent(user.username)}`)
        await loadUsers()
      } catch (e) {
        uni.showToast({ title: e.message || '删除失败', icon: 'none' })
      }
    },
  })
}

function onSwitchUser(username) {
  if (username === chatStore.username) return
  uni.showModal({
    title: '切换用户',
    content: `切换到「${username}」？当前会话将关闭。`,
    success: async (res) => {
      if (!res.confirm) return
      uni.setStorageSync('username', username)
      chatStore.username = username
      try {
        await apiGet(`/api/users/by-username/${encodeURIComponent(username)}`)
      } catch (e) {
        /* get-or-create is best effort */
      }
      closeSocket()
      uni.reLaunch({ url: '/pages/chat/chat' })
    },
  })
}

function goBack() {
  uni.navigateBack()
}

onLoad(() => {
  loadConfig()
  loadUsers()
})

onUnload(() => {})
</script>

<style lang="scss" scoped>
.settings-page {
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
  margin-bottom: 6px;
}
.hint {
  font-size: 12px;
  color: #999;
  margin-bottom: 10px;
}
.hint.warn {
  color: #e6a23c;
  margin-top: 10px;
  margin-bottom: 0;
}
.field {
  display: flex;
  align-items: center;
  margin-top: 10px;
}
.label {
  width: 90px;
  flex-shrink: 0;
  font-size: 13px;
  color: #666;
}
.input,
.picker {
  flex: 1;
  height: 36px;
  line-height: 36px;
  padding: 0 10px;
  border: 1px solid #dfe3ec;
  border-radius: 8px;
  font-size: 13px;
  color: #333;
  box-sizing: border-box;
  background: #fff;
}
.save-row {
  margin-bottom: 16px;
}
.save-btn {
  height: 42px;
  line-height: 42px;
  text-align: center;
  color: #fff;
  background: #4f6df5;
  border-radius: 8px;
  font-size: 15px;
}
.save-btn[disabled] {
  background: #c3cae8;
}
.user-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid #f2f3f6;
}
.user-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.user-name {
  font-size: 14px;
  color: #333;
}
.user-current {
  margin-left: 6px;
  padding: 1px 6px;
  background: #eef1ff;
  color: #4f6df5;
  border-radius: 8px;
  font-size: 11px;
}
.user-meta {
  margin-top: 3px;
  font-size: 12px;
  color: #aaa;
}
.user-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}
.link {
  font-size: 13px;
  color: #4f6df5;
}
.link.danger {
  color: #f56c6c;
}
.create-user {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
}
.small-btn {
  flex-shrink: 0;
  padding: 0 14px;
  height: 36px;
  line-height: 36px;
  font-size: 13px;
  color: #fff;
  background: #4f6df5;
  border-radius: 8px;
}
</style>
