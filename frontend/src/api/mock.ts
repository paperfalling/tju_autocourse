import type { Account, Course, CourseGroup, LogRecord, TaskRecord } from '../types'

export const account: Account = {
  id: 'acc_01',
  name: '李同学',
  studentId: '3024200000',
  cookieMasked: 'JSESSIONID=••••••••8fa2',
  profileId: 3820,
  semesterId: 116,
  status: 'valid',
}

export const courses: Course[] = [
  { id: 'c1', no: '06488', code: 'PE1001', name: '游泳', teacher: '王老师', credits: 1, campus: '北洋园', schedule: '周二 3-4节 · 游泳馆', selected: 28, capacity: 30, available: true },
  { id: 'c2', no: '06491', code: 'PE1001', name: '羽毛球', teacher: '张老师', credits: 1, campus: '北洋园', schedule: '周四 5-6节 · 体育馆', selected: 30, capacity: 30, available: false },
  { id: 'c3', no: '02134', code: 'MATH204', name: '数学建模', teacher: '陈老师', credits: 2, campus: '卫津路', schedule: '周三 7-8节 · 26教A204', selected: 41, capacity: 60, available: true },
  { id: 'c4', no: '08321', code: 'ART1202', name: '电影艺术赏析', teacher: '刘老师', credits: 2, campus: '北洋园', schedule: '周五 9-10节 · 44教B区', selected: 73, capacity: 80, available: true },
  { id: 'c5', no: '04719', code: 'CS3012', name: '数据可视化', teacher: '赵老师', credits: 2, campus: '北洋园', schedule: '周一 5-6节 · 45教C310', selected: 48, capacity: 55, available: true },
  { id: 'c6', no: '03117', code: 'ENG2101', name: '学术英语写作', teacher: '孙老师', credits: 2, campus: '北洋园', schedule: '周二 7-8节 · 33教A108', selected: 36, capacity: 40, available: true },
]

export const initialGroups: CourseGroup[] = [
  { id: 'g1', name: '体育课', limit: 1, courses: [{ ...courses[0], priority: 1 }, { ...courses[1], priority: 2 }] },
  { id: 'g2', name: '通识选修', limit: 1, courses: [{ ...courses[3], priority: 1 }] },
]

export const tasks: TaskRecord[] = [
  { id: 'task_20260828', accountName: '李同学', status: 'scheduled', startTime: '2026-08-29 08:00', progress: 0, successCount: 0, targetCount: 2 },
  { id: 'task_20260218', accountName: '李同学', status: 'completed', startTime: '2026-02-18 12:30', progress: 100, successCount: 2, targetCount: 2 },
]

export const logs: LogRecord[] = [
  { id: 1, time: '19:42:01', level: 'INFO', message: '配置检查完成，2 个课程组待执行' },
  { id: 2, time: '19:42:02', level: 'SUCCESS', message: '账号凭证有效，已同步课程信息' },
  { id: 3, time: '19:42:02', level: 'INFO', message: '任务已就绪，等待 08:00 开始' },
]
