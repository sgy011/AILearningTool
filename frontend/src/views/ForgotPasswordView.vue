<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { normalizeApiError } from '../api/http'
import { authResetPassword, authResetRequestCode } from '../api/auth'

const router = useRouter()
const email = ref('')
const code = ref('')
const password = ref('')
const confirm = ref('')

const busyCode = ref(false)
const busyReset = ref(false)

async function onSendCode() {
  const em = email.value.trim().toLowerCase()
  if (!em) return ElMessage.error('请输入邮箱')
  busyCode.value = true
  try {
    const d = await authResetRequestCode({ email: em })
    if (!d.success) throw new Error(d.error || '发送失败')
    ElMessage.success('验证码已发送（有效期 10 分钟）')
  } catch (e) {
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    busyCode.value = false
  }
}

async function onReset() {
  const em = email.value.trim().toLowerCase()
  if (!em) return ElMessage.error('请输入邮箱')
  if (!code.value.trim()) return ElMessage.error('请输入验证码')
  if (!password.value) return ElMessage.error('请输入新密码')
  if (password.value !== confirm.value) return ElMessage.error('两次密码不一致')
  busyReset.value = true
  try {
    const d = await authResetPassword({ email: em, code: code.value.trim(), password: password.value })
    if (!d.success) throw new Error(d.error || '重置失败')
    ElMessage.success('密码已重置，请重新登录')
    router.push('/login')
  } catch (e) {
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    busyReset.value = false
  }
}
</script>

<template>
  <div class="authPage">
    <div class="shell">
      <section class="heroPanel">
        <div class="heroInner">
          <div class="heroLogo">
            <img src="/logo.png" alt="云栈智助" class="logoImg" />
            <span class="logoText">云栈智助</span>
          </div>

          <p class="heroDesc">一站式解决，让创意与技术无缝连接。<br />图片处理、音频修复、文档处理，尽在掌握</p>

          <ul class="featureList">
            <li>
              <span class="featureIcon">✉</span>
              <span class="featureMain">邮箱验证码校验</span>
              <span class="featureSub">防止未授权重置，保障账号安全</span>
            </li>
            <li>
              <span class="featureIcon">⊞</span>
              <span class="featureMain">密码强度要求</span>
              <span class="featureSub">降低盗号风险，企业级保护</span>
            </li>
            <li>
              <span class="featureIcon">✓</span>
              <span class="featureMain">全程加密传输</span>
              <span class="featureSub">验证码有效期管控，安全可靠</span>
            </li>
          </ul>
        </div>
      </section>

      <section class="formPanel">
        <div class="formCard">
          <div class="titleWrap">
            <div class="title">忘记密码</div>
            <div class="subTitle">验证邮箱后设置新密码，完成账号恢复</div>
          </div>

          <el-form label-position="top" @submit.prevent>
            <el-form-item label="QQ 邮箱">
              <el-input v-model="email" size="large" placeholder="example@qq.com" />
            </el-form-item>
            <el-form-item label="邮箱验证码">
              <el-input v-model="code" size="large" placeholder="6 位数字验证码" @keyup.enter="onReset">
                <template #append>
                  <el-button :loading="busyCode" @click="onSendCode">获取验证码</el-button>
                </template>
              </el-input>
            </el-form-item>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="新密码">
                  <el-input
                    v-model="password"
                    size="large"
                    type="password"
                    show-password
                    placeholder="至少 8 位字母+数字"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="确认新密码">
                  <el-input
                    v-model="confirm"
                    size="large"
                    type="password"
                    show-password
                    placeholder="再次输入"
                    @keyup.enter="onReset"
                  />
                </el-form-item>
              </el-col>
            </el-row>

            <el-button type="primary" class="submitBtn" :loading="busyReset" @click="onReset">
              重置密码并返回登录
            </el-button>

            <div class="links">
              <el-button link @click="router.push('/login')">返回登录</el-button>
              <el-button link @click="router.push('/register')">去注册</el-button>
            </div>
          </el-form>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.authPage {
  height: 100vh;
  width: 100%;
  overflow: hidden;
  display: block;
  padding: 0;
  background: linear-gradient(135deg, #eff3ff 0%, #f8fbff 100%);
  box-sizing: border-box;
}

.authPage :deep(h1),
.authPage :deep(h2),
.authPage :deep(p) {
  margin: 0;
}

.shell {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-radius: 0;
  overflow: hidden;
  border: none;
  box-shadow: none;
  background: linear-gradient(160deg, #c8e8f8 0%, #b8dcf5 30%, #a8d8f0 60%, #98ccef 100%);
}

.heroPanel {
  height: 100vh;
  padding: 60px 64px;
  background: transparent;
  color: #1a3a5c;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.heroPanel::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 60% 40% at 20% 80%, rgba(100, 180, 240, 0.15), transparent 70%),
    radial-gradient(ellipse 50% 35% at 80% 20%, rgba(100, 180, 240, 0.1), transparent 60%);
  pointer-events: none;
}

.heroPanel::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(58% 38% at 72% 18%, rgba(255, 255, 255, 0.4), transparent 78%);
  pointer-events: none;
}

.heroInner {
  position: relative;
  z-index: 1;
  max-width: 560px;
  width: 100%;
  margin: 0 auto;
  animation: fadeInUp 0.7s ease both;
}

.heroLogo {
  margin-bottom: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.logoImg {
  width: 120px;
  height: 120px;
  object-fit: contain;
  filter: drop-shadow(0 2px 8px rgba(21, 101, 168, 0.2));
}

.logoText {
  font-size: 72px;
  font-weight: 700;
  color: #1565a8;
  line-height: 1.2;
  letter-spacing: 2px;
}

.heroDesc {
  margin: 0 0 16px;
  font-size: 24px;
  line-height: 1.7;
  color: #2a6a9e;
  text-align: center;
  font-weight: 400;
}

.featureList {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.featureList li {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(100, 180, 240, 0.3);
  border-radius: 12px;
  padding: 14px 18px;
  animation: fadeInUp 0.7s ease both;
  transition: background 0.2s, box-shadow 0.2s;
}

.featureList li:hover {
  background: rgba(255, 255, 255, 0.75);
  box-shadow: 0 4px 16px rgba(100, 180, 240, 0.15);
}

.featureIcon {
  font-size: 20px;
  color: #64b4f0;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 2px;
}

.featureMain {
  display: block;
  font-size: 17px;
  font-weight: 700;
  color: #1565a8;
}

.featureSub {
  display: block;
  font-size: 13px;
  font-weight: 400;
  color: #4a7a9e;
  margin-top: 2px;
}

.formPanel {
  padding: 40px 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background: transparent;
  box-sizing: border-box;
}

.formCard {
  width: 100%;
  max-width: 520px;
  padding: 36px 40px;
  border-radius: 16px;
  border: 1px solid rgba(100, 180, 240, 0.25);
  box-shadow: 0 8px 32px rgba(21, 101, 168, 0.1), 0 2px 8px rgba(21, 101, 168, 0.06);
  background: #ffffff;
  animation: fadeInUp 0.75s ease both;
}

.titleWrap {
  display: grid;
  gap: 6px;
  margin-bottom: 28px;
}

.title {
  font-size: 32px;
  font-weight: 700;
  line-height: 1.15;
  color: #1f2937;
}

.subTitle {
  font-size: 16px;
  color: #6b7280;
}

.submitBtn {
  width: 100%;
  height: 48px;
  margin-top: 6px;
  border-radius: 10px;
  border: none;
  background: linear-gradient(90deg, #50b0f0 0%, #3090d0 100%);
  box-shadow: 0 10px 20px rgba(80, 176, 240, 0.28);
  position: relative;
  overflow: hidden;
}

.submitBtn::after {
  content: '';
  position: absolute;
  top: 0;
  left: -130%;
  width: 40%;
  height: 100%;
  transform: skewX(-20deg);
  background: linear-gradient(90deg, rgba(255, 255, 255, 0), rgba(255, 255, 255, 0.45), rgba(255, 255, 255, 0));
  animation: btnShine 3.6s ease-in-out infinite;
}

::deep(.el-input__wrapper) {
  transition: box-shadow 0.25s ease, transform 0.25s ease;
}

::deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px rgba(80, 176, 240, 0.4), 0 8px 20px rgba(80, 176, 240, 0.15) !important;
  transform: translateY(-1px);
}

.links {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(14px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes btnShine {
  0%,
  55% {
    left: -130%;
  }
  80%,
  100% {
    left: 160%;
  }
}

@media (max-width: 1100px) {
  .shell {
    height: 100%;
    grid-template-columns: 1fr;
  }

  .heroPanel {
    height: 100vh;
    padding: 40px 24px;
  }

  .heroTitle {
    font-size: 30px;
  }

  

  .featureList li {
    font-size: 16px;
  }

  .formPanel {
    padding: 40px 24px;
    background: transparent;
  }

  .formCard {
    max-width: 100%;
  }
}

@media (max-width: 600px) {
  .heroPanel {
    height: auto;
    min-height: 100vh;
    padding: 28px 16px;
  }

  .formPanel {
    padding: 32px 16px;
    background: transparent;
  }

  .heroTitle {
    font-size: 24px;
  }

  

  .title {
    font-size: 26px;
  }

  .subTitle {
    font-size: 14px;
  }
}
</style>