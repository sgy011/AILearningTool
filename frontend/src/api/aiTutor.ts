import { api } from './http'

export async function kbIngest(roots: string[]) {
  const { data } = await api.post('/api/kb/ingest', { roots })
  return data
}

export async function aiTutorChat(message: string, top_k?: number) {
  const { data } = await api.post('/api/ai-tutor/chat', { message, top_k })
  return data
}

