import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { getModelscopeSettings, saveModelscopeSettings, type ModelscopeSettingsSavePayload } from '../api/settings'

function normalizeProvider(v: string) {
  const t = (v || '').trim().toLowerCase()
  if (!t) return 'modelscope'
  if (t === 'kimi') return 'moonshot'
  return t
}

export const useSettingsStore = defineStore('settings', () => {
  const loaded = ref(false)
  const provider = ref<'modelscope' | 'moonshot'>('modelscope')
  const tokenSet = ref(false)
  const tokenPreview = ref('')
  const moonshotKeySet = ref(false)
  const moonshotKeyPreview = ref('')

  const baseUrl = ref('')
  const moonshotBaseUrl = ref('')
  const chatModel = ref('')
  const moonshotChatModel = ref('')

  const statusText = computed(() => {
    const ms = tokenSet.value ? `ModelScope 已配置 ${tokenPreview.value || ''}` : 'ModelScope 未配置'
    const mo = moonshotKeySet.value ? `Moonshot 已配置 ${moonshotKeyPreview.value || ''}` : 'Moonshot 未配置'
    return `${ms}；${mo}`
  })

  async function refresh() {
    const d = await getModelscopeSettings()
    if (!d.success) throw new Error(d.error || '加载失败')
    loaded.value = true
    provider.value = normalizeProvider(d.provider || 'modelscope') as any
    tokenSet.value = !!d.token_set
    tokenPreview.value = d.token_preview || ''
    moonshotKeySet.value = !!d.moonshot_key_set
    moonshotKeyPreview.value = d.moonshot_key_preview || ''
    baseUrl.value = d.base_url || ''
    moonshotBaseUrl.value = d.moonshot_base_url || ''
    chatModel.value = d.chat_model || ''
    moonshotChatModel.value = d.moonshot_chat_model || ''
    return d
  }

  async function save(payload: ModelscopeSettingsSavePayload) {
    const d = await saveModelscopeSettings(payload)
    if (!d.success) throw new Error(d.error || '保存失败')
    // 写回状态
    provider.value = normalizeProvider(d.provider || provider.value) as any
    tokenSet.value = !!d.token_set
    tokenPreview.value = d.token_preview || ''
    moonshotKeySet.value = !!d.moonshot_key_set
    moonshotKeyPreview.value = d.moonshot_key_preview || ''
    return d
  }

  return {
    loaded,
    provider,
    tokenSet,
    tokenPreview,
    moonshotKeySet,
    moonshotKeyPreview,
    baseUrl,
    moonshotBaseUrl,
    chatModel,
    moonshotChatModel,
    statusText,
    refresh,
    save,
  }
})

