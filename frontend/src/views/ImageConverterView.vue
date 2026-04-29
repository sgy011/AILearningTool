<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ToolPageShell from '../components/ToolPageShell.vue'
import { convertImage } from '../api/image'
import { normalizeApiError } from '../api/http'
import { downloadBlob } from '../api/download'
import { base64ToBlob } from '../utils/base64'
import { toFileList } from '../utils/files'
import FileDropZone from '../components/FileDropZone.vue'

type Item = { file: File; status: 'pending' | 'done' | 'error'; error?: string }

const files = ref<Item[]>([])
const mode = ref<'convert' | 'repair'>('convert')
const format = ref<'png' | 'jpg' | 'webp' | 'bmp' | 'gif'>('png')
const qualityPercent = ref(85)
const busy = ref(false)
const doneCount = computed(() => files.value.filter((f) => f.status === 'done').length)

function onPick(list: FileList | null) {
  if (!list) return
  const arr = Array.from(list)
  arr.forEach((f) => {
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

async function run() {
  if (!files.value.length) return ElMessage.error('请先选择图片')
  busy.value = true
  try {
    for (let i = 0; i < files.value.length; i++) {
      const it = files.value[i]
      if (it.status === 'done') continue
      it.status = 'pending'
      try {
        const d = await convertImage({
          file: it.file,
          format: format.value,
          quality: qualityPercent.value / 100,
          mode: mode.value,
        })
        if (!d.success || !d.converted_data) throw new Error(d.error || '转换失败')
        const mime =
          format.value === 'png'
            ? 'image/png'
            : format.value === 'jpg'
              ? 'image/jpeg'
              : format.value === 'webp'
                ? 'image/webp'
                : format.value === 'bmp'
                  ? 'image/bmp'
                  : 'image/gif'
        const blob = base64ToBlob(d.converted_data, mime)
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
    title="图片修复与转换"
    subtitle="批量格式转换与画质修复，适用于素材整理与发布前处理。"
  >
    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="24">
        <el-alert type="info" :closable="false" show-icon>
          支持 PNG/JPG/WEBP/BMP/GIF。模式选择“修复并导出”会按 EXIF 转正、自动对比度并轻度锐化。
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
        <div class="label">目标格式</div>
        <el-select v-model="format" style="width: 100%">
          <el-option value="png" label="PNG" />
          <el-option value="jpg" label="JPG" />
          <el-option value="webp" label="WEBP" />
          <el-option value="bmp" label="BMP" />
          <el-option value="gif" label="GIF" />
        </el-select>
      </el-col>
      <el-col :span="8">
        <div class="label">质量（JPG/WEBP）</div>
        <el-slider v-model="qualityPercent" :min="1" :max="100" />
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="24">
        <FileDropZone
          accept="image/*"
          :multiple="true"
          title="拖拽图片到此处"
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

