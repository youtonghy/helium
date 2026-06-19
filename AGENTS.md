  - 用 Context7 查最新文档
  - 先把架构方向和功能目标用通俗方式对齐
  - 尽量简化代码，避免过度防御
  - 能并行的地方优先用 subagents
  - 先确认“做什么、实现什么”，再动手改代码

  
  - 改 `devutils` / `utils` 时，按 CI 同款 `python -m yapf --style .style.yapf -e '*/third_party/*' -rpd devutils` 和 `... utils` 先验一遍，确保没有格式漂移再交付
  - 每次编辑代码、配置、补丁、i18n、脚本或项目说明后，使用项目 skill `$helium-validate` 收尾验证：默认运行 `python3 .codex/skills/helium-validate/scripts/run_validation.py`，让脚本按本次改动选择 CI 同款检查；影响面不明确、跨模块、CI 配置或交付前，运行 `python3 .codex/skills/helium-validate/scripts/run_validation.py --full`
  - 改补丁或 source list 且本地有 Chromium source tree 时，补跑 `python3 .codex/skills/helium-validate/scripts/run_validation.py --with-source --source-tree chromium_src`；需要复刻 CI 下载/解包源码时才显式加 `--prepare-source`
  - 如果验证失败，交付时说明失败命令和具体阻塞原因；不要把会自动改文件的 `devutils/check_all_code.sh` 当作默认收尾验证
