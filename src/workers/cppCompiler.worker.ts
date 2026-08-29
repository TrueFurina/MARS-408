import { Archive } from '@obsidize/tar-browserify'
import { WASIWorkerHost } from '@runno/wasi'
import { inflate as pakoInflate } from 'pako'

const TOOLCHAIN_BASE_URL = import.meta.env.VITE_RUNNO_TOOLCHAIN_BASE_URL || 'https://runno.dev/langs'
const CLANG_URL = `${TOOLCHAIN_BASE_URL}/clang.wasm`
const SYSROOT_URL = `${TOOLCHAIN_BASE_URL}/clang-fs.tar.gz`
const LINKER_URL = `${TOOLCHAIN_BASE_URL}/wasm-ld.wasm`
const MAX_SOURCE_CHARS = 20000
const MAX_INPUT_CHARS = 8000
const MAX_OUTPUT_CHARS = 20000
const COMMAND = 'clang++ main.cpp -std=c++17 -O0 -o main.wasm'

let sysrootPromise: Promise<Record<string, any>> | null = null

function emitProgress(id: string, stage: string) {
  ;(self as any).postMessage({ id, type: 'progress', stage })
}

function limitOutput(value: unknown): string {
  // eslint-disable-next-line no-control-regex -- ANSI escape stripping is intentional
const text = String(value || '').replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, '')
  if (text.length <= MAX_OUTPUT_CHARS) return text
  const suffix = '\n[输出已截断]'
  return `${text.slice(0, MAX_OUTPUT_CHARS - suffix.length)}${suffix}`
}

function makeFile(path: string, content: any, mode = 'binary') {
  const now = new Date()
  return {
    path,
    content,
    mode,
    timestamps: { access: now, modification: now, change: now },
  }
}

async function loadSysroot(): Promise<Record<string, any>> {
  if (!sysrootPromise) {
    sysrootPromise = (async () => {
      const response = await fetch(SYSROOT_URL)
      if (!response.ok) throw new Error(`C++ sysroot 下载失败：HTTP ${response.status}`)
      const compressed = new Uint8Array(await response.arrayBuffer())
      const archive = pakoInflate(compressed)
      const parsed = await Archive.extract(archive)
      const files: Record<string, any> = {}
      for (const entry of parsed.entries) {
        if (!entry.isFile()) continue
        const path = entry.fileName.replace(/^([^/])/, '/$1')
        files[path] = makeFile(path, entry.content)
      }
      return files
    })().catch(error => {
      sysrootPromise = null
      throw error
    })
  }
  return sysrootPromise
}

async function runWasi(binaryUrl: string, binaryName: string, args: string[], fs: Record<string, any>, stdin = '') {
  let stdout = ''
  let stderr = ''
  const host = new WASIWorkerHost(binaryUrl, {
    args: [binaryName, ...args],
    env: {},
    fs,
    stdout: (chunk: string) => { stdout += chunk },
    stderr: (chunk: string) => { stderr += chunk },
  })
  const execution = host.start()
  if (stdin) await host.pushStdin(stdin)
  await host.pushEOF()
  const result = await execution
  return { ...result, stdout, stderr }
}

function postResult(id: string, startedAt: number, stage: string, result: any, extra: Record<string, any> = {}) {
  ;(self as any).postMessage({
    id,
    type: 'result',
    result: {
      stage,
      code: result.exitCode,
      stdout: limitOutput(result.stdout),
      stderr: limitOutput(result.stderr),
      durationMs: Math.round(performance.now() - startedAt),
      compiler: 'Runno clang 8 · wasm32-wasi',
      language: 'cpp',
      command: COMMAND,
      ...extra,
    },
  })
}

self.addEventListener('message', async event => {
  const { id, source, stdin = '' } = event.data || {}
  const startedAt = performance.now()
  try {
    if (typeof source !== 'string' || !source.trim()) throw new Error('C++ 源码不能为空')
    if (source.length > MAX_SOURCE_CHARS) throw new Error('C++ 源码不能超过 20000 个字符')
    if (String(stdin).length > MAX_INPUT_CHARS) throw new Error('标准输入不能超过 8000 个字符')

    emitProgress(id, 'toolchain')
    const sysroot = await loadSysroot()
    let fs: Record<string, any> = { ...sysroot, '/main.cpp': makeFile('/main.cpp', source, 'string') }

    emitProgress(id, 'compile')
    const compilation = await runWasi(CLANG_URL, 'clang', [
      '-cc1',
      '-emit-obj',
      '-disable-free',
      '-isysroot', '/sys',
      '-internal-isystem', '/sys/include/c++/v1',
      '-internal-isystem', '/sys/include',
      '-internal-isystem', '/sys/lib/clang/8.0.1/include',
      '-ferror-limit', '8',
      '-fmessage-length', '100',
      '-fcolor-diagnostics',
      '-std=c++17',
      '-O0',
      '-o', '/program.o',
      '-x', 'c++',
      '/main.cpp',
    ], fs)
    if (compilation.exitCode !== 0) {
      postResult(id, startedAt, 'compile', compilation)
      return
    }
    fs = compilation.fs

    const linking = await runWasi(LINKER_URL, 'wasm-ld', [
      '--no-threads',
      '--export-dynamic',
      '-z', 'stack-size=1048576',
      '-L/sys/lib/wasm32-wasi',
      '/sys/lib/wasm32-wasi/crt1.o',
      '/program.o',
      '-lc',
      '-lc++',
      '-lc++abi',
      '-o', '/program.wasm',
    ], fs)
    if (linking.exitCode !== 0) {
      linking.stderr = [compilation.stderr, linking.stderr].filter(Boolean).join('\n')
      postResult(id, startedAt, 'compile', linking)
      return
    }
    fs = linking.fs

    const binary = fs['/program.wasm']
    if (!binary || binary.mode !== 'binary') throw new Error('C++ 链接器没有生成 WASM 文件')
    const binaryUrl = URL.createObjectURL(new Blob([binary.content], { type: 'application/wasm' }))
    try {
      emitProgress(id, 'run')
      const execution = await runWasi(binaryUrl, 'main.wasm', [], fs, String(stdin))
      execution.stderr = [compilation.stderr, linking.stderr, execution.stderr].filter(Boolean).join('\n')
      postResult(id, startedAt, 'run', execution, { binarySize: binary.content.byteLength })
    } finally {
      URL.revokeObjectURL(binaryUrl)
    }
  } catch (error) {
    const message = (error as Error)?.message === 'Failed to fetch'
      ? 'C++ 工具链资源加载失败，请检查网络或配置同域工具链镜像'
      : (error as Error)?.message || String(error)
    ;(self as any).postMessage({ id, type: 'error', message })
  }
})
