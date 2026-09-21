---
name: test-gate
description: study-help-pro 测试闸门——全量 pytest 不可用，必须分文件/分标记跑；触发词：测试、pytest、跑测试、验证
---
# 测试闸门 — study-help-pro

## 铁律
**全量 pytest 会因 FastAPI 版本兼容问题全部报错**——报错不代表代码坏了，先看是不是这个已知坑。

## 正确姿势
```bash
cd py-server
# 分文件跑（推荐）
python -m pytest tests/test_wave_c_security.py -v --timeout=30   # 安全测试 (12 个)
python -m pytest tests/test_safety_redline.py -v --timeout=30    # 安全红线 (42 个)
# 分标记跑（排除重型依赖）
python -m pytest -m "not system and not requires_milvus and not slow" --timeout=60 -q
```

## 功能级验证
Router 版本问题导致 HTTP 测试失效时，用直接调用函数/脚本的方式验证功能，验证命令落盘留档（工件可信）。

## 汇报纪律
- 说"已验证"必须给出具体命令 + 结果，没跑过的标注"未验证"
- 区分：本次改动相关失败 vs 既有历史失败（FastAPI 兼容问题属后者）
