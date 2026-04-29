<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ToolPageShell from '../components/ToolPageShell.vue'
import { filenameFromContentDisposition, downloadBlob } from '../api/download'
import { normalizeApiError } from '../api/http'
import { getTextCleanConfig, textCleanExport, textCleanPreview } from '../api/textClean'
import FileDropZone from '../components/FileDropZone.vue'

const title = ref('')
const instructionsOrContent = ref('')
const useAi = true
const sourceMode = ref<'paste' | 'generate'>('paste')
const genKind = ref<'article' | 'table'>('article')
const format = ref<'pdf' | 'docx' | 'xlsx'>('pdf')
const file = ref<File | null>(null)
const fileTable = computed(() => (file.value ? [file.value] : []))
const quickMode = ref<'clean' | 'generate' | 'rewrite'>('clean')

const cfgLoaded = ref(false)
const cfgText = ref('')

const previewBusy = ref(false)
const exportBusy = ref(false)
const previewText = ref('')
const previewMethod = ref('')

const isOffice = computed(() => !!file.value && /\.(docx|xlsx|xlsm)$/i.test(file.value.name))
const isTextFile = computed(() => !!file.value && /\.txt$/i.test(file.value.name))
const inputLabel = computed(() => {
  if (isOffice.value) return '处理要求（必填）'
  return sourceMode.value === 'generate' ? '生成提示词（必填）' : '正文内容'
})

function setQuickMode(mode: 'clean' | 'generate' | 'rewrite') {
  quickMode.value = mode
  if (mode === 'generate') {
    sourceMode.value = 'generate'
    if (!title.value.trim()) title.value = '智能生成文稿'
    return
  }
  sourceMode.value = 'paste'
  if (mode === 'rewrite') {
    if (!title.value.trim()) title.value = '文档改写结果'
    return
  }
  if (!title.value.trim()) title.value = '文稿'
}

function onFileSelected(files: File[]) {
  file.value = files[0] || null
  if (file.value && isOffice.value) {
    quickMode.value = 'rewrite'
    sourceMode.value = 'paste'
  }
}

async function loadConfig() {
  try {
    const d = await getTextCleanConfig()
    if (!d.success) throw new Error(d.error || '加载失败')
    cfgLoaded.value = true
    cfgText.value = d.ai_available ? 'AI 可用' : 'AI 不可用（未配置 Token）'
  } catch (e) {
    cfgLoaded.value = true
    cfgText.value = '配置加载失败'
  }
}
loadConfig()

async function onPreview() {
  previewBusy.value = true
  previewText.value = ''
  try {
    if (isOffice.value) {
      const d = await textCleanPreview({
        use_ai: useAi,
        file: file.value,
        instructions: instructionsOrContent.value,
        title: title.value || undefined,
        gen_kind: genKind.value,
        format: format.value,
      } as any)
      // office preview 返回 cleaned/method
      if (!d.success) throw new Error(d.error || '预览失败')
      previewText.value = d.cleaned || ''
      previewMethod.value = d.method || ''
    } else {
      const textInput = (instructionsOrContent.value || '').trim()
      const textFromFile = isTextFile.value && file.value ? (await file.value.text()).trim() : ''
      const d =
        sourceMode.value === 'generate'
          ? await textCleanPreview({
              source: 'generate',
              use_ai: useAi,
              prompt: textInput,
              gen_kind: genKind.value,
            } as any)
          : await textCleanPreview({
              source: 'paste',
              use_ai: useAi,
              text: textInput || textFromFile,
              gen_kind: genKind.value,
            } as any)
      if (!d.success) throw new Error(d.error || '预览失败')
      previewText.value = d.cleaned || ''
      previewMethod.value = d.method || ''
    }
  } catch (e) {
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    previewBusy.value = false
  }
}

async function onExport() {
  exportBusy.value = true
  try {
    const fd = new FormData()
    fd.append('use_ai', 'true')
    fd.append('format', format.value)
    fd.append('title', title.value || '')
    fd.append('gen_kind', genKind.value)

    if (isOffice.value) {
      // Office file fill
      fd.append('source', 'file_fill')
      fd.append('file', file.value as File)
      fd.append('instructions', instructionsOrContent.value || '')
      fd.append('original_filename', file.value?.name || '')
    } else {
      const t = (instructionsOrContent.value || '').trim()
      if (sourceMode.value === 'generate') {
        fd.append('source', 'generate')
        if (!t) throw new Error('请输入生成提示词')
        fd.append('prompt', t)
      } else {
        fd.append('source', 'paste')
        if (t) {
          fd.append('text', t)
        } else if (isTextFile.value && file.value) {
          fd.append('file', file.value)
        } else {
          throw new Error('请输入正文内容，或上传 .txt 文件')
        }
      }
    }

    const res = await textCleanExport(fd)
    const ct = res.headers.get('Content-Type') || ''
    if (ct.includes('application/json')) {
      const j = await res.json()
      throw new Error(j.error || '导出失败')
    }
    const blob = await res.blob()
    const cd = res.headers.get('Content-Disposition')
    const fn = filenameFromContentDisposition(cd) || `${title.value || '文稿'}.${format.value}`
    downloadBlob(blob, fn)
    ElMessage.success('已开始下载')
  } catch (e) {
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    exportBusy.value = false
  }
}
</script>

<template>
  <ToolPageShell
    title="文档文稿处理"
    subtitle="支持文本清理、提示词编写文档、按要求改写文档并保持原格式。"
  >
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      1) 清理其它来源粘贴文本并写入文档返回；2) 根据提示词要求编写文档返回；3) 按要求编写/修改文档并尽量保持格式不变。配置状态：{{ cfgText }}
    </el-alert>

    <div class="mode-cards">
      <button
        type="button"
        class="mode-card"
        :class="{ active: quickMode === 'clean' }"
        @click="setQuickMode('clean')"
      >
        <div class="mode-title">1. 清理粘贴文本</div>
        <div class="mode-desc">清理其它来源粘贴的正文，并导出文档返回。</div>
      </button>
      <button
        type="button"
        class="mode-card"
        :class="{ active: quickMode === 'generate' }"
        @click="setQuickMode('generate')"
      >
        <div class="mode-title">2. 提示词编写文档</div>
        <div class="mode-desc">根据提示词要求生成完整文档并返回。</div>
      </button>
      <button
        type="button"
        class="mode-card"
        :class="{ active: quickMode === 'rewrite' }"
        @click="setQuickMode('rewrite')"
      >
        <div class="mode-title">3. 按要求改写文档</div>
        <div class="mode-desc">上传 Word/Excel，按要求编写或修改并尽量保持格式不变。</div>
      </button>
    </div>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="12">
        <div class="label">导出文件名（可选）</div>
        <el-input v-model="title" placeholder="不填则使用默认名" />
      </el-col>
      <el-col :span="12">
        <div class="label">导出格式</div>
        <el-select v-model="format" style="width: 100%">
          <el-option value="pdf" label="PDF" />
          <el-option value="docx" label="Word (.docx)" />
          <el-option value="xlsx" label="Excel (.xlsx)" />
        </el-select>
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="12">
        <div class="label">生成类型（提示词生成时）</div>
        <el-select v-model="genKind" style="width: 100%" :disabled="isOffice || sourceMode !== 'generate'">
          <el-option value="article" label="文章 / 段落" />
          <el-option value="table" label="表格数据" />
        </el-select>
      </el-col>
      <el-col :span="12" />
    </el-row>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="24">
        <div class="label">上传文件（可选，.txt/.docx/.xlsx/.xlsm）</div>
        <FileDropZone
          accept=".txt,.docx,.xlsx,.xlsm"
          :multiple="false"
          title="拖拽文件到此处"
          description="单个文件；也可点击选择"
          @select="onFileSelected"
        />
      </el-col>
    </el-row>

    <el-table :data="fileTable" size="small" style="width: 100%; margin-bottom: 12px" v-if="file">
      <el-table-column label="文件" min-width="240">
        <template #default>{{ file!.name }}</template>
      </el-table-column>
      <el-table-column label="大小" width="120">
        <template #default>{{ Math.round(file!.size / 1024) }} KB</template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default>
          <el-button link type="danger" @click="file = null">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="label">{{ inputLabel }}</div>
    <el-input
      v-model="instructionsOrContent"
      type="textarea"
      :rows="10"
      :placeholder="
        isOffice
          ? '上传 Word/Excel 后，请输入处理要求（例如：补全文档第3节并统一术语）。'
          : sourceMode === 'generate'
            ? '请输入生成提示词（主题、风格、结构要求等）。'
            : '请输入正文，或上传 .txt 文件。'
      "
    />

    <div class="actions">
      <el-button :loading="previewBusy" @click="onPreview">仅预览清理结果</el-button>
      <el-button type="primary" :loading="exportBusy" @click="onExport">清理并下载</el-button>
    </div>

    <div v-if="previewText" style="margin-top: 12px">
      <div class="label">预览（{{ previewMethod }}）</div>
      <el-card shadow="never">
        <pre class="pre">{{ previewText }}</pre>
      </el-card>
    </div>
  </ToolPageShell>
</template>

<style scoped>
.label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 8px 0 6px;
}
.mode-cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
  width: 100%;
}
.mode-card {
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-blank);
  border-radius: 10px;
  padding: 14px 16px;
  text-align: left;
  cursor: pointer;
  min-height: 112px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}
.mode-card:hover {
  border-color: var(--el-color-primary-light-3);
  transform: translateY(-1px);
}
.mode-card.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--el-color-primary) 18%, transparent);
}
.mode-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 6px;
}
.mode-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  margin-top: auto;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
.pre {
  white-space: pre-wrap;
  margin: 0;
  font-size: 13px;
}
.muted {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
@media (max-width: 1024px) {
  .mode-cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 760px) {
  .mode-cards {
    grid-template-columns: 1fr;
  }
}
</style>

