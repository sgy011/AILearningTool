import { api } from './http'

export async function docsMergeConvert(payload: {
  files: File[]
  order?: number[]
  out_format: 'docx' | 'pdf' | 'xlsx'
  name?: string
  header_case_insensitive?: boolean
  column_merge_mode?: 'union' | 'intersection'
}): Promise<Blob> {
  const fd = new FormData()
  payload.files.forEach((f) => fd.append('files', f))
  if (payload.order && payload.order.length) fd.append('order', JSON.stringify(payload.order))
  fd.append('out_format', payload.out_format)
  if (payload.name) fd.append('name', payload.name)
  if (payload.header_case_insensitive != null) {
    fd.append('header_case_insensitive', payload.header_case_insensitive ? 'true' : 'false')
  }
  if (payload.column_merge_mode) fd.append('column_merge_mode', payload.column_merge_mode)
  const resp = await api.post('/api/docs/merge-convert', fd, { responseType: 'blob' })
  return resp.data as Blob
}

