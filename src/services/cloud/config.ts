/**
 * 云服务公开配置（publicConfig）
 * ============================================================================
 * 这四个值由 WorkBuddy 云服务开通流程下发，**是唯一可以放进前端代码的凭证**：
 *   - publishableKey 只标识「是哪个应用」，本身不带权限；服务端按 Origin 精确匹配放行；
 *   - endpoint 必须是发布域数据面地址，**禁止硬编码别处的地址**、也禁止从 location/env 推断；
 *   - oauthRelayBaseUrl 是 Web 端微信扫码登录所必需（缺失会在运行时才报错）。
 * 底层环境 id / 各模型厂商密钥始终留在服务端，绝不会出现在这里。
 *
 * ⚠️ 重新开通或换应用后，本文件必须与 activate 返回的 publicConfig 重新对齐。
 */
export const CLOUD_PUBLIC_CONFIG = {
  resourceId: 'wbcs_tEWXVAvM30yJNbt7nr37TB',
  endpoint: 'https://mangdehenzhi.app.workbuddy.host',
  oauthRelayBaseUrl: 'https://www.workbuddy.cn/v2/as/genie-baas/oauth',
  publishableKey: 'wbpk_SCV2PQvaYZGxutFzKn3mwC_55z5pxfoP4Y0jGZypCw8209NGFpBFVWp',
} as const
