import axios from 'axios'
import { storage } from '@/lib/storage'
import type { GatewayStatus, CredentialStatus, ModelsResponse, GatewayConfig, ConnectivityResult, ImportCredentialsResult, ImportHistoryResponse, UsageInfo, ApiKeyListResponse, ApiKeyCreateResult, ApiKeyInfo, ApiKeyUpdateRequest, ChatTestRequest, ChatTestResult, RequestHistoryResponse } from '@/types/admin'

const api = axios.create({
  baseURL: '/api/admin',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const apiKey = storage.getApiKey()
  if (apiKey) {
    config.headers['Authorization'] = `Bearer ${apiKey}`
  }
  return config
})

export async function getStatus(): Promise<GatewayStatus> {
  const { data } = await api.get<GatewayStatus>('/status')
  return data
}

export async function getCredentials(): Promise<CredentialStatus> {
  const { data } = await api.get<CredentialStatus>('/credentials')
  return data
}

export async function refreshCredentials(): Promise<{ success: boolean; message: string }> {
  const { data } = await api.post('/credentials/refresh')
  return data
}

export async function getModels(): Promise<ModelsResponse> {
  const { data } = await api.get<ModelsResponse>('/models')
  return data
}

export async function getConfig(): Promise<GatewayConfig> {
  const { data } = await api.get<GatewayConfig>('/config')
  return data
}

export async function testConnectivity(): Promise<ConnectivityResult> {
  const { data } = await api.post<ConnectivityResult>('/connectivity/test')
  return data
}

export async function importCredentials(file: File): Promise<ImportCredentialsResult> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post<ImportCredentialsResult>('/credentials/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function getImportHistory(): Promise<ImportHistoryResponse> {
  const { data } = await api.get<ImportHistoryResponse>('/credentials/import/history')
  return data
}

export async function getUsage(): Promise<UsageInfo> {
  const { data } = await api.get<UsageInfo>('/usage')
  return data
}

// --- API Key Management ---

export async function getApiKeys(): Promise<ApiKeyListResponse> {
  const { data } = await api.get<ApiKeyListResponse>('/apikeys')
  return data
}

export async function createApiKey(name: string): Promise<ApiKeyCreateResult> {
  const { data } = await api.post<ApiKeyCreateResult>('/apikeys', { name })
  return data
}

export async function updateApiKey(id: string, updates: ApiKeyUpdateRequest): Promise<ApiKeyInfo> {
  const { data } = await api.put<ApiKeyInfo>(`/apikeys/${id}`, updates)
  return data
}

export async function deleteApiKey(id: string): Promise<void> {
  await api.delete(`/apikeys/${id}`)
}

// --- Request History ---

export async function getHistory(limit = 50, offset = 0): Promise<RequestHistoryResponse> {
  const { data } = await api.get<RequestHistoryResponse>('/history', { params: { limit, offset } })
  return data
}

export async function clearHistory(): Promise<{ cleared: number }> {
  const { data } = await api.delete<{ cleared: number }>('/history')
  return data
}

// --- Chat Test (calls gateway's own /v1/chat/completions) ---

export async function chatTest(req: ChatTestRequest): Promise<ChatTestResult> {
  const apiKey = storage.getApiKey()
  const start = Date.now()
  try {
    if (req.endpoint === 'anthropic') {
      // Anthropic /v1/messages endpoint
      const { data } = await axios.post('/v1/messages', {
        model: req.model,
        messages: [{ role: 'user', content: req.message }],
        stream: req.stream,
        max_tokens: 256,
      }, {
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01',
        },
        ...(req.stream ? { responseType: 'text' } : {}),
      })
      const latency_ms = Date.now() - start
      if (req.stream) {
        // Parse SSE text to extract content
        const text = typeof data === 'string' ? data : ''
        const blocks = text.split('\n').filter((l: string) => l.startsWith('data: ')).map((l: string) => l.slice(6))
        let content = ''
        for (const block of blocks) {
          try {
            const evt = JSON.parse(block)
            if (evt.type === 'content_block_delta' && evt.delta?.text) content += evt.delta.text
          } catch {}
        }
        return { success: true, latency_ms, model: req.model, response: content || '(stream completed)' }
      }
      const content = data?.content?.[0]?.text ?? ''
      return { success: true, latency_ms, model: req.model, response: content }
    } else {
      // OpenAI /v1/chat/completions endpoint
      const { data } = await axios.post('/v1/chat/completions', {
        model: req.model,
        messages: [{ role: 'user', content: req.message }],
        stream: req.stream,
        max_tokens: 256,
      }, {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`,
        },
        ...(req.stream ? { responseType: 'text' } : {}),
      })
      const latency_ms = Date.now() - start
      if (req.stream) {
        // Parse SSE text to extract content
        const text = typeof data === 'string' ? data : ''
        const lines = text.split('\n').filter((l: string) => l.startsWith('data: ') && l !== 'data: [DONE]')
        let content = ''
        for (const line of lines) {
          try {
            const chunk = JSON.parse(line.slice(6))
            const delta = chunk.choices?.[0]?.delta?.content
            if (delta) content += delta
          } catch {}
        }
        return { success: true, latency_ms, model: req.model, response: content || '(stream completed)' }
      }
      const content = data?.choices?.[0]?.message?.content ?? ''
      return { success: true, latency_ms, model: req.model, response: content }
    }
  } catch (e: any) {
    const latency_ms = Date.now() - start
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail || e?.message || String(e)
    return { success: false, latency_ms, model: req.model, error: detail }
  }
}
