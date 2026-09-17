/**
 * 场景状态 —— 双场景集成（2026-09-15）
 *
 * 平台含两个业务场景：
 *   · kaoyan —— 场景A 专业能力训练（考研408）
 *   · career —— 场景B 职业素养实训（芒得很职主线）
 *
 * 当前场景由本 composable 统一持有，持久化到 localStorage['mars408_scene']，
 * 供 App.vue 侧栏导航过滤（visibleGroups(role, scene)）与场景切换控件使用。
 *
 * 注意：navConfig 的 Scene 类型含 'common'（表示"两场景通用"），
 * 但 'common' 不是可切换值 —— 可切换集合见 SELECTABLE_SCENES。
 */
import { ref, computed } from 'vue'
import type { Scene } from '@/router/navConfig'

const STORAGE_KEY = 'mars408_scene'

/** 可切换的场景值（不含 common） */
export const SELECTABLE_SCENES = ['kaoyan', 'career'] as const
export type SelectableScene = (typeof SELECTABLE_SCENES)[number]

/** 场景展示元数据（切换控件用） */
export const SCENE_META: Record<SelectableScene, { label: string; sub: string; route: string }> = {
  kaoyan: { label: '专业能力训练', sub: '考研408智能学习', route: '/kaoyan' },
  career: { label: '职业素养实训', sub: 'AI 对抗式能力训练', route: '/career/training' },
}

function readStored(): SelectableScene {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'kaoyan' || v === 'career') return v
  } catch { /* localStorage 不可用（隐私模式等）时静默降级 */ }
  return 'career' // 默认主推职业素养（芒得很职主线）
}

// 模块级单例：多处调用共享同一状态（与 Pinia store 等价，避免为一项 UI 状态引入新 store）
const currentScene = ref<SelectableScene>(readStored())

export function useScene() {
  function setScene(scene: SelectableScene) {
    currentScene.value = scene
    try { localStorage.setItem(STORAGE_KEY, scene) } catch { /* */ }
  }

  function toggleScene() {
    setScene(currentScene.value === 'kaoyan' ? 'career' : 'kaoyan')
  }

  /** 当前场景（响应式） */
  const scene = computed(() => currentScene.value)
  /** 当前场景的 Scene 过滤值（恒为 SelectableScene，可安全传给 visibleGroups） */
  const sceneFilter = computed<Scene>(() => currentScene.value)

  return { scene, sceneFilter, setScene, toggleScene, scenes: SELECTABLE_SCENES, SCENE_META }
}
