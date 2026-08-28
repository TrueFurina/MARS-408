<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import {
  cancelCompilation,
  compileAndRunC,
  getCompilerEnvironment,
  isCompilerBusy,
  type CompileResult,
} from '@/services/wasmCompiler'
import {
  SOURCE_LAB_EXERCISES,
  SOURCE_LAB_EXERCISES_BY_ID,
  evaluateSourceLabPass,
  type SourceLabExercise,
} from '@/data/sourceLabExercises'

type LabMode = 'source' | 'experiment'

const STORAGE_KEY = 'mars408_sourcelab_progress_v1'

const exercises = SOURCE_LAB_EXERCISES
const firstExercise = exercises[0]
const activeId = ref(firstExercise ? firstExercise.id : '')
const activeMode = ref<LabMode>('source')
const editorCode = ref('')
const terminalOutput = ref('')
const running = ref(false)
const progressLabel = ref('')
const lastResult = ref<CompileResult | null>(null)

const compilerEnvironment = getCompilerEnvironment()

function loadProgress(): { completed: string[]; attempts: Record<string, number> } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        completed: Array.isArray(parsed.completed) ? parsed.completed : [],
        attempts: parsed.attempts && typeof parsed.attempts === 'object' ? parsed.attempts : {},
      }
    }
  } catch { /* 忽略损坏的进度缓存 */ }
  return { completed: [], attempts: {} }
}

const progress = ref(loadProgress())

function saveProgress() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(progress.value))
  } catch { /* 存储失败不影响实验 */ }
}

const activeExercise = computed<SourceLabExercise | undefined>(
  () => SOURCE_LAB_EXERCISES_BY_ID[activeId.value],
)
const completedIds = computed(() => new Set(progress.value.completed))
const activePassed = computed(() => completedIds.value.has(activeId.value))
const activeAttemptCount = computed(() => progress.value.attempts[activeId.value] || 0)
const completedCount = computed(() => progress.value.completed.length)

function selectExercise(id: string) {
  activeId.value = id
  activeMode.value = 'source'
  editorCode.value = ''
  terminalOutput.value = ''
  lastResult.value = null
}

function switchMode(mode: LabMode) {
  if (running.value) return
  activeMode.value = mode
  terminalOutput.value = ''
  lastResult.value = null
}

function copySource() {
  const ex = activeExercise.value
  if (!ex) return
  try {
    navigator.clipboard?.writeText(ex.source_excerpt)
  } catch { /* 剪贴板不可用时忽略 */ }
}

function resetCode() {
  const ex = activeExercise.value
  if (!ex) return
  editorCode.value = ex.experiment.starter_code
  terminalOutput.value = ''
  lastResult.value = null
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

async function runExperiment() {
  const ex = activeExercise.value
  if (running.value || !ex || !editorCode.value.trim()) return
  if (!compilerEnvironment.ready) {
    terminalOutput.value = compilerEnvironment.message || '浏览器编译环境未就绪'
    return
  }
  running.value = true
  terminalOutput.value = ''
  lastResult.value = null
  progressLabel.value = ''

  const onProgress = (stage: string) => {
    const labels: Record<string, string> = {
      runtime: '正在初始化 WASM 运行时...',
      toolchain: '正在加载编译工具链...',
      compile: '正在编译...',
      run: '正在运行程序...',
    }
    progressLabel.value = labels[stage] || stage
  }

  try {
    const result = await compileAndRunC(editorCode.value, ex.experiment.stdin, { onProgress })
    lastResult.value = result
    progress.value.attempts[ex.id] = (progress.value.attempts[ex.id] || 0) + 1

    const parts: string[] = []
    if (result.stdout) parts.push(result.stdout)
    if (result.stderr) parts.push(result.stderr)
    terminalOutput.value = parts.join('\n') || '(无输出)'

    if (evaluateSourceLabPass(ex, result.stage, result.code, result.stdout)) {
      if (!completedIds.value.has(ex.id)) {
        progress.value.completed.push(ex.id)
        terminalOutput.value += '\n\n✅ 实验通过：输出符合预期！'
      }
    } else if (result.stage === 'run') {
      terminalOutput.value += '\n\n❌ 未通过：请对照「实验目标」检查输出。'
    }
    saveProgress()
  } catch (e) {
    terminalOutput.value = String((e as Error)?.message || e)
  } finally {
    running.value = false
    progressLabel.value = ''
  }
}

function stopExperiment() {
  cancelCompilation()
  running.value = false
  progressLabel.value = ''
  terminalOutput.value += '\n[任务已终止]'
}

onBeforeUnmount(() => {
  if (isCompilerBusy()) cancelCompilation()
})
</script>

<template>
  <div class="source-lab-workspace">
    <aside class="source-browser">
      <div class="browser-heading">
        <strong>linux-0.11</strong>
        <small>精选源码 · {{ completedCount }}/{{ exercises.length }} 完成</small>
      </div>
      <div class="source-list">
        <button
          v-for="ex in exercises"
          :key="ex.id"
          type="button"
          :class="{ active: ex.id === activeId }"
          @click="selectExercise(ex.id)"
        >
          <span class="source-path">{{ ex.path }}</span>
          <span class="source-title">{{ ex.title }}</span>
          <span v-if="completedIds.has(ex.id)" class="completed-mark">✓</span>
        </button>
      </div>
      <a class="archive-link" :href="activeExercise?.source_url" target="_blank" rel="noopener noreferrer">
        kernel.org 历史归档 ↗
      </a>
    </aside>

    <section class="editor-panel">
      <div class="sandbox-toolbar">
        <span class="sandbox-title">
          {{ activeExercise?.path }} <small>L{{ activeExercise?.source_lines }}</small>
        </span>
        <div class="sandbox-actions">
          <div class="lang-switch" aria-label="代码视图">
            <button
              type="button"
              :class="{ active: activeMode === 'source' }"
              :disabled="running"
              @click="switchMode('source')"
            >原始源码</button>
            <button
              type="button"
              :class="{ active: activeMode === 'experiment' }"
              :disabled="running"
              @click="switchMode('experiment')"
            >可运行实验</button>
          </div>
          <button v-if="activeMode === 'source'" class="sandbox-btn" @click="copySource">复制</button>
          <template v-else>
            <button class="sandbox-btn" :disabled="running" @click="resetCode">重置</button>
            <button
              v-if="!running"
              class="sandbox-run-btn"
              :disabled="!editorCode.trim()"
              @click="runExperiment"
            >▶ 编译运行</button>
            <button v-else class="sandbox-run-btn stop" @click="stopExperiment">■ 终止</button>
          </template>
        </div>
      </div>

      <div v-if="activeMode === 'source'" class="source-viewer">
        <pre><code>{{ activeExercise?.source_excerpt }}</code></pre>
      </div>
      <div v-else class="editor-wrap">
        <div v-if="!editorCode && activeExercise" class="editor-placeholder">
          <p>点击「重置」载入本实验的起始代码，或在下方直接编写。</p>
        </div>
        <textarea
          v-model="editorCode"
          class="sandbox-editor"
          placeholder="在这里输入 C 代码..."
          spellcheck="false"
          :disabled="running"
        ></textarea>
      </div>

      <div class="terminal-panel">
        <div class="sandbox-toolbar" style="border-top:1px solid var(--border-light);border-bottom:none;">
          <span class="sandbox-title">📤 运行终端</span>
          <span class="sandbox-title" v-if="lastResult">
            exit {{ lastResult.code }} · {{ formatDuration(lastResult.durationMs) }}
          </span>
          <span class="sandbox-title" v-if="running">{{ progressLabel }}</span>
        </div>
        <div class="sandbox-output">
          <pre class="output-text" :class="{ 'has-error': lastResult && lastResult.code !== 0 }">{{ terminalOutput }}</pre>
          <div v-if="!terminalOutput && !running" class="output-placeholder">
            点击「编译运行」执行实验代码
          </div>
        </div>
      </div>
    </section>

    <aside class="learning-panel">
      <div class="topic-heading">
        <span class="topic-chapter">{{ activeExercise?.chapter }}</span>
        <strong>{{ activeExercise?.title }}</strong>
        <small>{{ activeExercise?.difficulty }}</small>
      </div>
      <p class="topic-summary">{{ activeExercise?.summary }}</p>

      <section class="learning-block">
        <h3>🎯 实验目标</h3>
        <p>{{ activeExercise?.experiment.objective }}</p>
      </section>

      <section class="learning-block">
        <h3>📋 实践任务</h3>
        <ol>
          <li v-for="(instruction, i) in activeExercise?.experiment.instructions || []" :key="i">
            {{ instruction }}
          </li>
        </ol>
      </section>

      <section class="learning-block">
        <h3>🔗 关联概念</h3>
        <div class="concept-list">
          <span v-for="concept in activeExercise?.concepts || []" :key="concept">{{ concept }}</span>
        </div>
      </section>

      <div class="record-status" :class="{ passed: activePassed }">
        <strong>{{ activePassed ? '✅ 实验已通过' : '⏳ 尚未通过' }}</strong>
        <small>{{ activeAttemptCount }} 次运行记录</small>
      </div>
      <p class="source-note">{{ activeExercise?.attribution }}</p>
    </aside>
  </div>
</template>

<style scoped>
.source-lab-workspace {
  display: grid;
  grid-template-columns: 14rem 1fr 18rem;
  gap: 1rem;
  height: calc(100vh - 12.5rem);
  min-height: 31.25rem;
}
@media (max-width: 1100px) {
  .source-lab-workspace { grid-template-columns: 1fr; height: auto; }
}
.source-browser, .editor-panel, .learning-panel {
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  overflow: hidden;
  backdrop-filter: blur(12px);
}
.browser-heading {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  padding: 0.75rem 0.875rem;
  border-bottom: 1px solid var(--border-light);
}
.browser-heading strong { font-size: 0.8125rem; color: var(--text-primary); }
.browser-heading small { font-size: 0.6875rem; color: var(--text-muted); }
.source-list { flex: 1; overflow: auto; padding: 0.375rem; }
.source-list button {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  width: 100%;
  padding: 0.5rem 0.625rem;
  margin-bottom: 0.25rem;
  text-align: left;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  transition: var(--transition);
}
.source-list button:hover { background: var(--accent-1-light); }
.source-list button.active { background: var(--accent-1-light); outline: 1px solid var(--accent-1); }
.source-path { font-family: 'SF Mono', 'Consolas', monospace; font-size: 0.6875rem; color: var(--accent-1); }
.source-title { font-size: 0.75rem; color: var(--text-primary); }
.completed-mark { position: absolute; right: 0.5rem; color: var(--accent-success); font-weight: 700; }
.archive-link {
  padding: 0.5rem 0.875rem;
  border-top: 1px solid var(--border-light);
  font-size: 0.6875rem;
  color: var(--text-muted);
  text-decoration: none;
}
.archive-link:hover { color: var(--accent-1); }
.sandbox-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.625rem 0.875rem;
  border-bottom: 1px solid var(--border-light);
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.sandbox-title { font-size: 0.8125rem; font-weight: 600; color: var(--text-secondary); }
.sandbox-title small { font-weight: 400; color: var(--text-muted); }
.sandbox-actions { display: flex; gap: 0.375rem; align-items: center; }
.sandbox-btn {
  padding: 0.3125rem 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: var(--transition);
}
.sandbox-btn:hover { border-color: var(--accent-1); color: var(--accent-1); }
.sandbox-run-btn {
  padding: 0.3125rem 1rem;
  border-radius: var(--radius-sm);
  border: none;
  background: var(--gradient-accent);
  color: var(--text-user);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition);
}
.sandbox-run-btn.stop { background: var(--accent-danger); }
.sandbox-run-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.lang-switch { display: flex; gap: 0.25rem; }
.lang-switch button {
  padding: 0.25rem 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: var(--transition);
}
.lang-switch button.active { background: var(--gradient-accent); color: var(--text-user); border-color: transparent; }
.source-viewer {
  flex: 1;
  overflow: auto;
  padding: 0.875rem;
  background: var(--color-surface-2);
}
.source-viewer pre {
  margin: 0;
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 0.75rem;
  line-height: 1.6;
  color: var(--color-text);
  white-space: pre;
}
.editor-wrap { flex: 1; display: flex; flex-direction: column; position: relative; }
.editor-placeholder {
  position: absolute;
  top: 0.75rem;
  left: 0.875rem;
  font-size: 0.75rem;
  color: var(--color-text-3);
  pointer-events: none;
}
.sandbox-editor {
  flex: 1;
  padding: 0.875rem;
  border: none;
  outline: none;
  background: var(--color-surface-2);
  color: var(--color-text);
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 0.8125rem;
  line-height: 1.6;
  resize: none;
  tab-size: 4;
}
.sandbox-editor::placeholder { color: var(--color-text-3); }
.terminal-panel { flex-shrink: 0; display: flex; flex-direction: column; }
.sandbox-output {
  flex: 1;
  min-height: 6.25rem;
  max-height: 10rem;
  overflow: auto;
  padding: 0.875rem;
  background: var(--bg-elevated);
}
.output-text {
  margin: 0;
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: var(--accent-success);
  white-space: pre-wrap;
}
.output-text.has-error { color: var(--accent-danger); }
.output-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-text-3);
  font-size: 0.8125rem;
  text-align: center;
}
.learning-panel { padding: 0.875rem; overflow: auto; gap: 0.75rem; }
.topic-heading { display: flex; flex-direction: column; gap: 0.125rem; }
.topic-chapter { font-size: 0.6875rem; color: var(--accent-1); }
.topic-heading strong { font-size: 1rem; color: var(--text-primary); }
.topic-heading small { font-size: 0.6875rem; color: var(--text-muted); }
.topic-summary { font-size: 0.8125rem; color: var(--text-secondary); line-height: 1.6; margin: 0.375rem 0 0; }
.learning-block h3 { font-size: 0.75rem; color: var(--text-primary); margin: 0 0 0.375rem; }
.learning-block p { font-size: 0.75rem; color: var(--text-secondary); line-height: 1.6; margin: 0; }
.learning-block ol { margin: 0; padding-left: 1.125rem; }
.learning-block li { font-size: 0.75rem; color: var(--text-secondary); line-height: 1.6; margin-bottom: 0.25rem; }
.concept-list { display: flex; flex-wrap: wrap; gap: 0.375rem; }
.concept-list span {
  padding: 0.1875rem 0.5rem;
  border-radius: 999px;
  background: var(--accent-1-light);
  color: var(--accent-1);
  font-size: 0.6875rem;
}
.record-status {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  padding: 0.625rem 0.75rem;
  border-radius: var(--radius-sm);
  background: var(--accent-warning-light, rgba(255, 193, 7, 0.12));
  border: 1px solid rgba(255, 193, 7, 0.35);
}
.record-status.passed {
  background: rgba(82, 196, 26, 0.1);
  border-color: rgba(82, 196, 26, 0.4);
}
.record-status strong { font-size: 0.75rem; color: var(--text-primary); }
.record-status small { font-size: 0.6875rem; color: var(--text-muted); }
.source-note { font-size: 0.625rem; color: var(--text-muted); margin: 0; }
</style>
