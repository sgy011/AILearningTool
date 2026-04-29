import { api } from './http'

export async function getModelFormats(): Promise<any> {
  const { data } = await api.get('/api/model-formats')
  return data
}

export async function convertModel(payload: {
  file: File
  format: string
  input_shape?: string
  opset_version?: number
}): Promise<any> {
  const fd = new FormData()
  fd.append('file', payload.file)
  fd.append('format', payload.format)
  if (payload.input_shape) fd.append('input_shape', payload.input_shape)
  if (payload.opset_version != null) fd.append('opset_version', String(payload.opset_version))
  const { data } = await api.post('/convert-model', fd)
  return data
}

