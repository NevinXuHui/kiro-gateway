import { useState, useEffect } from 'react'
import { Moon, Sun, Zap, LogOut, RefreshCw, Shield, Server, Wifi, Settings, LayoutGrid, Key, Trash2, Plus, Copy, Send, Clock } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useGatewayStatus, useCredentials, useRefreshCredentials, useModels, useGatewayConfig, useConnectivityTest, useImportCredentials, useImportHistory, useUsage, useApiKeys, useCreateApiKey, useUpdateApiKey, useDeleteApiKey, useChatTest, useHistory, useClearHistory } from '@/hooks/use-admin'

interface DashboardProps {
  onLogout: () => void
}

function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text).catch(() => fallbackCopy(text))
  }
  return fallbackCopy(text)
}

function fallbackCopy(text: string): Promise<void> {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  document.execCommand('copy')
  document.body.removeChild(ta)
  return Promise.resolve()
}

export function Dashboard({ onLogout }: DashboardProps) {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem('admin-active-tab') || 'overview')
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem('task-ui-dark')
    if (saved !== null) return saved === 'true'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => { document.documentElement.classList.toggle('dark', darkMode) }, [darkMode])
  useEffect(() => { localStorage.setItem('admin-active-tab', activeTab) }, [activeTab])

  const toggleDark = () => {
    const next = !darkMode
    setDarkMode(next)
    localStorage.setItem('task-ui-dark', String(next))
  }

  const { data: status } = useGatewayStatus()
  const { data: creds } = useCredentials()
  const { data: models } = useModels()
  const { data: config } = useGatewayConfig()
  const refreshMutation = useRefreshCredentials()
  const connectivityMutation = useConnectivityTest()
  const importMutation = useImportCredentials()
  const { data: importHistory } = useImportHistory()
  const { data: usage } = useUsage()
  const { data: apiKeysData } = useApiKeys()
  const createApiKeyMutation = useCreateApiKey()
  const updateApiKeyMutation = useUpdateApiKey()
  const deleteApiKeyMutation = useDeleteApiKey()
  const [newKeyName, setNewKeyName] = useState('')
  const [chatModel, setChatModel] = useState('')
  const [chatMessage, setChatMessage] = useState('Hello, reply in one sentence.')
  const [chatEndpoint, setChatEndpoint] = useState<'openai' | 'anthropic'>('openai')
  const [chatStream, setChatStream] = useState(false)
  const [credentialsJson, setCredentialsJson] = useState('')
  const chatTestMutation = useChatTest()
  const { data: historyData } = useHistory()
  const clearHistoryMutation = useClearHistory()
  const [expandedErrors, setExpandedErrors] = useState<Set<string>>(new Set())

  const handleRefresh = () => queryClient.invalidateQueries()
  const handleImportCredentials = () => {
    if (!credentialsJson.trim()) {
      toast.error('请输入凭证 JSON')
      return
    }
    importMutation.mutate(credentialsJson.trim(), {
      onSuccess: (r) => {
        toast.success(`凭证导入成功 (${r.auth_type} / ${r.region})`)
        setCredentialsJson('')
      },
      onError: (err: any) => toast.error(err?.response?.data?.detail || '凭证导入失败'),
    })
  }
  const handleTokenRefresh = () => {
    refreshMutation.mutate(undefined, {
      onSuccess: () => toast.success('Token 刷新成功'),
      onError: () => toast.error('Token 刷新失败'),
    })
  }
  const handleConnTest = () => {
    connectivityMutation.mutate(undefined, {
      onSuccess: (r) => r.success ? toast.success(`连通性测试通过 (${r.latency_ms}ms)`) : toast.error(`测试失败: ${r.error}`),
      onError: () => toast.error('连通性测试失败'),
    })
  }

  const formatUptime = (s: number) => {
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    return h > 0 ? `${h}h ${m}m` : `${m}m`
  }

  const tabs = [
    { id: 'overview', label: '概览', icon: LayoutGrid },
    { id: 'credentials', label: '凭据', icon: Shield },
    { id: 'apikeys', label: 'API Keys', icon: Key },
    { id: 'models', label: '模型', icon: Server },
    { id: 'connectivity', label: '连通性', icon: Wifi },
    { id: 'history', label: '历史', icon: Clock },
    { id: 'settings', label: '配置', icon: Settings },
  ]

  return (
    <div className="min-h-screen bg-background">
      {/* 顶部导航栏 */}
      <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto flex h-14 items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-primary" />
            <span className="font-semibold text-lg">Kiro Gateway</span>
            {status && <Badge variant="outline" className="ml-2">v{status.version}</Badge>}
          </div>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" onClick={handleRefresh} title="刷新"><RefreshCw className="h-4 w-4" /></Button>
            <Button variant="ghost" size="icon" onClick={toggleDark} title="切换主题">{darkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}</Button>
            <Button variant="ghost" size="icon" onClick={onLogout} title="登出"><LogOut className="h-4 w-4" /></Button>
          </div>
        </div>
      </header>

      {/* Tab 导航 */}
      <div className="border-b">
        <div className="container mx-auto px-4">
          <nav className="flex gap-1 overflow-x-auto">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${activeTab === tab.id ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
                  <Icon className="h-4 w-4" />{tab.label}
                </button>
              )
            })}
          </nav>
        </div>
      </div>

      <main className="container mx-auto px-4 py-6 space-y-6">
        {/* 概览 Tab */}
        {activeTab === 'overview' && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <Card><CardContent className="p-4"><p className="text-sm text-muted-foreground">运行时间</p><p className="text-2xl font-bold">{status ? formatUptime(status.uptime_seconds) : '-'}</p></CardContent></Card>
              <Card><CardContent className="p-4"><p className="text-sm text-muted-foreground">Token 状态</p><p className="text-2xl font-bold">{status?.token_valid ? <span className="text-green-500">有效</span> : <span className="text-red-500">无效</span>}</p></CardContent></Card>
              <Card><CardContent className="p-4"><p className="text-sm text-muted-foreground">可用模型</p><p className="text-2xl font-bold">{status?.models_loaded ?? 0}</p></CardContent></Card>
              <Card><CardContent className="p-4"><p className="text-sm text-muted-foreground">剩余使用量</p><p className="text-2xl font-bold">{usage ? `${usage.remaining} / ${usage.limit}` : '-'}</p></CardContent></Card>
            </div>
            <Card><CardHeader><CardTitle className="text-base">快速操作</CardTitle></CardHeader>
              <CardContent className="flex flex-wrap gap-3">
                <Button onClick={handleTokenRefresh} disabled={refreshMutation.isPending}>{refreshMutation.isPending ? '刷新中...' : '刷新 Token'}</Button>
                <Button variant="outline" onClick={handleConnTest} disabled={connectivityMutation.isPending}>{connectivityMutation.isPending ? '测试中...' : '连通性测试'}</Button>
              </CardContent>
            </Card>
          </>
        )}

        {/* 凭据 Tab */}
        {activeTab === 'credentials' && (
          <>
          <Card>
            <CardHeader><CardTitle className="text-base">凭据状态</CardTitle></CardHeader>
            <CardContent>
              {creds ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-1"><p className="text-sm text-muted-foreground">认证方式</p><p className="font-medium">{creds.auth_type}</p></div>
                    <div className="space-y-1"><p className="text-sm text-muted-foreground">区域</p><p className="font-medium">{creds.region}</p></div>
                    <div className="space-y-1"><p className="text-sm text-muted-foreground">Token 状态</p><Badge variant={creds.token_valid ? 'success' : 'destructive'}>{creds.token_valid ? '有效' : '无效'}</Badge></div>
                    <div className="space-y-1"><p className="text-sm text-muted-foreground">Token 过期时间</p><p className="font-medium">{creds.token_expires_at ? new Date(creds.token_expires_at).toLocaleString('zh-CN') : '-'}</p></div>
                    <div className="space-y-1"><p className="text-sm text-muted-foreground">剩余有效期</p><p className="font-medium">{creds.token_expires_in_seconds != null ? `${Math.floor(creds.token_expires_in_seconds / 60)} 分钟` : '-'}</p></div>
                    <div className="space-y-1"><p className="text-sm text-muted-foreground">Profile ARN</p><p className="font-medium text-xs break-all">{creds.profile_arn || '无'}</p></div>
                    <div className="space-y-1"><p className="text-sm text-muted-foreground">API Host</p><p className="font-medium text-xs break-all">{creds.api_host}</p></div>
                    <div className="space-y-1"><p className="text-sm text-muted-foreground">Q Host</p><p className="font-medium text-xs break-all">{creds.q_host}</p></div>
                  </div>
                  <Button onClick={handleTokenRefresh} disabled={refreshMutation.isPending}>{refreshMutation.isPending ? '刷新中...' : '强制刷新 Token'}</Button>
                </div>
              ) : <p className="text-muted-foreground">加载中...</p>}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">导入凭证</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">粘贴 Kiro 凭证 JSON 内容</p>
              <textarea
                value={credentialsJson}
                onChange={(e) => setCredentialsJson(e.target.value)}
                placeholder='{"refreshToken": "...", "region": "us-east-1", ...}'
                className="w-full h-32 rounded-md border border-input bg-background px-3 py-2 text-sm font-mono resize-y"
              />
              <Button onClick={handleImportCredentials} disabled={importMutation.isPending || !credentialsJson.trim()}>
                {importMutation.isPending ? '导入中...' : '导入凭证'}
              </Button>
            </CardContent>
          </Card>
          {importHistory?.history !== undefined && (
            <Card>
              <CardHeader><CardTitle className="text-base">导入历史</CardTitle></CardHeader>
              <CardContent>
                {importHistory.history.length > 0 ? (
                <div className="space-y-2">
                  {importHistory.history.map((r, i) => (
                    <div key={i} className="flex items-center justify-between p-3 rounded-lg border text-sm">
                      <div className="space-y-0.5">
                        <p className="font-medium">{r.source || 'web_ui'}</p>
                        <p className="text-xs text-muted-foreground">{new Date(r.time).toLocaleString('zh-CN')}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        {r.success ? (
                          <>
                            <Badge variant="success">成功</Badge>
                            <span className="text-xs text-muted-foreground">{r.auth_type} / {r.region}</span>
                          </>
                        ) : (
                          <>
                            <Badge variant="destructive">失败</Badge>
                            <span className="text-xs text-destructive">{r.error}</span>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                ) : <p className="text-sm text-muted-foreground">暂无导入记录</p>}
              </CardContent>
            </Card>
          )}
          </>
        )}

        {/* API Keys Tab */}
        {activeTab === 'apikeys' && (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">API Keys</CardTitle>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    placeholder="Key 名称"
                    value={newKeyName}
                    onChange={(e) => setNewKeyName(e.target.value)}
                    className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && newKeyName.trim()) {
                        createApiKeyMutation.mutate(newKeyName.trim(), {
                          onSuccess: (r) => {
                            toast.success(
                              <div className="space-y-1">
                                <p>API Key 创建成功</p>
                                <div className="flex items-center gap-1">
                                  <code className="text-xs bg-muted px-1 py-0.5 rounded break-all">{r.key}</code>
                                  <button onClick={() => copyToClipboard(r.key).then(() => toast.info('已复制'))} className="shrink-0"><Copy className="h-3 w-3" /></button>
                                </div>
                                <p className="text-xs text-muted-foreground">请立即保存，此密钥仅显示一次</p>
                              </div>,
                              { duration: 30000 }
                            )
                            setNewKeyName('')
                          },
                          onError: (err: any) => toast.error(err?.response?.data?.detail || '创建失败'),
                        })
                      }
                    }}
                  />
                  <Button
                    size="sm"
                    disabled={!newKeyName.trim() || createApiKeyMutation.isPending}
                    onClick={() => {
                      if (!newKeyName.trim()) return
                      createApiKeyMutation.mutate(newKeyName.trim(), {
                        onSuccess: (r) => {
                          toast.success(
                            <div className="space-y-1">
                              <p>API Key 创建成功</p>
                              <div className="flex items-center gap-1">
                                <code className="text-xs bg-muted px-1 py-0.5 rounded break-all">{r.key}</code>
                                <button onClick={() => copyToClipboard(r.key).then(() => toast.info('已复制'))} className="shrink-0"><Copy className="h-3 w-3" /></button>
                              </div>
                              <p className="text-xs text-muted-foreground">请立即保存，此密钥仅显示一次</p>
                            </div>,
                            { duration: 30000 }
                          )
                          setNewKeyName('')
                        },
                        onError: (err: any) => toast.error(err?.response?.data?.detail || '创建失败'),
                      })
                    }}
                  >
                    <Plus className="h-4 w-4 mr-1" />创建
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {apiKeysData?.keys.length ? (
                <div className="grid gap-2">
                  {apiKeysData.keys.map((k) => (
                    <div key={k.id} className="flex items-center justify-between p-3 rounded-lg border">
                      <div className="space-y-0.5">
                        <p className="font-medium text-sm">{k.name}</p>
                        <div className="flex items-center gap-1">
                          <p className="text-xs text-muted-foreground font-mono">{k.key_preview}</p>
                          <button
                            onClick={() => copyToClipboard(k.key_preview).then(() => toast.info('已复制 Key 前缀'))}
                            className="text-muted-foreground hover:text-foreground"
                            title="复制"
                          >
                            <Copy className="h-3 w-3" />
                          </button>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {k.created_at === 'N/A' ? 'N/A' : new Date(k.created_at).toLocaleString('zh-CN')}
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        {k.id !== 'env_default' && (
                          <>
                            <button
                              onClick={() => updateApiKeyMutation.mutate({ id: k.id, updates: { enabled: !k.enabled } }, {
                                onSuccess: () => toast.success(k.enabled ? 'Key 已禁用' : 'Key 已启用'),
                                onError: () => toast.error('更新失败'),
                              })}
                              className="flex items-center gap-2"
                            >
                              <span className={`text-xs font-medium ${k.enabled ? 'text-green-500' : 'text-muted-foreground'}`}>{k.enabled ? '启用' : '禁用'}</span>
                              <span className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${k.enabled ? 'bg-green-500' : 'bg-muted'}`}>
                                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${k.enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                              </span>
                            </button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-destructive hover:text-destructive"
                              onClick={() => {
                                if (confirm('确定要删除此 API Key 吗？')) {
                                  deleteApiKeyMutation.mutate(k.id, {
                                    onSuccess: () => toast.success('Key 已删除'),
                                    onError: () => toast.error('删除失败'),
                                  })
                                }
                              }}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </>
                        )}
                        {k.id === 'env_default' && (
                          <span className="text-xs text-muted-foreground">默认密钥（不可修改）</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : <p className="text-muted-foreground">暂无 API Key</p>}
            </CardContent>
          </Card>
        )}

        {/* 模型 Tab */}
        {activeTab === 'models' && (
          <Card>
            <CardHeader><CardTitle className="text-base">可用模型 ({models?.total ?? 0})</CardTitle></CardHeader>
            <CardContent>
              {models?.models.length ? (
                <div className="grid gap-2">
                  {models.models.map((m) => (
                    <div key={m.id} className="flex items-center justify-between p-3 rounded-lg border">
                      <div><p className="font-medium text-sm">{m.display_name}</p><p className="text-xs text-muted-foreground">{m.id}</p></div>
                      <Badge variant="secondary">{m.provider}</Badge>
                    </div>
                  ))}
                </div>
              ) : <p className="text-muted-foreground">暂无模型数据</p>}
            </CardContent>
          </Card>
        )}

        {/* 连通性 Tab */}
        {activeTab === 'connectivity' && (
          <>
          <Card>
            <CardHeader><CardTitle className="text-base">API 连通性</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">向 Kiro API 发送真实请求，验证凭据、网络和接口可用性。</p>
              <Button onClick={handleConnTest} disabled={connectivityMutation.isPending}>{connectivityMutation.isPending ? '测试中...' : '开始测试'}</Button>
              {connectivityMutation.data && (
                <div className="p-4 rounded-lg border space-y-2">
                  <div className="flex items-center gap-2">
                    <Badge variant={connectivityMutation.data.success ? 'success' : 'destructive'}>{connectivityMutation.data.success ? '通过' : '失败'}</Badge>
                    <span className="text-sm text-muted-foreground">{connectivityMutation.data.latency_ms}ms</span>
                  </div>
                  {connectivityMutation.data.success ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                      <div><span className="text-muted-foreground">认证方式: </span>{connectivityMutation.data.auth_type}</div>
                      <div><span className="text-muted-foreground">区域: </span>{connectivityMutation.data.region}</div>
                      <div><span className="text-muted-foreground">API Host: </span><span className="text-xs">{connectivityMutation.data.api_host}</span></div>
                      <div><span className="text-muted-foreground">可用模型: </span>{connectivityMutation.data.models_count ?? '-'}</div>
                    </div>
                  ) : <p className="text-sm text-destructive">{connectivityMutation.data.error}</p>}
                </div>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Chat 测试</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">选择接口、模型并发送消息，验证完整的请求链路。</p>
              <div className="flex flex-col sm:flex-row gap-3">
                <select
                  value={chatEndpoint}
                  onChange={(e) => setChatEndpoint(e.target.value as 'openai' | 'anthropic')}
                  className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="openai">OpenAI (/v1/chat/completions)</option>
                  <option value="anthropic">Anthropic (/v1/messages)</option>
                </select>
                <select
                  value={chatModel}
                  onChange={(e) => setChatModel(e.target.value)}
                  className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[200px]"
                >
                  <option value="">选择模型...</option>
                  {models?.models.map((m) => (
                    <option key={m.id} value={m.id}>{m.display_name}</option>
                  ))}
                </select>
                <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
                  <button
                    type="button"
                    onClick={() => setChatStream(!chatStream)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${chatStream ? 'bg-primary' : 'bg-muted'}`}
                  >
                    <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${chatStream ? 'translate-x-6' : 'translate-x-1'}`} />
                  </button>
                  Stream
                </label>
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={chatMessage}
                  onChange={(e) => setChatMessage(e.target.value)}
                  placeholder="输入测试消息..."
                  className="flex-1 h-9 rounded-md border border-input bg-background px-3 text-sm"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && chatModel && chatMessage.trim() && !chatTestMutation.isPending) {
                      chatTestMutation.mutate({ model: chatModel, message: chatMessage.trim(), endpoint: chatEndpoint, stream: chatStream })
                    }
                  }}
                />
                <Button
                  size="sm"
                  disabled={!chatModel || !chatMessage.trim() || chatTestMutation.isPending}
                  onClick={() => chatTestMutation.mutate({ model: chatModel, message: chatMessage.trim(), endpoint: chatEndpoint, stream: chatStream })}
                >
                  <Send className="h-4 w-4 mr-1" />{chatTestMutation.isPending ? '请求中...' : '发送'}
                </Button>
              </div>
              {chatTestMutation.data && (
                <div className="p-4 rounded-lg border space-y-2">
                  <div className="flex items-center gap-2">
                    <Badge variant={chatTestMutation.data.success ? 'success' : 'destructive'}>{chatTestMutation.data.success ? '成功' : '失败'}</Badge>
                    <span className="text-sm text-muted-foreground">{chatTestMutation.data.latency_ms}ms</span>
                    <span className="text-xs text-muted-foreground">{chatTestMutation.data.model}</span>
                  </div>
                  {chatTestMutation.data.success ? (
                    <div className="p-3 rounded bg-muted text-sm whitespace-pre-wrap">{chatTestMutation.data.response}</div>
                  ) : <p className="text-sm text-destructive">{chatTestMutation.data.error}</p>}
                </div>
              )}
            </CardContent>
          </Card>
          </>
        )}

        {/* 历史 Tab */}
        {activeTab === 'history' && (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">请求历史 ({historyData?.total ?? 0})</CardTitle>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={clearHistoryMutation.isPending || !historyData?.total}
                  onClick={() => {
                    if (confirm('确定要清空所有请求历史吗？')) {
                      clearHistoryMutation.mutate(undefined, {
                        onSuccess: (r) => toast.success(`已清空 ${r.cleared} 条记录`),
                        onError: () => toast.error('清空失败'),
                      })
                    }
                  }}
                >
                  <Trash2 className="h-4 w-4 mr-1" />{clearHistoryMutation.isPending ? '清空中...' : '清空'}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {historyData?.records.length ? (
                <div className="grid gap-2">
                  {historyData.records.map((r) => (
                    <div key={r.id} className="p-3 rounded-lg border space-y-1">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs text-muted-foreground">{new Date(r.time).toLocaleString('zh-CN')}</span>
                          <Badge variant="secondary" className="font-mono text-xs">{r.endpoint}</Badge>
                          <span className="text-sm font-medium">{r.model}</span>
                          {r.stream && <Badge variant="outline" className="text-xs">stream</Badge>}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-muted-foreground">{r.latency_ms}ms</span>
                          <Badge variant={r.status_code >= 200 && r.status_code < 300 ? 'success' : r.status_code >= 400 && r.status_code < 500 ? 'warning' : 'destructive'}>
                            {r.status_code}
                          </Badge>
                        </div>
                      </div>
                      {r.error && (
                        <div>
                          <button
                            className="text-xs text-destructive hover:underline"
                            onClick={() => setExpandedErrors(prev => {
                              const next = new Set(prev)
                              next.has(r.id) ? next.delete(r.id) : next.add(r.id)
                              return next
                            })}
                          >
                            {expandedErrors.has(r.id) ? '收起错误' : '查看错误'}
                          </button>
                          {expandedErrors.has(r.id) && (
                            <p className="text-xs text-destructive mt-1 p-2 rounded bg-destructive/10 break-all">{r.error}</p>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : <p className="text-muted-foreground">暂无请求记录</p>}
            </CardContent>
          </Card>
        )}

        {/* 配置 Tab */}
        {activeTab === 'settings' && (
          <Card>
            <CardHeader><CardTitle className="text-base">网关配置</CardTitle></CardHeader>
            <CardContent>
              {config ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1"><p className="text-sm text-muted-foreground">版本</p><p className="font-medium">{config.version}</p></div>
                  <div className="space-y-1"><p className="text-sm text-muted-foreground">监听地址</p><p className="font-medium">{config.server_host}:{config.server_port}</p></div>
                  <div className="space-y-1"><p className="text-sm text-muted-foreground">区域</p><p className="font-medium">{config.region}</p></div>
                  <div className="space-y-1"><p className="text-sm text-muted-foreground">代理</p><Badge variant={config.proxy_enabled ? 'success' : 'secondary'}>{config.proxy_enabled ? '已启用' : '未启用'}</Badge>{config.proxy_url && <p className="text-xs text-muted-foreground mt-1">{config.proxy_url}</p>}</div>
                </div>
              ) : <p className="text-muted-foreground">加载中...</p>}
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  )
}

