import { Directory, init, Wasmer } from '@wasmer/sdk'

const CLANG_PACKAGE = 'clang/clang@0.160000.1'
const MAX_SOURCE_CHARS = 20000
const MAX_INPUT_CHARS = 8000
const MAX_OUTPUT_CHARS = 20000
const MAX_RUNTIME_MEMORY_PAGES = 4096

const LANGUAGE_CONFIG: Record<string, { fileName: string; label: string; args: string[]; command: string }> = {
  c: {
    fileName: 'main.c',
    label: 'C',
    args: ['main.c', '-std=c11', '-Wall', '-Wextra', '-O0', '-o', 'main.wasm'],
    command: 'clang main.c -std=c11 -Wall -Wextra -O0 -o main.wasm',
  },
}

let runtimePromise: Promise<unknown> | undefined
let compilerPromise: Promise<any> | undefined

function emitProgress(id: string, stage: string) {
  ;(self as any).postMessage({ id, type: 'progress', stage })
}

function initializeRuntime(id: string): Promise<unknown> {
  if (!runtimePromise) {
    emitProgress(id, 'runtime')
    const memory = new WebAssembly.Memory({
      initial: 34,
      maximum: MAX_RUNTIME_MEMORY_PAGES,
      shared: true,
    })
    runtimePromise = init({ memory })
  }
  return runtimePromise
}

async function loadCompiler(id: string): Promise<any> {
  await initializeRuntime(id)
  if (!compilerPromise) {
    emitProgress(id, 'toolchain')
    compilerPromise = Wasmer.fromRegistry(CLANG_PACKAGE)
  }
  return compilerPromise
}

function limitOutput(value: unknown): string {
  // eslint-disable-next-line no-control-regex -- ANSI escape stripping is intentional
// eslint-disable-next-line no-control-regex -- ANSI escape stripping is intentional
const text = String(value || '').replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, '')
  if (text.length <= MAX_OUTPUT_CHARS) return text
  const suffix = '\n[输出已截断]'
  return `${text.slice(0, MAX_OUTPUT_CHARS - suffix.length)}${suffix}`
}

self.addEventListener('message', async event => {
  const { id, language = 'c', source, stdin = '' } = event.data || {}
  const startedAt = performance.now()
  let workspace: any = null
  try {
    const config = LANGUAGE_CONFIG[language]
    if (!config) throw new Error(`不支持的本地编译语言：${language}`)
    if (typeof source !== 'string' || !source.trim()) throw new Error(`${config.label} 源码不能为空`)
    if (source.length > MAX_SOURCE_CHARS) throw new Error(`${config.label} 源码不能超过 20000 个字符`)
    if (String(stdin).length > MAX_INPUT_CHARS) throw new Error('标准输入不能超过 8000 个字符')

    const compiler = await loadCompiler(id)
    workspace = new Directory({ [config.fileName]: source })
    emitProgress(id, 'compile')
    const compilation = await compiler.commands.clang.run({
      args: config.args,
      cwd: '/workspace',
      mount: { '/workspace': workspace },
    })
    const compileResult = await compilation.wait()
    if (!compileResult.ok) {
      ;(self as any).postMessage({
        id,
        type: 'result',
        result: {
          stage: 'compile',
          code: compileResult.code,
          stdout: limitOutput(compileResult.stdout),
          stderr: limitOutput(compileResult.stderr),
          durationMs: Math.round(performance.now() - startedAt),
          compiler: CLANG_PACKAGE,
          language,
          command: config.command,
        },
      })
      return
    }

    const binary = await workspace.readFile('main.wasm')
    emitProgress(id, 'run')
    const program = await Wasmer.fromFile(binary)
    let runResult: any
    try {
      if (!program.entrypoint) throw new Error('编译产物没有可执行入口')
      const execution = await program.entrypoint.run({ stdin: String(stdin) })
      runResult = await execution.wait()
    } finally {
      program.free()
    }
    ;(self as any).postMessage({
      id,
      type: 'result',
      result: {
        stage: 'run',
        code: runResult.code,
        stdout: limitOutput(runResult.stdout),
        stderr: limitOutput(runResult.stderr),
        binarySize: binary.byteLength,
        durationMs: Math.round(performance.now() - startedAt),
        compiler: CLANG_PACKAGE,
        language,
        command: config.command,
      },
    })
  } catch (error) {
    ;(self as any).postMessage({ id, type: 'error', message: (error as Error)?.message || String(error) })
  } finally {
    workspace?.free()
  }
})
