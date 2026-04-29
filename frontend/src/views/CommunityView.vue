<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  ChatDotRound,
  Download,
  FolderOpened,
  Link,
  Plus,
  Search,
} from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import {
  getCategories,
  getPosts,
  getPostDetail,
  createPost,
  deletePost,
  createReply,
  downloadAttachmentUrl,
  type Post,
  type PostDetail,
  type Reply,
} from '../api/community'

const auth = useAuthStore()

// --- 视图切换 ---
const view = ref<'list' | 'detail' | 'create'>('list')

// --- 列表 ---
const categories = ref<string[]>(['全部'])
const activeCategory = ref('全部')
const activeType = ref<'all' | 'question' | 'project'>('all')
const keyword = ref('')
const posts = ref<Post[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)

async function loadCategories() {
  try { categories.value = await getCategories() } catch { /* ignore */ }
}

async function loadPosts() {
  loading.value = true
  try {
    const d = await getPosts({
      category: activeCategory.value,
      post_type: activeType.value === 'all' ? undefined : activeType.value,
      keyword: keyword.value,
      page: page.value,
      page_size: pageSize,
    })
    posts.value = d.items
    total.value = d.total
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '加载失败')
  } finally {
    loading.value = false
  }
}

function onSearch() { page.value = 1; loadPosts() }
function onCategoryChange(cat: string) { activeCategory.value = cat; page.value = 1; loadPosts() }
function onTypeChange(t: 'all' | 'question' | 'project') { activeType.value = t; page.value = 1; loadPosts() }

onMounted(() => { loadCategories(); loadPosts() })

// --- 发布 ---
const createForm = ref({
  title: '', content: '', category: '机器学习',
  post_type: 'question' as 'question' | 'project',
  attachment: null as File | null,
  project_link: '',
})
const createBusy = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

function openCreate(type: 'question' | 'project') {
  createForm.value = { title: '', content: '', category: '机器学习', post_type: type, attachment: null, project_link: '' }
  view.value = 'create'
}
function onAttachmentChange(e: Event) {
  createForm.value.attachment = (e.target as HTMLInputElement).files?.[0] || null
}
async function submitCreate() {
  if (!createForm.value.title.trim()) return ElMessage.error('请输入标题')
  createBusy.value = true
  try {
    await createPost({
      title: createForm.value.title, content: createForm.value.content,
      category: createForm.value.category, post_type: createForm.value.post_type,
      attachment: createForm.value.attachment || undefined,
      project_link: createForm.value.project_link || undefined,
    })
    ElMessage.success('发布成功'); view.value = 'list'; loadPosts()
  } catch (e: any) { ElMessage.error(e?.response?.data?.error || '发布失败') }
  finally { createBusy.value = false }
}

// --- 详情页 ---
const detailPost = ref<PostDetail | null>(null)
const detailReplies = ref<Reply[]>([])
const detailLoading = ref(false)
const replyContent = ref('')
const replyBusy = ref(false)

async function openDetail(postId: number) {
  detailLoading.value = true; view.value = 'detail'
  try {
    const d = await getPostDetail(postId)
    detailPost.value = d.post; detailReplies.value = d.replies
  } catch (e: any) { ElMessage.error(e?.response?.data?.error || '加载失败') }
  finally { detailLoading.value = false }
}

function goBack() {
  view.value = 'list'; detailPost.value = null; detailReplies.value = []; replyContent.value = ''
}

async function submitReply() {
  if (!replyContent.value.trim()) return ElMessage.error('请输入回复内容')
  if (!detailPost.value) return
  replyBusy.value = true
  try {
    await createReply(detailPost.value.id, replyContent.value)
    replyContent.value = ''
    const d = await getPostDetail(detailPost.value.id)
    detailReplies.value = d.replies; detailPost.value = d.post; loadPosts()
  } catch (e: any) { ElMessage.error(e?.response?.data?.error || '回复失败') }
  finally { replyBusy.value = false }
}

async function onDeletePost(postId: number) {
  try { await deletePost(postId); ElMessage.success('已删除'); goBack(); loadPosts() }
  catch (e: any) { ElMessage.error(e?.response?.data?.error || '删除失败') }
}

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function onDownload(postId: number, filename: string | null) {
  const a = document.createElement('a')
  a.href = downloadAttachmentUrl(postId); a.download = filename || 'attachment'; a.click()
}

function openLink(url: string) {
  window.open(url, '_blank', 'noopener')
}
</script>

<template>
  <!-- ========== 列表页 ========== -->
  <div v-if="view === 'list'" class="community-page">
    <header class="page-hero">
      <div class="heroGlow" aria-hidden="true" />
      <div class="heroAccent" aria-hidden="true" />
      <div class="heroInner">
        <h1 class="pageTitle">AI 社区</h1>
        <p class="pageSubtitle">交流问题、分享项目，共建人工智能学习社区。</p>
      </div>
    </header>

    <div class="pageBody">
      <!-- 搜索栏 -->
      <div class="search-bar">
        <el-input v-model="keyword" placeholder="搜索帖子标题或内容…" clearable :prefix-icon="Search"
          @keyup.enter="onSearch" @clear="onSearch" class="search-input" />
        <el-button type="primary" :icon="Search" @click="onSearch">搜索</el-button>
        <div style="flex:1" />
        <el-button :icon="Plus" @click="openCreate('question')">发布问题</el-button>
        <el-button :icon="FolderOpened" @click="openCreate('project')">分享项目</el-button>
      </div>

      <!-- 分类标签 -->
      <div class="category-tags">
        <span class="cat-label">分类：</span>
        <el-tag v-for="cat in categories" :key="cat"
          :type="activeCategory === cat ? '' : 'info'"
          :effect="activeCategory === cat ? 'dark' : 'plain'"
          class="cat-tag" @click="onCategoryChange(cat)">
          {{ cat }}
        </el-tag>
      </div>

      <!-- 类型切换 -->
      <div class="type-tabs">
        <el-radio-group v-model="activeType" @change="onTypeChange">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="question">问题</el-radio-button>
          <el-radio-button value="project">项目</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 帖子列表（网页行格式） -->
      <div class="post-list">
        <el-empty v-if="!loading && !posts.length" description="暂无帖子" style="margin-top: 40px" />

        <div class="post-list-header">
          <span class="col-type">类型</span>
          <span class="col-category">分类</span>
          <span class="col-title">标题</span>
          <span class="col-author">作者</span>
          <span class="col-reply">回复</span>
          <span class="col-attach">附件</span>
          <span class="col-time">时间</span>
        </div>

        <div
          v-for="p in posts"
          :key="p.id"
          class="post-row"
          @click="openDetail(p.id)"
        >
          <span class="col-type">
            <el-tag size="small" :type="p.post_type === 'project' ? 'warning' : 'primary'">
              {{ p.post_type === 'project' ? '项目' : '问题' }}
            </el-tag>
          </span>
          <span class="col-category">
            <el-tag size="small" type="info">{{ p.category }}</el-tag>
          </span>
          <span class="col-title">{{ p.title }}</span>
          <span class="col-author">{{ p.username }}</span>
          <span class="col-reply">
            <el-icon style="vertical-align: -2px"><ChatDotRound /></el-icon> {{ p.reply_count }}
          </span>
          <span class="col-attach">
            <el-icon v-if="p.attachment_name" style="color: var(--el-color-primary)"><Download /></el-icon>
            <el-icon v-else-if="p.project_link" style="color: var(--el-color-success)"><Link /></el-icon>
            <span v-else class="no-attach">—</span>
          </span>
          <span class="col-time">{{ formatTime(p.created_at) }}</span>
        </div>
      </div>

      <!-- 分页 -->
      <div class="pagination" v-if="total > pageSize">
        <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total"
          layout="prev, pager, next" @current-change="loadPosts" />
      </div>
    </div>
  </div>

  <!-- ========== 发布页（铺满页面） ========== -->
  <div v-if="view === 'create'" class="community-page create-page">
    <header class="create-topbar">
      <el-button :icon="ArrowLeft" @click="view = 'list'">返回列表</el-button>
      <h2 class="create-topbar-title">{{ createForm.post_type === 'project' ? '分享项目' : '发布问题' }}</h2>
      <div style="flex:1" />
      <el-button @click="view = 'list'">取消</el-button>
      <el-button type="primary" :loading="createBusy" @click="submitCreate">发布</el-button>
    </header>

    <div class="create-body">
      <el-form label-position="top" class="create-form">
        <el-form-item label="标题" required>
          <el-input v-model="createForm.title" placeholder="请输入标题" maxlength="100" show-word-limit size="large" />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="分类">
              <el-select v-model="createForm.category" style="width: 100%" size="large">
                <el-option v-for="c in categories.filter(x => x !== '全部')" :key="c" :value="c" :label="c" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12" v-if="createForm.post_type === 'project'">
            <el-form-item label="项目压缩包">
              <div class="upload-area" @click="fileInput?.click()">
                <el-icon class="upload-icon"><FolderOpened /></el-icon>
                <span v-if="!createForm.attachment" class="upload-text">点击选择压缩包</span>
                <span v-else class="upload-text has-file">{{ createForm.attachment.name }}</span>
              </div>
              <input ref="fileInput" type="file" accept=".zip,.rar,.7z,.tar,.tar.gz,.gz" @change="onAttachmentChange" class="sr-only" />
            </el-form-item>
          </el-col>
          <el-col :span="12" v-if="createForm.post_type === 'project'">
            <el-form-item label="项目链接">
              <el-input v-model="createForm.project_link" placeholder="如 GitHub 仓库地址等" size="large" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="详细描述">
          <el-input v-model="createForm.content" type="textarea" :rows="14" placeholder="请描述问题或项目详情…" />
        </el-form-item>
      </el-form>
    </div>
  </div>

  <!-- ========== 详情页（铺满页面） ========== -->
  <div v-if="view === 'detail'" class="community-page detail-page">
    <header class="detail-topbar">
      <el-button :icon="ArrowLeft" @click="goBack">返回列表</el-button>
      <div style="flex:1" />
      <el-button
        v-if="detailPost && detailPost.username === auth.username"
        type="danger" text size="small"
        @click="onDeletePost(detailPost.id)"
      >删除帖子</el-button>
    </header>

    <div class="detail-body">
      <template v-if="detailPost">
        <!-- 帖子主区域 -->
        <div class="detail-main">
          <div class="detail-tags">
            <el-tag :type="detailPost.post_type === 'project' ? 'warning' : 'primary'">
              {{ detailPost.post_type === 'project' ? '项目' : '问题' }}
            </el-tag>
            <el-tag type="info">{{ detailPost.category }}</el-tag>
          </div>
          <h1 class="detail-title">{{ detailPost.title }}</h1>
          <div class="detail-meta">
            <span class="meta-author">{{ detailPost.username }}</span>
            <span class="meta-time">{{ formatTime(detailPost.created_at) }}</span>
          </div>
          <div class="detail-content">{{ detailPost.content || '（无详细描述）' }}</div>
          <div v-if="detailPost.attachment_name || detailPost.project_link" class="detail-attachment">
            <el-button v-if="detailPost.attachment_name" type="primary" :icon="Download" @click="onDownload(detailPost.id, detailPost.attachment_name)">
              下载项目：{{ detailPost.attachment_name }}
            </el-button>
            <el-button v-if="detailPost.project_link" type="success" @click="openLink(detailPost.project_link)">
              访问项目链接
            </el-button>
          </div>
        </div>

        <!-- 回复区 -->
        <div class="replies-section">
          <h2 class="replies-heading">回复（{{ detailReplies.length }}）</h2>

          <div v-if="!detailReplies.length" class="no-reply">暂无回复，来抢沙发吧！</div>

          <div v-for="r in detailReplies" :key="r.id" class="reply-item">
            <div class="reply-avatar">{{ r.username.charAt(0).toUpperCase() }}</div>
            <div class="reply-body">
              <div class="reply-meta">
                <strong class="reply-author">{{ r.username }}</strong>
                <span class="reply-time">{{ formatTime(r.created_at) }}</span>
              </div>
              <div class="reply-content">{{ r.content }}</div>
            </div>
          </div>

          <!-- 回复输入 -->
          <div class="reply-input-box">
            <el-input v-model="replyContent" type="textarea" :rows="4" placeholder="写下你的回复…" />
            <div class="reply-actions">
              <el-button type="primary" :loading="replyBusy" @click="submitReply">发表回复</el-button>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* ---- 公共 ---- */
.community-page {
  animation: enter 0.35s ease both;
}
@keyframes enter {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ---- 列表页 ---- */
.page-hero {
  position: relative;
  padding: 28px 36px;
  overflow: hidden;
  background: linear-gradient(125deg, #1e3a5f 0%, #2a5a8c 35%, #3a6a9c 65%, #4c7db0 100%);
  border-radius: 14px;
  margin-bottom: 20px;
}
.heroGlow {
  position: absolute; inset: 0;
  background:
    radial-gradient(80% 120% at 90% 0%, rgba(80,176,240,0.3), transparent 55%),
    radial-gradient(60% 80% at 0% 100%, rgba(56,189,248,0.15), transparent 50%);
  pointer-events: none;
}
.heroAccent {
  position: absolute; bottom: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, rgba(80,176,240,0), rgba(80,176,240,0.6) 30%, rgba(96,200,250,0.8) 50%, rgba(80,176,240,0.6) 70%, rgba(80,176,240,0));
  pointer-events: none;
}
.heroInner { position: relative; z-index: 1; }
.pageTitle { margin: 0; font-size: 26px; font-weight: 700; color: #f0f7ff; letter-spacing: 0.02em; }
.pageSubtitle { margin: 8px 0 0; font-size: 14px; color: rgba(210,230,250,0.88); line-height: 1.5; }

.pageBody { padding: 0 4px; }

.search-bar {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 16px; flex-wrap: wrap;
}
.search-input { max-width: 420px; }
.category-tags {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 14px; flex-wrap: wrap;
}
.cat-label {
  font-size: 13px; color: var(--el-text-color-secondary);
  font-weight: 500; white-space: nowrap;
}
.cat-tag { cursor: pointer; transition: transform 0.15s ease; }
.cat-tag:hover { transform: scale(1.05); }
.type-tabs { margin-bottom: 16px; }

/* 帖子列表行 */
.post-list {
  border: 1px solid rgba(80,176,240,0.1);
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255,255,255,0.92);
  backdrop-filter: blur(8px);
}
.post-list-header {
  display: flex; align-items: center;
  padding: 12px 18px;
  background: linear-gradient(90deg, rgba(80,176,240,0.08), rgba(80,176,240,0.03));
  border-bottom: 1px solid rgba(80,176,240,0.1);
  font-size: 12px; font-weight: 600; color: var(--el-text-color-secondary);
  letter-spacing: 0.04em;
}
.post-row {
  display: flex; align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(80,176,240,0.06);
  cursor: pointer;
  transition: background 0.2s ease, transform 0.15s ease;
  font-size: 14px;
}
.post-row:last-child { border-bottom: none; }
.post-row:hover {
  background: rgba(80,176,240,0.06);
  transform: translateX(2px);
}

/* 列宽 */
.col-type { width: 72px; flex-shrink: 0; text-align: center; }
.col-category { width: 110px; flex-shrink: 0; text-align: center; }
.col-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.col-author { width: 110px; flex-shrink: 0; color: var(--el-text-color-secondary); font-size: 13px; }
.col-reply { width: 70px; flex-shrink: 0; text-align: center; font-size: 13px; }
.col-attach { width: 60px; flex-shrink: 0; text-align: center; }
.col-time { width: 120px; flex-shrink: 0; font-size: 12px; color: var(--el-text-color-secondary); }
.no-attach { color: var(--el-text-color-placeholder); }

.pagination { display: flex; justify-content: center; margin-top: 22px; }

/* ---- 详情页 ---- */
.detail-page {
  position: absolute;
  inset: 0;
  display: flex; flex-direction: column;
  background: linear-gradient(165deg, #eaf6fa 0%, #f4fafe 35%, #edf6f9 100%);
  z-index: 10;
}
.detail-topbar {
  flex-shrink: 0;
  display: flex; align-items: center; gap: 10px;
  padding: 12px 24px;
  background: rgba(255,255,255,0.95);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(80,176,240,0.12);
  box-shadow: 0 2px 12px rgba(15,23,42,0.04);
}
.detail-body {
  flex: 1; overflow-y: auto;
  padding: 32px 48px 48px;
  max-width: 960px;
  width: 100%;
  margin: 0 auto;
}

.detail-main {
  margin-bottom: 36px;
  padding-bottom: 28px;
  border-bottom: 2px solid rgba(80,176,240,0.1);
}
.detail-tags {
  display: flex; gap: 8px; margin-bottom: 14px;
}
.detail-title {
  margin: 0 0 12px; font-size: 28px; font-weight: 700;
  color: var(--el-text-color-primary); line-height: 1.35;
}
.detail-meta {
  display: flex; align-items: center; gap: 18px;
  font-size: 14px; margin-bottom: 24px;
}
.meta-author { font-weight: 600; color: var(--el-text-color-primary); }
.meta-time { color: var(--el-text-color-secondary); }
.detail-content {
  font-size: 15px; line-height: 1.85; color: var(--el-text-color-primary);
  white-space: pre-wrap; margin-bottom: 20px;
}
.detail-attachment { margin-bottom: 8px; }

/* 回复区 */
.replies-section {
  padding-top: 28px;
}
.replies-heading {
  margin: 0 0 20px; font-size: 20px; font-weight: 600;
  color: var(--el-text-color-primary);
}
.no-reply {
  color: var(--el-text-color-placeholder); font-size: 14px;
  text-align: center; padding: 32px 0;
}
.reply-item {
  display: flex; gap: 14px; padding: 16px 0;
  border-bottom: 1px solid rgba(80,176,240,0.06);
}
.reply-item:last-of-type { border-bottom: none; }
.reply-avatar {
  flex-shrink: 0; width: 40px; height: 40px;
  border-radius: 50%; background: linear-gradient(135deg, #50b0f0, #3a8ac0);
  color: #fff; font-weight: 700; font-size: 16px;
  display: flex; align-items: center; justify-content: center;
}
.reply-body { flex: 1; min-width: 0; }
.reply-meta {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 6px;
}
.reply-author { font-size: 14px; color: var(--el-text-color-primary); }
.reply-time { font-size: 12px; color: var(--el-text-color-secondary); }
.reply-content {
  font-size: 14px; line-height: 1.7; white-space: pre-wrap;
  color: var(--el-text-color-regular);
}

/* 回复输入 */
.reply-input-box {
  margin-top: 28px;
  padding: 24px;
  border-radius: 14px;
  background: rgba(255,255,255,0.85);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(80,176,240,0.1);
}
.reply-actions {
  display: flex; justify-content: flex-end;
  margin-top: 12px;
}

/* 公共 */
.file-input { font-size: 13px; }
.muted { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }

/* ---- 发布页 ---- */
.create-page {
  position: absolute;
  inset: 0;
  display: flex; flex-direction: column;
  background: linear-gradient(165deg, #eaf6fa 0%, #f4fafe 35%, #edf6f9 100%);
  z-index: 10;
}
.create-topbar {
  flex-shrink: 0;
  display: flex; align-items: center; gap: 14px;
  padding: 12px 24px;
  background: rgba(255,255,255,0.95);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(80,176,240,0.12);
  box-shadow: 0 2px 12px rgba(15,23,42,0.04);
}
.create-topbar-title {
  margin: 0; font-size: 18px; font-weight: 700;
  color: var(--el-text-color-primary);
}
.create-body {
  flex: 1; overflow-y: auto;
  padding: 32px 48px 48px;
}
.create-form {
  max-width: 860px;
  margin: 0 auto;
}
.upload-area {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 20px;
  border: 1.5px dashed rgba(80,176,240,0.35);
  border-radius: 10px;
  background: rgba(248,252,255,0.7);
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease;
}
.upload-area:hover {
  border-color: rgba(80,176,240,0.6);
  background: rgba(248,252,255,0.95);
}
.upload-icon { font-size: 22px; color: #50b0f0; }
.upload-text { font-size: 14px; color: var(--el-text-color-secondary); }
.upload-text.has-file { color: var(--el-color-primary); font-weight: 500; }
.sr-only {
  position: absolute; width: 1px; height: 1px;
  padding: 0; margin: -1px; overflow: hidden;
  clip: rect(0,0,0,0); border: 0;
}

@media (max-width: 768px) {
  .page-hero { padding: 18px 20px; border-radius: 10px; }
  .pageTitle { font-size: 20px; }
  .detail-body { padding: 20px 16px 28px; }
  .detail-title { font-size: 22px; }
  .col-category { display: none; }
  .col-author { width: 80px; }
  .col-time { width: 90px; font-size: 11px; }
}
</style>
