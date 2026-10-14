<script setup lang="ts">
/**
 * 云端实验存档（云服务接入页）
 * ============================================================================
 * 把「源码实验室」这个既有功能接到真实云服务上：
 *   · 身份   —— 云 Auth（邮箱密码 / 邮箱验证码 / 微信扫码）
 *   · 进度   —— 云端 Database（本机 localStorage 进度可按账号存档与恢复）
 *   · 源码   —— 云端 Storage（实验源码文件上传、列表、签名下载、读回校验）
 *   · AI助教 —— 云 LLM（免密钥流式问答）
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { SOURCE_LAB_EXERCISES } from '@/data/sourceLabExercises'
import { CLOUD_ENABLED } from '@/services/cloud/client'
import {
  completeWechatRedirect,
  fetchUser,
  getSession,
  onAuthChange,
  sendEmailCode,
  signInWithPassword,
  signOut,
  startWechatLogin,
  verifyEmailCode,
  type CloudSession,
  type CloudUser,
} from '@/services/cloud/auth'
import {
  createFileUrl,
  describeCloudError,
  downloadSourceText,
  listProgress,
  listSourceFiles,
  pullProgress,
  pushProgress,
  removeSourceFiles,
  uploadSourceFile,
  type LabProgressRow,
  type SourceFileItem,
} from '@/services/cloud/labArchive'
import { askTutor, listModels, type TutorModel } from '@/services/cloud/tutor'

/* ── 本机进度（与 SourceLabPane 共用同一份存储，这才是「现有功能」） ── */
const LOCAL_KEY = 'mangdehenzhi_sourcelab_progress_v1'
interface LocalProgress { completed: string[]; attempts: Record<string, number> }

function readLocal(): LocalProgress {
  try {
    const raw = localStorage.getItem(LOCAL_KEY)
    if (raw) {
      const p = JSON.parse(raw)
      return {
        completed: Array.isArray(p.completed) ? p.completed : [],
        attempts: p && typeof p.attempts === 'object' && p.attempts ? p.attempts : {},
      }
    }
  } catch { /* 损坏缓存按空处理 */ }
  return { completed: [], attempts: {} }
}

function writeLocal(v: LocalProgress) {
  try { localStorage.setItem(LOCAL_KEY, JSON.stringify(v)) } catch { /* 隐私模式忽略 */ }
}

const exercises = SOURCE_LAB_EXERCISES
const labId = ref(exercises[0]?.id || '')
const current = computed(() => exercises.find((e) => e.id === labId.value))

/* ── 身份 ── */
const session = ref<CloudSession | null>(null)
const user = ref<CloudUser | null>(null)
const authBusy = ref(false)
const authMsg = ref('')
const authErr = ref('')

const email = ref('')
const password = ref('')
const code = ref('')
const codeSent = ref(false)
let pendingOtp: { email: string; verificationId: string; isExistingUser: boolean } | null = null

async function refreshIdentity() {
  session.value = await getSession()
  user.value = session.value ? await fetchUser() : null
}

async function doPasswordLogin() {
  authBusy.value = true; authErr.value = ''; authMsg.value = ''
  try {
    await signInWithPassword(email.value.trim(), password.value)
    await refreshIdentity()
    authMsg.value = '已登录'
  } catch (e) { authErr.value = describeCloudError(e) } finally { authBusy.value = false }
}

async function doSendCode() {
  const addr = email.value.trim()
  if (!addr) { authErr.value = '请先填写邮箱'; return }
  authBusy.value = true; authErr.value = ''; authMsg.value = ''
  try {
    const c = await sendEmailCode(addr)
    pendingOtp = { email: addr, verificationId: c.verificationId, isExistingUser: c.isExistingUser }
    codeSent.value = true
    authMsg.value = c.isExistingUser ? '验证码已发送，请查收邮箱' : '验证码已发送；新邮箱注册需同时设置密码'
  } catch (e) { authErr.value = describeCloudError(e) } finally { authBusy.value = false }
}

async function doVerifyCode() {
  const p = pendingOtp
  if (!p) { authErr.value = '请先获取验证码'; return }
  authBusy.value = true; authErr.value = ''; authMsg.value = ''
  try {
    await verifyEmailCode({
      email: p.email,
      verificationId: p.verificationId,
      isExistingUser: p.isExistingUser,
      token: code.value.trim(),
      password: password.value || undefined,
    })
    pendingOtp = null; code.value = ''; codeSent.value = false
    await refreshIdentity()
    authMsg.value = '已登录'
  } catch (e) { authErr.value = describeCloudError(e) } finally { authBusy.value = false }
}

async function doWechatLogin() {
  authErr.value = ''
  try { window.location.assign(await startWechatLogin()) }
  catch (e) { authErr.value = describeCloudError(e) }
}

async function doSignOut() {
  try { await signOut() } catch (e) { authErr.value = describeCloudError(e) }
  await refreshIdentity()
  cloudRows.value = []; files.value = []
}

/* ── 进度同步 ── */
const local = ref<LocalProgress>(readLocal())
const cloudRows = ref<LabProgressRow[]>([])
const syncBusy = ref(false)
const syncMsg = ref('')
const syncErr = ref('')

function reloadLocal() { local.value = readLocal() }

async function doPush() {
  syncBusy.value = true; syncErr.value = ''; syncMsg.value = ''
  try {
    reloadLocal()
    await pushProgress({ lab_id: labId.value, completed: local.value.completed, attempts: local.value.attempts })
    syncMsg.value = `已把本机进度存档到云端（${local.value.completed.length} 个已完成实验）`
    cloudRows.value = await listProgress()
  } catch (e) { syncErr.value = describeCloudError(e) } finally { syncBusy.value = false }
}

async function doPull() {
  syncBusy.value = true; syncErr.value = ''; syncMsg.value = ''
  try {
    const row = await pullProgress(labId.value)
    if (!row) { syncErr.value = '云端暂无该实验的存档'; return }
    writeLocal({ completed: row.completed || [], attempts: row.attempts || {} })
    reloadLocal()
    syncMsg.value = `已从云端恢复到本机（存档时间 ${row.updated_at ? new Date(row.updated_at).toLocaleString() : '未知'}）`
  } catch (e) { syncErr.value = describeCloudError(e) } finally { syncBusy.value = false }
}

async function doListCloud() {
  syncBusy.value = true; syncErr.value = ''; syncMsg.value = ''
  try {
    cloudRows.value = await listProgress()
    if (!cloudRows.value.length) syncMsg.value = '云端暂无存档'
  } catch (e) { syncErr.value = describeCloudError(e) } finally { syncBusy.value = false }
}

/* ── 源码文件 ── */
const files = ref<SourceFileItem[]>([])
const fileBusy = ref(false)
const fileMsg = ref('')
const fileErr = ref('')
const picked = ref<File | null>(null)

function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  picked.value = input.files?.[0] || null
}

async function doUpload() {
  if (!picked.value) { fileErr.value = '请先选择文件'; return }
  fileBusy.value = true; fileErr.value = ''; fileMsg.value = ''
  try {
    await uploadSourceFile(labId.value, picked.value)
    fileMsg.value = `已上传：${picked.value.name}`
    picked.value = null
    files.value = await listSourceFiles(labId.value)
  } catch (e) { fileErr.value = describeCloudError(e) } finally { fileBusy.value = false }
}

async function doListFiles() {
  fileBusy.value = true; fileErr.value = ''; fileMsg.value = ''
  try {
    files.value = await listSourceFiles(labId.value)
    if (!files.value.length) fileMsg.value = '该实验下暂无云端文件'
  } catch (e) { fileErr.value = describeCloudError(e) } finally { fileBusy.value = false }
}

async function doOpen(f: SourceFileItem) {
  fileErr.value = ''; fileMsg.value = ''
  try {
    const url = await createFileUrl(f.path)
    window.open(url, '_blank', 'noopener')
    fileMsg.value = `已生成签名下载链接（10 分钟有效）：${f.name}`
  } catch (e) { fileErr.value = describeCloudError(e) }
}

async function doVerifyReadback(f: SourceFileItem) {
  fileErr.value = ''; fileMsg.value = ''
  try {
    const text = await downloadSourceText(f.path)
    const firstLine = (text.split('\n')[0] ?? '').slice(0, 40)
    fileMsg.value = `读回成功：${f.name}，${text.length} 字符，首行「${firstLine}」`
  } catch (e) { fileErr.value = describeCloudError(e) }
}

async function doRemove(f: SourceFileItem) {
  fileErr.value = ''; fileMsg.value = ''
  try {
    await removeSourceFiles([f.path])
    files.value = await listSourceFiles(labId.value)
    fileMsg.value = `已删除：${f.name}`
  } catch (e) { fileErr.value = describeCloudError(e) }
}

/* ── AI 助教 ── */
const models = ref<TutorModel[]>([])
const modelId = ref('')
const question = ref('')
const answer = ref('')
const aiBusy = ref(false)
const aiErr = ref('')
const modelErr = ref('')
let abort: AbortController | null = null

async function loadModels() {
  modelErr.value = ''
  try {
    models.value = await listModels()
    if (!models.value.length) { modelErr.value = '当前环境未返回可用模型'; return }
    const firstModel = models.value[0]
    if (!modelId.value && firstModel) modelId.value = firstModel.id
  } catch (e) { modelErr.value = describeCloudError(e) }
}

async function doAsk() {
  if (!modelId.value) { aiErr.value = '请先选择模型'; return }
  if (!question.value.trim()) { aiErr.value = '请先写下你的问题'; return }
  aiBusy.value = true; aiErr.value = ''; answer.value = ''
  abort = new AbortController()
  try {
    await askTutor({
      model: modelId.value,
      question: question.value,
      code: current.value?.source_excerpt,
      signal: abort.signal,
      onDelta: (t) => { answer.value += t },
    })
    if (!answer.value) aiErr.value = '模型没有返回内容'
  } catch (e) { aiErr.value = describeCloudError(e) } finally { aiBusy.value = false; abort = null }
}

function doStop() { abort?.abort() }

/* ── 生命周期 ── */
let offAuth: (() => void) | null = null

onMounted(async () => {
  if (!CLOUD_ENABLED) return
  try {
    // 应用启动阶段的微信回调用例（本页也会兜一次，防路由守卫抢先）
    const s = await completeWechatRedirect()
    if (s) await refreshIdentity()
  } catch { /* 无 code 属正常路径 */ }
  await refreshIdentity()
  offAuth = onAuthChange(() => { void refreshIdentity() })
})

onBeforeUnmount(() => { offAuth?.(); abort?.abort() })
</script>

<template>
  <div class="cloud-lab">
    <h1>云端实验存档</h1>
    <p class="lead">
      把源码实验室的进度与源码文件存到云服务，换设备也能接着做；并可用免密钥 AI 助教点评当前实验。
    </p>

    <div v-if="!CLOUD_ENABLED" class="c-error">云服务未配置：缺少 endpoint / publishableKey，本页功能不可用。</div>

    <!-- 1 · 云身份 -->
    <section class="card">
      <h2>1 · 云账号</h2>

      <template v-if="session">
        <p class="ok">
          已登录：<code>{{ user?.email || session.user.id }}</code>
          <span class="dim">（用户 ID {{ session.user.id }}）</span>
        </p>
        <button class="ghost-btn" @click="doSignOut">退出登录</button>
      </template>

      <template v-else>
        <p class="hint">登录后才能读写云端数据与文件。可用邮箱密码、邮箱验证码或微信扫码。</p>
        <div class="grid2">
          <label>
            <span>邮箱</span>
            <input v-model="email" type="email" placeholder="you@example.com" autocomplete="email" />
          </label>
          <label>
            <span>密码{{ codeSent ? '（新邮箱注册需填）' : '' }}</span>
            <input v-model="password" type="password" placeholder="登录密码" autocomplete="current-password" />
          </label>
        </div>

        <div class="row">
          <button class="primary-btn" :disabled="authBusy" @click="doPasswordLogin">邮箱密码登录</button>
          <button class="ghost-btn" type="button" :disabled="authBusy" @click="doSendCode">获取邮箱验证码</button>
          <input v-model="code" class="code" type="text" inputmode="numeric" placeholder="6 位验证码" />
          <button class="ghost-btn" :disabled="authBusy || !codeSent" @click="doVerifyCode">验证码登录 / 注册</button>
        </div>

        <div class="row">
          <button class="ghost-btn" :disabled="authBusy" @click="doWechatLogin">微信扫码 / 一键登录</button>
          <span class="dim">微信登录需在已发布的 HTTPS 域名下使用（本地与预览域不可用）</span>
        </div>
      </template>

      <p v-if="authMsg" class="ok">{{ authMsg }}</p>
      <p v-if="authErr" class="c-error">{{ authErr }}</p>
    </section>

    <!-- 2 · 进度同步 -->
    <section class="card">
      <h2>2 · 实验进度云端存档</h2>
      <div class="row">
        <label class="inline">
          <span>实验</span>
          <select v-model="labId">
            <option v-for="e in exercises" :key="e.id" :value="e.id">{{ e.title }}（{{ e.difficulty }}）</option>
          </select>
        </label>
        <button class="ghost-btn" @click="reloadLocal">刷新本机进度</button>
      </div>

      <p class="hint">
        本机进度：完成 <strong>{{ local.completed.length }}</strong> 个 ·
        尝试记录 <strong>{{ Object.keys(local.attempts).length }}</strong> 条
        <span class="dim">（读取自 localStorage：{{ LOCAL_KEY }}，与源码实验室共用）</span>
      </p>

      <div class="row">
        <button class="primary-btn" :disabled="syncBusy" @click="doPush">本机进度存档到云端</button>
        <button class="ghost-btn" :disabled="syncBusy" @click="doPull">从云端恢复到本机</button>
        <button class="ghost-btn" :disabled="syncBusy" @click="doListCloud">查看云端存档列表</button>
      </div>

      <p v-if="syncMsg" class="ok">{{ syncMsg }}</p>
      <p v-if="syncErr" class="c-error">{{ syncErr }}</p>

      <table v-if="cloudRows.length">
        <thead><tr><th>实验 ID</th><th>已完成</th><th>尝试</th><th>更新时间</th></tr></thead>
        <tbody>
          <tr v-for="r in cloudRows" :key="r.lab_id">
            <td><code>{{ r.lab_id }}</code></td>
            <td>{{ (r.completed || []).length }}</td>
            <td>{{ Object.keys(r.attempts || {}).length }}</td>
            <td>{{ r.updated_at ? new Date(r.updated_at).toLocaleString() : '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 3 · 源码文件 -->
    <section class="card">
      <h2>3 · 源码文件云端存档</h2>
      <p class="hint">文件存放在「当前账号 / 该实验」目录下，只有本人可读写；他人不可见。</p>
      <div class="row">
        <input type="file" accept=".c,.h,.cpp,.txt,.md" @change="onPick" />
        <button class="primary-btn" :disabled="fileBusy" @click="doUpload">上传到云端</button>
        <button class="ghost-btn" :disabled="fileBusy" @click="doListFiles">刷新列表</button>
      </div>

      <p v-if="fileMsg" class="ok">{{ fileMsg }}</p>
      <p v-if="fileErr" class="c-error">{{ fileErr }}</p>

      <ul v-if="files.length" class="files">
        <li v-for="f in files" :key="f.path">
          <span class="fname">{{ f.name }}</span>
          <span class="dim">{{ f.size ?? '—' }} B</span>
          <button class="mini" @click="doVerifyReadback(f)">读回校验</button>
          <button class="mini" @click="doOpen(f)">签名下载</button>
          <button class="mini danger" @click="doRemove(f)">删除</button>
        </li>
      </ul>
    </section>

    <!-- 4 · AI 助教 -->
    <section class="card">
      <h2>4 · AI 助教（免密钥云模型）</h2>
      <div class="row">
        <label class="inline">
          <span>模型</span>
          <select v-model="modelId" :disabled="!models.length">
            <option v-if="!models.length" value="">（无可用模型）</option>
            <option v-for="m in models" :key="m.id" :value="m.id">{{ m.label }}</option>
          </select>
        </label>
        <button class="ghost-btn" @click="loadModels">刷新模型列表</button>
      </div>
      <p v-if="modelErr" class="c-error">{{ modelErr }}</p>

      <label class="block">
        <span>你的问题（会附带当前实验的源码片段）</span>
        <textarea v-model="question" rows="2" placeholder="例：这个调度计数器的自增为什么不是原子的？" />
      </label>
      <div class="row">
        <button class="primary-btn" :disabled="aiBusy" @click="doAsk">{{ aiBusy ? '生成中…' : '请教助教' }}</button>
        <button class="ghost-btn" :disabled="!aiBusy" @click="doStop">停止</button>
      </div>
      <p v-if="aiErr" class="c-error">{{ aiErr }}</p>
      <pre v-if="answer" class="answer">{{ answer }}</pre>
    </section>
  </div>
</template>

<style scoped>
.cloud-lab { padding: var(--space-6, 24px); max-width: 980px; margin: 0 auto; display: grid; gap: var(--space-5, 20px); }
h1 { font-size: var(--text-2xl, 1.6rem); margin: 0; }
.lead { color: var(--color-text-2, var(--text-dim)); margin: 0; }
.card { border: 1px solid var(--color-border, rgba(255,255,255,.12)); border-radius: 12px; padding: var(--space-4, 16px); display: grid; gap: 12px; }
.card h2 { font-size: var(--text-lg, 1.1rem); margin: 0; }
.row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
label span { display: block; font-size: var(--text-xs, .78rem); color: var(--color-text-3, var(--text-dim)); margin-bottom: 4px; }
label.inline { display: flex; align-items: center; gap: 8px; }
label.inline span { margin: 0; }
label.block { display: block; }
input, select, textarea { background: var(--color-surface-2, rgba(255,255,255,.06)); color: inherit; border: 1px solid var(--color-border, rgba(255,255,255,.14)); border-radius: 8px; padding: 8px 10px; font: inherit; width: 100%; }
label.inline select { width: auto; min-width: 220px; }
.code { width: 120px; }
.primary-btn, .ghost-btn, .mini { border-radius: 8px; padding: 8px 12px; cursor: pointer; font: inherit; border: 1px solid var(--color-border, rgba(255,255,255,.16)); }
.primary-btn { background: var(--color-accent); color: #fff; border-color: transparent; }
.ghost-btn { background: transparent; color: inherit; }
.mini { padding: 2px 8px; font-size: var(--text-xs, .78rem); background: transparent; color: inherit; }
.mini.danger { color: var(--accent-danger); }
.primary-btn:disabled, .ghost-btn:disabled { opacity: .5; cursor: not-allowed; }
.hint, .dim { color: var(--color-text-3, var(--text-dim)); font-size: var(--text-sm, .86rem); }
.ok { color: var(--color-success); font-size: var(--text-sm, .86rem); }
.c-error { color: var(--accent-danger); font-size: var(--text-sm, .86rem); background: rgba(var(--danger-rgb), 0.1); border-radius: 8px; padding: 8px 10px; }
table { width: 100%; border-collapse: collapse; font-size: var(--text-sm, .86rem); }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--color-border, rgba(255,255,255,.1)); }
.files { list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; }
.files li { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.fname { font-family: var(--font-mono, monospace); }
.answer { white-space: pre-wrap; background: var(--color-surface-2, rgba(255,255,255,.05)); border-radius: 10px; padding: 12px; margin: 0; font-size: var(--text-sm, .88rem); line-height: 1.6; }
</style>
