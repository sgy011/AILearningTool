<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ToolPageShell from '../components/ToolPageShell.vue'
import { datasetScrapeClean, datasetScrapeOnly, getMmAlignModels } from '../api/dataset'
import { normalizeApiError } from '../api/http'
import { downloadBlob } from '../api/download'

const query = ref('')
const count = ref(50)
const minW = ref(256)
const minH = ref(256)
const seed = ref(42)
const name = ref('')
const model = ref('')
const modelOptions = ref<string[]>([])
const busy = ref(false)

onMounted(async () => {
  try {
    const data = await getMmAlignModels()
    modelOptions.value = data.models || []
    model.value = data.default_model || data.models?.[0] || ''
  } catch {
    modelOptions.value = [
      'Qwen/Qwen3.5-397B-A17B',
      'Qwen/Qwen3-VL-8B-Instruct',
      'Qwen/Qwen3-VL-235B-A22B-Instruct',
    ]
    model.value = modelOptions.value[0]
  }
})

async function run() {
  if (!query.value.trim()) return ElMessage.error('请输入关键词')
  busy.value = true
  try {
    const { blob, filename } = await datasetScrapeClean({
      query: query.value.trim(),
      count: count.value,
      min_width: minW.value,
      min_height: minH.value,
      seed: seed.value,
      model: model.value || undefined,
      name: name.value.trim() || undefined,
    })
    downloadBlob(blob, filename || `${name.value.trim() || `dataset_${query.value.trim()}`}.zip`)
    ElMessage.success('已开始下载')
  } catch (e) {
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    busy.value = false
  }
}

async function scrapeOnlyRun() {
  if (!query.value.trim()) return ElMessage.error('请输入关键词')
  busy.value = true
  try {
    const defaultName = name.value.trim() || `images_${query.value.trim()}`
    const { blob, filename } = await datasetScrapeOnly({
      query: query.value.trim(),
      count: count.value,
      name: defaultName,
    })
    downloadBlob(blob, filename || `${defaultName}.zip`)
    ElMessage.success('已开始下载')
  } catch (e) {
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ToolPageShell
    title="图片数据集制作"
    subtitle="关键词爬取、清洗与打包，快速沉淀可用于训练的图片集。"
  >
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      从百度图片按关键词抓取并清洗（去重/过滤/语义匹配），输出 images/ + report.jsonl 的 zip；
      也可仅爬取不清洗，直接输出 images/ 的 zip。
    </el-alert>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="14">
        <div class="label">关键词</div>
        <el-input v-model="query" placeholder="例如：猫、消防车、螺丝刀" />
      </el-col>
      <el-col :span="10">
        <div class="label">数量</div>
        <el-input-number v-model="count" :min="1" :max="500" :step="1" style="width: 100%" />
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="8">
        <div class="label">最小宽度</div>
        <el-input-number v-model="minW" :min="1" :step="1" style="width: 100%" />
      </el-col>
      <el-col :span="8">
        <div class="label">最小高度</div>
        <el-input-number v-model="minH" :min="1" :step="1" style="width: 100%" />
      </el-col>
      <el-col :span="8">
        <div class="label">随机种子</div>
        <el-input-number v-model="seed" :min="0" :step="1" style="width: 100%" />
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="24">
        <div class="label">输出包名（可选）</div>
        <el-input v-model="name" placeholder="dataset_xxx（默认：dataset_关键词）" />
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="24">
        <div class="label">多模态清洗模型</div>
        <el-select v-model="model" style="width: 100%" placeholder="请选择模型">
          <el-option v-for="item in modelOptions" :key="item" :label="item" :value="item" />
        </el-select>
      </el-col>
    </el-row>

    <div class="actions">
      <el-button :loading="busy" @click="scrapeOnlyRun">开始爬取</el-button>
      <el-button type="primary" :loading="busy" @click="run">开始抓取并清洗</el-button>
    </div>
  </ToolPageShell>
</template>

<style scoped>
.label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 8px 0 6px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 12px;
}
</style>
