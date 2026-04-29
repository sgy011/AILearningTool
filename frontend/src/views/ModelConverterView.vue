<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import ToolPageShell from '../components/ToolPageShell.vue'
import { getModelFormats, convertModel } from '../api/model'
import { normalizeApiError } from '../api/http'
import { downloadBlob } from '../api/download'
import { base64ToBlob } from '../utils/base64'
import { toFileList } from '../utils/files'
import FileDropZone from '../components/FileDropZone.vue'

const formats = ref<any>(null)
const loadingFormats = ref(false)

const files = ref<File[]>([])
const outFormat = ref('onnx')
const inputShape = ref('1,3,224,224')
const opset = ref(12)
const busy = ref(false)

async function loadFormats() {
  loadingFormats.value = true
  try {
    const d = await getModelFormats()
    formats.value = d
    if (Array.isArray(d?.output_formats) && d.output_formats.length) outFormat.value = d.output_formats[0]
  } catch (e) {
    formats.value = null
  } finally {
    loadingFormats.value = false
  }
}
loadFormats()

function onPick(list: FileList | null) {
  if (!list) return
  files.value = Array.from(list)
}

function onFilesFromZone(selected: File[]) {
  onPick(toFileList(selected))
}

function removeAt(index: number) {
  files.value.splice(index, 1)
}

function clearFiles() {
  files.value = []
}

async function run() {
  if (!files.value.length) return ElMessage.error('请先选择模型文件')
  busy.value = true
  try {
    for (const f of files.value) {
      const d = await convertModel({
        file: f,
        format: outFormat.value,
        input_shape: inputShape.value || undefined,
        opset_version: opset.value,
      })
      if (!d.success || !d.converted_data) throw new Error(d.error || '转换失败')
      const blob = base64ToBlob(d.converted_data, 'application/octet-stream')
      const base = f.name.replace(/\.[^/.]+$/, '')
      downloadBlob(blob, `${base}.${outFormat.value}`)
    }
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
    title="模型转换"
    subtitle="跨框架模型格式互转，便于部署与多端推理管线对接。"
  >
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      支持 PyTorch/ONNX/Keras/TensorFlow/TFLite 等（依赖不完整时会提示不可用）。
    </el-alert>

    <div class="muted" v-if="formats && formats.available_libs">
      可用库：ultralytics={{ formats.available_libs.ultralytics ? 'yes' : 'no' }}，torch={{ formats.available_libs.torch ? 'yes' : 'no' }}，
      onnx={{ formats.available_libs.onnx ? 'yes' : 'no' }}，tensorflow={{ formats.available_libs.tensorflow ? 'yes' : 'no' }}，keras={{ formats.available_libs.keras ? 'yes' : 'no' }}
    </div>

    <div style="margin: 12px 0">
      <FileDropZone
        :multiple="true"
        accept=".pt,.pth,.pkl,.h5,.keras,.onnx,.pb,.tflite,.mar"
        title="拖拽模型文件到此处"
        description="支持多选；也可点击选择文件"
        @select="onFilesFromZone"
      />
      <div class="muted" v-if="files.length" style="margin-top: 8px">已选择 {{ files.length }} 个模型文件</div>
    </div>

    <el-table v-if="files.length" :data="files" size="small" style="width: 100%; margin-bottom: 12px">
      <el-table-column label="文件名" min-width="320">
        <template #default="{ row }">{{ row.name }}</template>
      </el-table-column>
      <el-table-column label="大小" width="120">
        <template #default="{ row }">{{ Math.round(row.size / 1024) }} KB</template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ $index }">
          <el-button link type="danger" @click="removeAt($index)">移除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="8">
        <div class="label">目标格式</div>
        <el-select v-model="outFormat" style="width: 100%">
          <el-option v-for="f in (formats?.output_formats || ['onnx','tflite','pt'])" :key="f" :value="f" :label="String(f)" />
        </el-select>
      </el-col>
      <el-col :span="8">
        <div class="label">输入形状（PyTorch→ONNX 常用）</div>
        <el-input v-model="inputShape" placeholder="1,3,224,224" />
      </el-col>
      <el-col :span="8">
        <div class="label">ONNX Opset</div>
        <el-input-number v-model="opset" :min="11" :max="17" style="width: 100%" />
      </el-col>
    </el-row>

    <div class="actions">
      <el-button @click="clearFiles" :disabled="busy || !files.length">清空文件</el-button>
      <el-button type="primary" :loading="busy" @click="run">批量转换并下载</el-button>
    </div>
  </ToolPageShell>
</template>

<style scoped>
.muted {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.actions {
  display: flex;
  justify-content: flex-end;
}
</style>

