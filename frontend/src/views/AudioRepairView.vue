<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ToolPageShell from '../components/ToolPageShell.vue'
import { normalizeApiError } from '../api/http'
import { repairAudio } from '../api/audio'
import { downloadBlob } from '../api/download'
import { base64ToBlob } from '../utils/base64'
import { toFileList } from '../utils/files'
import FileDropZone from '../components/FileDropZone.vue'

type Item = { file: File; status: 'pending' | 'done' | 'error'; error?: string }

const files = ref<Item[]>([])
const mode = ref<'repair' | 'convert'>('repair')
const format = ref<'wav' | 'mp3' | 'm4a' | 'flac' | 'ogg'>('wav')
const quality = ref(320)
const autoDetectMono = ref(true)
const enhanceStereo = ref(true)
const busy = ref(false)
const doneCount = computed(() => files.value.filter((f) => f.status === 'done').length)

function onPick(list: FileList | null) {
  if (!list) return
  Array.from(list).forEach((f) => {
    if (files.value.some((x) => x.file.name === f.name && x.file.size === f.size)) return
    files.value.push({ file: f, status: 'pending' })
  })
}

function onFilesFromZone(selected: File[]) {
  onPick(toFileList(selected))
}

function removeAt(i: number) {
  files.value.splice(i, 1)
}

function reset() {
  files.value = []
}

function mimeOf(fmt: string) {
  if (fmt === 'wav') return 'audio/wav'
  if (fmt === 'mp3') return 'audio/mpeg'
  if (fmt === 'm4a') return 'audio/mp4'
  if (fmt === 'flac') return 'audio/flac'
  if (fmt === 'ogg') return 'audio/ogg'
  return 'application/octet-stream'
}

async function run() {
  if (!files.value.length) return ElMessage.error('请先选择音频文件')
  busy.value = true
  try {
    for (let i = 0; i < files.value.length; i++) {
      const it = files.value[i]
      if (it.status === 'done') continue
      it.status = 'pending'
      try {
        const d = await repairAudio({
          file: it.file,
          format: format.value,
          quality: quality.value,
          auto_detect_mono: autoDetectMono.value,
          enhance_stereo: enhanceStereo.value,
          mode: mode.value,
        })
        if (!d.success || !d.repaired_data) throw new Error(d.error || '处理失败')
        const blob = base64ToBlob(d.repaired_data, mimeOf(format.value))
        const base = it.file.name.replace(/\.[^/.]+$/, '')
        downloadBlob(blob, `${base}.${format.value}`)
        it.status = 'done'
      } catch (e: any) {
        it.status = 'error'
        it.error = normalizeApiError(e).message
      }
    }
    ElMessage.success(`处理完成：${doneCount.value}/${files.value.length}`)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ToolPageShell
    title="音频修复与转换"
    subtitle="响度标准化、声道增强与多格式转码，适合播客与素材批量处理。"
  >
    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="24">
        <el-alert type="info" :closable="false" show-icon>
          修复模式会做单声道转立体声、立体声增强与响度标准化；仅格式转换则只转码。
        </el-alert>
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="8">
        <div class="label">模式</div>
        <el-radio-group v-model="mode">
          <el-radio-button value="convert">仅格式转换</el-radio-button>
          <el-radio-button value="repair">修复并导出</el-radio-button>
        </el-radio-group>
      </el-col>
      <el-col :span="8">
        <div class="label">输出格式</div>
        <el-select v-model="format" style="width: 100%">
          <el-option value="wav" label="WAV" />
          <el-option value="mp3" label="MP3" />
          <el-option value="m4a" label="M4A" />
          <el-option value="flac" label="FLAC" />
          <el-option value="ogg" label="OGG" />
        </el-select>
      </el-col>
      <el-col :span="8">
        <div class="label">质量（kbps，有损格式）</div>
        <el-input-number v-model="quality" :min="64" :max="320" :step="32" style="width: 100%" />
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="12">
        <el-checkbox v-model="autoDetectMono" :disabled="mode !== 'repair'">自动检测并修复单音道</el-checkbox>
      </el-col>
      <el-col :span="12">
        <el-checkbox v-model="enhanceStereo" :disabled="mode !== 'repair'">增强立体声效果</el-checkbox>
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="24">
        <FileDropZone
          accept="audio/*"
          :multiple="true"
          title="拖拽音频到此处"
          description="支持多选；也可点击选择文件"
          @select="onFilesFromZone"
        />
      </el-col>
    </el-row>

    <el-table :data="files" size="small" style="width: 100%; margin-bottom: 12px" v-if="files.length">
      <el-table-column label="文件" min-width="240">
        <template #default="{ row }">{{ row.file.name }}</template>
      </el-table-column>
      <el-table-column label="大小" width="120">
        <template #default="{ row }">{{ Math.round(row.file.size / 1024) }} KB</template>
      </el-table-column>
      <el-table-column label="状态" width="140">
        <template #default="{ row }">
          <el-tag v-if="row.status === 'done'" type="success">完成</el-tag>
          <el-tag v-else-if="row.status === 'error'" type="danger">失败</el-tag>
          <el-tag v-else type="info">待处理</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="错误" min-width="220">
        <template #default="{ row }">{{ row.error || '' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ $index }">
          <el-button link type="danger" @click="removeAt($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="actions">
      <el-button @click="reset" :disabled="busy">清空</el-button>
      <el-button type="primary" @click="run" :loading="busy">开始处理</el-button>
    </div>
  </ToolPageShell>
</template>

<style scoped>
.label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>

