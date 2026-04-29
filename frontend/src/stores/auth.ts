import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authLogin, authLogout, authMe } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const loaded = ref(false)
  const loggedIn = ref(false)
  const email = ref<string | null>(null)
  const username = ref<string | null>(null)

  const displayName = computed(() => username.value || email.value || '')

  async function refresh() {
    const d = await authMe()
    loaded.value = true
    loggedIn.value = !!d.logged_in
    email.value = d.email || null
    username.value = d.username || null
    return d
  }

  async function login(payload: { email: string; password: string }) {
    const d = await authLogin(payload)
    if (!d.success) return d
    await refresh()
    return d
  }

  async function logout() {
    try {
      await authLogout()
    } finally {
      loaded.value = true
      loggedIn.value = false
      email.value = null
      username.value = null
    }
  }

  return { loaded, loggedIn, email, username, displayName, refresh, login, logout }
})

