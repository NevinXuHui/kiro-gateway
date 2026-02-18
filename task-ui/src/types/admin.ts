// Admin API types matching kiro.rs admin-ui patterns

export interface GatewayStatus {
  version: string
  uptime_seconds: number
  region: string
  auth_type: string
  token_valid: boolean
  token_expires_at: string | null
  models_loaded: number
  proxy_enabled: boolean
  proxy_url: string | null
}

export interface CredentialStatus {
  auth_type: string
  region: string
  token_valid: boolean
  token_expires_at: string | null
  token_expires_in_seconds: number | null
  profile_arn: string | null
  api_host: string
  q_host: string
}

export interface ModelInfo {
  id: string
  display_name: string
  provider: string
}

export interface ModelsResponse {
  models: ModelInfo[]
  total: number
}

export interface GatewayConfig {
  server_host: string
  server_port: number
  region: string
  proxy_enabled: boolean
  proxy_url: string | null
  version: string
}

export interface ConnectivityResult {
  success: boolean
  latency_ms: number
  auth_type?: string
  region?: string
  api_host?: string
  models_count?: number
  error?: string
}

export interface ChatTestRequest {
  model: string
  message: string
  endpoint: 'openai' | 'anthropic'
  stream: boolean
}

export interface ChatTestResult {
  success: boolean
  latency_ms: number
  model: string
  response?: string
  error?: string
}

export interface ImportCredentialsResult {
  success: boolean
  auth_type: string
  region: string
  token_valid: boolean
  api_host: string
  q_host: string
}

export interface ImportHistoryRecord {
  time: string
  source: string
  success: boolean
  auth_type?: string
  region?: string
  token_valid?: boolean
  error?: string
}

export interface ImportHistoryResponse {
  history: ImportHistoryRecord[]
}

export interface UsageInfo {
  limit: number
  used: number
  remaining: number
}

// API Key Management
export interface ApiKeyInfo {
  id: string
  name: string
  key_preview: string
  created_at: string
  enabled: boolean
}

export interface ApiKeyCreateResult {
  id: string
  name: string
  key: string
  created_at: string
}

export interface ApiKeyListResponse {
  keys: ApiKeyInfo[]
}

export interface ApiKeyUpdateRequest {
  name?: string
  enabled?: boolean
}

// Request History
export interface RequestRecord {
  id: string
  time: string
  endpoint: string
  method: string
  model: string
  stream: boolean
  status_code: number
  latency_ms: number
  input_tokens?: number | null
  output_tokens?: number | null
  error?: string | null
}

export interface RequestHistoryResponse {
  records: RequestRecord[]
  total: number
}
