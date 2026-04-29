<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useSettingsStore } from '../stores/settings'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const store = useSettingsStore()
const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const apiKey = ref('')
const clearKey = ref(false)
const saving = ref(false)

const providerLabel = computed(() =>
  store.provider === 'moonshot' ? 'Moonshot API Key（MOONSHOT_API_KEY）' : 'ModelScope Token（MODELSCOPE_TOKEN）',
)
const providerHint = computed(() =>
  store.provider === 'moonshot' ? '请粘贴 Kimi 官方 API Key（不要带引号/空格/换行）。' : '请粘贴魔塔 ModelScope Token（不要带引号/空格/换行）。',
)
const clearLabel = computed(() =>
  store.provider === 'moonshot' ? '清除已保存的 Moonshot Key（运行时文件中的项）' : '清除已保存的 ModelScope Token（运行时文件中的项）',
)

watch(
  () => open.value,
  async (v) => {
    if (!v) return
    apiKey.value = ''
    clearKey.value = false
    try {
      await store.refresh()
      // fill defaults like old UI
      if (!store.baseUrl) store.baseUrl = 'https://api-inference.modelscope.cn/v1'
      if (!store.moonshotBaseUrl) store.moonshotBaseUrl = 'https://api.moonshot.cn/v1'
      if (!store.chatModel) store.chatModel = 'moonshotai/Kimi-K2.5'
      if (!store.moonshotChatModel) store.moonshotChatModel = 'kimi-k2.5'
    } catch (e: any) {
      ElMessage.error(e?.message || String(e))
    }
  },
)

async function onSave() {
  saving.value = true
  try {
    const pv = (store.provider || 'modelscope').toLowerCase()
    const keyVal = apiKey.value || ''
    const clear = !!clearKey.value
    const payload: any = {
      provider: pv,
      base_url: (store.baseUrl || '').trim(),
      moonshot_base_url: (store.moonshotBaseUrl || '').trim(),
      chat_model: (store.chatModel || '').trim(),
      moonshot_chat_model: (store.moonshotChatModel || '').trim(),
      token: '',
      clear_token: false,
      moonshot_api_key: '',
      clear_moonshot_key: false,
    }
    if (pv === 'moonshot') {
      payload.moonshot_api_key = keyVal
      payload.clear_moonshot_key = clear
    } else {
      payload.token = keyVal
      payload.clear_token = clear
    }

    const d = await store.save(payload)
    let msg = '已保存并写入运行时配置。'
    if ((d as any).refresh_error) msg += ` 每日必读资讯模块：${(d as any).refresh_error}`
    if ((d as any).refresh_error) ElMessage.warning(msg)
    else ElMessage.success(msg)

    apiKey.value = ''
    clearKey.value = false
  } catch (e: any) {
    ElMessage.error(e?.message || String(e))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog v-model="open" title="API 配置（魔塔 / Kimi）" width="820px">
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      配置保存在服务器 <code>instance/modelscope_runtime.json</code>，会覆盖启动时已加载的 <code>.env</code> 同名变量。
    </el-alert>

    <el-form label-position="top">
      <el-form-item label="API 提供方（AI_API_PROVIDER）">
        <el-select v-model="store.provider" style="width: 100%">
          <el-option value="modelscope" label="魔塔 ModelScope（OpenAI 兼容）" />
          <el-option value="moonshot" label="Kimi 官方（https://api.moonshot.cn/v1）" />
        </el-select>
        <div class="help">文档文稿处理 / 云智学习 / 新闻总结等接口会按此选择 base_url + key。</div>
      </el-form-item>

      <el-form-item label="当前 Key 状态">
        <div class="status">{{ store.statusText }}</div>
      </el-form-item>

      <el-form-item :label="providerLabel">
        <el-input v-model="apiKey" type="password" show-password placeholder="粘贴 Key；留空表示不修改" />
        <div class="help">{{ providerHint }}</div>
      </el-form-item>

      <el-form-item>
        <el-checkbox v-model="clearKey">{{ clearLabel }}</el-checkbox>
      </el-form-item>

      <el-collapse>
        <el-collapse-item title="高级设置（可选）">
          <el-form-item label="ModelScope Base URL（MODELSCOPE_BASE_URL）">
            <el-input v-model="store.baseUrl" placeholder="https://api-inference.modelscope.cn/v1" />
          </el-form-item>
          <el-form-item label="Moonshot Base URL（MOONSHOT_BASE_URL）">
            <el-input v-model="store.moonshotBaseUrl" placeholder="https://api.moonshot.cn/v1" />
          </el-form-item>
          <el-form-item label="默认对话模型（MODELSCOPE_CHAT_MODEL）">
            <el-input v-model="store.chatModel" placeholder="moonshotai/Kimi-K2.5" />
          </el-form-item>
          <el-form-item label="默认对话模型（MOONSHOT_CHAT_MODEL）">
            <el-input v-model="store.moonshotChatModel" placeholder="kimi-k2.5" />
          </el-form-item>
          <div class="help">一般无需改动；Base URL 在后端会自动补全 /v1。</div>
        </el-collapse-item>
      </el-collapse>
    </el-form>

    <template #footer>
      <el-button @click="open = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="onSave">保存并生效</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.help {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 6px;
}
.status {
  font-size: 13px;
  color: var(--el-text-color-regular);
}
</style>

