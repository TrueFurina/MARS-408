<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import {
  cancelCompilation,
  compileAndRunC,
  compileAndRunCpp,
  getCompilerEnvironment,
  isCompilerBusy,
  type CompileResult,
} from '@/services/wasmCompiler'
import SourceLabPane from '@/components/SourceLabPane.vue'

type Workspace = 'playground' | 'source'
const workspace = ref<Workspace>('playground')

const language = ref<'c' | 'cpp'>('c')
const sourceCode = ref(`#include <stdio.h>

int main(void) {
    printf("Hello, OS World!\\n");
    return 0;
}
`)
const stdinValue = ref('')
const terminalOutput = ref('')
const running = ref(false)
const progressLabel = ref('')
const lastResult = ref<CompileResult | null>(null)
const envError = ref('')

const cExamples = [
  {
    id: 'hello',
    title: 'Hello World',
    code: `#include <stdio.h>

int main(void) {
    printf("Hello, OS World!\\n");
    return 0;
}
`,
  },
  {
    id: 'fcfs',
    title: 'FCFS 调度',
    code: `#include <stdio.h>

int main(void) {
    int n = 4;
    int at[] = {0, 1, 2, 3};
    int bt[] = {4, 3, 1, 2};
    int ct[4], wt[4], tat[4];
    int time = 0, i;
    for (i = 0; i < n; i++) {
        if (time < at[i]) time = at[i];
        ct[i] = time + bt[i];
        time = ct[i];
        tat[i] = ct[i] - at[i];
        wt[i] = tat[i] - bt[i];
        printf("P%d: 完成=%d 周转=%d 等待=%d\\n", i + 1, ct[i], tat[i], wt[i]);
    }
    return 0;
}
`,
  },
  {
    id: 'page-replace',
    title: 'FIFO 页面置换',
    code: `#include <stdio.h>

int main(void) {
    int frames = 3;
    int refs[] = {7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2};
    int n = sizeof(refs) / sizeof(refs[0]);
    int queue[3] = {-1, -1, -1};
    int faults = 0, pos = 0, i, j, hit;
    for (i = 0; i < n; i++) {
        hit = 0;
        for (j = 0; j < frames; j++)
            if (queue[j] == refs[i]) { hit = 1; break; }
        if (!hit) {
            queue[pos] = refs[i];
            pos = (pos + 1) % frames;
            faults++;
            printf("访问 %2d -> 缺页\\n", refs[i]);
        } else {
            printf("访问 %2d -> 命中\\n", refs[i]);
        }
    }
    printf("总缺页次数: %d\\n", faults);
    return 0;
}
`,
  },
]

const cppExamples = [
  {
    id: 'hello-cpp',
    title: 'Hello C++',
    code: `#include <iostream>
#include <vector>

int main() {
    std::vector<int> v = {1, 2, 3, 4, 5};
    int sum = 0;
    for (int x : v) sum += x;
    std::cout << "sum = " << sum << std::endl;
    return 0;
}
`,
  },
  {
    id: 'producer-consumer',
    title: '生产者消费者模拟',
    code: `#include <iostream>
#include <queue>

int main() {
    std::queue<int> buffer;
    const int capacity = 3;
    int produced = 0, consumed = 0;
    for (int i = 0; i < 6; i++) {
        if (buffer.size() < capacity) {
            buffer.push(produced);
            std::cout << "生产 " << produced++ << std::endl;
        }
        if (!buffer.empty()) {
            std::cout << "消费 " << buffer.front() << std::endl;
            buffer.pop();
            consumed++;
        }
    }
    std::cout << "共消费 " << consumed << " 个" << std::endl;
    return 0;
}
`,
  },
]

const examples = computed(() => (language.value === 'c' ? cExamples : cppExamples))
const selectedExampleId = ref('hello')

const compilerEnvironment = getCompilerEnvironment()
envError.value = compilerEnvironment.ready ? '' : compilerEnvironment.message

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

function loadExample(id: string) {
  const ex = examples.value.find(e => e.id === id)
  if (ex) {
    sourceCode.value = ex.code
    terminalOutput.value = ''
    lastResult.value = null
  }
}

function switchLanguage(lang: 'c' | 'cpp') {
  if (running.value) return
  language.value = lang
  const first = examples.value[0]
  if (first) {
    selectedExampleId.value = first.id
    sourceCode.value = first.code
  }
  terminalOutput.value = ''
  lastResult.value = null
}

async function runCode() {
  if (running.value || !sourceCode.value.trim()) return
  if (!compilerEnvironment.ready) {
    terminalOutput.value = envError.value || '浏览器编译环境未就绪'
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
    const result = language.value === 'c'
      ? await compileAndRunC(sourceCode.value, stdinValue.value, { onProgress })
      : await compileAndRunCpp(sourceCode.value, stdinValue.value, { onProgress })
    lastResult.value = result
    const parts: string[] = []
    if (result.stdout) parts.push(result.stdout)
    if (result.stderr) parts.push(result.stderr)
    terminalOutput.value = parts.join('\n') || '(无输出)'
  } catch (e) {
    terminalOutput.value = String((e as Error)?.message || e)
  } finally {
    running.value = false
    progressLabel.value = ''
  }
}

function stopCode() {
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
  <div class="page-section active">
    <div class="section-header" style="text-align:center;">
      <div class="section-title">⚙️ 浏览器 C/C++ 实验室</div>
      <div class="section-desc">在浏览器内编译运行 C/C++（WASI），无需安装本地工具链</div>
      <div class="workspace-switch" aria-label="实验工作区">
        <button
          type="button"
          :class="{ active: workspace === 'playground' }"
          @click="workspace = 'playground'"
        >自由编程</button>
        <button
          type="button"
          :class="{ active: workspace === 'source' }"
          @click="workspace = 'source'"
        >Linux 0.11 源码</button>
      </div>
    </div>

    <div v-if="workspace === 'source'">
      <SourceLabPane />
    </div>

    <template v-else>
    <div v-if="!compilerEnvironment.ready" class="compiler-notice" role="status">
      <strong>浏览器编译环境尚未就绪</strong>
      <span>{{ envError }}</span>
      <small>开发模式需在 vite.config 中启用 COOP/COEP 响应头，生产环境需反向代理配置。</small>
    </div>

    <div class="sandbox-layout">
      <div class="sandbox-editor-panel">
        <div class="sandbox-toolbar">
          <div class="lang-switch" aria-label="编程语言">
            <button
              type="button"
              :class="{ active: language === 'c' }"
              :disabled="running"
              @click="switchLanguage('c')"
            >C</button>
            <button
              type="button"
              :class="{ active: language === 'cpp' }"
              :disabled="running"
              @click="switchLanguage('cpp')"
            >C++</button>
          </div>
          <div class="sandbox-actions">
            <select
              v-model="selectedExampleId"
              class="example-select"
              aria-label="示例代码"
              :disabled="running"
              @change="loadExample(selectedExampleId)"
            >
              <option v-for="ex in examples" :key="ex.id" :value="ex.id">{{ ex.title }}</option>
            </select>
            <button class="sandbox-btn" @click="sourceCode = ''; terminalOutput = ''">清空</button>
            <button
              v-if="!running"
              class="sandbox-run-btn"
              :disabled="!sourceCode.trim()"
              @click="runCode"
            >▶ 运行</button>
            <button v-else class="sandbox-run-btn stop" @click="stopCode">■ 终止</button>
          </div>
        </div>

        <textarea
          v-model="sourceCode"
          class="sandbox-editor"
          :placeholder="language === 'c' ? '在这里输入 C 代码...' : '在这里输入 C++ 代码...'"
          spellcheck="false"
          :disabled="running"
        ></textarea>
        <div class="sandbox-info">
          {{ language === 'c' ? 'clang · wasm32-wasi · C11' : 'clang++ · wasm32-wasi · C++17' }} — 单次最长 90s，源码 ≤ 20000 字符
        </div>
      </div>

      <div class="sandbox-output-panel">
        <div class="sandbox-toolbar">
          <span class="sandbox-title">📥 标准输入</span>
          <span class="sandbox-title" v-if="lastResult">exit {{ lastResult.code }} · {{ formatDuration(lastResult.durationMs) }}</span>
          <span class="sandbox-title" v-if="running">{{ progressLabel }}</span>
        </div>
        <textarea
          v-model="stdinValue"
          class="sandbox-editor stdin-editor"
          placeholder="可选：程序运行时读取的输入"
          spellcheck="false"
          :disabled="running"
          maxlength="8000"
        ></textarea>
        <div class="sandbox-toolbar" style="border-top:1px solid var(--border-light);border-bottom:none;">
          <span class="sandbox-title">📤 运行输出</span>
        </div>
        <div class="sandbox-output">
          <pre class="output-text" :class="{ 'has-error': lastResult && lastResult.code !== 0 }">{{ terminalOutput }}</pre>
          <div v-if="!terminalOutput && !running" class="output-placeholder">
            点击「运行」编译并执行代码，结果将显示在这里
          </div>
          <div v-if="running" class="output-placeholder">{{ progressLabel || '执行中...' }}</div>
        </div>
      </div>
    </div>
    </template>
  </div>
</template>

<style scoped>
.workspace-switch {
  display: inline-flex;
  gap: 0.375rem;
  margin-top: 0.5rem;
}
.workspace-switch button {
  padding: 0.3125rem 0.875rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: var(--transition);
}
.workspace-switch button:hover { border-color: var(--accent-1); color: var(--accent-1); }
.workspace-switch button.active {
  background: var(--gradient-accent);
  color: var(--text-user);
  border-color: transparent;
  font-weight: 600;
}
.sandbox-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  height: calc(100vh - 12.5rem);
  min-height: 31.25rem;
}
@media (max-width: 900px) {
  .sandbox-layout { grid-template-columns: 1fr; }
}
.sandbox-editor-panel, .sandbox-output-panel {
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  overflow: hidden;
  backdrop-filter: blur(12px);
}
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
.sandbox-run-btn:hover:not(:disabled) { opacity: 0.9; }
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
.example-select {
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 0.75rem;
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
.stdin-editor { flex: 0 0 5rem; border-bottom: 1px solid var(--border-light); }
.sandbox-editor::placeholder { color: var(--color-text-3); }
.sandbox-info {
  padding: 0.5rem 0.875rem;
  font-size: 0.6875rem;
  color: var(--text-muted);
  border-top: 1px solid var(--border-light);
  flex-shrink: 0;
}
.sandbox-output {
  flex: 1;
  padding: 0.875rem;
  overflow: auto;
  background: var(--bg-elevated);
}
.output-text {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: var(--accent-success);
  white-space: pre-wrap;
  margin: 0;
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
  padding: 2.5rem;
}
.compiler-notice {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
  border-radius: var(--radius-md);
  background: var(--accent-warning-light, rgba(255, 193, 7, 0.12));
  border: 1px solid rgba(255, 193, 7, 0.35);
  color: var(--text-primary);
  font-size: 0.8125rem;
}
.compiler-notice small { color: var(--text-muted); }
</style>
