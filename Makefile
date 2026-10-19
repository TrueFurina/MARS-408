# Makefile — 统一开发入口
# test：用环境清洗封装脚本跑 pytest（规避 WorkBuddy shell 注入的 sitecustomize shim 污染）
# 用法：make test ARGS="tests/test_x.py -q"
test:
	./scripts/test.sh $(ARGS)

# doctor：一键健康自检（只读聚合；--full 追加 npm run verify 全量门禁）
doctor:
	node scripts/doctor.mjs

.PHONY: test doctor
