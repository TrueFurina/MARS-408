<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { api } from '@/utils/api'
import { renderMarkdownSafe } from '@/utils/markdown'
import { icons } from '@/components/icons'

// L1/L2/L3 三层学情记忆（低侵入联动：代码实验室页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
onMounted(async () => {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞代码实验室页 */ }
})

const code = ref(`# 网络编程示例：TCP 客户端
# 在沙箱中模拟运行，不会发起真实连接
import socket

def tcp_client():
    """模拟 TCP 客户端"""
    sock = _net_simulate("192.168.1.100", 80)
    print("[模拟] 发送 HTTP GET 请求...")
    print("[模拟] 接收响应: HTTP/1.1 200 OK")
    return True

tcp_client()
print("TCP 客户端运行完成")
`)
const output = ref('')
const error = ref('')
const running = ref(false)
const showExamples = ref(false)

const examples = [
  {
    name: 'TCP 客户端',
    code: `# TCP 客户端示例
import socket

def scan_port(host, port):
    """模拟端口扫描"""
    print(f"[扫描] 检查 {host}:{port}...")

    # 模拟 TCP 连接
    _net_simulate(host, port)
    print(f"[结果] 端口 {port} 开放")

scan_port("192.168.1.1", 80)
print("扫描完成")`,
  },
  {
    name: '子网计算',
    code: `# 子网计算示例
import ipaddress

def calc_subnet(ip_str, prefix):
    net = ipaddress.IPv4Network(f"{ip_str}/{prefix}", strict=False)
    print(f"网络地址: {net.network_address}")
    print(f"广播地址: {net.broadcast_address}")
    print(f"子网掩码: {net.netmask}")
    print(f"可用主机: {net.num_addresses - 2}")
    hosts = list(net.hosts())
    print(f"主机范围: {hosts[0]} ~ {hosts[-1]}")

calc_subnet("192.168.1.0", 24)`,
  },
  {
    name: 'DNS 解析模拟',
    code: `# DNS 解析模拟
import random

def dns_lookup(domain):
    """模拟 DNS 解析"""
    print(f"[DNS] 查询 {domain}...")
    # 模拟 DNS 响应
    fake_ip = f"10.0.{random.randint(0,255)}.{random.randint(1,254)}"
    print(f"[DNS] {domain} -> {fake_ip}")
    return fake_ip

dns_lookup("www.example.com")
dns_lookup("mail.example.com")`,
  },
]

async function runCode() {
  if (running.value || !code.value.trim()) return
  running.value = true
  output.value = ''
  error.value = ''

  try {
    const data = await api.post<{ output: string; error: string }>('/sandbox/run', { code: code.value, language: 'python', timeout: 5 })
    output.value = data.output || ''
    error.value = data.error || ''
  } catch {
    error.value = '无法连接到后端沙箱服务'
  } finally {
    running.value = false
  }
}

function loadExample(exampleCode: string) {
  code.value = exampleCode
  output.value = ''
  error.value = ''
  showExamples.value = false
}

function clearAll() {
  code.value = ''
  output.value = ''
  error.value = ''
}
</script>

<template>
  <div class="page-section active">
    <div class="section-header" style="text-align:center;">
      <div class="section-title">💻 网络编程沙箱</div>
      <div class="section-desc">在线运行网络编程代码，学习 Socket 编程、子网计算等</div>

      <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
      <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
        <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 记忆薄弱点:</span>
        <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
      </div>
    </div>

    <div class="sandbox-layout">
      <!-- 代码编辑器 -->
      <div class="sandbox-editor-panel">
        <div class="sandbox-toolbar">
          <span class="sandbox-title">📝 Python 代码</span>
          <div class="sandbox-actions">
            <button class="sandbox-btn" @click="showExamples = !showExamples">📚 示例</button>
            <button class="sandbox-btn" @click="clearAll">🗑️ 清空</button>
            <button class="sandbox-run-btn" :disabled="running || !code.trim()" @click="runCode">
              {{ running ? '⏳ 运行中...' : '▶ 运行' }}
            </button>
          </div>
        </div>
        <!-- 示例下拉 -->
        <div v-if="showExamples" class="sandbox-examples">
          <div v-for="ex in examples" :key="ex.name" class="sandbox-example-item" role="button" tabindex="0" @click="loadExample(ex.code)" @keydown.enter="loadExample(ex.code)" @keydown.space.prevent="loadExample(ex.code)">
            <span class="example-name">{{ ex.name }}</span>
            <span class="example-arrow">→</span>
          </div>
        </div>
        <textarea
          v-model="code"
          class="sandbox-editor"
          placeholder="在这里输入 Python 代码..."
          spellcheck="false"
        ></textarea>
        <div class="sandbox-info">
          可用模块: socket, struct, ipaddress, hashlib, json, math, random
        </div>
      </div>

      <!-- 输出面板 -->
      <div class="sandbox-output-panel">
        <div class="sandbox-toolbar">
          <span class="sandbox-title">📤 输出</span>
          <span v-if="running" class="sandbox-status running">运行中...</span>
        </div>
        <div class="sandbox-output" :class="{ 'has-error': error }">
          <pre v-if="output" class="output-text">{{ output }}</pre>
          <pre v-if="error" class="error-text">{{ error }}</pre>
          <div v-if="!output && !error && !running" class="output-placeholder">
            点击「运行」执行代码，结果将显示在这里
          </div>
          <div v-if="running" class="output-placeholder">
            <div class="loading-spinner" style="width:24px;height:24px;margin:0 auto;"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sandbox-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap:1rem;
  height:calc(100vh - 12.5rem);
  min-height:31.25rem;
}
@media (max-width: 900px) {
  .sandbox-layout { grid-template-columns: 1fr; }
}
.sandbox-editor-panel, .sandbox-output-panel {
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius:var(--radius-md);
  overflow: hidden;
  backdrop-filter: blur(12px);
}
.sandbox-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding:0.625rem 0.875rem;
  border-bottom: 1px solid var(--border-light);
  flex-shrink: 0;
  flex-wrap: wrap;
  gap:0.5rem;
}
.sandbox-title { font-size:0.8125rem; font-weight: 600; color: var(--text-secondary); }
.sandbox-actions { display: flex; gap:0.375rem; }
.sandbox-btn {
  padding:0.3125rem 0.75rem;
  border-radius:var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  font-size:0.75rem;
  cursor: pointer;
  transition: var(--transition);
}
.sandbox-btn:hover { border-color: var(--accent-1); color: var(--accent-1); }
.sandbox-run-btn {
  padding:0.3125rem 1rem;
  border-radius:var(--radius-sm);
  border: none;
  background: var(--gradient-accent);
  color: var(--text-user);
  font-size:0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition);
}
.sandbox-run-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.sandbox-run-btn:hover:not(:disabled) { opacity: 0.9; }
.sandbox-examples {
  border-bottom: 1px solid var(--border-light);
  padding:0.25rem;
}
.sandbox-example-item {
  display: flex;
  justify-content: space-between;
  padding:0.5rem 0.875rem;
  cursor: pointer;
  border-radius:var(--radius-sm);
  font-size:0.8125rem;
  transition: var(--transition);
}
.sandbox-example-item:hover { background: var(--accent-1-light); }
.example-name { color: var(--text-primary); }
.example-arrow { color: var(--accent-1); }
.sandbox-editor {
  flex: 1;
  padding:0.875rem;
  border: none;
  outline: none;
  background: var(--color-surface-2);
  color: var(--color-text);
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  font-size:0.8125rem;
  line-height:1.6;
  resize: none;
  tab-size: 4;
}
.sandbox-editor::placeholder { color: var(--color-text-3); }
.sandbox-info {
  padding:0.5rem 0.875rem;
  font-size:0.6875rem;
  color: var(--text-muted);
  border-top: 1px solid var(--border-light);
  flex-shrink: 0;
}
.sandbox-output {
  flex: 1;
  padding:0.875rem;
  overflow: auto;
  background: var(--bg-elevated);
}
.output-text {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size:0.8125rem;
  line-height:1.5;
  color: var(--accent-success);
  white-space: pre-wrap;
}
.error-text {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size:0.8125rem;
  line-height:1.5;
  color: var(--accent-danger);
  white-space: pre-wrap;
}
.output-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height:100%;
  color: var(--color-text-3);
  font-size:0.8125rem;
  text-align: center;
  padding:2.5rem;
}
.sandbox-status.running { font-size:0.75rem; color: var(--accent-2); }
</style>
