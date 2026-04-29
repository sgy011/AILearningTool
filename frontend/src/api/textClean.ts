import { api, withProcessing } from './http'

export async function getTextCleanConfig(): Promise<any> {
  const { data } = await api.get('/api/text-clean/config')
  return data
}

export async function textCleanPreview(payload: {
  title?: string
  text?: string
  source?: 'paste' | 'generate'
  prompt?: string
  instructions?: string
  use_ai?: boolean
  gen_kind?: string
  format?: string
  file?: File | null
}): Promise<any> {
  if (!payload.file) {
    const body: Record<string, unknown> = {
      source: payload.source || 'paste',
      use_ai: payload.use_ai ?? true,
      gen_kind: payload.gen_kind,
    }
    if (body.source === 'generate') body.prompt = payload.prompt || ''
    else body.text = payload.text || ''
    const { data } = await api.post('/api/text-clean/preview', body)
    return data
  }

  const fd = new FormData()
  if (payload.title) fd.append('title', payload.title)
  if (payload.instructions) fd.append('instructions', payload.instructions)
  fd.append('use_ai', payload.use_ai ? 'true' : 'false')
  if (payload.gen_kind) fd.append('gen_kind', payload.gen_kind)
  if (payload.format) fd.append('format', payload.format)
  if (payload.file) fd.append('file', payload.file)
  const { data } = await api.post('/api/text-clean/preview', fd)
  return data
}

export async function textCleanExport(fd: FormData): Promise<Response> {
  // 这里不用 axios：需要读取 headers + blob，更贴近浏览器 fetch
  return withProcessing(() =>
    fetch('/api/text-clean/export', {
      method: 'POST',
      body: fd,
      credentials: 'include',
    }),
  )
}

