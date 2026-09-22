# D4 静默吞错专项审计 · 安全关键模块（2026-09-23）

**分支**：career-literacy ｜ **工作流**：P0 技术债 D4（认证/限流/中间件/启动路径静默吞错）
**方法**：AST 扫描器（`scripts`/临时）定位 `except` 处理体无日志、无 re-raise 的"静默吞错"，限定在
`main.py`（lifespan 启动 + 4 个 HTTP 中间件）、`api/auth.py`、`shared/auth.py`、`shared/ratelimit.py`、
`shared/{sse,circuit,url,semantic,prompt}_guard.py`。

## 结论
- 扫描前 **14 处静默吞错**（10 HIGH=空 `pass`、2 MED=直接 `return`、2 LOW=其他体无日志）。
- 修复原则：**行为零改动，仅补可见性**——把 `except ...: pass` 改为 `logger.debug(...)`，使"尽力而为/优雅降级"路径的故障不再隐身（符合 D4"启动/中间件/生命周期故障不可掩盖"）。
- 认证路径 `api/auth.py:79` 原本 `except Exception: diagnostic_required=True` 完全静默 → 改为 `logger.warning`（认证失败可见性最高优先级）。
- **1 处排除**：`shared/url_guard.py:95`（`is_allowed`）是 Docstring 明示"返回布尔、不抛异常"的设计型安全 API，非缺陷，保留。

## 修复清单（13 处，已落地 + AST 重扫验证）

| 文件 | 行 | 原状 | 修复 |
|------|----|------|------|
| `main.py` | 263 | `except Exception: pass` 凭证检测 | `logger.debug(检测失败不影响启动)` |
| `main.py` | 275 | `except ValueError: pass` `--workers` 解析 | `logger.debug(--workers 非整数)` |
| `main.py` | 306 | `except OSError: pass` 旧会话文件清理 | `logger.debug(清理失败跳过)` |
| `main.py` | 311 | `except OSError: pass` 空用户目录清理 | `logger.debug(清理失败跳过)` |
| `main.py` | 346 | `except Exception: pass` 取消清理任务 | `logger.debug(...)` |
| `main.py` | 354 | `except Exception: pass` 释放 httpx 池 | `logger.debug(...)` |
| `main.py` | 359 | `except Exception: pass` PG 断开 | `logger.debug(...)` |
| `main.py` | 363 | `except Exception: pass` Redis 断开 | `logger.debug(...)` |
| `main.py` | 527 | `except ValueError: body_len=0` 中间件 | `logger.debug(Content-Length 非整数)` |
| `api/auth.py` | 79 | `except Exception: diagnostic_required=True` | `logger.warning(获取测评状态失败)` + 保持保守默认 |
| `shared/sse_guard.py` | 40 | `except Exception: pass` 断连探测 | `logger.debug(探测异常已忽略)` |
| `shared/semantic_guard.py` | 85 | `except Exception: return {}` 配置读取 | `logger.debug(配置读取失败用默认)` |
| `shared/semantic_guard.py` | 163 | `except (...): pass`  verdict 解析 | `logger.debug(JSON 解析失败降级)` |

## 验证
- AST 重扫：剩余静默吞错 **1 处**（即上述排除项），HIGH=0。
- `py_compile`：`main.py` / `api/auth.py` / `shared/sse_guard.py` / `shared/semantic_guard.py` 全部 OK。
- 行为保持：所有 `except` 体原有控制流（保持默认/降级/忽略）未变，仅新增日志语句。

## 范围说明 / 已知局限
- 本审计**仅覆盖安全关键模块**。技术债报告 D4 全仓口径为 486 处 `except Exception`、其中 80 处零日志；其余（user_store/sandbox/import_*/engines 等）非认证/限流/生命周期关键路径，建议后续按 P1 节奏分批补 `logger.exception`，但**不在本次 P0 范围**。
- 未改动 `except ImportError` 类（依赖缺失降级，本就应有 `# pragma: no cover` 或明确注释）。
