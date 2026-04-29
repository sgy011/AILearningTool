<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ToolPageShell from '../components/ToolPageShell.vue'
import {
  newsConfig,
  newsPushplusConfigGet,
  newsPushplusConfigSave,
  newsPushplusPushNow,
  newsSearch,
} from '../api/news'
import { normalizeApiError } from '../api/http'

const feed = ref<'softunis' | 'tencent'>('softunis')
const softunisTag = ref('ai')
const qqChannel = ref('tech')
const limit = ref(5)
const useAi = ref(true)
const busy = ref(false)
const result = ref<any>(null)
const feedOptions = ref<{ key: 'softunis' | 'tencent'; label: string }[]>([
  { key: 'softunis', label: '软盟 · AI' },
  { key: 'tencent', label: '腾讯新闻' },
])
const softunisOptions = ref<{ key: string; label: string }[]>([{ key: 'ai', label: 'AI' }])
const tencentOptions = ref<{ key: string; label: string }[]>([
  { key: 'politics', label: '要闻' },
  { key: 'tech', label: '科技' },
  { key: 'kepu', label: '科学' },
  { key: 'sports', label: '体育' },
])

const pushEnabled = ref(false)
const pushToken = ref('')
const pushTime = ref('08:30')
const pushSaving = ref(false)
const pushTesting = ref(false)
const summaryText = computed(() => {
  const r = result.value || {}
  return (
    r.combined_summary ||
    r.summary ||
    r.message ||
    (Array.isArray(r.articles) && r.articles.length ? '暂无合并总结' : '')
  )
})

async function loadConfig() {
  try {
    const d = await newsConfig()
    if (d?.success) {
      if (Array.isArray(d.feeds) && d.feeds.length) {
        feedOptions.value = d.feeds.map((x: any) => ({ key: x.key, label: x.label }))
      }
      if (Array.isArray(d.softunis_tags) && d.softunis_tags.length) {
        softunisOptions.value = d.softunis_tags.map((x: any) => ({ key: x.key, label: x.label }))
      }
      if (Array.isArray(d.qq_channels) && d.qq_channels.length) {
        tencentOptions.value = d.qq_channels.map((x: any) => ({ key: x.key, label: x.label }))
      }
    }
  } catch {
    // ignore
  }
}

async function loadPushConfig() {
  try {
    const d = await newsPushplusConfigGet()
    if (!d.success || !d.config) return
    const c = d.config
    pushEnabled.value = !!c.enabled
    pushToken.value = c.token || ''
    pushTime.value = c.push_time || '08:30'
  } catch {
    // ignore
  }
}

async function run() {
  busy.value = true
  result.value = null
  try {
    const payload: any = {
      limit: limit.value,
      use_ai: useAi.value,
      feed: feed.value,
    }
    if (feed.value === 'tencent') payload.qq_channel = qqChannel.value
    if (feed.value === 'softunis') payload.softunis_tag = softunisTag.value
    const d = await newsSearch(payload)
    if (!d.success) throw new Error(d.message || d.error || '请求失败')
    result.value = d
  } catch (e) {
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    busy.value = false
  }
}

async function savePushConfig() {
  pushSaving.value = true
  try {
    const d = await newsPushplusConfigSave({
      enabled: pushEnabled.value,
      token: pushToken.value.trim(),
      feed: feed.value,
      softunis_tag: softunisTag.value,
      qq_channel: qqChannel.value,
      limit: limit.value,
      use_ai: useAi.value,
      push_time: pushTime.value,
    })
    if (!d.success) throw new Error(d.error || '保存失败')
    ElMessage.success('PushPlus 推送设置已保存')
  } catch (e) {
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    pushSaving.value = false
  }
}

async function pushNow() {
  pushTesting.value = true
  try {
    const d = await newsPushplusPushNow({
      feed: feed.value,
      softunis_tag: softunisTag.value,
      qq_channel: qqChannel.value,
      limit: limit.value,
      use_ai: useAi.value,
    })
    if (!d.success) throw new Error(d.error || '推送失败')
    ElMessage.success('已推送到微信（PushPlus）')
  } catch (e) {
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    pushTesting.value = false
  }
}

loadConfig()
loadPushConfig()
</script>

<template>
  <ToolPageShell
    title="每日必读资讯"
    subtitle="聚合行业频道与 AI 精选，可选大模型生成合并简报。"
  >
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      选择软盟 AI 或腾讯新闻频道，抓取后生成合并简报；AI 总结依赖已配置的 Token。
    </el-alert>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="8">
        <div class="label">资讯来源</div>
        <el-select v-model="feed" style="width: 100%">
          <el-option v-for="opt in feedOptions" :key="opt.key" :value="opt.key" :label="opt.label" />
        </el-select>
      </el-col>
      <el-col :span="8" v-if="feed==='softunis'">
        <div class="label">softunis tag</div>
        <el-select v-model="softunisTag" style="width: 100%" filterable allow-create default-first-option>
          <el-option v-for="opt in softunisOptions" :key="opt.key" :value="opt.key" :label="opt.label" />
        </el-select>
      </el-col>
      <el-col :span="8" v-if="feed==='tencent'">
        <div class="label">频道</div>
        <el-select v-model="qqChannel" style="width: 100%">
          <el-option v-for="opt in tencentOptions" :key="opt.key" :value="opt.key" :label="opt.label" />
        </el-select>
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="8">
        <div class="label">篇数</div>
        <el-select v-model="limit" style="width: 100%">
          <el-option :value="1" label="1" />
          <el-option :value="3" label="3" />
          <el-option :value="5" label="5" />
          <el-option :value="10" label="10" />
        </el-select>
      </el-col>
      <el-col :span="8" style="display:flex; align-items:end;">
        <el-switch v-model="useAi" active-text="AI 总结" />
      </el-col>
      <el-col :span="8" style="display:flex; justify-content:end; align-items:end;">
        <el-button type="primary" :loading="busy" @click="run">拉取并总结</el-button>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-top: 12px">
      <template #header>PushPlus 微信推送</template>
      <el-row :gutter="12" style="margin-bottom: 12px">
        <el-col :span="8">
          <el-switch v-model="pushEnabled" active-text="启用每日自动推送" />
        </el-col>
        <el-col :span="8">
          <div class="label">推送时间（HH:MM）</div>
          <el-input v-model="pushTime" placeholder="08:30" />
        </el-col>
        <el-col :span="8">
          <div class="label">PushPlus Token</div>
          <el-input v-model="pushToken" show-password placeholder="请填写 pushplus token" />
        </el-col>
      </el-row>
      <div class="push-actions">
        <el-button :loading="pushSaving" @click="savePushConfig">保存推送设置</el-button>
        <el-button type="primary" :loading="pushTesting" @click="pushNow">立即测试推送</el-button>
      </div>
    </el-card>

    <div v-if="result" style="margin-top: 12px">
      <el-card shadow="never">
        <template #header>合并简报</template>
        <pre class="pre">{{ summaryText }}</pre>
      </el-card>

      <el-card shadow="never" style="margin-top: 12px" v-if="Array.isArray(result.articles)">
        <template #header>文章列表（{{ result.articles.length }}）</template>
        <el-table :data="result.articles" size="small" style="width: 100%">
          <el-table-column label="标题" min-width="320">
            <template #default="{ row }">
              <a :href="row.url" target="_blank" rel="noreferrer">{{ row.title }}</a>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="120">
            <template #default="{ row }">{{ row.source || '' }}</template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  </ToolPageShell>
</template>

<style scoped>
.label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.pre {
  white-space: pre-wrap;
  margin: 0;
  font-size: 13px;
}
.push-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>

