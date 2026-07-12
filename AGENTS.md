# Nitrous — Agent 准则（唯一权威）

`CLAUDE.md` 符号链接到本文件。其它路径下的 AGENTS 副本一律无效。

**涉及改源码 / 改 patch / 修编译 / export 时：必须先按 `$nitrous-dev` 执行。**  
**任何产生仓库修改的任务在交付前：必须通过 `agent_patch_guard --mode pre-build`。**

## 总原则

1. 开发期只写热树；交付期才 export 到 `patches/`；验证树只读。
2. 禁止手改 `.patch` 的 diff 正文（只允许 quilt-fix / guard 写回）。
3. 长期有效修改必须落在 `patches/**`、`patches/series` 或本仓库源文件。
4. 跟上游时 `patches/helium/**` 是 **vendor 路径名**，不要为品牌全局改名。
5. `he` 是平台构建命令前缀，与产品名无关。
6. `quick`、`patch-source`、`run_validation.py`、定向编译和测试都是中间反馈；不能替代最终 `pre-build` 交付门禁。

## 任务模式（动手前必须选一）

| 模式 | 何时 | 可写 | 禁止 | 收尾 |
|------|------|------|------|------|
| `explore` | 只读调查 | 无 | 一切写 | — |
| **`hot-dev`（默认）** | 功能 / 修编译 | 仅已声明的 `build/src` 文件 | 未 `hot-start` 就编辑、每轮 `he merge&&he push` | `syntax_check` / `build_targets` |
| `export-patch` | 已有 hot-start 会话要交付 | guard staging 后写 `patches/` | 覆盖已有 patch、整文件回灌旧 patch | `agent_patch_guard --mode export-hotfix` |
| `patch-fix` | apply 冲突 / 合上游 | patchwork + series | 热树当 SoT | `agent_patch_guard --mode patch-source` |
| `package` | 出包 | 平台脚本（慎） | 未过 pre-build 就 package | guard pre-build 后 `he *` |

未声明模式时按 **`hot-dev`**。`hot-dev` 结束时不得声称 patch 已交付。

## 目录职责

| 路径 | 用途 | 可写 |
|------|------|------|
| `build/src` | 热增量开发 / 编译 | `hot-dev` |
| `codex_tmp/patchwork_src` | quilt 开发与 refresh | `export-patch` / `patch-fix` |
| `codex_tmp/patchcheck_src` | fresh apply 验证 | 否（每次重建） |
| `chromium_src` | clean baseline 验证 | 否 |
| `patches/` | Chromium 侧修改 SoT | 仅经 quilt-fix / guard |
| `platform/macos/` | macOS 构建与打包 | 包装层问题 |
| `devutils/i18n-data/` | 历史/参考，非默认打包入口 | 否（除非修它本身） |

## 硬禁止

- 在 `chromium_src` / `patchcheck_src` 写业务或做破坏性实验。
- 手改 patch hunk 行号 / diff 正文来「对齐」。
- 未先运行 `hot-start` 就把热树修改自动导出，或把完全 applied 热树整文件复制进旧 patch。
- 只删 `.pc/` 假装干净（源码仍可能已被 patch）。
- 热树迭代中每轮 `he merge && he push`（会打烂 siso 增量）。
- cheap / guard 失败仍 `he build` / `he auto-package`。
- 多个 agent 同时修改同一批 patch 或同一源文件。
- 使用已归档的独立 `helium-macos` 仓库作为默认开发入口。

## 命令入口（优先这些，勿自创流程）

```bash
# hot-dev：修改前先记录新栈顶 patch 和文件基线
python3 devutils/agent_patch_guard.py --mode hot-start \
  --patch helium/core/xxx.patch --file chrome/browser/xxx.cc
# 扩展范围时必须在编辑新文件前添加
python3 devutils/agent_patch_guard.py --mode hot-add --file chrome/browser/yyy.cc

# 秒级 / 分钟级编译反馈
python3 devutils/syntax_check.py [-o build/src/out/Default] FILE...
python3 devutils/build_targets.py [--from-failed] [target...]

# staging / replay / root+macOS 验证后自动发布新栈顶 patch
python3 devutils/agent_patch_guard.py --mode export-hotfix

# 修改过程中的定向反馈
python3 devutils/agent_patch_guard.py --mode patch-source
# 或
python3 .codex/skills/nitrous-validate/scripts/run_validation.py
python3 .codex/skills/nitrous-validate/scripts/run_validation.py --full
python3 .codex/skills/nitrous-validate/scripts/run_validation.py --with-source --source-tree chromium_src

# 任何产生仓库修改的任务：交付前必须成功执行
python3 devutils/agent_patch_guard.py --mode pre-build

# 打包（仅 pre-build 通过后）
source platform/macos/build.sh
he auto-package
```

最终门禁失败时必须先修复并重跑，不得把任务报告为完成。该要求只执行与 `he auto-package` 相同的前置检查，不要求实际执行 `he auto-package`；只有用户要求构建或出包时才运行打包命令。纯只读调查不需要运行。

环境变量优先 `NITROUS_*`，回退 `HELIUM_*`（`NITROUS_SRC_DIR` / `NITROUS_OUT_DIR` / `NITROUS_BUILD_ROOT` / `NITROUS_MERGED_PATCHES_DIR` / `NITROUS_QUILT_SRC` 等）。

## 污染处理

发现 quilt 路径/series/applied 状态与当前合并队列不一致、重复 applied、异常 `.orig`、`check_chromium_src_clean` 失败 → **重建该树**，不要在脏树上硬推。自动 export 发布后 root 队列已前进，也必须在下一轮 hot-dev 前重建 `build/src`。

```bash
rm -rf codex_tmp/patchwork_src codex_tmp/patchcheck_src
# 主验证树：
rm -rf chromium_src && python3 ./utils/downloads.py unpack -i downloads.ini -c chromium_download_cache chromium_src
# 热树：
rm -rf build/src && source platform/macos/build.sh && he auto-package   # 或分步 presetup/merge/push
```

## 通用代码风格

- 用 Context7 查库文档；先对齐「做什么」再改代码。
- 简化实现，避免过度防御。
- subagent 优先只读探索；**主 agent 统一改文件、refresh patch、验证**。
- 改 `devutils` / `utils` 后 yapf dry-run（与 CI 同）：

  ```bash
  python -m yapf --style .style.yapf -e '*/third_party/*' -rpd devutils
  python -m yapf --style .style.yapf -e '*/third_party/*' -rpd utils
  ```

- 不要把会改文件的 `devutils/check_all_code.sh` 当默认收尾。

## 交付说明（验证失败时必写）

- 失败命令与原因  
- 哪棵源码树可能污染  
- 是否需要重建 `chromium_src` / `codex_tmp/*` / `build/src`  

详细逐步流程见 `$nitrous-dev` 与 `$nitrous-validate`，不要在本文件外再维护平行长规范。
