import { api } from './http'

export async function imageAugment(payload: {
  files: File[]
  ops: string[]
  format: string
  quality: number
}): Promise<Blob> {
  const fd = new FormData()
  payload.files.forEach((f) => fd.append('files', f))
  payload.ops.forEach((o) => fd.append('ops', o))
  fd.append('format', payload.format)
  fd.append('quality', String(payload.quality))
  const resp = await api.post('/api/image-augment', fd, { responseType: 'blob' })
  return resp.data as Blob
}

export async function imageAugmentOptions(): Promise<any> {
  const { data } = await api.get('/api/image-augment/options')
  return data
}

