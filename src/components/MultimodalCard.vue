<template>
  <div class="multimodal-card">
    <!-- 教学插图 -->
    <div v-if="imageUrl || imageSvg" class="mm-image-section">
      <div class="mm-label">🎨 AI 教学插图</div>
      <div class="mm-image-wrapper">
        <img v-if="imageUrl" :src="imageUrl" alt="教学插图" class="mm-image" />
        <div v-else-if="imageSvg" v-html="imageSvg" class="mm-svg-container"></div>
      </div>
      <div class="mm-source-tag" :class="{ 'real': isRealImage }">
        {{ isRealImage ? '讯飞星火TTI 生成' : 'AI概念图（SVG）' }}
      </div>
    </div>

    <!-- 语音旁白 -->
    <div v-if="audioUrl || audioFallbackText" class="mm-audio-section">
      <div class="mm-label">🔊 语音旁白</div>
      <audio v-if="audioUrl" :src="audioUrl" controls class="mm-audio-player"></audio>
      <div v-else class="mm-tts-fallback">
        <button @click="speak" :disabled="isSpeaking" class="mm-speak-btn">
          {{ isSpeaking ? '⏸ 正在朗读...' : '▶ 朗读内容' }}
        </button>
        <button v-if="isSpeaking" @click="stopSpeak" class="mm-stop-btn">⏹ 停止</button>
        <span class="mm-tts-source">浏览器语音引擎</span>
      </div>
    </div>

    <!-- 生成中状态 -->
    <div v-if="loading" class="mm-loading">
      <Skeleton variant="block" height="7rem" radius="var(--radius-md)" />
      <span class="mm-loading-text">正在生成多模态内容...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import Skeleton from '@/components/Skeleton.vue'

const props = defineProps<{
  imageBase64?: string | null
  imageSvg?: string | null
  audioBase64?: string | null
  audioFallbackText?: string | null
  imageSource?: string
  audioSource?: string
  loading?: boolean
}>()

const isSpeaking = ref(false)

const imageUrl = computed(() => {
  if (props.imageBase64) return `data:image/jpeg;base64,${props.imageBase64}`
  return null
})

const isRealImage = computed(() => props.imageSource === 'xfyun')

const audioUrl = computed(() => {
  if (props.audioBase64) return `data:audio/mp3;base64,${props.audioBase64}`
  return null
})

// 浏览器 Web Speech API 朗读
const speak = () => {
  if (!props.audioFallbackText || !('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(props.audioFallbackText)
  utterance.lang = 'zh-CN'
  utterance.rate = 1.0
  utterance.onend = () => { isSpeaking.value = false }
  utterance.onerror = () => { isSpeaking.value = false }
  isSpeaking.value = true
  window.speechSynthesis.speak(utterance)
}

const stopSpeak = () => {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel()
    isSpeaking.value = false
  }
}

onUnmounted(() => stopSpeak())
</script>

<style scoped>
.multimodal-card {
  display: flex;
  flex-direction: column;
  gap:1rem;
}

.mm-image-section, .mm-audio-section {
  background: color-mix(in srgb, var(--accent-primary) 8%, var(--color-surface));
  border: 1px solid color-mix(in srgb, var(--accent-primary) 16%, transparent);
  border-radius:var(--radius-md);
  padding:1rem;
}

.mm-label {
  font-size:0.875rem;
  font-weight: 600;
  margin-bottom:0.75rem;
  color: var(--text-primary);
}

.mm-image-wrapper {
  display: flex;
  justify-content: center;
  border-radius:var(--radius-sm);
  overflow: hidden;
}

.mm-image {
  max-width:100%;
  border-radius:var(--radius-sm);
  box-shadow: var(--shadow-md);
}

.mm-svg-container {
  width:100%;
  display: flex;
  justify-content: center;
}

.mm-svg-container :deep(svg) {
  max-width:25rem;
  height:auto;
  border-radius:var(--radius-sm);
}

.mm-source-tag {
  margin-top:0.5rem;
  font-size:0.75rem;
  text-align: right;
  color: var(--text-secondary);
}

.mm-source-tag.real {
  /* 用主题感知的 --text-success：深色=#22c55e，浅色=#15803d；
     原 --accent-success 在浅色白底上对比度≈1.9:1(AA 不及格)且显色偏，
     浅色主题下读成"褪色/串色"。 */
  color: var(--text-success);
}

.mm-audio-player {
  width:100%;
  height:2.25rem;
}

.mm-tts-fallback {
  display: flex;
  align-items: center;
  gap:0.75rem;
  flex-wrap: wrap;
}

.mm-speak-btn, .mm-stop-btn {
  padding:0.5rem 1.25rem;
  border: none;
  border-radius:var(--radius-sm);
  font-size:0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.mm-speak-btn {
  background: var(--accent-primary);
  color: var(--text-user);
}

.mm-speak-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px var(--accent-primary-20);
}

.mm-speak-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.mm-stop-btn {
  background: var(--accent-danger-20);
  color: var(--text-danger);
  border: 1px solid var(--accent-danger-20);
}

.mm-tts-source {
  font-size:0.75rem;
  color: var(--text-secondary);
}

.mm-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap:0.75rem;
  padding:1.25rem;
  color: var(--text-secondary);
  font-size:0.875rem;
}
.mm-loading-text { color: var(--text-muted); }
</style>
