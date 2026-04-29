import { api } from './http'

export async function launchLabelImg(payload: { images_dir: string; save_dir?: string }) {
  const { data } = await api.post('/api/labelimg/launch', payload)
  return data
}

