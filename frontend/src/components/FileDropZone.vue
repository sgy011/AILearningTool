<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

const props = withDefaults(
  defineProps<{
    accept?: string
    multiple?: boolean
    disabled?: boolean
    title?: string
    description?: string
  }>(),
  {
    accept: '',
    multiple: true,
    disabled: false,
    title: '拖拽文件到此处上传',
    description: '或点击此区域从本地选择文件',
  },
)

const emit = defineEmits<{
  select: [files: File[]]
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
const dragover = ref(false)
let dragDepth = 0

function matchesAccept(file: File, accept: string): boolean {
  const raw = (accept || '').trim()
  if (!raw) return true
  const parts = raw.split(',').map((s) => s.trim()).filter(Boolean)
  for (const p of parts) {
    if (p.startsWith('.')) {
      if (file.name.toLowerCase().endsWith(p.toLowerCase())) return true
    } else if (p.includes('/*')) {
      const pre = p.split('/')[0]
      if (pre && file.type.startsWith(`${pre}/`)) return true
    } else if (file.type === p) {
      return true
    }
  }
  return false
}

function normalizeFiles(fileList: FileList | null): File[] {
  if (!fileList?.length) return []
  let arr = Array.from(fileList)
  if (props.accept) {
    arr = arr.filter((f) => matchesAccept(f, props.accept))
    const dropped = Array.from(fileList)
    if (dropped.length && !arr.length) {
      ElMessage.warning('没有符合格式的文件，请检查类型后重试')
      return []
    }
  }
  if (!props.multiple && arr.length > 1) {
    ElMessage.info('仅支持单个文件，已自动取第一个')
    arr = [arr[0]]
  }
  return props.multiple ? arr : arr.slice(0, 1)
}

function emitFiles(fileList: FileList | null) {
  const files = normalizeFiles(fileList)
  if (files.length) emit('select', files)
}

function onChange(e: Event) {
  const input = e.target as HTMLInputElement
  emitFiles(input.files)
  input.value = ''
}

function triggerPick() {
  if (props.disabled) return
  fileInputRef.value?.click()
}

function onDragEnter(e: DragEvent) {
  e.preventDefault()
  dragDepth++
  dragover.value = true
}

function onDragLeave(e: DragEvent) {
  e.preventDefault()
  dragDepth--
  if (dragDepth <= 0) {
    dragDepth = 0
    dragover.value = false
  }
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  dragDepth = 0
  dragover.value = false
  if (props.disabled) return
  const dt = e.dataTransfer
  if (!dt?.files?.length) return
  emitFiles(dt.files)
}
</script>

<template>
  <div
    class="dropzone"
    :class="{ 'is-drag': dragover, 'is-disabled': disabled }"
    role="button"
    tabindex="0"
    @click="triggerPick"
    @keydown.enter.prevent="triggerPick"
    @keydown.space.prevent="triggerPick"
    @dragenter="onDragEnter"
    @dragleave="onDragLeave"
    @dragover="onDragOver"
    @drop="onDrop"
  >
    <input
      ref="fileInputRef"
      type="file"
      class="sr-only"
      :accept="accept || undefined"
      :multiple="multiple"
      :disabled="disabled"
      @change="onChange"
    />
    <div class="inner">
      <el-icon class="ico"><UploadFilled /></el-icon>
      <div class="title">{{ title }}</div>
      <div class="desc">{{ description }}</div>
      <div v-if="accept" class="accept">支持：{{ accept }}</div>
    </div>
  </div>
</template>

<style scoped>
.dropzone {
  position: relative;
  border-radius: 12px;
  border: 1.5px dashed rgba(99, 102, 241, 0.35);
  background: linear-gradient(145deg, rgba(99, 102, 241, 0.06), rgba(255, 255, 255, 0.65));
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px 16px;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.15s ease;
}
.dropzone:hover:not(.is-disabled) {
  border-color: rgba(80, 176, 240, 0.55);
  background: linear-gradient(145deg, rgba(80, 176, 240, 0.1), rgba(255, 255, 255, 0.85));
  box-shadow: 0 6px 20px rgba(80, 176, 240, 0.12);
}
.dropzone.is-drag {
  border-color: #50b0f0;
  border-style: solid;
  background: linear-gradient(145deg, rgba(80, 176, 240, 0.16), rgba(255, 255, 255, 0.95));
  box-shadow: 0 8px 28px rgba(80, 176, 240, 0.2);
  transform: scale(1.01);
}
.dropzone.is-disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}
.inner {
  text-align: center;
  max-width: 420px;
}
.ico {
  font-size: 36px;
  color: #6366f1;
  margin-bottom: 8px;
}
.title {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 4px;
}
.desc {
  font-size: 13px;
  color: #64748b;
  line-height: 1.45;
}
.accept {
  margin-top: 8px;
  font-size: 12px;
  color: #94a3b8;
  word-break: break-all;
}
</style>
