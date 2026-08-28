<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

// ── 数据：与 DESIGN.md §2 / src/assets/styles/_variables.css 严格同步 ──
// 应用已全局注入 _variables.css（语义层 --color-* + 兼容别名 --bg-/*/--glass-/*/--border-/*/--text-*），本页只引用，不重定义。
const semantic: [string, string, string, string][] = [
  ['--color-canvas', '#080812', '#f5f6fb', '页面底色'],
  ['--color-surface', 'rgba(255,255,255,0.03)', '#ffffff', '卡片/玻璃表面'],
  ['--color-surface-2', '#0f0f1a', '#eef0f6', '侧栏/输入底'],
  ['--color-surface-hover', 'rgba(255,255,255,0.06)', '#e7eaf3', '悬停表面'],
  ['--color-elevated', '#1c1c2b', '#ffffff', '抬升层(弹层)'],
  ['--color-glass', 'rgba(15,15,26,0.65)', 'rgba(255,255,255,0.72)', '玻璃态底'],
  ['--color-glass-border', 'rgba(255,255,255,0.08)', 'rgba(15,18,40,0.10)', '玻璃态边框'],
  ['--color-border', 'rgba(255,255,255,0.06)', 'rgba(15,18,40,0.10)', '默认边框'],
  ['--color-border-focus', 'rgba(124,106,242,0.45)', 'rgba(124,106,242,0.50)', '聚焦/强调边框'],
  ['--color-text', '#f8fafc', '#1a1d2e', '主文本'],
  ['--color-text-2', '#94a3b8', '#525a72', '次文本'],
  ['--color-text-3', '#7c8aa0', '#8a92a8', '弱文本'],
]
const brand: [string, string, string][] = [
  ['--accent', '#7c6af2', '主色·紫'],
  ['--accent-blue', '#5b8bd8', '辅助·蓝'],
  ['--accent-cyan', '#06b6d4', '青'],
  ['--accent-warm', '#f59e0b', '琥珀'],
  ['--accent-success', '#22c55e', '成功'],
  ['--accent-danger', '#ef4444', '危险'],
  ['--accent-pink', '#f472b6', '粉'],
]
const subjects: [string, string, string][] = [
  ['--subject-ds', '#8b5cf6', '数据结构'],
  ['--subject-cn', '#3b82f6', '计网'],
  ['--subject-co', '#06b6d4', '计组'],
  ['--subject-os', '#f472b6', '操作系统'],
]
const typeScale: [string, string, string, string, string, string][] = [
  ['Display Hero', '32px', '700', '1.1', '-0.8px', '首页 hero 标题'],
  ['H1', '24px', '700', '1.2', '-0.5px', '页面主标题'],
  ['H2 / Section', '20px', '700', '1.3', '-0.3px', '.section-title'],
  ['H3 / Card', '16px', '600', '1.4', '0', '.card-title'],
  ['Body', '14px', '400', '1.6', '0', '正文'],
  ['Body Strong', '14px', '500', '1.6', '0', '标签/强调'],
  ['Caption', '13px', '400', '1.5', '0', '次文本'],
  ['Nano / Label', '12px', '500', '1.4', '0.2px', '徽章/说明'],
]
const spacing: [string, number][] = [
  ['--space-1', 4], ['--space-2', 8], ['--space-3', 12],
  ['--space-4', 16], ['--space-5', 20], ['--space-6', 24], ['--space-8', 32],
]

// ── 主题切换：与 App.vue 完全一致（persist 到 mars408-theme，data-theme 挂 documentElement）──
const theme = ref<'dark' | 'light'>((document.documentElement.dataset.theme as 'dark' | 'light') || 'dark')
const themeLabel = computed(() => (theme.value === 'dark' ? '切换到浅色' : '切换到深色'))
function applyTheme(t: 'dark' | 'light') {
  document.documentElement.dataset.theme = t
  theme.value = t
  try { localStorage.setItem('mars408-theme', t) } catch {}
}
function toggleTheme() {
  applyTheme(theme.value === 'dark' ? 'light' : 'dark')
}
onMounted(() => {
  const t = (document.documentElement.dataset.theme as 'dark' | 'light') || 'dark'
  theme.value = t
})

// ── 右侧抽屉（Vue ref 驱动，不用 getElementById）──
const drawerOpen = ref(false)
function openDrawer() { drawerOpen.value = true }
function closeDrawer() { drawerOpen.value = false }

// swatch chip 背景 = 该 token 的实时值（自动跟随双主题）
function chipStyle(tok: string) {
  return { background: `var(${tok})` }
}
</script>

<template>
  <div class="ds">
    <!-- 顶栏 -->
    <div class="topbar">
      <div class="brandmark">
        <span class="dot"></span>MARS-408 设计系统
        <span class="src-note">v8 · 应用内 Living Style Guide</span>
      </div>
      <button class="theme-toggle" @click="toggleTheme" :title="themeLabel">
        <svg v-if="theme === 'dark'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
        <span>{{ themeLabel }}</span>
      </button>
    </div>

    <div class="wrap">
      <!-- HERO -->
      <div class="hero-band">
        <h1>克制深色 · 玻璃态 · 学科分色</h1>
        <p>MARS-408 前端设计系统 v8。语义化双主题 token，组件只引用 <code>--color-*</code> 语义层，<code>[data-theme="light"]</code> 覆盖即双主题。本页所有元素实时响应右上角主题切换，且与全局导航栏主题键（mars408-theme）完全一致。</p>
        <div class="glass-card">
          <div class="gc-k">GLASSMORPHISM</div>
          <div class="gc-v">backdrop-filter: blur(12px)</div>
          <div class="gc-d">毛玻璃质感 · 低存在感边框</div>
        </div>
      </div>

      <!-- 1. COLOR -->
      <section>
        <div class="sec-head"><span class="idx">01</span><h2>调色板与角色</h2><span class="desc">语义层 · 双主题恒定品牌色 · 408 四科色</span></div>
        <p class="sub">语义层（组件只引用此层；浅色主题自动覆盖）</p>
        <div class="swatches">
          <div v-for="r in semantic" :key="r[0]" class="swatch">
            <div class="chip" :style="chipStyle(r[0])"></div>
            <div class="meta">
              <div class="tok">{{ r[0] }}</div>
              <div class="val">dark: {{ r[1] }}</div>
              <div class="val">light: {{ r[2] }}</div>
              <div class="val" style="color:var(--color-text-2)">{{ r[3] }}</div>
            </div>
          </div>
        </div>
        <p class="sub" style="margin-top:24px;">品牌色（双主题恒定）</p>
        <div class="swatches">
          <div v-for="r in brand" :key="r[0]" class="swatch">
            <div class="chip" :style="chipStyle(r[0])"></div>
            <div class="meta">
              <div class="tok">{{ r[0] }}</div>
              <div class="val">{{ r[1] }}</div>
              <div class="val" style="color:var(--color-text-2)">{{ r[2] }} · 恒定</div>
            </div>
          </div>
        </div>
        <p class="sub" style="margin-top:24px;">408 四科色（语义着色用 color-mix 14% tint）</p>
        <div class="swatches">
          <div v-for="r in subjects" :key="r[0]" class="swatch">
            <div class="chip" :style="chipStyle(r[0])"></div>
            <div class="meta">
              <div class="tok">{{ r[0] }}</div>
              <div class="val">{{ r[1] }}</div>
              <div class="val" style="color:var(--color-text-2)">{{ r[2] }} · 恒定</div>
            </div>
          </div>
        </div>
      </section>

      <!-- 2. TYPOGRAPHY -->
      <section>
        <div class="sec-head"><span class="idx">02</span><h2>排版规则</h2><span class="desc">字号 + 字重 + 负字距建立层级</span></div>
        <div class="type-block">
          <div v-for="r in typeScale" :key="r[0]" class="type-row">
            <div class="lvl">{{ r[0] }}</div>
            <div class="samp" :style="{ 'font-size': r[1], 'font-weight': r[2], 'line-height': r[3], 'letter-spacing': r[4] }">
              MARS-408 个性化学习系统 <span style="font-size:12px;color:var(--color-text-3);font-weight:400;">— {{ r[5] }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 3. BUTTONS -->
      <section>
        <div class="sec-head"><span class="idx">03</span><h2>按钮系统</h2><span class="desc">.btn + 变体 / 尺寸 / 状态</span></div>
        <p class="sub">变体</p>
        <div class="row">
          <button class="btn btn-primary">主操作 Primary</button>
          <button class="btn btn-secondary">次操作 Secondary</button>
          <button class="btn btn-ghost">幽灵 Ghost</button>
          <button class="btn btn-soft">柔和 Soft</button>
          <button class="btn btn-danger">危险 Danger</button>
          <button class="btn btn-primary" disabled>禁用 Disabled</button>
        </div>
        <p class="sub" style="margin-top:20px;">尺寸 + 图标 + 块级</p>
        <div class="row">
          <button class="btn btn-primary btn-sm">小 sm</button>
          <button class="btn btn-primary">中 md</button>
          <button class="btn btn-primary btn-lg">大 lg</button>
          <button class="btn btn-secondary">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>带图标
          </button>
        </div>
        <div style="margin-top:16px;"><button class="btn btn-primary btn-block">块级按钮 .btn-block</button></div>
      </section>

      <!-- 4. CARDS -->
      <section>
        <div class="sec-head"><span class="idx">04</span><h2>卡片与表面</h2><span class="desc">.card / .glass-card / .stat-card</span></div>
        <div class="grid-3">
          <div class="card">
            <div style="font-weight:600;font-size:16px;margin-bottom:8px;">讲解文档</div>
            <div style="font-size:14px;color:var(--color-text-2);">数据结构 · 第 3 章 栈与队列，含可视化推导与易错点标注。</div>
            <div style="margin-top:14px;"><span class="tag tag-purple">数据结构</span></div>
          </div>
          <div class="glass-card">
            <div style="font-weight:600;font-size:16px;margin-bottom:8px;">玻璃态卡片</div>
            <div style="font-size:14px;color:var(--color-text-2);">backdrop-filter 毛玻璃，置于彩色背景上可见模糊质感。</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">87.5%</div>
            <div class="stat-label">本周知识掌握度</div>
            <div class="stat-delta">▲ 4.2% vs 上周</div>
          </div>
        </div>
      </section>

      <!-- 5. INPUTS -->
      <section>
        <div class="sec-head"><span class="idx">05</span><h2>输入控件</h2><span class="desc">聚焦态 / 占位符 / 圆角刻度</span></div>
        <div class="grid-3">
          <div>
            <p class="sub">文本输入</p>
            <input class="ds-input" placeholder="输入问题，如：TCP 三次握手？" />
          </div>
          <div>
            <p class="sub">下拉选择</p>
            <select class="ds-select">
              <option>数据结构</option><option>计算机网络</option><option>计算机组成</option><option>操作系统</option>
            </select>
          </div>
          <div>
            <p class="sub">聚焦态</p>
            <input class="ds-input ds-focus" value="已聚焦（看蓝光边框）" />
          </div>
        </div>
      </section>

      <!-- 6. TAGS -->
      <section>
        <div class="sec-head"><span class="idx">06</span><h2>标签与徽章</h2><span class="desc">.tag-* · color-mix 双主题自适应</span></div>
        <div class="row">
          <span class="tag tag-purple">数据结构</span>
          <span class="tag tag-blue">计网</span>
          <span class="tag tag-cyan">计组</span>
          <span class="tag tag-pink">操作系统</span>
          <span class="tag tag-warm">高亮</span>
          <span class="tag tag-green">已掌握</span>
          <span class="tag tag-primary">主色标签</span>
          <span class="tag tag-danger">校验失败</span>
        </div>
      </section>

      <!-- 7. NAV -->
      <section>
        <div class="sec-head"><span class="idx">07</span><h2>导航项</h2><span class="desc">.nav-item · 活跃态 + 学科色激活</span></div>
        <div style="max-width:320px;display:flex;flex-direction:column;gap:4px;">
          <div class="nav-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>仪表盘</div>
          <div class="nav-item active"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>智能对话</div>
          <div class="nav-item active nav-subject-0"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>数据结构</div>
          <div class="nav-item active nav-subject-1"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>计算机网络</div>
        </div>
      </section>

      <!-- 8. SHADOWS -->
      <section>
        <div class="sec-head"><span class="idx">08</span><h2>深度与阴影</h2><span class="desc">--shadow-* 刻度 · 彩色微光</span></div>
        <div class="shadow-demo">
          <div class="shadow-box" style="box-shadow:var(--shadow-sm);">shadow-sm</div>
          <div class="shadow-box" style="box-shadow:var(--shadow-md);">shadow-md</div>
          <div class="shadow-box" style="box-shadow:var(--shadow-lg);">shadow-lg</div>
          <div class="shadow-box" style="box-shadow:var(--shadow-xl);">shadow-xl</div>
          <div class="shadow-box" style="box-shadow:var(--shadow-card);">shadow-card</div>
          <div class="shadow-box" style="box-shadow:var(--shadow-glow);">shadow-glow</div>
        </div>
      </section>

      <!-- 9. SPACING + RADIUS -->
      <section>
        <div class="sec-head"><span class="idx">09</span><h2>间距与圆角</h2><span class="desc">4px 基数 · 4 倍数刻度</span></div>
        <div class="grid-3">
          <div class="card">
            <p class="sub">间距刻度（4 倍数）</p>
            <div class="spacing-demo">
              <div v-for="s in spacing" :key="s[0]" class="space-bar" :style="{ width: s[1] + 'px', height: (s[1] * 3) + 'px' }">{{ s[1] }}</div>
            </div>
          </div>
          <div class="card">
            <p class="sub">圆角刻度</p>
            <div class="row">
              <div style="text-align:center;"><div style="width:56px;height:56px;background:var(--accent-primary-10);border:1px solid var(--color-border-focus);border-radius:var(--radius-xs);"></div><div style="font-size:11px;color:var(--color-text-3);margin-top:6px;font-family:var(--font-mono);">xs 6</div></div>
              <div style="text-align:center;"><div style="width:56px;height:56px;background:var(--accent-primary-10);border:1px solid var(--color-border-focus);border-radius:var(--radius-sm);"></div><div style="font-size:11px;color:var(--color-text-3);margin-top:6px;font-family:var(--font-mono);">sm 10</div></div>
              <div style="text-align:center;"><div style="width:56px;height:56px;background:var(--accent-primary-10);border:1px solid var(--color-border-focus);border-radius:var(--radius-md);"></div><div style="font-size:11px;color:var(--color-text-3);margin-top:6px;font-family:var(--font-mono);">md 14</div></div>
              <div style="text-align:center;"><div style="width:56px;height:56px;background:var(--accent-primary-10);border:1px solid var(--color-border-focus);border-radius:var(--radius-lg);"></div><div style="font-size:11px;color:var(--color-text-3);margin-top:6px;font-family:var(--font-mono);">lg 18</div></div>
              <div style="text-align:center;"><div style="width:56px;height:56px;background:var(--accent-primary-10);border:1px solid var(--color-border-focus);border-radius:var(--radius-full);"></div><div style="font-size:11px;color:var(--color-text-3);margin-top:6px;font-family:var(--font-mono);">full</div></div>
            </div>
          </div>
          <div class="card">
            <p class="sub">模态 / 抽屉</p>
            <button class="btn btn-secondary" @click="openDrawer">打开右侧抽屉 →</button>
            <p style="font-size:13px;color:var(--color-text-2);margin-top:12px;">.panel-overlay（遮罩 blur 4px）+ .demo-panel（玻璃态 blur 20px，宽 400px，slide-in）。</p>
          </div>
        </div>
      </section>

      <footer>
        MARS-408 设计系统 v8 · 单源真理 <code>DESIGN.md</code> 与 <code>src/assets/styles/_variables.css</code> · AI 可读，供 Cursor / Claude Code / Google Stitch 直接消费。<br/>
        本页为应用内正式路由页，所有 token 直接引用全局 <code>_variables.css</code>；切换右上角主题可见全部元素实时双主题渲染，且与全局导航主题键（mars408-theme）一致。
      </footer>
    </div>

    <!-- 抽屉 -->
    <div class="panel-overlay" :class="{ open: drawerOpen }" @click="closeDrawer"></div>
    <div class="demo-panel" :class="{ open: drawerOpen }">
      <h3>右侧滑出抽屉</h3>
      <p>这是 .demo-panel 玻璃态抽屉示例。遮罩 .panel-overlay 使用 blur(4px) + 半透明 overlay，内容区 backdrop-filter 20px 毛玻璃。</p>
      <div style="margin-top:20px;"><button class="btn btn-primary btn-block" @click="closeDrawer">关闭</button></div>
    </div>
  </div>
</template>

<style scoped>
/* ============================================================
   BASE（仅组件样式；token 全部来自全局 _variables.css）
   ============================================================ */
.ds { min-height:100%; background: var(--color-canvas); color: var(--color-text); }
* { box-sizing: border-box; }
.ds :deep(code) { font-family: var(--font-mono); font-size:0.92em; background: var(--color-surface-hover); padding:0.0625rem 0.375rem; border-radius:var(--radius-xs); color: var(--accent-primary); }

.topbar {
  position: sticky; top: 0; z-index: 100;
  display: flex; align-items: center; justify-content: space-between;
  padding:0.875rem var(--space-8);
  background: var(--color-glass); backdrop-filter: blur(var(--glass-blur-heavy));
  border-bottom: 1px solid var(--color-glass-border);
}
.brandmark { display: flex; align-items: center; gap:0.75rem; font-weight: 700; font-size:1rem; }
.brandmark .dot { width: 12px; height: 12px; border-radius: var(--radius-full); background: var(--gradient-primary); box-shadow: var(--glow-primary); }
.src-note { font-size:0.75rem; color: var(--color-text-3); font-weight: 500; }
.theme-toggle {
  display: inline-flex; align-items: center; gap:0.5rem;
  padding:0.5rem 0.875rem; border-radius:var(--radius-full);
  border: 1px solid var(--color-border); background: var(--color-surface-hover);
  color: var(--color-text); font-size:0.8125rem; font-weight: 600; cursor: pointer;
  transition: var(--transition);
}
.theme-toggle:hover { border-color: var(--color-border-focus); }
.theme-toggle svg { width:1rem; height:1rem; }

.wrap { max-width:75rem; margin:0 auto; padding:var(--space-6) var(--space-8); font-family: var(--font-sans); line-height:1.6; }

section { margin-top:var(--space-8); }
.sec-head { display: flex; align-items: baseline; gap:0.75rem; margin-bottom:var(--space-5); border-bottom: 1px solid var(--color-border); padding-bottom:var(--space-3); }
.sec-head h2 { font-size:1.25rem; font-weight: 700; letter-spacing:-0.0187rem; }
.sec-head .idx { font-family: var(--font-mono); font-size:0.8125rem; color: var(--accent-primary); font-weight: 700; }
.sec-head .desc { font-size:0.8125rem; color: var(--color-text-3); margin-left:auto; }
.sub { font-size:0.8125rem; color: var(--color-text-2); margin-bottom:var(--space-4); }

/* ── 组件样式：与 DESIGN.md §4 同步 ── */
.btn { display: inline-flex; align-items: center; justify-content: center; gap:0.5rem;
  font-size:0.875rem; font-weight: 600; line-height:1; padding:0.625rem 1.25rem;
  border-radius:var(--radius-md); border: 1px solid transparent; cursor: pointer;
  transition: var(--transition); font-family: var(--font-sans); }
.btn svg { width:1rem; height:1rem; }
.btn-primary { background: var(--gradient-primary); color: var(--text-user); }
.btn-primary:hover { opacity: 0.92; transform: translateY(-1px); box-shadow: var(--shadow-card-hover); }
.btn-secondary { background: var(--color-surface-hover); color: var(--color-text); border-color: var(--color-border); }
.btn-secondary:hover { background: var(--color-surface-2); border-color: var(--color-border-focus); }
.btn-ghost { background: transparent; color: var(--color-text-2); }
.btn-ghost:hover { background: var(--color-surface-hover); color: var(--color-text); }
.btn-soft { background: var(--accent-primary-10); color: var(--accent-primary); }
.btn-soft:hover { background: var(--accent-primary-20); }
.btn-danger { background: var(--accent-danger-10); color: var(--accent-danger); }
.btn-danger:hover { background: var(--accent-danger-20); }
.btn-sm { padding:0.4375rem 0.875rem; font-size:0.8125rem; border-radius:var(--radius-sm); }
.btn-lg { padding:0.8125rem 1.75rem; font-size:0.9375rem; }
.btn-block { width:100%; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

.card, .glass-card, .stat-card {
  padding:1.25rem; border-radius:var(--radius-lg);
  background: var(--color-surface); border: 1px solid var(--color-border);
  box-shadow: var(--shadow-card); transition: var(--transition);
}
.card:hover, .stat-card:hover {
  border-color: transparent; transform: scale(1.02);
  box-shadow: var(--shadow-card-hover), 0 0 0 1px color-mix(in srgb, var(--accent-primary) 15%, transparent);
}
.glass-card { background: var(--color-glass); backdrop-filter: blur(var(--glass-blur)); border-color: var(--color-glass-border); }
.stat-card { position: relative; overflow: hidden; }
.stat-card::before { content: ''; position: absolute; top:0; left:0; right:0; height:0.1875rem; background: var(--gradient-progress); }
.stat-value { font-size:1.875rem; font-weight: 700; letter-spacing:-0.0312rem; font-family: var(--font-mono); }
.stat-label { font-size:0.75rem; color: var(--color-text-3); font-weight: 500; letter-spacing:0.0125rem; margin-top:0.25rem; }
.stat-delta { font-size:0.75rem; font-weight: 600; color: var(--accent-success); margin-top:0.5rem; }

.ds-input, .ds-select {
  background: var(--bg-input); border: 1px solid var(--color-border);
  border-radius:var(--radius-md); padding:0.625rem 0.875rem; color: var(--color-text);
  font-size:0.875rem; transition: var(--transition); font-family: var(--font-sans); width:100%;
}
.ds-input:focus, .ds-select:focus { outline: none; border-color: var(--color-border-focus); box-shadow: 0 0 0 3px var(--accent-primary-10); }
.ds-input::placeholder { color: var(--color-text-3); }
.ds-focus { border-color: var(--color-border-focus); box-shadow: 0 0 0 3px var(--accent-primary-10); }

.nav-item { position: relative; display: flex; align-items: center; gap:0.75rem; padding:0.6875rem 0.75rem;
  border-radius:var(--radius-sm); color: var(--color-text-2); font-size:0.875rem; font-weight: 500; cursor: pointer; transition: var(--transition); }
.nav-item:hover { background: var(--color-surface-hover); color: var(--color-text); }
.nav-item.active { background: var(--accent-primary-10); color: var(--accent-primary); }
.nav-item.active::before { content: ''; position: absolute; left: 0; top: 50%; transform: translateY(-50%);
  width: 3px; height: 18px; border-radius: 0 3px 3px 0; background: var(--gradient-primary); box-shadow: var(--glow-primary-strong); }
.nav-item.active.nav-subject-0 { background: color-mix(in srgb, var(--subject-ds) 14%, transparent); color: var(--subject-ds); }
.nav-item.active.nav-subject-1 { background: color-mix(in srgb, var(--subject-cn) 14%, transparent); color: var(--subject-cn); }
.nav-item.active.nav-subject-2 { background: color-mix(in srgb, var(--subject-co) 14%, transparent); color: var(--subject-co); }
.nav-item.active.nav-subject-3 { background: color-mix(in srgb, var(--subject-os) 14%, transparent); color: var(--subject-os); }
.nav-item svg { width:1.125rem; height:1.125rem; }

.tag { display: inline-flex; align-items: center; padding:0.25rem 0.625rem; border-radius:var(--radius-full); font-size:0.75rem; font-weight: 600; }
.tag-purple { background: color-mix(in srgb, var(--subject-ds) 14%, transparent); color: var(--subject-ds); }
.tag-blue   { background: color-mix(in srgb, var(--subject-cn) 14%, transparent); color: var(--subject-cn); }
.tag-cyan   { background: color-mix(in srgb, var(--subject-co) 14%, transparent); color: var(--subject-co); }
.tag-pink   { background: color-mix(in srgb, var(--subject-os) 14%, transparent); color: var(--subject-os); }
.tag-warm   { background: color-mix(in srgb, var(--accent-warm) 14%, transparent); color: var(--accent-warm); }
.tag-green  { background: color-mix(in srgb, var(--accent-success) 14%, transparent); color: var(--accent-success); }
.tag-primary { background: var(--accent-primary-10); color: var(--accent-primary); }
.tag-danger { background: var(--accent-danger-10); color: var(--accent-danger); }

/* ── 布局辅助 ── */
.grid-3 { display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; }
.row { display: flex; flex-wrap: wrap; gap:0.75rem; align-items: center; }
.swatches { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px,1fr)); gap: 12px; }
.swatch { border-radius:var(--radius-md); border: 1px solid var(--color-border); overflow: hidden; background: var(--color-surface); }
.swatch .chip { height:4rem; }
.swatch .meta { padding:0.625rem 0.75rem; }
.swatch .tok { font-family: var(--font-mono); font-size:0.75rem; font-weight: 600; color: var(--color-text); }
.swatch .val { font-family: var(--font-mono); font-size:0.6875rem; color: var(--color-text-3); margin-top:0.1875rem; }
.type-block { display: flex; flex-direction: column; }
.type-row { display: flex; align-items: baseline; gap:1.25rem; padding:0.875rem 0; border-bottom: 1px solid var(--color-border); }
.type-row .lvl { width:10rem; flex: none; font-size:0.75rem; font-weight: 600; color: var(--accent-primary); font-family: var(--font-mono); }
.type-row .samp { flex: 1; }
.shadow-demo { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px,1fr)); gap: 24px; }
.shadow-box { height:5.625rem; border-radius:var(--radius-md); background: var(--color-surface); border: 1px solid var(--color-border); display: flex; align-items: center; justify-content: center; font-size:0.75rem; color: var(--color-text-3); font-family: var(--font-mono); }
.hero-band { position: relative; border-radius:var(--radius-xl); padding:3rem; overflow: hidden; background: var(--gradient-hero); border: 1px solid var(--color-glass-border); }
.hero-band h1 { font-size:2rem; font-weight: 700; letter-spacing:-0.05rem; background: var(--gradient-text); -webkit-background-clip: text; background-clip: text; color: transparent; }
.hero-band p { color: var(--color-text-2); margin-top:0.75rem; max-width:32.5rem; }
.hero-band .glass-card { position: absolute; right: 48px; top: 50%; transform: translateY(-50%); width: 280px; padding: 20px; border-radius: var(--radius-lg); background: var(--color-glass); backdrop-filter: blur(var(--glass-blur)); border: 1px solid var(--color-glass-border); box-shadow: var(--shadow-card); }
.gc-k { font-size:0.75rem; color: var(--color-text-3); font-weight: 600; letter-spacing:0.0125rem; }
.gc-v { font-size:1.125rem; font-weight: 700; margin-top:0.375rem; }
.gc-d { font-size:0.8125rem; color: var(--color-text-2); margin-top:0.375rem; }
.spacing-demo { display: flex; align-items: flex-end; gap:0.5rem; }
.space-bar { background: var(--accent-primary-20); border: 1px solid var(--color-border-focus); border-radius:var(--radius-xs); display: flex; align-items: flex-start; justify-content: center; font-size:0.625rem; color: var(--accent-primary); font-family: var(--font-mono); padding-top:0.125rem; }
footer { margin-top:var(--space-8); padding-top:var(--space-5); border-top: 1px solid var(--color-border); font-size:0.8125rem; color: var(--color-text-3); }

/* ── 抽屉 ── */
.panel-overlay { position: fixed; inset: 0; background: var(--color-overlay); z-index: 900; opacity: 0; pointer-events: none; transition: var(--transition-slow); backdrop-filter: blur(4px); }
.panel-overlay.open { opacity: 1; pointer-events: auto; }
.demo-panel { position: fixed; top: 0; right: 0; bottom: 0; width: 400px; max-width: 90vw; z-index: 950; transform: translateX(100%); transition: transform var(--duration-slow) cubic-bezier(0.4,0,0.2,1); background: var(--color-glass); backdrop-filter: blur(var(--glass-blur-heavy)); border-left: 1px solid var(--color-glass-border); box-shadow: var(--shadow-xl); padding: 24px; }
.demo-panel.open { transform: translateX(0); }
.demo-panel h3 { font-size:1.25rem; font-weight: 700; margin-bottom:0.5rem; }
.demo-panel p { font-size:0.875rem; color: var(--color-text-2); }

/* ── 响应式 ── */
@media (max-width: 1024px) {
  .grid-3 { grid-template-columns: repeat(2,1fr); }
  .hero-band .glass-card { position: static; transform: none; margin-top: 24px; width: 100%; }
  .wrap { padding:var(--space-5) var(--space-4); }
  .topbar { padding:0.75rem var(--space-4); }
}
@media (max-width: 480px) {
  .grid-3 { grid-template-columns: 1fr; }
  .sec-head .desc { display: none; }
}
</style>
