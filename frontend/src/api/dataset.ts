import { api, withProcessing } from './http'
import { filenameFromContentDisposition } from './download'

export async function datasetProcessLocal(payload: {
  images_dir: string
  labels_dir?: string
  in_format: string
  out_format: string
  train: number
  val: number
  test: number
  seed: number
  name?: string
}): Promise<Blob> {
  const resp = await api.post('/api/dataset/process-local', payload, { responseType: 'blob' })
  return resp.data as Blob
}

export async function datasetProcess(payload: {
  zip: File
  in_format: string
  out_format: string
  train: number
  val: number
  test: number
  seed: number
  name?: string
}): Promise<Blob> {
  const fd = new FormData()
  fd.append('file', payload.zip)
  fd.append('in_format', payload.in_format)
  fd.append('out_format', payload.out_format)
  fd.append('train', String(payload.train))
  fd.append('val', String(payload.val))
  fd.append('test', String(payload.test))
  fd.append('seed', String(payload.seed))
  if (payload.name) fd.append('name', payload.name)
  const resp = await api.post('/api/dataset/process', fd, { responseType: 'blob' })
  return resp.data as Blob
}

export async function datasetScrapeClean(payload: {
  query: string
  count: number
  min_width: number
  min_height: number
  seed: number
  model?: string
  name?: string
}): Promise<{ blob: Blob; filename: string | null }> {
  const fd = new FormData()
  fd.append('query', payload.query)
  fd.append('count', String(payload.count))
  fd.append('min_width', String(payload.min_width))
  fd.append('min_height', String(payload.min_height))
  fd.append('seed', String(payload.seed))
  if (payload.model) fd.append('model', payload.model)
  if (payload.name) fd.append('name', payload.name)
  const resp = await withProcessing(() =>
    fetch('/api/dataset/scrape-clean', {
      method: 'POST',
      body: fd,
      credentials: 'include',
    }),
  )
  const contentType = (resp.headers.get('Content-Type') || '').toLowerCase()
  if (contentType.includes('application/json')) {
    const data = await resp.json().catch(() => ({}))
    throw new Error(data?.error || data?.message || `请求失败（${resp.status}）`)
  }
  if (!resp.ok) {
    throw new Error(`请求失败（${resp.status}）`)
  }
  const blob = await resp.blob()
  const filename = filenameFromContentDisposition(resp.headers.get('Content-Disposition'))
  return { blob, filename }
}

export async function datasetScrapeOnly(payload: {
  query: string
  count: number
  name?: string
}): Promise<{ blob: Blob; filename: string | null }> {
  const fd = new FormData()
  fd.append('query', payload.query)
  fd.append('count', String(payload.count))
  if (payload.name) fd.append('name', payload.name)
  const resp = await withProcessing(() =>
    fetch('/api/dataset/scrape-only', {
      method: 'POST',
      body: fd,
      credentials: 'include',
    }),
  )
  const contentType = (resp.headers.get('Content-Type') || '').toLowerCase()
  if (contentType.includes('application/json')) {
    const data = await resp.json().catch(() => ({}))
    throw new Error(data?.error || data?.message || `请求失败（${resp.status}）`)
  }
  if (!resp.ok) {
    throw new Error(`请求失败（${resp.status}）`)
  }
  const blob = await resp.blob()
  const filename = filenameFromContentDisposition(resp.headers.get('Content-Disposition'))
  return { blob, filename }
}

export async function mmAlignScrapeCleanCaption(payload: {
  query: string
  count: number
  min_width: number
  min_height: number
  seed: number
  export_format: 'txt' | 'jsonl' | 'csv'
  model?: string
  name?: string
}): Promise<{ blob: Blob; filename: string | null }> {
  const fd = new FormData()
  fd.append('query', payload.query)
  fd.append('count', String(payload.count))
  fd.append('min_width', String(payload.min_width))
  fd.append('min_height', String(payload.min_height))
  fd.append('seed', String(payload.seed))
  fd.append('export_format', payload.export_format)
  if (payload.model) fd.append('model', payload.model)
  if (payload.name) fd.append('name', payload.name)
  const resp = await withProcessing(() =>
    fetch('/api/mm-align/scrape-clean-caption', {
      method: 'POST',
      body: fd,
      credentials: 'include',
    }),
  )
  const contentType = (resp.headers.get('Content-Type') || '').toLowerCase()
  if (contentType.includes('application/json')) {
    const data = await resp.json().catch(() => ({}))
    throw new Error(data?.error || data?.message || `请求失败（${resp.status}）`)
  }
  if (!resp.ok) throw new Error(`请求失败（${resp.status}）`)
  const blob = await resp.blob()
  const filename = filenameFromContentDisposition(resp.headers.get('Content-Disposition'))
  return { blob, filename }
}

export async function mmAlignUploadCaption(payload: {
  files: File[]
  export_format: 'txt' | 'jsonl' | 'csv'
  model?: string
  name?: string
  query?: string
}): Promise<{ blob: Blob; filename: string | null }> {
  const fd = new FormData()
  payload.files.forEach((f) => fd.append('files', f))
  fd.append('export_format', payload.export_format)
  if (payload.model) fd.append('model', payload.model)
  if (payload.name) fd.append('name', payload.name)
  if (payload.query) fd.append('query', payload.query)
  const resp = await withProcessing(() =>
    fetch('/api/mm-align/upload-caption', {
      method: 'POST',
      body: fd,
      credentials: 'include',
    }),
  )
  const contentType = (resp.headers.get('Content-Type') || '').toLowerCase()
  if (contentType.includes('application/json')) {
    const data = await resp.json().catch(() => ({}))
    throw new Error(data?.error || data?.message || `请求失败（${resp.status}）`)
  }
  if (!resp.ok) throw new Error(`请求失败（${resp.status}）`)
  const blob = await resp.blob()
  const filename = filenameFromContentDisposition(resp.headers.get('Content-Disposition'))
  return { blob, filename }
}

export async function getMmAlignModels(): Promise<{ models: string[]; default_model: string }> {
  const resp = await api.get('/api/mm-align/models')
  return {
    models: Array.isArray(resp.data?.models) ? resp.data.models : [],
    default_model: String(resp.data?.default_model || ''),
  }
}

