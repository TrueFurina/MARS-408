# ============================================================
# 导入 CLI 客户端（ADR-007）
# ------------------------------------------------------------
# 导入脚本的新形态：不再直写向量库，而是向后端提交导入 job，
# 由后端内部 Worker（单写者）在进程内完成解析→分块→embedding→入库。
# 彻底消除「导入脚本 vs 在线后端」的 last-writer-wins 覆盖风险。
#
# 用法：
#   python tools/import_client.py --type pdf --rebuild
#   python tools/import_client.py --type docling --max-pages 50
#   python tools/import_client.py --type textbook
#   python tools/import_client.py --type pdf --source /abs/path/to/file.pdf
# ============================================================

import sys
import json
import time
import argparse
import urllib.request
import urllib.error

DEFAULT_HOST = "http://127.0.0.1:8002"


def _request(method: str, url: str, token: str = None, body: dict = None, timeout: int = 30):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def login(host: str, username: str, password: str) -> str:
    url = f"{host}/api/auth/login"
    resp = _request("POST", url, body={"username": username, "password": password}, timeout=15)
    token = resp.get("access_token") or resp.get("token")
    if not token:
        raise RuntimeError(f"登录失败，响应: {resp}")
    return token


def submit(host: str, token: str, type_: str, source: str, params: dict) -> str:
    url = f"{host}/api/imports/submit"
    resp = _request("POST", url, token=token, body={"type": type_, "source": source, "params": params})
    if "job_id" not in resp:
        raise RuntimeError(f"提交失败，响应: {resp}")
    return resp["job_id"]


def poll(host: str, token: str, job_id: str, interval: float = 2.0):
    url = f"{host}/api/imports/jobs/{job_id}"
    terminal = {"succeeded", "failed", "cancelled", "interrupted"}
    while True:
        job = _request("GET", url, token=token, timeout=15)
        status = job.get("status", "?")
        prog = job.get("progress", {})
        stage = prog.get("stage", "")
        cur = prog.get("current_file", "")
        ins = prog.get("inserted_chunks", 0)
        pf = prog.get("processed_files", 0)
        tf = prog.get("total_files", 0)
        print(f"  [{status}] {stage} | 文件 {pf}/{tf} | 已入库 {ins} | {cur}", flush=True)
        if status in terminal:
            if job.get("error"):
                print(f"  ❌ 错误: {job['error']}", flush=True)
            return status
        time.sleep(interval)


def main(argv=None):
    parser = argparse.ArgumentParser(description="MARS-408 导入 CLI 客户端（提交 job 到后端导入队列）")
    parser.add_argument("--type", choices=["pdf", "docling", "textbook"], default="pdf")
    parser.add_argument("--source", default="scan", help='"scan" 或显式文件路径')
    parser.add_argument("--rebuild", action="store_true", help="导入前清空同类型旧数据")
    parser.add_argument("--use-ocr", action="store_true", help="PDF 扫描版启用 OCR")
    parser.add_argument("--max-pages", type=int, default=100, help="docling 页数上限")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    args = parser.parse_args(argv)

    import os
    username = args.username or os.environ.get("NETLEARN_ADMIN_USER", "admin")
    password = args.password or os.environ.get("NETLEARN_ADMIN_PASSWORD", "admin123456")

    print(f"[import-client] 登录 {args.host} as {username} ...")
    try:
        token = login(args.host, username, password)
    except urllib.error.HTTPError as e:
        print(f"  ❌ 登录失败 (HTTP {e.code})：请确认后端已启动且凭证正确", flush=True)
        return 1
    except Exception as e:
        print(f"  ❌ 无法连接后端：{e}\n  请先启动后端 (python main.py)，再运行本客户端。", flush=True)
        return 1

    params = {"rebuild": args.rebuild, "use_ocr": args.use_ocr, "max_pages": args.max_pages}
    print(f"[import-client] 提交导入任务 type={args.type} source={args.source} params={params}")
    try:
        job_id = submit(args.host, token, args.type, args.source, params)
    except urllib.error.HTTPError as e:
        if e.code == 503:
            print("  ❌ 导入 Worker 未启用（import_worker.enabled=false）。", flush=True)
        else:
            print(f"  ❌ 提交失败 (HTTP {e.code})", flush=True)
        return 1

    print(f"[import-client] job_id={job_id}，开始轮询进度（Ctrl+C 取消不影响后台任务）...")
    try:
        status = poll(args.host, token, job_id)
    except KeyboardInterrupt:
        print(f"\n[import-client] 已停止轮询；后台 job {job_id} 仍在运行，可用 GET {args.host}/api/imports/jobs/{job_id} 查看。")
        return 0
    print(f"[import-client] 任务结束：{status}")
    return 0 if status == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
