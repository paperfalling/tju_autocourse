<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  Activity,
  ArrowRight,
  Bell,
  BookOpenCheck,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Clock3,
  GraduationCap,
  GripVertical,
  LayoutDashboard,
  MapPin,
  MoreHorizontal,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  SquareTerminal,
  Trash2,
  UserRound,
  UsersRound,
  X,
} from 'lucide-vue-next'
import { api } from './api/client'
import {
  account as mockAccount,
  courses as mockCourses,
  initialGroups,
  logs as mockLogs,
  tasks as mockTasks,
} from './api/mock'
import type { Account, Course, CourseGroup, LogRecord, SettingsPayload, TaskRecord } from './types'

type Page = 'overview' | 'courses' | 'tasks' | 'accounts' | 'settings'

const navItems = [
  { key: 'overview' as Page, label: '概览', icon: LayoutDashboard },
  { key: 'courses' as Page, label: '课程方案', icon: BookOpenCheck },
  { key: 'tasks' as Page, label: '运行任务', icon: Activity },
  { key: 'accounts' as Page, label: '账号管理', icon: UsersRound },
]

const page = ref<Page>('overview')
const keyword = ref('')
const availability = ref<'all' | 'available'>('all')
const useMock = import.meta.env.VITE_USE_MOCK === 'true'
const accounts = ref<Account[]>([mockAccount])
const selectedAccountId = ref(mockAccount.id)
const emptyAccount: Account = { id: '', name: '尚未添加账号', studentId: '', cookieMasked: '未设置', profileId: 0, semesterId: 0, status: 'checking' }
const account = computed(() => accounts.value.find((item) => item.id === selectedAccountId.value) ?? accounts.value[0] ?? (useMock ? mockAccount : emptyAccount))
const courseCatalog = ref<Course[]>(structuredClone(mockCourses))
const groups = ref<CourseGroup[]>(structuredClone(initialGroups))
const tasks = ref<TaskRecord[]>(structuredClone(mockTasks))
const logs = ref<LogRecord[]>(structuredClone(mockLogs))
const showAccountModal = ref(false)
const showTaskModal = ref(false)
const toast = ref('')
const cookieVisible = ref(false)
const serverOnline = ref(import.meta.env.VITE_USE_MOCK === 'true')
const loading = ref(false)
const accountName = ref('')
const accountCookie = ref('')
const taskStartTime = ref(defaultStartTime())
const settings = ref<SettingsPayload>({ domain: 'classes.tju.edu.cn', profileId: 0, semesterId: 0, startTime: '1970-01-01T08:00:00', skipPre: false })
const desktopNotifications = ref(true)
let eventSource: EventSource | null = null

const pageTitle = computed(() => ({
  overview: '晚上好，准备就绪',
  courses: '课程方案',
  tasks: '运行任务',
  accounts: '账号管理',
  settings: '偏好设置',
}[page.value]))

const filteredCourses = computed(() => courseCatalog.value.filter((course) => {
  const query = keyword.value.trim().toLowerCase()
  const matched = !query || [course.name, course.no, course.code, course.teacher]
    .some((field) => field.toLowerCase().includes(query))
  return matched && (availability.value === 'all' || course.available)
}))

const plannedCourseCount = computed(() => groups.value.reduce((sum, group) => sum + group.courses.length, 0))
const successRate = computed(() => {
  const completed = tasks.value.filter((task) => task.status === 'completed')
  if (!completed.length) return 0
  return Math.round(completed.reduce((sum, task) => sum + (task.targetCount ? task.successCount / task.targetCount : 0), 0) / completed.length * 100)
})

function defaultStartTime() {
  const date = new Date()
  date.setDate(date.getDate() + 1)
  date.setHours(8, 0, 0, 0)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

async function loadRemoteData() {
  if (useMock) return
  loading.value = true
  try {
    await api.health()
    serverOnline.value = true
    const [remoteAccounts, remoteTasks, remoteSettings] = await Promise.all([api.accounts(), api.tasks(), api.settings()])
    accounts.value = remoteAccounts
    tasks.value = remoteTasks
    settings.value = remoteSettings
    const selected = remoteAccounts.find((item) => item.id === selectedAccountId.value) ?? remoteAccounts[0]
    if (selected) {
      selectedAccountId.value = selected.id
      const remoteTargets = await api.targets(selected.id)
      let remoteCourses: Course[] = []
      try {
        remoteCourses = await api.courses(selected.id)
      } catch (error) {
        notify(error instanceof Error ? error.message : '课程同步失败')
      }
      courseCatalog.value = remoteCourses
      groups.value = remoteTargets.map((group, groupIndex) => ({
        id: group.id || `group-${groupIndex}`,
        name: group.name,
        limit: group.limit,
        courses: group.courseNos.map((courseNo, courseIndex) => {
          const matched = remoteCourses.find((course) => course.no === courseNo)
          return {
            ...(matched || {
              id: `missing-${courseNo}`,
              no: courseNo,
              code: '',
              name: `课程序号 ${courseNo}`,
              teacher: '未找到',
              credits: 0,
              campus: '未知',
              schedule: '课程信息暂不可用',
              selected: 0,
              capacity: 0,
              available: false,
            }),
            priority: courseIndex + 1,
          }
        }),
      }))
    } else {
      courseCatalog.value = []
      groups.value = []
    }
    const activeTask = remoteTasks.find((task) => task.status === 'scheduled' || task.status === 'running')
    if (activeTask) connectTaskEvents(activeTask.id)
  } catch (error) {
    serverOnline.value = false
    accounts.value = []
    courseCatalog.value = []
    groups.value = []
    tasks.value = []
    logs.value = []
    notify(error instanceof Error ? error.message : '无法连接后端服务')
  } finally {
    loading.value = false
  }
}

function connectTaskEvents(taskId: string) {
  eventSource?.close()
  eventSource = new EventSource(api.eventsUrl(taskId))
  eventSource.addEventListener('task.status', (event) => {
    const record = JSON.parse((event as MessageEvent).data) as TaskRecord
    const index = tasks.value.findIndex((task) => task.id === record.id)
    if (index >= 0) tasks.value[index] = record
    else tasks.value.unshift(record)
    if (['completed', 'failed', 'stopped'].includes(record.status)) eventSource?.close()
  })
  eventSource.addEventListener('task.log', (event) => {
    const record = JSON.parse((event as MessageEvent).data) as LogRecord
    if (!logs.value.some((log) => log.id === record.id)) logs.value.push(record)
  })
}

function goTo(next: Page) {
  page.value = next
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function notify(message: string) {
  toast.value = message
  window.setTimeout(() => {
    if (toast.value === message) toast.value = ''
  }, 2400)
}

function isPlanned(course: Course) {
  return groups.value.some((group) => group.courses.some((item) => item.id === course.id))
}

function addCourse(course: Course) {
  if (isPlanned(course)) return
  if (!groups.value.length) addGroup()
  const target = groups.value[0]
  target.courses.push({ ...course, priority: target.courses.length + 1 })
  notify(`已将「${course.name}」加入 ${target.name}`)
}

function removeCourse(groupId: string, courseId: string) {
  const target = groups.value.find((group) => group.id === groupId)
  if (!target) return
  target.courses = target.courses.filter((course) => course.id !== courseId)
  target.courses.forEach((course, index) => { course.priority = index + 1 })
}

function addGroup() {
  groups.value.push({ id: `g${Date.now()}`, name: `新课程组 ${groups.value.length + 1}`, limit: 1, courses: [] })
}

async function savePlan() {
  if (useMock) return notify('课程方案已保存')
  if (!account.value.id) return notify('请先添加账号')
  try {
    await api.saveTargets(account.value.id, groups.value.map((group) => ({
      id: group.id,
      name: group.name,
      limit: group.limit,
      courseNos: group.courses.map((course) => course.no),
    })))
    notify('课程方案已保存')
  } catch (error) {
    notify(error instanceof Error ? error.message : '方案保存失败')
  }
}

async function startTask() {
  if (!account.value.id) return notify('请先添加账号')
  const draft: TaskRecord = {
    id: `task_${Date.now()}`,
    accountName: account.value.name,
    status: 'scheduled',
    startTime: taskStartTime.value,
    progress: 0,
    successCount: 0,
    targetCount: groups.value.reduce((sum, group) => sum + Math.max(0, group.limit), 0),
  }
  try {
    if (!useMock) {
      await api.saveTargets(account.value.id, groups.value.map((group) => ({
        id: group.id,
        name: group.name,
        limit: group.limit,
        courseNos: group.courses.map((course) => course.no),
      })))
    }
    const created = useMock ? draft : await api.createTask({
      accountIds: [account.value.id],
      startTime: new Date(taskStartTime.value).toISOString(),
      skipPrecheck: false,
    })
    tasks.value.unshift(created)
    if (!useMock) connectTaskEvents(created.id)
    showTaskModal.value = false
    notify('任务已创建，将在设定时间自动执行')
    goTo('tasks')
  } catch (error) {
    notify(error instanceof Error ? error.message : '任务创建失败')
  }
}

async function submitAccount() {
  if (!accountCookie.value.trim()) return notify('请填写完整 Cookie')
  try {
    const created = useMock ? mockAccount : await api.createAccount({
      name: accountName.value.trim() || '未命名账号',
      cookie: accountCookie.value.trim(),
      validate: true,
    })
    accounts.value.push(created)
    selectedAccountId.value = created.id
    showAccountModal.value = false
    accountName.value = ''
    accountCookie.value = ''
    notify('账号验证并添加成功')
    if (!useMock) await loadRemoteData()
  } catch (error) {
    notify(error instanceof Error ? error.message : '账号添加失败')
  }
}

async function refreshAccount(target: Account = account.value) {
  if (!target.id || useMock) return notify('账号状态正常')
  try {
    const updated = await api.initializeAccount(target.id)
    const index = accounts.value.findIndex((item) => item.id === updated.id)
    if (index >= 0) accounts.value[index] = updated
    notify('账号信息已更新')
  } catch (error) {
    notify(error instanceof Error ? error.message : '账号验证失败')
  }
}

async function selectAccount(accountId: string) {
  if (selectedAccountId.value === accountId) return
  selectedAccountId.value = accountId
  await loadRemoteData()
}

async function stopTask(task: TaskRecord) {
  if (useMock) {
    task.status = 'stopped'
    return notify('任务已停止')
  }
  try {
    await api.stopTask(task.id)
    task.status = 'stopped'
    notify('停止请求已发送')
  } catch (error) {
    notify(error instanceof Error ? error.message : '停止任务失败')
  }
}

async function saveSettings() {
  if (useMock) return notify('设置已保存')
  try {
    settings.value = await api.saveSettings(settings.value)
    notify('设置已保存')
  } catch (error) {
    notify(error instanceof Error ? error.message : '设置保存失败')
  }
}

function taskStatusLabel(status: TaskRecord['status']) {
  return ({ scheduled: '等待执行', running: '正在执行', completed: '已完成', failed: '执行失败', stopped: '已停止' })[status]
}

onMounted(loadRemoteData)
onBeforeUnmount(() => eventSource?.close())
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <button class="brand" aria-label="返回概览" @click="goTo('overview')">
        <span class="brand-mark"><GraduationCap :size="22" :stroke-width="1.8" /></span>
        <span><strong>AutoCourse</strong><small>Tianjin University</small></span>
      </button>

      <nav class="main-nav" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.key"
          :class="['nav-item', { active: page === item.key }]"
          @click="goTo(item.key)"
        >
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
          <span v-if="item.key === 'tasks' && tasks.filter(task => task.status === 'scheduled' || task.status === 'running').length" class="nav-dot">{{ tasks.filter(task => task.status === 'scheduled' || task.status === 'running').length }}</span>
        </button>
      </nav>

      <div class="sidebar-spacer" />
      <button :class="['nav-item', { active: page === 'settings' }]" @click="goTo('settings')">
        <Settings :size="18" /><span>偏好设置</span>
      </button>
      <div class="sidebar-account">
        <span class="avatar">李</span>
        <span class="account-copy"><strong>{{ account.name }}</strong><small>账号状态正常</small></span>
        <MoreHorizontal :size="18" />
      </div>
    </aside>

    <main class="main-content">
      <header class="topbar">
        <div>
          <p class="eyebrow">2026 秋季学期</p>
          <h1>{{ pageTitle }}</h1>
        </div>
        <div class="top-actions">
          <span :class="['system-status', { offline: !serverOnline }]"><i /> {{ serverOnline ? (useMock ? '演示模式' : '系统在线') : '后端离线' }}</span>
          <button class="icon-button" aria-label="通知"><Bell :size="19" /><span class="notification-dot" /></button>
          <button class="button primary" @click="showTaskModal = true"><Play :size="16" fill="currentColor" /> 新建任务</button>
        </div>
      </header>

      <section v-if="page === 'overview'" class="page page-overview">
        <div class="hero-card">
          <div class="hero-copy">
            <span class="soft-label"><CalendarClock :size="14" /> 下一任务</span>
            <h2>距离选课开始还有</h2>
            <div class="countdown"><strong>12</strong><span>小时</span><strong>17</strong><span>分钟</span><strong>42</strong><span>秒</span></div>
            <p>任务将在 8月29日 08:00 自动启动，建议提前保持设备与网络在线。</p>
            <button class="text-button" @click="goTo('tasks')">查看任务详情 <ArrowRight :size="16" /></button>
          </div>
          <div class="orbit-visual" aria-hidden="true">
            <span class="orbit orbit-one" /><span class="orbit orbit-two" />
            <span class="orbit-core"><BookOpenCheck :size="38" :stroke-width="1.35" /></span>
          </div>
        </div>

        <div class="metric-grid">
          <article class="metric-card">
            <span class="metric-icon plum"><BookOpenCheck :size="20" /></span>
            <div><span>已规划课程</span><strong>{{ plannedCourseCount }}</strong><small>来自 {{ groups.length }} 个课程组</small></div>
          </article>
          <article class="metric-card">
            <span class="metric-icon green"><CheckCircle2 :size="20" /></span>
            <div><span>历史成功率</span><strong>{{ successRate }}%</strong><small>最近任务全部完成</small></div>
          </article>
          <article class="metric-card">
            <span class="metric-icon blue"><Clock3 :size="20" /></span>
            <div><span>等待任务</span><strong>1</strong><small>明天 08:00 执行</small></div>
          </article>
        </div>

        <div class="content-grid">
          <article class="panel plan-preview">
            <div class="panel-heading">
              <div><h3>当前选课方案</h3><p>按课程组中的优先级依次尝试</p></div>
              <button class="quiet-button" @click="goTo('courses')">编辑方案</button>
            </div>
            <div class="group-preview" v-for="group in groups" :key="group.id">
              <div class="group-title"><span>{{ group.name }}</span><small>限选 {{ group.limit }} 门</small></div>
              <div class="course-chips">
                <div class="course-chip" v-for="course in group.courses" :key="course.id">
                  <span class="priority">{{ course.priority }}</span>
                  <span><strong>{{ course.name }}</strong><small>{{ course.no }} · {{ course.teacher }}</small></span>
                  <span :class="['seat-badge', { full: !course.available }]">{{ course.capacity - course.selected > 0 ? `余 ${course.capacity - course.selected}` : '已满' }}</span>
                </div>
              </div>
            </div>
          </article>

          <article class="panel activity-panel">
            <div class="panel-heading"><div><h3>运行动态</h3><p>任务与账号的最新状态</p></div><span class="live-label"><i /> LIVE</span></div>
            <div class="timeline">
              <div v-for="log in logs" :key="log.id" class="timeline-item">
                <span :class="['timeline-icon', log.level.toLowerCase()]">
                  <Check v-if="log.level === 'SUCCESS'" :size="13" />
                  <Clock3 v-else :size="13" />
                </span>
                <div><p>{{ log.message }}</p><small>今天 {{ log.time }}</small></div>
              </div>
            </div>
            <button class="full-quiet-button" @click="goTo('tasks')">查看全部日志</button>
          </article>
        </div>
      </section>

      <section v-else-if="page === 'courses'" class="page">
        <div class="section-intro">
          <div><h2>安排你的候选课程</h2><p>同组内按顺序尝试，达到限选数量后自动停止。</p></div>
          <div class="intro-actions"><button class="button secondary" @click="addGroup"><Plus :size="16" /> 添加课程组</button><button class="button primary" :disabled="loading" @click="savePlan"><Save :size="16" /> 保存方案</button></div>
        </div>

        <div class="course-layout">
          <div class="planner-column">
            <article v-for="group in groups" :key="group.id" class="panel group-card">
              <div class="group-card-header">
                <div><input v-model="group.name" class="title-input" aria-label="课程组名称" /><span>{{ group.courses.length }} 门候选课程</span></div>
                <label class="limit-control">最多选中 <input v-model.number="group.limit" type="number" min="-1" /> 门</label>
              </div>
              <div v-if="group.courses.length" class="sortable-list">
                <div v-for="course in group.courses" :key="course.id" class="planned-course">
                  <GripVertical class="drag-handle" :size="18" />
                  <span class="priority large">{{ course.priority }}</span>
                  <div class="planned-main"><strong>{{ course.name }}</strong><span>{{ course.no }} · {{ course.teacher }}</span></div>
                  <div class="planned-schedule"><Clock3 :size="14" /> {{ course.schedule }}</div>
                  <span :class="['seat-badge', { full: !course.available }]">{{ course.available ? `余 ${course.capacity - course.selected}` : '已满' }}</span>
                  <button class="icon-button subtle" aria-label="移除课程" @click="removeCourse(group.id, course.id)"><Trash2 :size="16" /></button>
                </div>
              </div>
              <div v-else class="empty-drop"><Plus :size="18" /><span>从右侧课程库添加候选课程</span></div>
            </article>
          </div>

          <aside class="panel course-library">
            <div class="library-heading"><div><h3>课程库</h3><p>{{ loading ? '正在同步课程…' : `共 ${filteredCourses.length} 门课程` }}</p></div><button class="icon-button subtle" :disabled="loading" @click="loadRemoteData"><RefreshCw :size="16" /></button></div>
            <label class="search-box"><Search :size="17" /><input v-model="keyword" placeholder="搜索课程名、教师或课程序号" /></label>
            <div class="filter-row">
              <button :class="['filter-chip', { active: availability === 'all' }]" @click="availability = 'all'">全部课程</button>
              <button :class="['filter-chip', { active: availability === 'available' }]" @click="availability = 'available'">仅看有余量</button>
              <button class="filter-icon"><SlidersHorizontal :size="15" /></button>
            </div>
            <div class="library-list">
              <div v-for="course in filteredCourses" :key="course.id" class="library-course">
                <div class="library-course-top"><div><strong>{{ course.name }}</strong><span>{{ course.no }} · {{ course.teacher }}</span></div><button :disabled="isPlanned(course)" @click="addCourse(course)"><Check v-if="isPlanned(course)" :size="15" /><Plus v-else :size="15" /></button></div>
                <div class="course-meta"><span><Clock3 :size="13" />{{ course.schedule.split(' · ')[0] }}</span><span><MapPin :size="13" />{{ course.campus }}</span><span :class="{ danger: !course.available }">{{ course.selected }}/{{ course.capacity }}</span></div>
              </div>
            </div>
          </aside>
        </div>
      </section>

      <section v-else-if="page === 'tasks'" class="page">
        <div class="section-intro"><div><h2>任务状态与日志</h2><p>查看选课进度、执行结果和实时反馈。</p></div><button class="button primary" @click="showTaskModal = true"><Plus :size="16" /> 新建任务</button></div>
        <div class="task-list">
          <article v-for="task in tasks" :key="task.id" class="panel task-card">
            <div class="task-icon" :class="task.status"><CalendarClock v-if="task.status === 'scheduled'" :size="21" /><CheckCircle2 v-else :size="21" /></div>
            <div class="task-main"><div><strong>{{ task.startTime }}</strong><span>{{ task.accountName }} · {{ task.targetCount }} 个目标</span></div><div class="progress-track"><i :style="{ width: `${task.progress}%` }" /></div></div>
            <span :class="['status-pill', task.status]">{{ taskStatusLabel(task.status) }}</span>
            <button class="icon-button subtle" :aria-label="task.status === 'scheduled' || task.status === 'running' ? '停止任务' : '任务详情'" @click="task.status === 'scheduled' || task.status === 'running' ? stopTask(task) : undefined"><X v-if="task.status === 'scheduled' || task.status === 'running'" :size="17" /><MoreHorizontal v-else :size="18" /></button>
          </article>
        </div>
        <article class="panel console-card">
          <div class="console-heading"><div><SquareTerminal :size="18" /><span>实时日志</span><i /></div><button>清空</button></div>
          <div class="console-body">
            <div v-for="log in logs" :key="log.id" class="console-row"><span>{{ log.time }}</span><strong :class="log.level.toLowerCase()">{{ log.level }}</strong><p>{{ log.message }}</p></div>
            <div class="console-cursor"><span /> 等待新消息</div>
          </div>
        </article>
      </section>

      <section v-else-if="page === 'accounts'" class="page">
        <div class="section-intro"><div><h2>账号与凭证</h2><p>凭证只保存在本机，并在界面中始终脱敏。</p></div><button class="button primary" @click="showAccountModal = true"><Plus :size="16" /> 添加账号</button></div>
        <article v-for="item in accounts" :key="item.id" :class="['panel', 'account-card', { selected: item.id === account.id }]" @click="selectAccount(item.id)">
          <span class="large-avatar">{{ item.name.slice(0, 1) }}</span>
          <div class="account-identity"><strong>{{ item.name }}</strong><span>{{ item.studentId ? `学号 ${item.studentId}` : '未读取学号' }}</span></div>
          <div class="account-detail"><span>登录凭证</span><strong>{{ item.cookieMasked }}</strong></div>
          <div class="account-detail"><span>当前学期</span><strong>{{ item.semesterId || '待读取' }}</strong></div>
          <span :class="['status-pill', item.status]"><i v-if="item.status === 'valid'" /> {{ item.status === 'valid' ? '凭证有效' : '待验证' }}</span>
          <button class="button secondary small" @click.stop="refreshAccount(item)">重新验证</button>
        </article>
        <div v-if="!accounts.length" class="panel empty-account"><UsersRound :size="24" /><strong>还没有账号</strong><span>添加账号后即可同步课程并创建任务</span></div>
        <div class="security-note"><ShieldCheck :size="20" /><div><strong>凭证安全提示</strong><p>请勿分享包含完整 Cookie 的截图或日志。建议在选课结束后及时退出登录并清除凭证。</p></div></div>
      </section>

      <section v-else class="page settings-page">
        <div class="section-intro"><div><h2>偏好设置</h2><p>调整界面和默认任务行为。</p></div><button class="button primary" @click="saveSettings"><Save :size="16" /> 保存设置</button></div>
        <article class="panel settings-card">
          <div class="setting-row"><div><strong>学校选课域名</strong><span>通常无需修改</span></div><input v-model="settings.domain" /></div>
          <div class="setting-row"><div><strong>跳过余量预检</strong><span>开启后减少一次查询，但无法提前过滤满员课程</span></div><label class="switch"><input v-model="settings.skipPre" type="checkbox" /><i /></label></div>
          <div class="setting-row"><div><strong>桌面通知</strong><span>选课成功或任务异常时提醒</span></div><label class="switch"><input v-model="desktopNotifications" type="checkbox" /><i /></label></div>
        </article>
      </section>
    </main>

    <Transition name="toast"><div v-if="toast" class="toast"><CheckCircle2 :size="17" />{{ toast }}</div></Transition>

    <div v-if="showTaskModal" class="modal-backdrop" @click.self="showTaskModal = false">
      <div class="modal-card">
        <div class="modal-heading"><div><span class="modal-icon"><CalendarClock :size="20" /></span><div><h3>创建选课任务</h3><p>确认账号、方案与启动时间</p></div></div><button class="icon-button subtle" @click="showTaskModal = false"><X :size="18" /></button></div>
        <label class="field"><span>执行账号</span><button class="select-control"><span><span class="mini-avatar">李</span>{{ account.name }}</span><ChevronDown :size="16" /></button></label>
        <label class="field"><span>开始时间</span><input v-model="taskStartTime" type="datetime-local" /></label>
        <div class="task-summary"><span><BookOpenCheck :size="18" /></span><div><strong>{{ groups.length }} 个课程组，{{ plannedCourseCount }} 门候选课程</strong><p>预计选中 {{ groups.reduce((sum, group) => sum + Math.max(0, group.limit), 0) }} 门课程</p></div></div>
        <div class="modal-actions"><button class="button secondary" @click="showTaskModal = false">取消</button><button class="button primary" @click="startTask"><Play :size="15" fill="currentColor" /> 创建任务</button></div>
      </div>
    </div>

    <div v-if="showAccountModal" class="modal-backdrop" @click.self="showAccountModal = false">
      <div class="modal-card">
        <div class="modal-heading"><div><span class="modal-icon"><UserRound :size="20" /></span><div><h3>添加选课账号</h3><p>录入登录凭证后自动读取账号信息</p></div></div><button class="icon-button subtle" @click="showAccountModal = false"><X :size="18" /></button></div>
        <label class="field"><span>账号备注</span><input v-model="accountName" placeholder="例如：我的账号" /></label>
        <label class="field"><span>Cookie</span><div class="password-field"><input v-model="accountCookie" :type="cookieVisible ? 'text' : 'password'" placeholder="粘贴完整 Cookie" /><button type="button" @click="cookieVisible = !cookieVisible">{{ cookieVisible ? '隐藏' : '显示' }}</button></div></label>
        <div class="inline-warning"><CircleAlert :size="16" /><span>Cookie 相当于登录密码，请只在自己的设备上使用。</span></div>
        <div class="modal-actions"><button class="button secondary" @click="showAccountModal = false">取消</button><button class="button primary" :disabled="loading" @click="submitAccount"><RefreshCw :size="15" /> 验证并添加</button></div>
      </div>
    </div>
  </div>
</template>
