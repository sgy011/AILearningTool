import { api } from './http'

export type AuthMeResponse = {
  success: boolean
  logged_in: boolean
  email: string | null
  username: string | null
}

export async function authMe(): Promise<AuthMeResponse> {
  const { data } = await api.get<AuthMeResponse>('/api/auth/me')
  return data
}

export async function authLogout(): Promise<{ success: boolean }> {
  const { data } = await api.post('/api/auth/logout')
  return data
}

export async function authLogin(payload: { email: string; password: string }): Promise<{ success: boolean; error?: string }> {
  const { data } = await api.post('/api/auth/login', payload)
  return data
}

export async function authRegisterRequestCode(payload: { email: string }): Promise<{ success: boolean; error?: string }> {
  const { data } = await api.post('/api/auth/register/request-code', payload)
  return data
}

export async function authRegister(payload: {
  username: string
  email: string
  password: string
  code: string
}): Promise<{ success: boolean; error?: string }> {
  const { data } = await api.post('/api/auth/register', payload)
  return data
}

export async function authResetRequestCode(payload: { email: string }): Promise<{ success: boolean; error?: string }> {
  const { data } = await api.post('/api/auth/reset/request-code', payload)
  return data
}

export async function authResetPassword(payload: {
  email: string
  code: string
  password: string
}): Promise<{ success: boolean; error?: string }> {
  const { data } = await api.post('/api/auth/reset', payload)
  return data
}

