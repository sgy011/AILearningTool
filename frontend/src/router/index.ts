import { createRouter, createWebHistory } from 'vue-router'

import AppShell from '../layouts/AppShell.vue'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import ForgotPasswordView from '../views/ForgotPasswordView.vue'

import ImageConverterView from '../views/ImageConverterView.vue'
import AudioRepairView from '../views/AudioRepairView.vue'
import TextCleanView from '../views/TextCleanView.vue'
import DocsMergeView from '../views/DocsMergeView.vue'
import DatasetView from '../views/DatasetView.vue'
import ImageAugmentView from '../views/ImageAugmentView.vue'
import DatasetMakerView from '../views/DatasetMakerView.vue'
import MmAlignView from '../views/MmAlignView.vue'
import ModelConverterView from '../views/ModelConverterView.vue'
import NewsView from '../views/NewsView.vue'
import AiTutorView from '../views/AiTutorView.vue'
import CommunityView from '../views/CommunityView.vue'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
    },
    {
      path: '/forgot-password',
      name: 'forgotPassword',
      component: ForgotPasswordView,
    },
    {
      path: '/',
      component: AppShell,
      children: [
        { path: '', redirect: '/tools/image' },
        { path: '/tools/image', name: 'toolImage', component: ImageConverterView },
        { path: '/tools/audio', name: 'toolAudio', component: AudioRepairView },
        { path: '/tools/text-clean', name: 'toolTextClean', component: TextCleanView },
        { path: '/tools/docs-merge', name: 'toolDocsMerge', component: DocsMergeView },
        { path: '/tools/dataset', name: 'toolDataset', component: DatasetView },
        { path: '/tools/augment', name: 'toolAugment', component: ImageAugmentView },
        { path: '/tools/dataset-maker', name: 'toolDatasetMaker', component: DatasetMakerView },
        { path: '/tools/mm-align', name: 'toolMmAlign', component: MmAlignView },
        { path: '/tools/model', name: 'toolModel', component: ModelConverterView },
        { path: '/tools/news', name: 'toolNews', component: NewsView },
        { path: '/tools/ai-tutor', name: 'toolAiTutor', component: AiTutorView },
        { path: '/tools/community', name: 'toolCommunity', component: CommunityView },
      ],
    },
  ],
})

const DEFAULT_TITLE = '云栈智助'

router.afterEach(() => {
  document.title = DEFAULT_TITLE
})

router.beforeEach(async (to) => {
  if (to.path === '/login' || to.path === '/register' || to.path === '/forgot-password') return true
  const auth = useAuthStore()
  if (!auth.loaded) {
    try {
      await auth.refresh()
    } catch {
      // ignore
    }
  }
  if (!auth.loggedIn) return { path: '/login', query: { next: to.fullPath } }
  return true
})

export default router

