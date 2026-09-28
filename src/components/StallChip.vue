<script setup lang="ts">
import { useStallClock } from '@/composables/useStallClock'

const props = defineProps<{ loading: boolean; lastEventAt: number }>()
const { stalled, stalledSec } = useStallClock(() => props.loading, () => props.lastEventAt)
</script>

<template>
  <span v-if="stalled" class="rv-mon-chip is-warn">已 {{ stalledSec }}s 无进展</span>
</template>
