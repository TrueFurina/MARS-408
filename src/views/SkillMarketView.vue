<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { icons } from '@/components/icons'
import Skeleton from '@/components/Skeleton.vue'
import EmptyState from '@/components/EmptyState.vue'
import SkillCard from '@/components/SkillCard.vue'
import { useSkillStore, type SkillItem } from '@/stores/skillStore'
import { api } from '@/utils/api'

const router = useRouter()
const store = useSkillStore()

const searchQuery = ref('')
const selectedCategory = ref('')
const sortBy = ref('usage_count')
let searchTimer: ReturnType<typeof setTimeout> | null = null

function debouncedSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => doSearch(), 300)
}

const categories = [
  { value: '', label: '全部' },
  { value: 'teaching', label: '教学讲解' },
  { value: 'quiz', label: '出题练习' },
  { value: 'diagnosis', label: '诊断评估' },
  { value: 'guide', label: '学习引导' },
  { value: 'code', label: '代码实践' },
  { value: 'mindmap', label: '思维导图' },
  { value: 'other', label: '其他' },
]

const sortOptions = [
  { value: 'usage_count', label: '最热门' },
  { value: 'avg_rating', label: '评分最高' },
  { value: 'updated_at', label: '最新发布' },
  { value: 'name', label: '名称排序' },
]

const showMySkills = ref(false)
const showMyDrafts = ref(false)
const showFavorites = ref(false)
const favoritesList = ref<SkillItem[]>([])

const displayItems = computed(() => {
  if (showFavorites.value) return favoritesList.value
  if (showMySkills.value) {
    if (showMyDrafts.value) return store.mySkills
    return store.mySkills.filter(s => s.status === 'published')
  }
  return store.marketItems
})

const displayTotal = computed(() => {
  if (showFavorites.value) return favoritesList.value.length
  if (showMySkills.value) return store.mySkillsTotal
  return store.marketTotal
})

function doSearch() {
  if (showMySkills.value || showFavorites.value) return
  store.fetchMarket({
    search: searchQuery.value || undefined,
    category: selectedCategory.value || undefined,
    sort_by: sortBy.value,
  })
}

function goToDrafts() {
  showMyDrafts.value = true
  showMySkills.value = true
  showFavorites.value = false
  store.fetchMySkills({ status: 'draft' })
}

function goSkill(id: string) {
  router.push(`/skills/${id}`)
}

function goCreate() {
  router.push('/studio')
}

function goEdit(id: string) {
  router.push(`/studio/${id}`)
}

function switchToMySkills() {
  showMySkills.value = true
  store.fetchMySkills()
}

function switchToMarket() {
  showMySkills.value = false
  showMyDrafts.value = false
  showFavorites.value = false
  doSearch()
}

async function switchToFavorites() {
  showMySkills.value = false
  showMyDrafts.value = false
  showFavorites.value = true
  try {
    const res: any = await api.get('/skills/favorites')
    favoritesList.value = res.items || []
  } catch { favoritesList.value = [] }
}

onMounted(async () => {
  await Promise.all([
    store.fetchMarket({ sort_by: sortBy.value }),
    store.fetchTemplates(),
    store.fetchOfficial(),
  ])
  loadMemoryOverview()
})

// L1/L2/L3 三层学情记忆（低侵入联动：技能市场页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞技能市场页 */ }
}
</script>

<template>
  <div class="page-section">
    <div class="section-header">
      <div class="section-title-group">
        <div class="section-title" v-html="icons.skill"></div>
        <div>
          <div class="section-title">AI 技能市场</div>
          <div class="section-desc">发现、创建和分享 AI 教学技能</div>
        </div>
      </div>
      <div class="section-actions">
        <button class="btn btn-primary" @click="goCreate">
          <span v-html="icons.plus"></span> 创建技能
        </button>
      </div>
    </div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 记忆薄弱点:</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
    </div>

    <!-- 切换 Tab -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: !showMySkills && !showFavorites }" @click="switchToMarket">🎪 市场</button>
      <button class="tab-btn" :class="{ active: showMySkills && !showMyDrafts }" @click="switchToMySkills">📦 我的技能</button>
      <button class="tab-btn" :class="{ active: showMyDrafts }" @click="goToDrafts">📝 草稿箱</button>
      <button class="tab-btn" :class="{ active: showFavorites }" @click="switchToFavorites">⭐ 收藏</button>
    </div>

    <!-- 搜索 & 过滤栏 -->
    <div class="search-bar">
      <div class="search-input-wrap">
        <span v-html="icons.search" class="search-icon"></span>
        <input
          v-model="searchQuery"
          class="search-input"
          placeholder="搜索技能名称或描述..."
          @input="debouncedSearch"
        />
      </div>
      <select v-model="selectedCategory" class="filter-select" @change="doSearch">
        <option v-for="c in categories" :key="c.value" :value="c.value">{{ c.label }}</option>
      </select>
      <select v-model="sortBy" class="filter-select" @change="doSearch">
        <option v-for="s in sortOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
      </select>
    </div>

    <!-- 官方技能横幅 -->
    <div v-if="!showMySkills && store.officialSkills.length" class="official-banner">
      <div class="official-title">⭐ 官方推荐</div>
      <div class="official-list">
        <SkillCard
          v-for="s in store.officialSkills.slice(0, 4)"
          :key="s.id"
          :skill="s"
          compact
          @click="goSkill"
        />
      </div>
    </div>

    <!-- 技能列表 -->
    <div v-if="store.loading" class="skeleton-grid-auto">
      <Skeleton v-for="i in 6" :key="i" variant="card" />
    </div>
    <div v-else-if="store.error" class="engine-error">{{ store.error }}</div>
    <EmptyState v-else-if="displayItems.length === 0" :icon="icons.skill" title="暂无技能" :description="showMySkills ? '你还没有创建过技能，点击上方「创建技能」开始吧' : '没有找到匹配的技能'" />
    <div v-else class="skill-grid">
      <SkillCard
        v-for="skill in displayItems"
        :key="skill.id"
        :skill="skill"
        @click="goSkill"
      />
    </div>
  </div>
</template>

<style scoped>
.section-header { display: flex; justify-content: space-between; align-items: flex-start; gap:1rem; flex-wrap: wrap; }
.section-title-group { display: flex; align-items: center; gap:0.75rem; }
.section-title-group :deep(svg) { width:2rem; height:2rem; color: var(--accent); }
.section-actions { display: flex; gap:0.5rem; }

.tab-bar { display: flex; gap:0.25rem; margin:1rem 0; background: var(--color-surface-2); border-radius:0.625rem; padding:0.25rem; }
.tab-btn { flex: 1; padding:0.5rem 1rem; border: none; border-radius:0.5rem; background: transparent; color: var(--color-text-2); font-size:0.875rem; font-weight: 500; cursor: pointer; transition: all 0.2s; }
.tab-btn.active { background: var(--color-elevated); color: var(--color-text); box-shadow: 0 1px 4px rgba(0,0,0,0.2); }
.tab-btn:hover:not(.active) { color: var(--color-text); }

.search-bar { display: flex; gap:0.5rem; margin-bottom:1rem; flex-wrap: wrap; }
.search-input-wrap { flex: 1; min-width:12.5rem; position: relative; display: flex; align-items: center; }
.search-icon { position: absolute; left:0.75rem; width:1.125rem; height:1.125rem; color: var(--color-text-3); }
.search-input { width:100%; padding:0.625rem 0.75rem 0.625rem 2.375rem; border: 1px solid var(--color-border); border-radius:0.5rem; background: var(--color-surface-2); color: var(--color-text); font-size:0.875rem; }
.search-input:focus { outline: none; border-color: var(--color-border-focus); }
.filter-select { padding: 10px 12px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface-2); color: var(--color-text); font-size: 14px; cursor: pointer; }

.official-banner { margin-bottom:1rem; padding:1rem; border-radius:0.75rem; background: linear-gradient(135deg, rgba(124,106,242,0.08), rgba(6,182,212,0.08)); border: 1px solid var(--color-border-focus); }
.official-title { font-size:0.875rem; font-weight: 600; color: var(--accent); margin-bottom:0.75rem; }
.official-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }

.skill-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
</style>