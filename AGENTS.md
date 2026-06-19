  - 用 Context7 查最新文档
  - 先把架构方向和功能目标用通俗方式对齐
  - 尽量简化代码，避免过度防御
  - 能并行的地方优先用 subagents
  - 先确认“做什么、实现什么”，再动手改代码

  
  - 改 `devutils` / `utils` 时，按 CI 同款 `python -m yapf --style .style.yapf -e '*/third_party/*' -rpd devutils` 和 `... utils` 先验一遍，确保没有格式漂移再交付
