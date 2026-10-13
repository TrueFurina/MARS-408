/**
 * 云服务客户端（全应用唯一实例）
 * ============================================================================
 * Auth / Database / Storage / LLM 四个模块共用这一个 client：
 * 登录后，共享请求层会自动把当前会话附加到 Database 与 Storage 请求上，
 * 因此业务代码**永远不要**手工传 token、user id 或 owner_id。
 *
 * 注意：不要另建第二个客户端，也不要自己手写 fetch 去打 `/.cloud/**`。
 */
import { createWorkBuddyCloud } from '@tencent-ai/workbuddy-cloud-sdk'
import { CLOUD_PUBLIC_CONFIG } from './config'

export const cloud = createWorkBuddyCloud({
  endpoint: CLOUD_PUBLIC_CONFIG.endpoint,
  oauthRelayBaseUrl: CLOUD_PUBLIC_CONFIG.oauthRelayBaseUrl,
  publishableKey: CLOUD_PUBLIC_CONFIG.publishableKey,
})

/** 云服务是否可用（未开通/配置缺失时为 false，UI 据此给出提示而不是空白页）。 */
export const CLOUD_ENABLED = Boolean(
  CLOUD_PUBLIC_CONFIG.endpoint && CLOUD_PUBLIC_CONFIG.publishableKey,
)
