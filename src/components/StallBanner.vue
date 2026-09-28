<script setup lang="ts">
import { useStallClock } from '@/composables/useStallClock'

const props = defineProps<{ loading: boolean; lastEventAt: number }>()
const { stalled, stalledSec } = useStallClock(() => props.loading, () => props.lastEventAt)
</script>

<template>
  <div v-if="stalled" class="rv-mon-stall">
    流水线已 {{ stalledSec }} 秒未推送新进展，可能是后端繁忙或连接中断。仍在等待中，可继续稍候或重新生成。
  </div>
</template>
