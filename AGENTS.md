# Nitrous — Agent 准则（唯一权威）

`CLAUDE.md` 符号链接到本文件。其它路径下的 AGENTS 副本一律无效。

**涉及改源码 / 改 patch / 修编译 / export 时：必须先按 `$nitrous-dev` 执行。**  
**交付前校验：必须按 `$nitrous-validate`（或 `agent_patch_guard`）执行。**

## 总原则

1. 开发期只写热树；交付期才 export 到 `patches/`；验证树只读。
2. 禁止手改 `.patch` 的 diff 正文（只允许 quilt-fix / guard 写回）。
3. 长期有效修改必须落在 `patches/**`、`patches/series` 或本仓库源文件。
4. 跟上游时 `patches/helium/**` 是 **vendor 路径名**，不要为品牌全局改名。
5. `he` 是平台构建命令前缀，与产品名无关。

## 任务模式（动手前必须选一）

| 模式 | 何时 | 可写 | 禁止 | 收尾 |
|------|------|------|------|------|
| `explore` | 只读调查 | 无 | 一切写 | — |
| **`hot-dev`（默认）** | 功能 / 修编译 | 仅 `build/src` | `patches/**`、每轮 `he merge&&he push` | `syntax_check` / `build_targets` |
| `export-patch` | 热树改完要交付 | 经 quilt 写 `patches/` | 手改 diff | `agent_patch_guard --mode after-hotfix --patch …` |
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
- 只删 `.pc/` 假装干净（源码仍可能已被 patch）。
- 热树迭代中每轮 `he merge && he push`（会打烂 siso 增量）。
- cheap / guard 失败仍 `he build` / `he auto-package`。
- 多个 agent 同时修改同一批 patch 或同一源文件。
- 使用已归档的独立 `helium-macos` 仓库作为默认开发入口。

## 命令入口（优先这些，勿自创流程）

```bash
# hot-dev：秒级 / 分钟级
python3 devutils/syntax_check.py [-o build/src/out/Default] FILE...
python3 devutils/build_targets.py [--from-failed] [target...]

# export 某个 patch
python3 devutils/agent_patch_guard.py --mode after-hotfix --patch helium/core/xxx.patch

# 改了 patches 或交付前
python3 devutils/agent_patch_guard.py --mode patch-source
# 或
python3 .codex/skills/nitrous-validate/scripts/run_validation.py
python3 .codex/skills/nitrous-validate/scripts/run_validation.py --full
python3 .codex/skills/nitrous-validate/scripts/run_validation.py --with-source --source-tree chromium_src

# 打包（仅 pre-build 通过后）
source platform/macos/build.sh
he auto-package
```

环境变量优先 `NITROUS_*`，回退 `HELIUM_*`（`NITROUS_OUT_DIR` / `NITROUS_BUILD_ROOT` / `NITROUS_QUILT_SRC` 等）。

## 污染处理

发现 quilt 状态与源码不一致、重复 applied、异常 `.orig`、`check_chromium_src_clean` 失败 → **重建该树**，不要在脏树上硬推。

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
