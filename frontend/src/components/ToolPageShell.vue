<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
}>()
</script>

<template>
  <div class="tool-page">
    <el-card class="bodyCard" shadow="hover">
      <header class="hero">
        <div class="heroGlow" aria-hidden="true" />
        <div class="heroInner">
          <h1 class="title">{{ title }}</h1>
          <p v-if="subtitle" class="subtitle">{{ subtitle }}</p>
        </div>
      </header>
      <div class="content">
        <slot />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.tool-page {
  max-width: 1200px;
  margin: 0 auto;
  animation: enter 0.45s ease both;
}

.hero {
  position: relative;
  padding: 22px 24px;
  overflow: hidden;
  background: linear-gradient(135deg, #e8f6fd 0%, #d4eefc 35%, #c8e8f8 70%, #b8dcf5 100%);
  border-bottom: 1px solid rgba(80, 176, 240, 0.18);
  border-radius: 12px 12px 0 0;
}

.heroGlow {
  position: absolute;
  inset: 0;
  background: radial-gradient(80% 120% at 90% 0%, rgba(80, 176, 240, 0.25), transparent 55%),
    radial-gradient(60% 80% at 0% 100%, rgba(56, 189, 248, 0.15), transparent 50%);
  pointer-events: none;
}

.heroInner {
  position: relative;
  z-index: 1;
}

.title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #0a2a4a;
  line-height: 1.3;
}

.subtitle {
  margin: 8px 0 0;
  font-size: 14px;
  line-height: 1.55;
  color: rgba(10, 42, 74, 0.72);
  max-width: 720px;
}

.bodyCard {
  border-radius: 12px;
  border: 1px solid rgba(80, 176, 240, 0.14);
  background: #ffffff;
  box-shadow: 0 4px 24px rgba(15, 23, 42, 0.06);
  overflow: hidden;
}

:deep(.bodyCard .el-card__body) {
  padding: 0;
}

.content {
  padding: 20px 22px;
}

@keyframes enter {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 768px) {
  .hero {
    padding: 18px 16px;
  }
  .title {
    font-size: 18px;
  }
  .subtitle {
    font-size: 13px;
  }
}
</style>
