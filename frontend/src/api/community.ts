import { api } from './http'

export interface Post {
  id: number
  user_id: number
  username: string
  title: string
  content: string
  category: string
  post_type: 'question' | 'project'
  attachment_name: string | null
  project_link: string | null
  reply_count: number
  created_at: number
}

export interface PostDetail extends Post {
  attachment_path: string | null
  updated_at: number
}

export interface Reply {
  id: number
  post_id: number
  user_id: number
  username: string
  content: string
  created_at: number
}

export async function getCategories(): Promise<string[]> {
  const { data } = await api.get<{ success: boolean; categories: string[] }>('/api/community/categories')
  return data.categories
}

export async function getPosts(params: {
  category?: string
  post_type?: string
  keyword?: string
  page?: number
  page_size?: number
}): Promise<{ items: Post[]; total: number }> {
  const { data } = await api.get('/api/community/posts', { params })
  return { items: data.items, total: data.total }
}

export async function getPostDetail(postId: number): Promise<{ post: PostDetail; replies: Reply[] }> {
  const { data } = await api.get(`/api/community/posts/${postId}`)
  return { post: data.post, replies: data.replies }
}

export async function createPost(payload: {
  title: string
  content: string
  category: string
  post_type: string
  attachment?: File
  project_link?: string
}): Promise<{ success: boolean; id: number }> {
  const fd = new FormData()
  fd.append('title', payload.title)
  fd.append('content', payload.content)
  fd.append('category', payload.category)
  fd.append('post_type', payload.post_type)
  if (payload.attachment) fd.append('attachment', payload.attachment)
  if (payload.project_link) fd.append('project_link', payload.project_link)
  const { data } = await api.post('/api/community/posts', fd)
  return data
}

export async function deletePost(postId: number): Promise<{ success: boolean }> {
  const { data } = await api.delete(`/api/community/posts/${postId}`)
  return data
}

export function downloadAttachmentUrl(postId: number): string {
  return `/api/community/posts/${postId}/download`
}

export async function createReply(postId: number, content: string): Promise<{ success: boolean; id: number }> {
  const { data } = await api.post(`/api/community/posts/${postId}/replies`, { content })
  return data
}

export async function getReplies(postId: number): Promise<Reply[]> {
  const { data } = await api.get(`/api/community/posts/${postId}/replies`)
  return data.replies
}
