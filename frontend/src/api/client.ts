import type {
  Account,
  AccountCreatePayload,
  ApiResponse,
  Course,
  LogRecord,
  SettingsPayload,
  TargetGroupPayload,
  TaskCreatePayload,
  TaskRecord,
} from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  const payload = (await response.json()) as ApiResponse<T>
  if (!response.ok || payload.code !== 0) {
    throw new Error(payload.message || '请求失败')
  }
  return payload.data
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  settings: () => request<SettingsPayload>('/settings'),
  saveSettings: (payload: SettingsPayload) =>
    request<SettingsPayload>('/settings', { method: 'PUT', body: JSON.stringify(payload) }),
  accounts: () => request<Account[]>('/accounts'),
  createAccount: (payload: AccountCreatePayload) =>
    request<Account>('/accounts', { method: 'POST', body: JSON.stringify(payload) }),
  initializeAccount: (accountId: string) =>
    request<Account>(`/accounts/${accountId}/initialize`, { method: 'POST' }),
  courses: (accountId: string, keyword = '') =>
    request<Course[]>(`/accounts/${accountId}/courses?keyword=${encodeURIComponent(keyword)}`),
  targets: (accountId: string) => request<TargetGroupPayload[]>(`/accounts/${accountId}/targets`),
  saveTargets: (accountId: string, groups: TargetGroupPayload[]) =>
    request(`/accounts/${accountId}/targets`, { method: 'PUT', body: JSON.stringify({ groups }) }),
  tasks: () => request<TaskRecord[]>('/tasks'),
  task: (taskId: string) => request<TaskRecord & { logs: LogRecord[] }>(`/tasks/${taskId}`),
  createTask: (payload: TaskCreatePayload) =>
    request<TaskRecord>('/tasks', { method: 'POST', body: JSON.stringify(payload) }),
  stopTask: (taskId: string) => request<TaskRecord>(`/tasks/${taskId}/stop`, { method: 'POST' }),
  eventsUrl: (taskId: string) => `${API_BASE}/tasks/${taskId}/events`,
}
