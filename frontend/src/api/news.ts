import { api } from './http'

export async function newsSearch(payload: {
  limit: number
  use_ai: boolean
  feed: 'softunis' | 'tencent'
  qq_channel?: string
  softunis_tag?: string
}): Promise<any> {
  const { data } = await api.post('/api/news/search', payload)
  return data
}

export async function newsConfig(): Promise<any> {
  const { data } = await api.get('/api/news/config')
  return data
}

export async function newsPushplusConfigGet(): Promise<any> {
  const { data } = await api.get('/api/news/pushplus-config')
  return data
}

export async function newsPushplusConfigSave(payload: {
  enabled: boolean
  token: string
  feed: 'softunis' | 'tencent'
  softunis_tag?: string
  qq_channel?: string
  limit: number
  use_ai: boolean
  push_time: string
}): Promise<any> {
  const { data } = await api.post('/api/news/pushplus-config', payload)
  return data
}

export async function newsPushplusPushNow(payload?: {
  feed?: 'softunis' | 'tencent'
  softunis_tag?: string
  qq_channel?: string
  limit?: number
  use_ai?: boolean
}): Promise<any> {
  const { data } = await api.post('/api/news/pushplus-push-now', payload || {})
  return data
}

