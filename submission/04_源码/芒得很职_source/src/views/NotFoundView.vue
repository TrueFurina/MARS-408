<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="page-section" style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:60vh;gap:16px;">
    <div style="font-size:64px;font-weight:800;background:var(--gradient-primary);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">404</div>
    <div style="font-size:20px;color:var(--text-primary);font-weight:600;">页面不存在</div>
    <div style="font-size:14px;color:var(--text-muted);max-width:400px;text-align:center;">你访问的页面路径有误，请检查链接或返回首页</div>
    <button class="engine-btn" @click="router.push('/')">返回首页</button>
  </div>
</template>

<style scoped>
.engine-btn {
  padding:0.625rem 1.5rem;
  border-radius:var(--radius-full);
  border: none;
  background: var(--gradient-primary);
  color: var(--text-user);
  font-size:0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition-bounce);
}
.engine-btn:hover {
  transform: translateY(-2px) scale(1.02);
  box-shadow: var(--glow-primary);
}
</style>
