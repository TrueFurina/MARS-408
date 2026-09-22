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


def compile_patterns():
    secret_res = [(re.compile(p, re.IGNORECASE), desc) for p, desc in SECRET_PATTERNS]
    allow_res = [re.compile(p, re.IGNORECASE) for p in ALLOWLIST_PATTERNS]
    return secret_res, allow_res


def is_allowed(text: str, allow_res) -> bool:
    return any(r.search(text) for r in allow_res)


def scan_file(filepath: Path) -> list:
    """扫描单文件，返回命中列表 [(行号, 类型, 匹配内容)]"""
    hits = []
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return hits

    secret_res, allow_res = compile_patterns()

    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        # 跳过空行、注释
        if not stripped or stripped.startswith('#'):
            continue

        for pattern, desc in SECRET_PATTERNS:
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

        hits = scan_file(p)
        if hits:
            for line_num, match in hits:
                print(f'❌ {p}:{line_num}: 疑似密钥 - {match}')
            return 1

    print('✅ 密钥扫描通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())