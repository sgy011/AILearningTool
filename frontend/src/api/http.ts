import axios, { type AxiosError, type AxiosInstance } from 'axios'

export type ApiError = {
  status?: number
  message: string
  raw?: unknown
}

export function normalizeApiError(e: unknown): ApiError {
  const ax = e as AxiosError<any>
  const status = ax?.response?.status
  const data = ax?.response?.data
  const msg =
    (typeof data?.error === 'string' && data.error) ||
    (typeof data?.message === 'string' && data.message) ||
    ax?.message ||
    '请求失败'
  return { status, message: msg, raw: e }
}

export function createApiClient(): AxiosInstance {
  const api = axios.create({
    baseURL: '',
    withCredentials: true,
    timeout: 120_000,
  })

  api.interceptors.request.use((config) => config)

  api.interceptors.response.use(
    (r) => r,
    (err) => Promise.reject(err),
  )
  return api
}

export const api = createApiClient()

/** 直接执行任务，不再显示全局加载遮罩 */
export async function withProcessing<T>(task: () => Promise<T>): Promise<T> {
  return task()
}

