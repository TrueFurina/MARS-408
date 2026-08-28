<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  html: string
  title?: string
}>()

const emit = defineEmits<{
  close: []
}>()

const iframeRef = ref<HTMLIFrameElement | null>(null)
const loaded = ref(false)

function getIframeHtml(): string {
  return props.html || '<div style="display:flex;align-items:center;justify-content:center;height:100%;background:var(--color-canvas);color:var(--color-text-2);font-size:16px;">暂无视频内容</div>'
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  // 等待 iframe 加载
  if (iframeRef.value) {
    iframeRef.value.onload = () => { loaded.value = true }
  }
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <div class="video-overlay" @click.self="emit('close')" role="dialog" aria-modal="true" :aria-label="'视频播放器: ' + (title || '教学视频')">
      <div class="video-player">
        <div class="video-header">
          <span class="video-title">🎬 {{ title || '教学视频' }}</span>
          <div class="video-actions">
            <button class="video-btn" @click="emit('close')" title="关闭 (Esc)" aria-label="关闭视频">✕</button>
          </div>
        </div>
        <div class="video-body">
          <div v-if="!loaded" class="video-loading">
            <div class="loading-spinner"></div>
            <div class="loading-text">加载视频中...</div>
          </div>
          <iframe
            v-show="loaded"
            ref="iframeRef"
            class="video-iframe"
            :srcdoc="getIframeHtml()"
            sandbox="allow-scripts allow-same-origin"
            frameborder="0"
          ></iframe>
        </div>
        <div class="video-footer">
          <span class="video-hint">◀ ▶ 方向键翻页 · Space 播放/暂停 · Esc 关闭</span>
          <button class="btn btn-sm btn-primary" @click="emit('close')">关闭</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.video-overlay {
  position: fixed;
  inset: 0;
  background: var(--color-overlay);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fade-in 0.2s ease;
}
.video-player {
  width: 90%;
  max-width: 1100px;
  height: 85vh;
  background: var(--color-canvas);
  border: 1px solid var(--color-glass-border);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: var(--shadow-xl);
}
.video-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.video-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
}
.video-actions {
  display: flex;
  gap: 8px;
}
.video-btn {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  border: 1px solid var(--color-glass-border);
  background: transparent;
  color: var(--color-text-2);
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.video-btn:hover {
  background: color-mix(in srgb, var(--accent-primary) 15%, transparent);
  color: var(--accent);
  border-color: var(--accent);
}
.video-body {
  flex: 1;
  position: relative;
  overflow: hidden;
}
.video-iframe {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
}
.video-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
.loading-spinner {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 3px solid color-mix(in srgb, var(--accent-primary) 15%, transparent);
  border-top-color: var(--accent);
  animation: spin 0.7s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.loading-text {
  font-size: 14px;
  color: var(--color-text-2);
}
.video-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
}
.video-hint {
  font-size: 12px;
  color: var(--color-text-3);
}
@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* 移动端适配 */
@media (max-width: 768px) {
  .video-player { width: 100%; height: 100vh; max-height: 100vh; border-radius: 0; }
  .video-header { padding: 10px 14px; }
  .video-footer { padding: 8px 14px; }
  .video-hint { display: none; }
}
</style>