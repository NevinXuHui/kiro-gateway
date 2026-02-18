import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getStatus, getCredentials, refreshCredentials, getModels, getConfig, testConnectivity, importCredentials, getImportHistory, getUsage, getApiKeys, createApiKey, updateApiKey, deleteApiKey, chatTest, getHistory, clearHistory } from '@/api/admin'
import type { ApiKeyUpdateRequest, ChatTestRequest } from '@/types/admin'

export function useGatewayStatus() {
  return useQuery({
    queryKey: ['gateway-status'],
    queryFn: getStatus,
    refetchInterval: 10000,
  })
}

export function useCredentials() {
  return useQuery({
    queryKey: ['credentials'],
    queryFn: getCredentials,
    refetchInterval: 30000,
  })
}

export function useRefreshCredentials() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: refreshCredentials,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['credentials'] })
      qc.invalidateQueries({ queryKey: ['gateway-status'] })
      qc.invalidateQueries({ queryKey: ['usage'] })
      qc.invalidateQueries({ queryKey: ['models'] })
    },
  })
}

export function useModels() {
  return useQuery({
    queryKey: ['models'],
    queryFn: getModels,
  })
}

export function useGatewayConfig() {
  return useQuery({
    queryKey: ['gateway-config'],
    queryFn: getConfig,
  })
}

export function useConnectivityTest() {
  return useMutation({
    mutationFn: testConnectivity,
  })
}

export function useImportCredentials() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: importCredentials,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['credentials'] })
      qc.invalidateQueries({ queryKey: ['gateway-status'] })
      qc.invalidateQueries({ queryKey: ['import-history'] })
      qc.invalidateQueries({ queryKey: ['usage'] })
      qc.invalidateQueries({ queryKey: ['models'] })
    },
  })
}

export function useImportHistory() {
  return useQuery({
    queryKey: ['import-history'],
    queryFn: getImportHistory,
  })
}

export function useUsage() {
  return useQuery({
    queryKey: ['usage'],
    queryFn: getUsage,
    refetchInterval: 60000,
  })
}

export function useApiKeys() {
  return useQuery({
    queryKey: ['apikeys'],
    queryFn: getApiKeys,
  })
}

export function useCreateApiKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => createApiKey(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['apikeys'] })
    },
  })
}

export function useUpdateApiKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: ApiKeyUpdateRequest }) => updateApiKey(id, updates),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['apikeys'] })
    },
  })
}

export function useDeleteApiKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteApiKey(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['apikeys'] })
    },
  })
}

export function useChatTest() {
  return useMutation({
    mutationFn: (req: ChatTestRequest) => chatTest(req),
  })
}

export function useHistory() {
  return useQuery({
    queryKey: ['request-history'],
    queryFn: () => getHistory(),
    refetchInterval: 10000,
  })
}

export function useClearHistory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: clearHistory,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['request-history'] })
    },
  })
}
