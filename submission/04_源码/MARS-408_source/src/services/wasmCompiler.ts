const DEFAULT_TIMEOUT_MS = 90000

let worker: Worker | null = null
let workerLanguage: string | null = null
let activeRequest: {
  id: string
  resolve: (value: CompileResult | PromiseLike<CompileResult>) => void
  reject: (reason?: unknown) => void
  timeout: ReturnType<typeof setTimeout>
  onProgress?: (stage: string) => void
} | null = null
let sequence = 0

export interface CompilerEnvironment {
  ready: boolean
  secureContext: boolean
  isolated: boolean
  embedded: boolean
  message: string
}

export function getCompilerEnvironment(): CompilerEnvironment {
  const secureContext = globalThis.isSecureContext === true
  const isolated = globalThis.crossOriginIsolated === true
  const embedded = typeof window !== 'undefined' && window.self !== window.top

  if (isolated) {
    return { ready: true, secureContext, isolated, embedded, message: '' }
  }
  if (!secureContext) {
    return {
      ready: false,
      secureContext,
      isolated,
      embedded,
      message: '当前地址不是安全上下文，请通过 HTTPS、localhost 或 127.0.0.1 访问实验室。',
    }
  }
  if (embedded) {
    return {
      ready: false,
      secureContext,
      isolated,
      embedded,
      message: '当前实验室位于未隔离的嵌入式预览中，请在独立窗口运行 WASM 编译器。',
    }
  }
  return {
    ready: false,
    secureContext,
    isolated,
    embedded,
    message: '当前部署未启用 COOP/COEP 跨源隔离，请检查前端服务器或反向代理响应头。',
  }
}

function disposeWorker(error: Error | null = null) {
  worker?.terminate()
  worker = null
  workerLanguage = null
  if (activeRequest) {
    clearTimeout(activeRequest.timeout)
    if (error) activeRequest.reject(error)
    activeRequest = null
  }
}

function ensureWorker(language: string): Worker {
  if (worker && workerLanguage === language) return worker
  worker?.terminate()
  worker =
    language === 'cpp'
      ? new Worker(new URL('../workers/cppCompiler.worker.ts', import.meta.url), { type: 'module' })
      : new Worker(new URL('../workers/cCompiler.worker.ts', import.meta.url), { type: 'module' })
  workerLanguage = language
  worker.addEventListener('message', event => {
    if (!activeRequest || (event.data as any)?.id !== activeRequest.id) return
    if ((event.data as any).type === 'progress') {
      activeRequest.onProgress?.((event.data as any).stage)
      return
    }
    clearTimeout(activeRequest.timeout)
    const request = activeRequest
    activeRequest = null
    if ((event.data as any).type === 'result') request.resolve((event.data as any).result)
    else request.reject(new Error((event.data as any).message || '浏览器编译器执行失败'))
  })
  worker.addEventListener('error', event => {
    disposeWorker(new Error(event.message || '浏览器编译器 Worker 异常'))
  })
  return worker
}

export interface CompileOptions {
  timeoutMs?: number
  onProgress?: (stage: string) => void
}

export interface CompileResult {
  stage: 'compile' | 'run'
  code: number
  stdout: string
  stderr: string
  durationMs: number
  compiler: string
  language: string
  command: string
  binarySize?: number
}

export function compileAndRunCode(
  language: string,
  source: string,
  stdin = '',
  options: CompileOptions = {},
): Promise<CompileResult> {
  if (!['c', 'cpp'].includes(language)) {
    return Promise.reject(new Error(`不支持的本地编译语言：${language}`))
  }
  const environment = getCompilerEnvironment()
  if (!environment.ready) {
    return Promise.reject(new Error(environment.message))
  }
  if (activeRequest) {
    return Promise.reject(new Error('已有编译任务正在运行'))
  }
  const timeoutMs = Math.max(5000, Math.min(180000, options.timeoutMs || DEFAULT_TIMEOUT_MS))
  const id = `compile-${Date.now()}-${++sequence}`
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      disposeWorker(new Error(`编译运行超过 ${Math.round(timeoutMs / 1000)} 秒，任务已终止`))
    }, timeoutMs)
    activeRequest = { id, resolve, reject, timeout, onProgress: options.onProgress }
    ensureWorker(language).postMessage({ id, language, source, stdin })
  })
}

export function compileAndRunC(source: string, stdin = '', options: CompileOptions = {}): Promise<CompileResult> {
  return compileAndRunCode('c', source, stdin, options)
}

export function compileAndRunCpp(source: string, stdin = '', options: CompileOptions = {}): Promise<CompileResult> {
  return compileAndRunCode('cpp', source, stdin, options)
}

export function cancelCompilation(): boolean {
  if (!activeRequest) return false
  disposeWorker(new Error('编译任务已取消'))
  return true
}

export function isCompilerBusy(): boolean {
  return Boolean(activeRequest)
}
