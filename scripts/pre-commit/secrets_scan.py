#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""密钥/凭据扫描器 — pre-commit 门禁
用法：python scripts/pre-commit/secrets_scan.py [文件列表...]
退出码：0=通过，1=命中密钥（fail-closed）
"""
import re
import sys
from pathlib import Path

# 常见密钥模式（覆盖主流云厂商/数据库/消息队列）
SECRET_PATTERNS = [
    # AWS
    (r'AKIA[0-9A-Z]{16}', 'AWS Access Key ID'),
    (r'[0-9a-zA-Z/+]{40}', 'AWS Secret Access Key (base64)'),
    # GitHub
    (r'gh[pousr]_[A-Za-z0-9_]{36,}', 'GitHub Token'),
    # Generic API Key
    (r'(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)[\s:=]+[\'"]?([a-zA-Z0-9_\-]{20,})', 'Generic API Key'),
    # 数据库连接串
    (r'(?i)(postgres|mysql|redis|mongodb)://[^\s]+:\S+@[^\s/]+', 'Database Connection String'),
    # JWT
    (r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', 'JWT Token'),
    # Private Key
    (r'-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----', 'Private Key'),
    # Slack
    (r'xox[baprs]-[A-Za-z0-9-]{10,}', 'Slack Token'),
    # Generic
    (r'(?i)(secret|password|token)[\s:=]+[\'"]?([a-zA-Z0-9_\-]{20,})', 'Potential Secret'),
]

# 允许列表（测试/示例/占位符）
ALLOWLIST_PATTERNS = [
    r'your[_-]?api[_-]?key',
    r'your[_-]?secret',
    r'example[_-]?key',
    r'test[_-]?key',
    r'dummy[_-]?secret',
    r'placeholder',
    r'xxxxxxxx',
    r'your[_-]?password',
]

# 规则级路径豁免：仅对「低精度规则」在「特定目录」下豁免，其余规则照常生效。
#
# 背景（2026-09-27 实锤误报）：`[0-9a-zA-Z/+]{40}`（AWS Secret Access Key 形态）
# 会命中**任何 40 字符以上的字母数字串**。py-server/seed/ 存放 408 静态教学语料，
# 其中知识点长串（如 AES 轮变换 "SubBytes/ShiftRows/MixColumns/AddRoundKey"）
# 必然命中该规则 —— 这是语料内容，不是凭据。
#
# 为什么不做「文件级整体豁免」：那会让该目录完全脱离密钥扫描，将来真写进去
# 的凭据也扫不到。这里只豁免这一条低精度规则，generic/连接串/JWT/私钥等规则
# 对 seed/ 依然生效。
#
# 追加（2026-09-28 实锤误报）：py-server/openapi.json 是接口快照，其中
# `"$ref": "#/components/schemas/<长名字>"` 的 `/components/schemas/XXX` 段
# 本身就是一个 40+ 字符的 [0-9a-zA-Z/+] 串（`/` 属于该字符类），于是每条长
# schema 的 $ref 都被判成 AWS 密钥。影响不只是噪点：pre-commit 只扫描暂存文件，
# 意味着该快照一旦被拦，今后**任何一次更新都提交不进去**（事实上已被冻结）。
# 同样只豁免这一条低精度规则；generic/连接串/JWT/私钥四类规则对它依然生效。
#
# 追加（2026-09-29 实锤误报）：kg408 的溯源指纹 —— py-server/data/kg408/kg408.json 的
# `source_sha256` / `alias_sha256` / `chapter_map_sha256` / `manual_nodes_sha256` ——
# 是 64 位十六进制摘要，被 `[0-9a-zA-Z/+]{40}`（AWS Secret Access Key 形态）低精度规则
# 命中（恰 4 条）。这些是**溯源指纹，不是凭据**，与上面两类误报同源。
# 本次不改路径豁免，而是在 is_allowed() 加「令牌级」十六进制摘要豁免：fullmatch 只放行
# **整串纯十六进制且 ≥32 位**的匹配串（md5/sha1/sha256 摘要）。
# 为什么令牌级豁免是安全的：generic-api-key / JWT / 连接串 / 私钥 / GitHub 几条规则的
# 匹配串**必带关键词或结构前缀**（如 `gh[pousr]_`、`eyJ`、`AKIA`、`://`、`-----BEGIN`），
# 纯十六进制串 fullmatch 到不了，故这些规则不受影响，也**不会**整行跳过其它规则。
# 剩余风险（如实写明）：若某 AWS Secret Access Key 恰好是纯十六进制形态，会被放行；
# 但 AWS secret 使用 base64 字母表，40 位恰好全部落在十六进制字符集内的概率量级约 2⁻⁸⁰，
# 可忽略。
RULE_PATH_EXEMPT = {
    'AWS Secret Access Key (base64)': ['py-server/seed/', 'py-server/openapi.json'],
}


def compile_patterns():
    secret_res = [(re.compile(p, re.IGNORECASE), desc) for p, desc in SECRET_PATTERNS]
    allow_res = [re.compile(p, re.IGNORECASE) for p in ALLOWLIST_PATTERNS]
    return secret_res, allow_res


# 纯十六进制摘要（md5/sha1/sha256 等）：整串均为 [0-9a-fA-F] 且 ≥32 位，属哈希指纹，非密钥。
# 仅在 is_allowed() 做令牌级豁免（fullmatch），不整行放行。
HEX_DIGEST = re.compile(r'[0-9a-fA-F]{32,}')


def is_allowed(text: str, allow_res) -> bool:
    # 纯十六进制摘要是哈希指纹，非密钥（kg408 产物的 *_sha256 字段，2026-09-29 实锤误报）
    if HEX_DIGEST.fullmatch(text):
        return True
    return any(r.search(text) for r in allow_res)


def scan_file(filepath: Path) -> list:
    """扫描单文件，返回命中列表 [(行号, 类型, 匹配内容)]"""
    hits = []
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return hits

    secret_res, allow_res = compile_patterns()

    # 归一为 posix 形态，便于按仓库相对路径做规则级豁免
    posix_path = str(filepath).replace('\\', '/')
    exempt_rules = {
        desc for desc, prefixes in RULE_PATH_EXEMPT.items()
        if any(p in posix_path for p in prefixes)
    }

    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        # 跳过空行、注释
        if not stripped or stripped.startswith('#'):
            continue

        for pattern, desc in SECRET_PATTERNS:
            if desc in exempt_rules:
                continue
            matches = re.finditer(pattern, line, re.IGNORECASE)
            for m in matches:
                matched = m.group(0)
                if is_allowed(matched, allow_res):
                    continue
                hits.append((i, f'{matched[:50]}...' if len(matched) > 50 else matched))
    return hits


def main():
    import sys
    files = sys.argv[1:] if len(sys.argv) > 1 else [str(p) for p in Path('.').rglob('*') if p.is_file()]

    all_hits = []
    for f in files:
        p = Path(f)
        if not p.is_file():
            continue
        # 跳过二进制/大文件
        if p.stat().st_size > 1_000_000:
            continue
        # 跳过已知忽略
        if any(ign in str(p) for ign in ['.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build']):
            continue
        # 跳过依赖锁文件：其内容本就是 package URL + hash，非密钥（避免 SHA256 等被误判为 AWS secret）
        if p.name in {
            'uv.lock', 'poetry.lock', 'package-lock.json', 'yarn.lock',
            'pnpm-lock.yaml', 'Pipfile.lock', 'Cargo.lock', 'go.sum',
        }:
            continue

        hits = scan_file(p)
        if hits:
            for line_num, match in hits:
                print(f'❌ {p}:{line_num}: 疑似密钥 - {match}')
            return 1

    print('✅ 密钥扫描通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())