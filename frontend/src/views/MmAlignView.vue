<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ToolPageShell from '../components/ToolPageShell.vue'
import { getMmAlignModels, mmAlignScrapeCleanCaption, mmAlignUploadCaption } from '../api/dataset'
import { normalizeApiError } from '../api/http'
import { downloadBlob } from '../api/download'

const query = ref('')
const count = ref(50)
const minW = ref(256)
const minH = ref(256)
const seed = ref(42)
const name = ref('')
const exportFormat = ref<'txt' | 'jsonl' | 'csv'>('txt')
const model = ref('')
const modelOptions = ref<string[]>([])
const uploadName = ref('')
const uploadFiles = ref<File[]>([])
const uploadBusy = ref(false)
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
    const defaultName = name.value.trim() || `dataset_${query.value.trim()}`
    const { blob, filename } = await mmAlignScrapeCleanCaption({
      query: query.value.trim(),
      count: count.value,
      min_width: minW.value,
      min_height: minH.value,
      seed: seed.value,
      export_format: exportFormat.value,
      model: model.value || undefined,
      name: name.value.trim() || undefined,
    })
    downloadBlob(blob, filename || `${defaultName}.zip`)
    ElMessage.success('已开始下载')
  } catch (e) {
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    busy.value = false
  }
}

function onUploadFilesChanged(_file: any, fileList: any[]) {
  uploadFiles.value = (fileList || []).map((f: any) => f.raw).filter(Boolean)
}

function onUploadFilesExceed(files: File[]) {
  uploadFiles.value = files
}

async function runUploadCaption() {
  if (!uploadFiles.value.length) return ElMessage.error('请先选择图片')
  uploadBusy.value = true
  try {
    const { blob, filename } = await mmAlignUploadCaption({
      files: uploadFiles.value,
      export_format: exportFormat.value,
      model: model.value || undefined,
      name: uploadName.value.trim() || undefined,
      query: query.value.trim() || undefined,
    })
    const ext = exportFormat.value
    const fallbackName = `${uploadName.value.trim() || 'captions'}.${ext}`
    downloadBlob(blob, filename || fallbackName)
    ElMessage.success('已开始下载')
  } catch (e) {
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    uploadBusy.value = false
  }
}
</script>

<template>
  <ToolPageShell
    title="多模态图文对齐"
    subtitle="图片清洗后生成20字描述，或上传已有图片批量生成描述导出。"
  >
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      支持两种流程：1）百度图片抓取+清洗后生成20字描述并打包下载；2）上传已有图片或 zip 批量生成20字描述并导出。
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
      <el-col :span="16">
        <div class="label">输出包名（可选）</div>
        <el-input v-model="name" placeholder="dataset_xxx（默认：dataset_关键词）" />
      </el-col>
      <el-col :span="8">
        <div class="label">描述导出格式</div>
        <el-select v-model="exportFormat" style="width: 100%">
          <el-option label="TXT" value="txt" />
          <el-option label="JSONL" value="jsonl" />
          <el-option label="CSV" value="csv" />
        </el-select>
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="24">
        <div class="label">多模态模型</div>
        <el-select v-model="model" style="width: 100%" placeholder="请选择模型">
          <el-option v-for="item in modelOptions" :key="item" :label="item" :value="item" />
        </el-select>
      </el-col>
    </el-row>

    <div class="actions">
      <el-button type="primary" :loading="busy" @click="run">抓取+清洗+20字描述</el-button>
    </div>

    <el-divider />
    <h4 class="sub-title">上传已有图片生成20字描述</h4>
    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="16">
        <div class="label">图片文件/zip（可多选）</div>
        <el-upload
          :auto-upload="false"
          :on-change="onUploadFilesChanged"
          :on-exceed="onUploadFilesExceed"
          :file-list="[]"
          accept="image/*,.zip,application/zip"
          multiple
        >
          <template #trigger>
            <el-button>选择图片</el-button>
          </template>
        </el-upload>
      </el-col>
      <el-col :span="8">
        <div class="label">导出文件名（可选）</div>
        <el-input v-model="uploadName" placeholder="captions" />
      </el-col>
    </el-row>
    <div class="actions">
      <el-button type="success" :loading="uploadBusy" @click="runUploadCaption">上传并生成描述</el-button>
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
.sub-title {
  margin: 0 0 12px;
  font-size: 16px;
  font-weight: 600;
}
</style>
