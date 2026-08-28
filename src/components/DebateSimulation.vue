<script setup lang="ts">
import { ref } from 'vue'
import { api } from '@/utils/api'

const visible = ref(false)
const active = ref(false)
const log = ref<string[]>([])
const error = ref('')

async function simulate() {
  active.value = true
  error.value = ''
  log.value = ['🚀 正在调用后端冲突检测引擎...']
  
  try {
    const result = await api.post<any>('/engine/conflict-check', {
      agent_results: [
        { agent_name: 'teacher', content: 'TCP三次握手是标准流程，SYN→SYN+ACK→ACK，RFC 793明确规定。' },
        { agent_name: 'quizmaster', content: 'TCP建立连接使用三次握手，但题目选项中需要包含四次握手的干扰项。' },
        { agent_name: 'extension', content: 'TCP拥塞控制分为慢启动(指数增长)和拥塞避免(线性增长)两个阶段。' },
      ],
      course: 'computer_network',
    })
    
    log.value = []
    log.value.push('✅ 后端冲突检测完成')
    log.value.push('')
    
    if (result.conflicts && result.conflicts.length > 0) {
      for (const c of result.conflicts) {
        log.value.push(`⚡ 冲突: ${c.agent_a} vs ${c.agent_b}`)
        log.value.push(`   类型: ${c.type}`)
        log.value.push(`   描述: ${c.description}`)
        log.value.push(`   消解: ${c.resolution}`)
        log.value.push(`   置信度: ${((c.confidence ?? 0) * 100).toFixed(0)}%`)
        log.value.push(`   证据数: ${c.evidence_count}`)
        log.value.push('')
      }
      log.value.push(`📊 一致性评分: ${((result.overall_consistency ?? 0) * 100).toFixed(0)}%`)
    } else {
      log.value.push('✅ 未检测到冲突，所有 Agent 内容一致')
      log.value.push('')
      log.value.push('📊 一致性评分: 100%')
    }
    log.value.push(`🔍 共检测 ${result.total_conflicts} 个冲突，已消解 ${result.resolved} 个`)
    
  } catch (e: any) {
    error.value = e?.message || '调用后端失败'
    log.value.push(`❌ 错误: ${error.value}`)
    log.value.push('')
    log.value.push('💡 请确保后端已启动 (http://127.0.0.1:8002)')
  } finally {
    active.value = false
  }
}
</script>

<template>
  <div class="card">
    <div class="card-header">
      <div class="card-title">Agent 辩论模拟</div>
      <button class="debate-btn" :disabled="active" @click="simulate">
        {{ active ? '检测中...' : '启动冲突检测' }}
      </button>
    </div>
    <div v-if="error" class="debate-error">
      ⚠️ {{ error }} — <button class="retry-btn" @click="simulate">重试</button>
    </div>
    <div v-if="log.length > 0" class="debate-log">
      <div v-for="(line, i) in log" :key="i" class="debate-line">{{ line }}</div>
    </div>
    <div v-else class="debate-empty">点击按钮调用后端冲突检测引擎，获取真实检测结果</div>
  </div>
</template>

<style scoped>
.debate-btn {
  padding:0.5rem 1.125rem;
  border-radius:var(--radius-sm);
  border: 1px solid var(--accent-primary);
  background: transparent;
  color: var(--accent-primary);
  font-size:0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition);
}
.debate-btn:hover:not(:disabled) {
  background: var(--accent-primary-10);
}
.debate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.debate-error {
  margin-top:0.5rem;
  padding:0.5rem 0.75rem;
  background: var(--accent-danger-10);
  border-radius:var(--radius-sm);
  color: var(--accent-danger);
  font-size:0.75rem;
}
.retry-btn {
  background: none;
  border: 1px solid var(--accent-danger);
  color: var(--accent-danger);
  border-radius:0.25rem;
  padding:0.125rem 0.5rem;
  cursor: pointer;
  font-size:0.6875rem;
}
.debate-log {
  max-height:20rem;
  overflow-y: auto;
  padding:0.75rem;
  background: var(--bg-secondary);
  border-radius:var(--radius-sm);
  margin-top:0.75rem;
  font-family: var(--font-mono);
  font-size:0.75rem;
  line-height:1.7;
}
.debate-line {
  white-space: pre-wrap;
  color: var(--text-secondary);
}
.debate-empty {
  margin-top:0.75rem;
  padding:1.5rem;
  text-align: center;
  color: var(--text-muted);
  font-size:0.8125rem;
}
</style>