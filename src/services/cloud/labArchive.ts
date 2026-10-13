/**
 * 源码实验室「云端存档」：Database + Storage
 * ============================================================================
 * 现有功能的本机化问题：源码实验室的进度只存在 localStorage，换设备/换浏览器即丢。
 * 这里把同一份进度按云端身份存进数据库，并把实验源码文件存进对象存储。
 *
 * 安全边界（不要绕过）：
 *   - owner 由数据库 `DEFAULT auth.uid()` 决定，**前端绝不传 owner_id**；
 *     行级安全策略按 `owner_id = auth.uid()` 生效，读写他人数据会被 RLS 拦下。
 *   - 写操作返回空数组 = 被 RLS 拦下（不是成功），必须如实告知用户。
 *   - 文件路径只由 `cloud.storage.userPath(uid, …)` 生成，绝不接受外部传入的完整 key。
 */
import { cloud } from './client'
import { CloudCallError, getSession, toCallError } from './auth'

const TABLE = 'source_lab_progress'
const SOURCE_DIR = 'source-lab'

/**
 * 本项目未接入生成式 schema 类型，SDK 的表名参数会收窄成 never 而无法调用
 * （官方说明：不传泛型时行数据即 `any`）。这里在一个地方取宽松别名，
 * 避免在每个业务文件里散落类型断言。
 */
type UntypedFrom = (table: string) => any
const db = cloud.database as unknown as { from: UntypedFrom }

export interface LabProgressRow {
  lab_id: string
  completed: string[]
  attempts: Record<string, number>
  updated_at?: string
}

/** 上传（或覆盖）某实验的进度；同一用户同一实验只保留一条。 */
export async function pushProgress(row: LabProgressRow): Promise<void> {
  const res = await db
    .from(TABLE)
    .upsert(
      {
        lab_id: row.lab_id,
        completed: row.completed,
        attempts: row.attempts,
        updated_at: new Date().toISOString(),
      },
      { onConflict: 'owner_id,lab_id' },
    )
    .select()
  if (res.error) throw toCallError(res.error, '云端存档失败')
  // RLS 拦住时是「空数组 + 无 error」——必须显式识别，不能当成成功
  if (!Array.isArray(res.data) || res.data.length === 0) {
    throw new CloudCallError('云端存档未生效：可能未登录，或该记录不属于当前账号', 'permission-denied')
  }
}

/** 取回某实验的进度；没有记录返回 null。 */
export async function pullProgress(labId: string): Promise<LabProgressRow | null> {
  const res = await db
    .from(TABLE)
    .select('lab_id, completed, attempts, updated_at')
    .eq('lab_id', labId)
    .maybeSingle()
  if (res.error) throw toCallError(res.error, '读取云端存档失败')
  return (res.data as LabProgressRow | null) ?? null
}

/** 列出当前账号的全部云端进度（RLS 只会返回自己的行）。 */
export async function listProgress(): Promise<LabProgressRow[]> {
  const res = await db
    .from(TABLE)
    .select('lab_id, completed, attempts, updated_at')
    .order('updated_at', { ascending: false })
  if (res.error) throw toCallError(res.error, '读取云端存档列表失败')
  return (res.data as LabProgressRow[] | null) ?? []
}

// ── Storage：实验源码文件 ──────────────────────────────────────────────

export interface SourceFileItem {
  path: string
  name: string
  size: number | null
  updatedAt: string | null
}

/** 只保留基础文件名（不信任调用方传入的文件名，杜绝路径穿越）。 */
function safeName(name: string): string {
  const base = name.split(/[\\/]/).pop() || 'source.txt'
  return base.replace(/[^\w.\-\u4e00-\u9fa5]/g, '_').slice(0, 80)
}

async function requireUid(): Promise<string> {
  const session = await getSession()
  if (!session) throw new CloudCallError('请先登录后再使用云端存档', 'unauthenticated')
  return session.user.id
}

function labDir(uid: string, labId: string): string {
  return cloud.storage.userPath(uid, `${SOURCE_DIR}/${labId}`)
}

/** 上传一个源码文件到「当前用户 / 该实验」目录下（同名前缀不存在会自动建）。 */
export async function uploadSourceFile(labId: string, file: File): Promise<string> {
  const uid = await requireUid()
  const path = `${labDir(uid, labId)}/${safeName(file.name)}`
  const res = await cloud.storage.upload(path, file, {
    contentType: file.type || 'text/plain',
    upsert: true,
  })
  if (res.error) throw toCallError(res.error, '文件上传失败')
  return path
}

/** 列出某实验下当前用户已存档的源码文件。 */
export async function listSourceFiles(labId: string): Promise<SourceFileItem[]> {
  const uid = await requireUid()
  const dir = labDir(uid, labId)
  const res = await cloud.storage.list(dir, { limit: 100 })
  if (res.error) throw toCallError(res.error, '读取文件列表失败')
  const files = res.data ?? []
  return files.map((f) => {
    const meta = (f.metadata || {}) as Record<string, unknown>
    return {
      path: `${dir}/${f.name}`,
      name: f.name,
      size: typeof meta.size === 'number' ? (meta.size as number) : null,
      updatedAt: f.updated_at,
    }
  })
}

/** 生成短期签名下载链接（默认 600 秒；签名链接属短期凭证，不要长期保存或打印）。 */
export async function createFileUrl(path: string, ttlSeconds = 600): Promise<string> {
  await requireUid()
  const res = await cloud.storage.createSignedUrl(path, ttlSeconds)
  if (res.error) throw toCallError(res.error, '生成下载链接失败')
  const url = res.data?.signedUrl
  if (!url) throw new CloudCallError('生成下载链接失败：未返回地址')
  return url
}

/** 下载文件内容（用于页面内「读回校验」）。 */
export async function downloadSourceText(path: string): Promise<string> {
  await requireUid()
  const res = await cloud.storage.download(path)
  if (res.error) throw toCallError(res.error, '下载失败')
  const blob = res.data as unknown as Blob
  return await blob.text()
}

/** 删除明确列出的对象（不做前缀整删）。 */
export async function removeSourceFiles(paths: string[]): Promise<number> {
  await requireUid()
  const res = await cloud.storage.remove(paths)
  if (res.error) throw toCallError(res.error, '删除失败')
  return (res.data ?? []).length
}

/** 把 SDK 抛出的各种错误统一成一句人话，供 UI 直接展示。 */
export function describeCloudError(e: unknown): string {
  if (e instanceof CloudCallError) {
    if (e.kind === 'unauthenticated') return '请先登录云账号'
    if (e.kind === 'permission-denied') return '没有权限操作该数据（可能不属于当前账号）'
    if (e.kind === 'not-found') return '云端对象不存在（表或文件尚未创建）'
    return e.message
  }
  return e instanceof Error ? e.message : '云服务调用失败'
}
