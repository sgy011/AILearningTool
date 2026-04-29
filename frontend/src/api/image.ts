import { api } from './http'

export async function convertImage(payload: {
  file: File
  format: string
  quality: number
  mode: 'convert' | 'repair'
}): Promise<{ success: boolean; converted_data?: string; error?: string }> {
  const fd = new FormData()
  fd.append('file', payload.file)
  fd.append('format', payload.format)
  // 后端接受 float 0~1 或 1~100；这里传 0~1，保持语义一致
  fd.append('quality', String(payload.quality))
  fd.append('mode', payload.mode)
  const { data } = await api.post('/convert', fd)
  return data
}

