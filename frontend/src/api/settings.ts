import { api } from './http'

export type ModelscopeSettings = {
  success: boolean
  provider?: string
  token_set?: boolean
  token_preview?: string
  moonshot_key_set?: boolean
  moonshot_key_preview?: string
  base_url?: string
  moonshot_base_url?: string
  chat_model?: string
  moonshot_chat_model?: string
  error?: string
}

export type ModelscopeSettingsSavePayload = {
  provider: string
  base_url: string
  moonshot_base_url: string
  chat_model: string
  moonshot_chat_model: string
  token?: string
  clear_token?: boolean
  moonshot_api_key?: string
  clear_moonshot_key?: boolean
}

export async function getModelscopeSettings(): Promise<ModelscopeSettings> {
  const { data } = await api.get<ModelscopeSettings>('/api/settings/modelscope')
  return data
}

export async function saveModelscopeSettings(
  payload: ModelscopeSettingsSavePayload,
): Promise<ModelscopeSettings & { refresh_error?: string }> {
  const { data } = await api.post('/api/settings/modelscope', payload)
  return data
}

