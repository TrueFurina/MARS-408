# 资源分项测量（本文件由 scripts/resource_profile.py 生成，请勿手改）

- 生成时间：2026-10-20 12:10 UTC
- 平台：Windows-11-10.0.26200-SP0 / Python 3.13.14
- 口径：`observed` = 本次实测；`unknown` = 环境不具备（**不填 0，不猜**）

## A. 前端产物（dist/）

| 项 | 值 |
|---|---|
| 总字节 | 10.8 MiB |
| assets/ | 9.3 MiB |
| JS | 1.4 MiB |
| CSS | 510.4 KiB |

最大文件：

| 字节 | 文件 |
|---|---|
| 6.3 MiB | `assets/wasmer_js_bg-lccPpAdN.wasm` |
| 402.6 KiB | `brand/share-og.png` |
| 317.1 KiB | `brand/mangxiaocheng-512.png` |
| 255.0 KiB | `assets/katex-9T2eXOdT.js` |
| 220.2 KiB | `brand/mangxiaocheng-512-maskable.png` |
| 124.9 KiB | `assets/index-DmcK9eqL.js` |
| 111.5 KiB | `assets/vue-vendor-BnleL1jK.js` |
| 96.8 KiB | `brand/mangxiaocheng.png` |

## B. 后端导入内存与耗时（子进程实测）

| 项 | 值 |
|---|---|
| 导入 `main` 耗时 | 6436.4 ms |
| 进程 RSS（导入后） | 123136.0 KiB（约 120.2 MiB） |

> 说明：RSS 含解释器与已加载的 C 扩展驻留页；不含运行时按请求分配的峰值。

## C. 契约序列化（openapi.json）

| 项 | 值 |
|---|---|
| 快照字节 | 567.2 KiB |
| operation 数 | 262 |
| schema 定义数 | 133 |
| 反序列化+再序列化（20 次均值） | 7.11 ms |

## D. 源树规模（分母）

| 扩展名 | 文件 | 行 |
|---|---|---|
| `.mjs` | 3 | 295 |
| `.py` | 501 | 108936 |
| `.ts` | 63 | 24934 |
| `.vue` | 88 | 30509 |

---

复跑：`python scripts/resource_profile.py --write`（会覆盖本文件）
