export type TaskStatus = 'scheduled' | 'running' | 'completed' | 'failed' | 'stopped'

export interface Account {
  id: string
  name: string
  studentId: string
  cookieMasked: string
  profileId: number
  semesterId: number
  status: 'valid' | 'expired' | 'checking'
}

export interface Course {
  id: string
  no: string
  code: string
  name: string
  teacher: string
  credits: number
  campus: string
  schedule: string
  selected: number
  capacity: number
  available: boolean
  group?: string
  priority?: number
}

export interface CourseGroup {
  id: string
  name: string
  limit: number
  courses: Course[]
}

export interface TaskRecord {
  id: string
  accountName: string
  status: TaskStatus
  startTime: string
  progress: number
  successCount: number
  targetCount: number
}

export interface LogRecord {
  id: number
  time: string
  level: 'INFO' | 'SUCCESS' | 'WARNING' | 'ERROR'
  message: string
}

export interface ApiResponse<T> {
  code: number | string
  message: string
  data: T
}

export interface TargetGroupPayload {
  id?: string
  name: string
  limit: number
  courseNos: string[]
}

export interface AccountCreatePayload {
  name: string
  cookie: string
  validate?: boolean
}

export interface TaskCreatePayload {
  accountIds: string[]
  startTime: string
  skipPrecheck: boolean
}

export interface SettingsPayload {
  domain: string
  profileId: number
  semesterId: number
  startTime: string
  skipPre: boolean
}
