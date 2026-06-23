  - 用 Context7 查最新文档
  - 先把架构方向和功能目标用通俗方式对齐
  - 尽量简化代码，避免过度防御
  - 能并行的地方优先用 subagents
  - 先确认“做什么、实现什么”，再动手改代码

  
  - 改 `devutils` / `utils` 时，按 CI 同款 `python -m yapf --style .style.yapf -e '*/third_party/*' -rpd devutils` 和 `... utils` 先验一遍，确保没有格式漂移再交付
  - 每次编辑代码、配置、补丁、i18n、脚本或项目说明后，使用项目 skill `$helium-validate` 收尾验证：默认运行 `python3 .codex/skills/helium-validate/scripts/run_validation.py`，让脚本按本次改动选择 CI 同款检查；影响面不明确、跨模块、CI 配置或交付前，运行 `python3 .codex/skills/helium-validate/scripts/run_validation.py --full`
  - 改补丁或 source list 且本地有 Chromium source tree 时，补跑 `python3 .codex/skills/helium-validate/scripts/run_validation.py --with-source --source-tree chromium_src`；需要复刻 CI 下载/解包源码时才显式加 `--prepare-source`
  - 如果验证失败，交付时说明失败命令和具体阻塞原因；不要把会自动改文件的 `devutils/check_all_code.sh` 当作默认收尾验证

## Patch 规范

- 所有 `patches/**/*.patch` 必须以 clean 的 `chromium_src` 为比对基准；`/Users/youtonghy/github/3p/helium-macos/build/src` 这类已打补丁的构建树只能用于观察最终目标状态，不能当 source-backed 验证源。
- 新增或修补 patch 时，优先用 `diff -u clean_file target_file` 生成标准 unified diff，再落回 patch 文件；不要手工猜 hunk 行号，也不要只凭外部构建树直接挪上下文。
- patch 文件里的空白上下文行属于 diff 语法的一部分，允许存在单个前缀空格；不要把 `git diff --check` 的 patch 文件报错当成唯一判断，最终以 `validate_patches.py` 和 `run_validation.py --with-source` 为准。
- 修改、移动、删除 patch 时要同步检查 `patches/series`，避免同一段修改被两个 patch 重复覆盖，也避免 orphan patch 留在树里。
- 每次 patch 变更后，先跑 `python3 .codex/skills/helium-validate/scripts/run_validation.py --with-source --source-tree chromium_src`，通过后再跑 `--full` 做完整格式/CI 风格收尾。
- **严禁直接通过文本替换/编辑器修改 `.patch` 文件的 diff 代码块**。这会破坏统一 diff 格式与 hunk 行号，导致编译 apply 失败。
- **强制使用 `quilt` 工具链来开发和修复补丁**：
  1. 在 Shell 中运行 `source devutils/set_quilt_vars.sh` 以载入 quilt 环境变量。
  2. 使用 `quilt push` 应用到目标补丁，直接在 `chromium_src` 源码树中编辑代码并进行编译验证。
  3. 运行 `quilt refresh` 让工具自动更新补丁，以保证 diff 语法和行号 100% 精确。

