<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ToolPageShell from '../components/ToolPageShell.vue'
import { docsMergeConvert } from '../api/docs'
import { normalizeApiError } from '../api/http'
import { downloadBlob } from '../api/download'
import { toFileList } from '../utils/files'
import FileDropZone from '../components/FileDropZone.vue'

type Item = { file: File }
const items = ref<Item[]>([])
const outFormat = ref<'docx' | 'pdf' | 'xlsx'>('docx')
const name = ref('')
const busy = ref(false)
const headerCaseInsensitive = ref(true)
const columnMergeMode = ref<'union' | 'intersection'>('union')

function onPick(list: FileList | null) {
  if (!list) return
  Array.from(list).forEach((f) => items.value.push({ file: f }))
}

function onFilesFromZone(selected: File[]) {
  onPick(toFileList(selected))
}

function removeAt(i: number) {
  items.value.splice(i, 1)
}

function move(i: number, dir: -1 | 1) {
  const j = i + dir
  if (j < 0 || j >= items.value.length) return
  const tmp = items.value[i]
  items.value[i] = items.value[j]
  items.value[j] = tmp
}

const order = computed(() => items.value.map((_, idx) => idx))
const isExcelMerge = computed(
  () =>
    items.value.length > 0 &&
    items.value.every((x) => /\.(xlsx|xlsm)$/i.test(x.file.name)),
)

async function run() {
  if (items.value.length < 1) return ElMessage.error('请先选择文档')
  busy.value = true
  try {
    const blob = await docsMergeConvert({
      files: items.value.map((x) => x.file),
      order: order.value,
      out_format: outFormat.value,
      name: name.value.trim() || undefined,
      header_case_insensitive: headerCaseInsensitive.value,
      column_merge_mode: columnMergeMode.value,
    })
    const dlName = `${(name.value.trim() || 'merged')}.${outFormat.value}`
    downloadBlob(blob, dlName)
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
    title="文档合并与转换"
    subtitle="多文档按顺序合并，支持 Word / PDF 与 Excel 表格汇总导出。"
  >
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      支持 .docx 合并并导出 docx/pdf；支持 .xlsx/.xlsm 合并导出 xlsx。可调整顺序并删除。
    </el-alert>

    <div style="margin-bottom: 12px">
      <FileDropZone
        accept=".docx,.xlsx,.xlsm"
        :multiple="true"
        title="拖拽文档到此处"
        description="支持多选 Word / Excel；也可点击选择文件"
        @select="onFilesFromZone"
      />
    </div>

    <el-table :data="items" size="small" style="width: 100%; margin-bottom: 12px" v-if="items.length">
      <el-table-column label="顺序" width="70">
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column label="文件" min-width="260">
        <template #default="{ row }">{{ row.file.name }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ $index }">
          <el-button size="small" @click="move($index, -1)" :disabled="$index===0">上移</el-button>
          <el-button size="small" @click="move($index, 1)" :disabled="$index===items.length-1">下移</el-button>
          <el-button size="small" type="danger" @click="removeAt($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="8">
        <div class="label">输出格式</div>
        <el-select v-model="outFormat" style="width: 100%">
          <el-option value="docx" label="DOCX" />
          <el-option value="pdf" label="PDF" />
          <el-option value="xlsx" label="XLSX（仅 Excel 合并时有效）" />
        </el-select>
      </el-col>
      <el-col :span="16">
        <div class="label">输出文件名（可选）</div>
        <el-input v-model="name" placeholder="merged（默认）" />
      </el-col>
    </el-row>

    <el-card
      v-if="isExcelMerge"
      shadow="never"
      style="margin-bottom: 12px; background: var(--el-fill-color-lighter)"
    >
      <div class="label">Excel 列匹配策略</div>
      <el-row :gutter="12">
        <el-col :span="14">
          <div class="label">行列不一致处理</div>
          <el-select v-model="columnMergeMode" style="width: 100%">
            <el-option value="union" label="补齐相同列，额外列追加到后面" />
            <el-option value="intersection" label="只合并相同列（共同列）" />
          </el-select>
        </el-col>
        <el-col :span="10" style="display: flex; align-items: end">
          <el-switch
            v-model="headerCaseInsensitive"
            active-text="列名大小写不敏感（Name = name）"
          />
        </el-col>
      </el-row>
    </el-card>

    <div class="actions">
      <el-button type="primary" @click="run" :loading="busy">合并并导出</el-button>
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
}
</style>

