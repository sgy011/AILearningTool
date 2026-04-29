<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { Component } from 'vue'
import {
  ChatRound,
  Collection,
  CopyDocument,
  Cpu,
  Document,
  EditPen,
  Expand,
  Fold,
  Headset,
  House,
  MagicStick,
  Medal,
  Picture,
  Reading,
  Setting,
  SwitchButton,
  User,
  UserFilled,
  Avatar,
} from '@element-plus/icons-vue'
import ApiConfigDialog from '../components/ApiConfigDialog.vue'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const isCollapsed = ref(false)
const showApiConfig = ref(false)

const active = computed(() => route.path)

const menus: { group: string; icon: Component; children: { path: string; label: string; icon: Component }[] }[] = [
  {
    group: '资源修复转换',
    icon: Picture,
    children: [
      { path: '/tools/image', label: '图片修复与转换', icon: Picture },
      { path: '/tools/audio', label: '音频修复与转换', icon: Headset },
    ],
  },
  {
    group: '文档处理',
    icon: Document,
    children: [
      { path: '/tools/text-clean', label: '文档文稿处理', icon: Document },
      { path: '/tools/docs-merge', label: '文档合并与转换', icon: CopyDocument },
    ],
  },
  {
    group: '数据集',
    icon: EditPen,
    children: [
      { path: '/tools/dataset', label: '数据标注划分', icon: EditPen },
      { path: '/tools/augment', label: '图片数据增强', icon: MagicStick },
      { path: '/tools/dataset-maker', label: '图片数据集制作', icon: Collection },
      { path: '/tools/mm-align', label: '多模态图文对齐', icon: Collection },
    ],
  },
  {
    group: '模型转换',
    icon: Cpu,
    children: [{ path: '/tools/model', label: '模型转换', icon: Cpu }],
  },
  {
    group: '每日必读资讯',
    icon: Reading,
    children: [{ path: '/tools/news', label: '每日必读资讯', icon: Reading }],
  },
  {
    group: '云智学习',
    icon: Medal,
    children: [{ path: '/tools/ai-tutor', label: '云智学习', icon: Medal }],
  },
  {
    group: 'AI社区',
    icon: ChatRound,
    children: [{ path: '/tools/community', label: 'AI社区', icon: Avatar }],
  },
]

function go(path: string) {
  router.push(path)
}

onMounted(async () => {
  try {
    await auth.refresh()
  } catch (e: any) {
    // ignore: not logged in / network
  }
})

async function onLogout() {
  await auth.logout()
  ElMessage.success('已退出')
  router.push('/login')
}
</script>

<template>
  <el-container class="app-shell">
    <el-aside class="aside" :width="isCollapsed ? '72px' : '248px'">
      <div class="brand" @click="go('/tools/image')">
        <img src="/logo.png" alt="云栈智助" class="brandMark" />
        <span class="brandText" v-if="!isCollapsed">云栈智助</span>
      </div>
      <div class="asideMenuWrap">
        
        <el-scrollbar class="menuScroll">
          <el-menu :default-active="active" class="menu" :collapse="isCollapsed" @select="go">
            <template v-for="m in menus" :key="m.group">
              <el-sub-menu v-if="m.children.length > 1" :index="m.group">
                <template #title>
                  <el-icon class="menuIcon"><component :is="m.icon" /></el-icon>
                  <span class="menuLabel">{{ m.group }}</span>
                </template>
                <el-menu-item v-for="c in m.children" :key="c.path" :index="c.path">
                  <el-icon class="menuIcon"><component :is="c.icon" /></el-icon>
                  <span class="menuLabel">{{ c.label }}</span>
                </el-menu-item>
              </el-sub-menu>
              <el-menu-item v-else :index="m.children[0].path">
                <el-icon class="menuIcon"><component :is="m.icon" /></el-icon>
                <span class="menuLabel">{{ m.group }}</span>
              </el-menu-item>
            </template>
          </el-menu>
        </el-scrollbar>
      </div>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="headerLeft">
          <el-button text class="navBtn headerAction" @click="isCollapsed = !isCollapsed">
            <el-icon><component :is="isCollapsed ? Expand : Fold" /></el-icon>
            <span>{{ isCollapsed ? '展开' : '收起' }}</span>
          </el-button>
          <span class="headerTitle"><img src="/logo.png" alt="" class="headerLogo" /> 云栈智助</span>
        </div>
        <div class="headerRight">
          <template v-if="auth.loaded && auth.loggedIn">
            <span class="userText">已登录：<strong>{{ auth.displayName }}</strong></span>
            <el-button
              text
              class="navBtn headerAction"
              :class="{ 'is-active-route': active === '/tools/image' }"
              @click="router.push('/tools/image')"
            >
              <el-icon><House /></el-icon>
              <span>首页</span>
            </el-button>
            <el-button text class="navBtn headerAction" @click="showApiConfig = true">
              <el-icon><Setting /></el-icon>
              <span>API 配置</span>
            </el-button>
            <el-button text class="navBtn headerAction headerActionDanger" @click="onLogout">
              <el-icon><SwitchButton /></el-icon>
              <span>退出</span>
            </el-button>
          </template>
          <template v-else>
            <el-button text class="navBtn headerAction" @click="router.push('/login')">
              <el-icon><User /></el-icon>
              <span>登录</span>
            </el-button>
            <el-button text class="navBtn headerAction" @click="router.push('/register')">
              <el-icon><UserFilled /></el-icon>
              <span>注册</span>
            </el-button>
            <el-button
              text
              class="navBtn headerAction"
              :class="{ 'is-active-route': active === '/tools/image' }"
              @click="router.push('/tools/image')"
            >
              <el-icon><House /></el-icon>
              <span>首页</span>
            </el-button>
            <el-button text class="navBtn headerAction" @click="showApiConfig = true">
              <el-icon><Setting /></el-icon>
              <span>API 配置</span>
            </el-button>
          </template>
        </div>
      </el-header>
      <el-main class="main tool-workspace">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <ApiConfigDialog v-model="showApiConfig" />
</template>

<style scoped>
.app-shell {
  height: 100vh;
}
.aside {
  display: flex;
  flex-direction: column;
  height: 100vh;
  border-right: 1px solid rgba(80, 176, 240, 0.12);
  background: linear-gradient(180deg, #fafbff 0%, #f1f5f9 100%);
  box-shadow: 4px 0 24px rgba(15, 23, 42, 0.04);
}
.brand {
  flex-shrink: 0;
  height: 56px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  cursor: pointer;
  border-bottom: 1px solid rgba(80, 176, 240, 0.1);
  font-weight: 700;
  background: linear-gradient(90deg, rgba(80, 176, 240, 0.1), transparent);
  color: #1e293b;
  transition: background 0.2s ease;
}
.brand:hover {
  background: linear-gradient(90deg, rgba(80, 176, 240, 0.16), transparent);
}
.brandMark {
  width: 28px;
  height: 28px;
  object-fit: contain;
  flex-shrink: 0;
  filter: drop-shadow(0 1px 2px rgba(30, 41, 59, 0.12));
}
.brandText {
  user-select: none;
  letter-spacing: 0.02em;
}
.asideMenuWrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.menuSectionLabel {
  margin: 0;
  padding: 14px 18px 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #94a3b8;
}
.menuScroll {
  flex: 1;
  min-height: 0;
  padding: 0 8px 16px;
}
.menuScroll :deep(.el-scrollbar__wrap) {
  overflow-x: hidden !important;
}
.menu {
  border-right: none;
  background: transparent;
}
:deep(.menu .el-menu-item) {
  border-radius: 10px;
  margin: 3px 0;
  height: auto !important;
  min-height: 44px;
  line-height: 1.35;
  padding: 10px 12px !important;
  transition:
    background 0.2s ease,
    color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.15s ease;
}
:deep(.menu .el-menu-item:hover) {
  background: rgba(76, 61, 176, 0.1) !important;
  transform: translateX(1px);
}
:deep(.menu .el-menu-item.is-active) {
  background: linear-gradient(90deg, rgba(76, 61, 176, 0.22), rgba(76, 61, 176, 0.07)) !important;
  color: #2d4a7c !important;
  font-weight: 600;
  box-shadow: inset 3px 0 0 #4c3db0, 0 4px 14px rgba(76, 61, 176, 0.12);
}
:deep(.menu .el-menu-item.is-active .menuIcon) {
  color: #4c3db0;
}
:deep(.menu .el-menu-item .menuIcon) {
  font-size: 18px;
  margin-right: 10px;
  vertical-align: middle;
  color: #5a8a9e;
  transition: color 0.2s ease;
}
:deep(.menu .el-menu-item:hover .menuIcon) {
  color: #4c3db0;
}
.menuLabel {
  font-size: 13px;
}
:deep(.menu.el-menu--collapse .el-menu-item) {
  padding: 10px 0 !important;
  justify-content: center;
}
:deep(.menu.el-menu--collapse .el-menu-item .menuIcon) {
  margin-right: 0;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(80, 176, 240, 0.12);
  background: linear-gradient(135deg, #e8f6fd 0%, #d4eefc 35%, #c8e8f8 100%);
  color: #0a2a4a;
}
.headerLeft {
  display: flex;
  align-items: center;
  gap: 8px;
}
.headerTitle {
  font-weight: 700;
  font-size: 18px;
  color: #0a2a4a;
  display: flex;
  align-items: center;
  gap: 6px;
}

.headerLogo {
  width: 22px;
  height: 22px;
  object-fit: contain;
}
.main.tool-workspace {
  padding: 20px 24px 28px;
  background: linear-gradient(165deg, #eaf6fa 0%, #f4fafe 35%, #edf6f9 100%);
  min-height: calc(100vh - 60px);
  box-sizing: border-box;
  overflow: auto;
}
.userText {
  font-size: 13px;
  color: #2a6a9e;
}
.headerRight {
  display: flex;
  align-items: center;
  gap: 10px;
}
.navBtn {
  color: #0a2a4a;
  font-size: 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.navBtn:hover {
  color: #1e3a5f;
}
.headerAction {
  border-radius: 10px !important;
  padding: 8px 14px !important;
  border: 1px solid transparent !important;
  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease,
    box-shadow 0.2s ease;
}
.headerAction:hover {
  background: rgba(255, 255, 255, 0.1) !important;
  border-color: rgba(255, 255, 255, 0.14) !important;
  color: #fff !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}
.headerAction.is-active-route {
  background: rgba(255, 255, 255, 0.14) !important;
  border-color: rgba(255, 255, 255, 0.22) !important;
  color: #fff !important;
}
.headerActionDanger:hover {
  background: rgba(248, 113, 113, 0.18) !important;
  border-color: rgba(248, 113, 113, 0.35) !important;
}
:deep(.navBtn .el-icon) {
  font-size: 15px;
}
</style>

