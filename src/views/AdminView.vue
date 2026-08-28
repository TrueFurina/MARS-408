<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useStudyStore } from '@/stores/studyStore'
import { api } from '@/utils/api'
import { icons } from '@/components/icons'
import ErrorBoundary from '@/components/ErrorBoundary.vue'

const router = useRouter()
const store = useStudyStore()

const loading = ref(true)
const error = ref('')
const stats = ref<any>(null)
const users = ref<any[]>([])
const expandedUser = ref<string | null>(null)

const maxDaily = computed(() => {
  const d = stats.value?.daily_quiz || []
  return Math.max(1, ...d.map((x: any) => x.count))
})

function subjectName(s: string | number): string {
  const key = String(s)
  if (!key) return '—'
  if (store.subjects[key]) return store.subjects[key].name
  const legacy: Record<string, string> = {
    overview: '计网·概述', physical: '计网·物理层', datalink: '计网·数据链路层', network: '计网·网络层',
    transport: '计网·运输层', application: '计网·应用层', security: '计网·网络安全',
    os: '操作系统', co: '计算机组成', ds: '数据结构', general: '通用',
  }
  return legacy[key] || key
}

function roleLabel(r: string) {
  return r === 'admin' ? '管理员' : '学生'
}

function toggleExpand(id: string) {
  expandedUser.value = expandedUser.value === id ? null : id
}

function profileSummary(p: any): string[] {
  if (!p || typeof p !== 'object') return []
  const out: string[] = []
  const map: Record<string, string> = {
    knowledge_base: '基础', learning_style: '风格', goal: '目标', weak_points: '薄弱点',
    study_time: '学习时长', preferred_difficulty: '难度偏好', progress: '进度', interest_area: '兴趣方向',
  }
  for (const k of Object.keys(map)) {
    if (p[k] !== undefined && p[k] !== '' && p[k] !== null) {
      out.push(`${map[k]}: ${p[k]}`)
    }
  }
  return out
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [s, u] = await Promise.all([
      api.get<any>('/admin/stats'),
      api.get<{ users: any[] }>('/admin/users'),
    ])
    if (!s || !u) throw new Error('无权限或请求失败')
    stats.value = s
    users.value = u.users || []
  } catch (e: any) {
    error.value = e?.message || '加载管理员数据失败，请确认使用管理员账号登录'
  } finally {
    loading.value = false
  }
}

function goKnowledge() {
  router.push('/admin/knowledge')
}

onMounted(load)
</script>

<template>
  <ErrorBoundary title="平台数据看板加载异常">
  <div class="page-section">
    <div class="section-title"><span v-html="icons.dashboard" class="section-title-icon"></span>平台数据看板</div>
    <div class="section-desc">管理员视角 · 汇总所有用户的学习数据与平台整体运行情况</div>

    <div v-if="loading" class="empty-state">
      <div v-for="i in 4" :key="i" class="skeleton" style="width:100%;height:80px;margin-bottom:12px;"></div>
    </div>

    <div v-else-if="error" class="admin-error">
      <div class="error-bar">{{ error }}</div>
      <button class="btn btn-soft" @click="load">重试</button>
    </div>

    <template v-else>
      <!-- 平台级统计卡片 -->
      <div class="stat-grid">
        <div class="stat-card glass-card">
          <div class="stat-label">总用户数</div>
          <div class="stat-value">{{ stats.user_count }}</div>
          <div class="stat-sub">学生 {{ stats.student_count }} · 管理员 {{ stats.admin_count }}</div>
        </div>
        <div class="stat-card glass-card">
          <div class="stat-label">活跃用户</div>
          <div class="stat-value">{{ stats.active_users }}</div>
          <div class="stat-sub">有答题或对话记录</div>
        </div>
        <div class="stat-card glass-card">
          <div class="stat-label">总答题数</div>
          <div class="stat-value">{{ stats.total_quiz }}</div>
          <div class="stat-sub">正确 {{ stats.correct_quiz }} 题</div>
        </div>
        <div class="stat-card glass-card">
          <div class="stat-label">平台平均正确率</div>
          <div class="stat-value" :style="{ color: (stats.overall_accuracy * 100) >= 60 ? 'var(--accent-success)' : 'var(--accent-warm)' }">
            {{ (stats.overall_accuracy * 100).toFixed(1) }}%
          </div>
          <div class="stat-sub">全部用户综合</div>
        </div>
      </div>

      <div class="dash-grid">
        <!-- 7 日答题趋势 -->
        <div class="card glass-card">
          <div class="card-title"><span v-html="icons.chartUp" class="card-title-icon"></span>近 7 日答题量</div>
          <div class="bars">
            <div v-for="d in stats.daily_quiz" :key="d.date" class="bar-col">
              <div class="bar-track">
                <div class="bar-fill" :style="{ height: (d.count / maxDaily * 100) + '%' }"></div>
              </div>
              <div class="bar-val">{{ d.count }}</div>
              <div class="bar-date">{{ d.date.slice(5) }}</div>
            </div>
          </div>
        </div>

        <!-- 科目掌握度分布 -->
        <div class="card glass-card">
          <div class="card-title"><span v-html="icons.bookOpen" class="card-title-icon"></span>各科掌握度分布（平台平均）</div>
          <div v-if="Object.keys(stats.by_subject).length === 0" class="empty-mini"><span v-html="icons.chart" class="inline-icon"></span>暂无答题数据</div>
          <div v-for="(v, k) in stats.by_subject" :key="k" class="subj-row">
            <span class="subj-name">{{ subjectName(k) }}</span>
            <div class="subj-bar-bg">
              <div class="subj-bar-fill" :style="{ width: (v.accuracy * 100) + '%' }"></div>
            </div>
            <span class="subj-pct">{{ (v.accuracy * 100).toFixed(0) }}%</span>
            <span class="subj-cnt">({{ v.correct }}/{{ v.total }})</span>
          </div>
        </div>
      </div>

      <!-- 用户列表 -->
      <div class="card glass-card" style="margin-top:16px;">
        <div class="card-header">
          <span class="card-title"><span v-html="icons.user" class="card-title-icon"></span>用户总览（{{ users.length }} 人）</span>
          <button class="rag-btn" style="background:var(--accent-2);" @click="goKnowledge">🗂️ 知识库管理</button>
        </div>

        <div class="table-wrap">
          <table class="user-table">
            <thead>
              <tr>
                <th>用户</th>
                <th>角色</th>
                <th>注册时间</th>
                <th>答题数</th>
                <th>正确率</th>
                <th>对话数</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <template v-for="u in users" :key="u.id">
                <tr class="user-row" @click="toggleExpand(u.id)">
                  <td>
                    <div class="u-name">{{ u.display_name || u.username }}</div>
                    <div class="u-uname">@{{ u.username }}</div>
                  </td>
                  <td><span class="role-tag" :class="u.role">{{ roleLabel(u.role) }}</span></td>
                  <td class="muted">{{ u.created_at }}</td>
                  <td>{{ u.quiz_total }}</td>
                  <td :style="{ color: (u.quiz_accuracy * 100) >= 60 ? 'var(--accent-success)' : 'var(--accent-warm)' }">
                    {{ u.quiz_total ? (u.quiz_accuracy * 100).toFixed(0) + '%' : '—' }}
                  </td>
                  <td>{{ u.conversation_count }}</td>
                  <td><span class="expand-icon">{{ expandedUser === u.id ? '▾' : '▸' }}</span></td>
                </tr>
                <tr v-if="expandedUser === u.id" class="detail-row">
                  <td colspan="7">
                    <div class="detail">
                      <div class="detail-block">
                        <div class="detail-h">学习画像</div>
                        <div v-if="profileSummary(u.profile).length" class="chips">
                          <span v-for="(p, i) in profileSummary(u.profile)" :key="i" class="chip">{{ p }}</span>
                        </div>
                        <div v-else class="muted">尚未构建画像</div>
                      </div>
                      <div class="detail-block">
                        <div class="detail-h">各科正确率</div>
                        <div v-if="Object.keys(u.by_subject).length === 0" class="muted"><span v-html="icons.chart" class="inline-icon"></span>暂无答题</div>
                        <div v-for="(v, k) in u.by_subject" :key="k" class="mini-row">
                          <span class="mini-name">{{ subjectName(k) }}</span>
                          <div class="mini-bar-bg"><div class="mini-bar-fill" :style="{ width: (v.accuracy * 100) + '%' }"></div></div>
                          <span class="mini-pct">{{ (v.accuracy * 100).toFixed(0) }}%</span>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
  </ErrorBoundary>
</template>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap:1rem;
  margin-bottom:1rem;
}
.stat-card { padding:1.125rem 1.25rem; border-radius:var(--radius-lg); }
.stat-label { font-size:0.8125rem; color: var(--text-muted); }
.stat-value { font-size:1.875rem; font-weight: 800; color: var(--text-primary); margin:0.375rem 0 0.125rem; }
.stat-sub { font-size:0.75rem; color: var(--text-muted); }

.dash-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap:1rem;
}
@media (max-width: 880px) { .dash-grid { grid-template-columns: 1fr; } }
.card { padding:1.125rem 1.25rem; border-radius:var(--radius-lg); }
.card-title { font-size:0.9375rem; font-weight: 700; color: var(--text-primary); margin-bottom:0.875rem; }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom:0.75rem; }

.bars { display: flex; align-items: flex-end; gap:0.625rem; height:10rem; padding-top:0.5rem; }
.bar-col { flex: 1; display: flex; flex-direction: column; align-items: center; height:100%; justify-content: flex-end; }
.bar-track { width:100%; flex: 1; display: flex; align-items: flex-end; }
.bar-fill {
  width:100%; border-radius:0.375rem 0.375rem 0 0;
  background: linear-gradient(180deg, var(--accent-primary), var(--accent-2));
  min-height:0.1875rem; transition: height 0.4s ease;
}
.bar-val { font-size:0.75rem; color: var(--text-secondary); margin-top:0.375rem; }
.bar-date { font-size:0.625rem; color: var(--text-muted); }

.subj-row { display: flex; align-items: center; gap:0.625rem; margin-bottom:0.625rem; font-size:0.8125rem; }
.subj-name { width:6.875rem; color: var(--text-secondary); flex-shrink: 0; }
.subj-bar-bg { flex: 1; height:0.5rem; border-radius:0.25rem; background: var(--bg-secondary); overflow: hidden; }
.subj-bar-fill { height:100%; border-radius:0.25rem; background: linear-gradient(90deg, var(--accent-tertiary), var(--accent-primary)); }
.subj-pct { width:2.625rem; text-align: right; color: var(--text-primary); font-weight: 600; }
.subj-cnt { width:3.75rem; color: var(--text-muted); font-size:0.6875rem; }

.empty-mini, .muted { color: var(--text-muted); font-size:0.8125rem; }

.table-wrap { overflow-x: auto; }
.user-table { width:100%; border-collapse: collapse; font-size:0.8125rem; }
.user-table th {
  text-align: left; padding:0.625rem 0.75rem; color: var(--text-muted); font-weight: 600;
  border-bottom: 1px solid var(--border-color); font-size:0.75rem;
}
.user-row { cursor: pointer; transition: background 0.15s; }
.user-row:hover { background: var(--accent-primary-10); }
.user-table td { padding:0.6875rem 0.75rem; border-bottom: 1px solid var(--border-color); color: var(--text-primary); }
.u-name { font-weight: 600; color: var(--text-primary); }
.u-uname { font-size:0.6875rem; color: var(--text-muted); }
.role-tag { padding:0.125rem 0.625rem; border-radius:1.25rem; font-size:0.6875rem; font-weight: 600; }
.role-tag.admin { background: var(--accent-danger-20); color: var(--text-danger); }
.role-tag.student { background: var(--accent-primary-20); color: var(--accent-secondary); }
.expand-icon { color: var(--text-muted); }

.detail-row td { background: color-mix(in srgb, var(--accent-primary) 4%, transparent); padding:1rem 1.25rem; }
.detail { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
@media (max-width: 700px) { .detail { grid-template-columns: 1fr; } }
.detail-h { font-size:0.8125rem; font-weight: 700; color: var(--text-secondary); margin-bottom:0.5rem; }
.chips { display: flex; flex-wrap: wrap; gap:0.375rem; }
.chip { font-size:0.6875rem; padding:0.1875rem 0.5625rem; border-radius:1.25rem; background: color-mix(in srgb, var(--accent-primary) 12%, transparent); color: var(--accent-primary); }
.mini-row { display: flex; align-items: center; gap:0.5rem; margin-bottom:0.375rem; font-size:0.75rem; }
.mini-name { width:5.625rem; color: var(--text-secondary); flex-shrink: 0; }
.mini-bar-bg { flex: 1; height:0.375rem; border-radius:0.1875rem; background: var(--bg-secondary); overflow: hidden; }
.mini-bar-fill { height:100%; background: var(--accent-tertiary); }
.mini-pct { width:2.375rem; text-align: right; color: var(--text-primary); }

.empty-state { padding:2.5rem; text-align: center; }
.empty-title { color: var(--text-secondary); }
.admin-error { display: flex; flex-direction: column; gap: 1rem; align-items: flex-start; }
.engine-btn {
  padding:0.5625rem 1.25rem; border: none; border-radius:0.625rem; cursor: pointer; color: var(--text-user); font-weight: 600;
  background: linear-gradient(135deg, var(--accent-primary), var(--accent-2));
}
.rag-btn {
  padding:0.5rem 1rem; border: none; border-radius:0.625rem; cursor: pointer; color: var(--text-user); font-size:0.8125rem; font-weight: 600;
  background: var(--accent-primary);
}
.skeleton { border-radius: var(--radius-lg); background: linear-gradient(90deg, var(--color-surface) 25%, var(--color-surface-hover) 37%, var(--color-surface) 63%); background-size: 400% 100%; animation: shimmer 1.4s ease infinite; }
</style>
