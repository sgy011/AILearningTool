<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Close } from '@element-plus/icons-vue'
import ToolPageShell from '../components/ToolPageShell.vue'
import { imageAugment, imageAugmentOptions } from '../api/augment'
import { normalizeApiError } from '../api/http'
import { downloadBlob } from '../api/download'
import { toFileList } from '../utils/files'
import FileDropZone from '../components/FileDropZone.vue'

const files = ref<File[]>([])
const ops = ref<string[]>([])
const fmt = ref<'png' | 'jpg' | 'webp'>('png')
const quality = ref(90)
const busy = ref(false)
const options = ref<{ id: string; label: string }[]>([])

async function loadOps() {
  try {
    const d = await imageAugmentOptions()
    const raw = Array.isArray(d?.options) ? d.options : Array.isArray(d?.ops) ? d.ops : null
    if (d?.success && Array.isArray(raw) && raw.length) {
      options.value = raw.map((x: any) => {
        if (typeof x === 'string') return { id: x, label: x }
        return { id: x.id, label: x.label || x.id }
      })
    } else {
      // fallback（保持与旧版更接近）
      options.value = [
        { id: 'hflip', label: '水平翻转' },
        { id: 'vflip', label: '垂直翻转' },
        { id: 'rot90', label: '旋转 90°' },
        { id: 'rot180', label: '旋转 180°' },
        { id: 'rot270', label: '旋转 270°' },
        { id: 'brightness_up', label: '亮度提高' },
        { id: 'brightness_down', label: '亮度降低' },
        { id: 'contrast_up', label: '对比度提高' },
        { id: 'color_up', label: '饱和度提高' },
        { id: 'sharpness', label: '锐化' },
        { id: 'blur', label: '轻度模糊' },
        { id: 'edge_enhance', label: '边缘增强' },
        { id: 'grayscale', label: '灰度（导出为 RGB）' },
      ]
    }
  } catch {
    options.value = [
      { id: 'hflip', label: '水平翻转' },
      { id: 'vflip', label: '垂直翻转' },
      { id: 'rot90', label: '旋转 90°' },
      { id: 'rot180', label: '旋转 180°' },
      { id: 'rot270', label: '旋转 270°' },
      { id: 'brightness_up', label: '亮度提高' },
      { id: 'brightness_down', label: '亮度降低' },
      { id: 'contrast_up', label: '对比度提高' },
      { id: 'color_up', label: '饱和度提高' },
      { id: 'sharpness', label: '锐化' },
      { id: 'blur', label: '轻度模糊' },
      { id: 'edge_enhance', label: '边缘增强' },
      { id: 'grayscale', label: '灰度（导出为 RGB）' },
    ]
  }
}
loadOps()

function onPick(list: FileList | null) {
  if (!list) return
  Array.from(list).forEach((f) => files.value.push(f))
}

function onFilesFromZone(selected: File[]) {
  onPick(toFileList(selected))
}

function clear() {
  files.value = []
  ops.value = []
}

function selectAllOps() {
  ops.value = options.value.map((o) => o.id)
}

function clearOps() {
  ops.value = []
}

async function run() {
  if (!files.value.length) return ElMessage.error('请先选择图片')
  if (!ops.value.length) return ElMessage.error('请至少选择一种增强类型')
  busy.value = true
  try {
    const blob = await imageAugment({
      files: files.value,
      ops: ops.value,
      format: fmt.value,
      quality: quality.value,
    })
    downloadBlob(blob, 'image_augment.zip')
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
    title="图片数据增强"
    subtitle="几何变换与色彩增强组合，批量扩充训练样本并打包下载。"
  >
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      一次上传多张图片；勾选增强类型后，每张原图会按所选类型各生成一张增强图，并打包 ZIP 下载。
    </el-alert>

    <div style="margin-bottom: 12px">
      <FileDropZone
        accept="image/*"
        :multiple="true"
        title="拖拽图片到此处"
        description="支持多选；也可点击选择文件"
        @select="onFilesFromZone"
      />
      <div class="file-list" v-if="files.length">
        <div class="file-item" v-for="(f, i) in files" :key="i">
          <span class="file-name" :title="f.name">{{ f.name }}</span>
          <el-icon class="file-remove" @click="files.splice(i, 1)"><Close /></el-icon>
        </div>
      </div>
    </div>

    <el-card shadow="never" style="margin-bottom: 12px">
      <template #header>
        <div class="ops-header">
          <span>增强类型（可多选）</span>
          <div class="ops-actions">
            <el-button text type="primary" size="small" @click="selectAllOps">全选</el-button>
            <el-button text size="small" @click="clearOps">清空选择</el-button>
          </div>
        </div>
      </template>
      <el-checkbox-group v-model="ops">
        <el-checkbox v-for="o in options" :key="o.id" :value="o.id">{{ o.label }}</el-checkbox>
      </el-checkbox-group>
    </el-card>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="8">
        <div class="label">输出格式</div>
        <el-select v-model="fmt" style="width: 100%">
          <el-option value="png" label="PNG" />
          <el-option value="jpg" label="JPG" />
          <el-option value="webp" label="WEBP" />
        </el-select>
      </el-col>
      <el-col :span="8">
        <div class="label">质量（JPG/WEBP）</div>
        <el-input-number v-model="quality" :min="60" :max="100" style="width: 100%" />
      </el-col>
      <el-col :span="8" style="display:flex; align-items:end; justify-content:end;">
        <div class="actions">
          <el-button @click="clear" :disabled="busy">清空</el-button>
          <el-button type="primary" :loading="busy" @click="run">生成并下载 ZIP</el-button>
        </div>
      </el-col>
    </el-row>
  </ToolPageShell>
</template>

<style scoped>
.muted {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 6px;
}
.file-list {
  margin-top: 8px;
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 4px 0;
}
.file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.file-item:hover {
  background: var(--el-fill-color-light);
}
.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 8px;
}
.file-remove {
  cursor: pointer;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.file-remove:hover {
  color: var(--el-color-danger);
}
.label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.actions {
  display: flex;
  gap: 8px;
}
.ops-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.ops-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>

