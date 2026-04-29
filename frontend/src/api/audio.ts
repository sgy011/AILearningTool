import { api } from './http'

export async function repairAudio(payload: {
  file: File
  format: string
  quality: number
  auto_detect_mono: boolean
  enhance_stereo: boolean
  mode: 'convert' | 'repair'
}): Promise<{ success: boolean; repaired_data?: string; audio_info?: any; error?: string }> {
  const fd = new FormData()
  fd.append('file', payload.file)
  fd.append('format', payload.format)
  fd.append('quality', String(payload.quality))
  fd.append('auto_detect_mono', payload.auto_detect_mono ? 'true' : 'false')
  fd.append('enhance_stereo', payload.enhance_stereo ? 'true' : 'false')
  fd.append('mode', payload.mode)
  const { data } = await api.post('/repair-audio', fd)
  return data
}

