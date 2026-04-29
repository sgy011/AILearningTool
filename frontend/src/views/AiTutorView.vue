<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ToolPageShell from '../components/ToolPageShell.vue'
import { aiTutorChat, kbIngest } from '../api/aiTutor'
import { normalizeApiError } from '../api/http'

const ingestBusy = ref(false)
const ingestMsg = ref('')

const message = ref('')
const busy = ref(false)
const answer = ref('')
const sources = ref<any[]>([])

type Segment = { type: 'text'; content: string } | { type: 'code'; content: string; lang: string }

const answerSegments = computed<Segment[]>(() => parseAnswer(answer.value))

function parseAnswer(raw: string): Segment[] {
  if (!raw) return []
  const out: Segment[] = []
  // 逐行解析：遇到 ``` 开头行则进入代码块模式，再遇 ``` 则退出
  const lines = raw.split(/\r?\n/)
  let inCode = false
  let lang = ''
  let codeLines: string[] = []
  let textLines: string[] = []

  function flushText() {
    if (textLines.length) {
      const t = textLines.join('\n')
      if (t.trim()) out.push({ type: 'text', content: t })
      textLines = []
    }
  }
  function flushCode() {
    const c = codeLines.join('\n').replace(/\s+$/, '')
    if (c) out.push({ type: 'code', lang: lang, content: c })
    codeLines = []
    lang = ''
  }

  for (const line of lines) {
    // 去掉行尾 \r 以兼容 CRLF
    const l = line.replace(/\r$/, '')
    if (inCode) {
      // 在代码块内：遇 ``` 结束
      if (/^```/.test(l)) {
        inCode = false
        flushCode()
      } else {
        codeLines.push(l)
      }
    } else {
      // 不在代码块内：遇 ``` 开头行则进入代码块
      if (/^```/.test(l)) {
        flushText()
        inCode = true
        // 提取语言标签（``` 后面的内容，去掉空白）
        lang = l.slice(3).trim()
        codeLines = []
      } else {
        textLines.push(l)
      }
    }
  }
  // 循环结束后的收尾
  if (inCode) {
    // 未闭合的代码块
    flushCode()
  } else {
    flushText()
  }

  return out.length ? out : [{ type: 'text', content: raw }]
}

async function copyCode(content: string) {
  try {
    await navigator.clipboard.writeText(content)
    ElMessage.success('代码已复制')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

async function ingest() {
  ingestBusy.value = true
  ingestMsg.value = '正在更新知识库（zsk/AI + zsk/API_MCP）…'
  try {
    const d = await kbIngest(['zsk/AI', 'zsk/API_MCP'])
    if (!d.success) throw new Error(d.error || '更新失败')
    const roots = Array.isArray(d.roots) ? d.roots.join(', ') : ''
    const byRoot = d.counts?.by_root
    const detail =
      byRoot && typeof byRoot === 'object'
        ? `（AI=${byRoot['zsk/AI']?.files ?? '-'}，API_MCP=${byRoot['zsk/API_MCP']?.files ?? '-'}）`
        : ''
    ingestMsg.value = `完成：${roots ? '目录 ' + roots + '；' : ''}文件 ${d.counts.total} ${detail}，入库 chunks ${d.upserted_chunks}（模型：${d.embed_model}）`
    ElMessage.success('知识库已更新')
  } catch (e) {
    ingestMsg.value = ''
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    ingestBusy.value = false
  }
}

async function send() {
  const msg = message.value.trim()
  if (!msg) return ElMessage.error('请输入问题')
  busy.value = true
  answer.value = ''
  sources.value = []
  try {
    const d = await aiTutorChat(msg, 6)
    if (!d.success) throw new Error(d.error || '请求失败')
    answer.value = d.answer || ''
    sources.value = d.sources || []
  } catch (e) {
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ToolPageShell
    title="云智学习（知识库优先）"
    subtitle="优先检索课程与 API 文档，支持专业问答与调用示例说明。"
  >
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      课程文档（zsk/AI）与接口说明（zsk/API_MCP）会一并入库；涉及代码时将以代码块返回，并支持一键复制。
    </el-alert>

    <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px">
      <el-button type="primary" plain :loading="ingestBusy" @click="ingest">更新知识库</el-button>
      <span class="muted">{{ ingestMsg }}</span>
    </div>

    <el-form label-position="top">
      <el-form-item label="提问">
        <el-input v-model="message" type="textarea" :rows="4" placeholder="例如：登录接口怎么调？MCP 如何调用某个 tool？" />
      </el-form-item>
      <el-button type="primary" :loading="busy" @click="send">发送</el-button>
    </el-form>

    <div v-if="answer" style="margin-top: 12px">
      <div class="sectionTitle">回答</div>
      <el-card shadow="never" style="margin-top: 8px">
        <div class="answerBody">
          <template v-for="(seg, idx) in answerSegments" :key="idx">
            <pre v-if="seg.type === 'text'" class="pre">{{ seg.content }}</pre>
            <div v-else class="codeBlock">
              <div class="codeToolbar">
                <span class="codeLang">{{ seg.lang || 'text' }}</span>
                <el-button size="small" text @click="copyCode(seg.content)">复制代码</el-button>
              </div>
              <pre class="codePre"><code>{{ seg.content }}</code></pre>
            </div>
          </template>
        </div>
      </el-card>
    </div>

    <div v-if="sources.length" style="margin-top: 12px">
      <div class="sectionTitle">来源</div>
      <el-table :data="sources" size="small" style="width: 100%; margin-top: 8px">
        <el-table-column label="bucket" width="120">
          <template #default="{ row }">{{ row.kb_bucket || '' }}</template>
        </el-table-column>
        <el-table-column label="source_path" min-width="320">
          <template #default="{ row }">{{ row.source_path }}</template>
        </el-table-column>
        <el-table-column label="chunk_id" width="90">
          <template #default="{ row }">{{ row.chunk_id }}</template>
        </el-table-column>
        <el-table-column label="score" width="90">
          <template #default="{ row }">{{ row.score }}</template>
        </el-table-column>
      </el-table>
    </div>
  </ToolPageShell>
</template>

<style scoped>
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.sectionTitle {
  font-weight: 700;
}
.pre {
  white-space: pre-wrap;
  margin: 0 0 10px;
  font-size: 13px;
}
.answerBody :last-child.pre {
  margin-bottom: 0;
}
.codeBlock {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  overflow: hidden;
  margin: 8px 0 12px;
  background: #0f172a;
}
.codeToolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.06);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}
.codeLang {
  color: #cbd5e1;
  font-size: 12px;
  text-transform: lowercase;
}
.codePre {
  margin: 0;
  padding: 12px;
  background: #0f172a;
  color: #e2e8f0;
  white-space: pre-wrap;
  font-size: 12px;
  line-height: 1.5;
  overflow: auto;
}
.codePre code {
  display: block;
  width: 100%;
  margin: 0;
  padding: 0 !important;
  background: transparent !important;
  border-radius: 0 !important;
  color: inherit !important;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New',
    monospace;
  line-height: inherit;
}
</style>

