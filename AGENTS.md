# Nitrous — Agent 准则（唯一权威）

`CLAUDE.md` 符号链接到本文件（本文件是实体）。其它路径下的 AGENTS 副本一律无效。

skill 实体在 `.codex/skills/`；`.claude/skills/` 下是指向它的符号链接，供 Claude Code 发现（Claude Code 只扫 `.claude/skills/`、`~/.claude/skills/` 和插件目录，不读 `.codex/`）。改 skill 时改 `.codex/` 下的实体，不要改链接。

对话回复统一使用中文；SKILL.md 与代码注释保持仓库原有语言。

**涉及改源码 / 改 patch / 修编译 / export 时：必须先按 `$nitrous-dev` 执行。**  
**任何产生仓库修改的任务在交付前：必须通过 `agent_patch_guard --mode pre-build`。**

## 总原则

1. 开发期只写热树；交付期才 export 到 `patches/`；验证树只读。
2. 禁止手改 `.patch` 的 diff 正文（只允许 quilt-fix / guard 写回）。
3. 长期有效修改必须落在 `patches/**`、`patches/series` 或本仓库源文件。
4. 跟上游时 `patches/helium/**` 是 **vendor 路径名**，不要为品牌全局改名。
5. `he` 是平台构建命令前缀，与产品名无关。
6. `quick`、`patch-source`、`run_validation.py` 和测试都是中间反馈；不能替代最终 `pre-build` 交付门禁。
7. **编译由用户在功能模块攒够后统一执行，agent 运行期不编译。** 见下节。

## 编译分工（agent 运行期硬约束）

**agent 在编辑后只跑验证，不准启动编译。** 用户的流程是先完成多个功能模块，最后自己统一编译。冷树全量编译动辄几十分钟，agent 在中途触发它会白烧时间，还会因为半途中断留下不完整的 `out/Default`。

agent **允许**跑（都是分钟级以内、不产出编译产物）：

```bash
python3 devutils/agent_patch_guard.py --mode hot-start|hot-add|hot-abort
python3 devutils/agent_patch_guard.py --mode export-hotfix
python3 devutils/agent_patch_guard.py --mode patch-source
python3 devutils/agent_patch_guard.py --mode pre-build      # 交付门禁，不含 C++ 编译
python3 .codex/skills/nitrous-validate/scripts/run_validation.py [--ci-env --keep-going|--full|--with-source]
python -m yapf --style .style.yapf -e '*/third_party/*' -rpd devutils utils
```

agent **禁止**跑（只有用户显式要求构建/出包时才可以）：

```bash
he build / he auto-build / he package / he auto-package / he configure
python3 devutils/build_targets.py ...
gn gen ...
```

`devutils/syntax_check.py` 是灰色地带：它直接调编译命令，热树已有生成依赖时是秒级反馈，可以用；但**不准为了让它通过而去跑 `build_targets.py` 补生成依赖**。缺生成头时按「验证边界」处理——记为未验证，不是源码错误，留给用户的统一编译暴露。

交付说明里必须写清「validation 通过，编译未运行」，不得暗示源码已编译通过。

增量编译是天然支持的：`he auto-package` 的 `___helium_build_products` 直接调 `autoninja`(siso)，`___helium_auto_prepare` 的 `ensure_*` 全是幂等 guard（source / merged queue / patches applied / GN 各自判定后跳过）。所以用户最后跑一次 `he auto-package` 会自动只编译改动部分，不需要 agent 预热。唯一会破坏增量的是 `___helium_ensure_merged_queue` 在 patch queue stale 时 `quilt pop -a` 再 merge——所以 agent 迭代期间不要反复 export patch、也不要 `he merge && he push`。

## 任务模式（动手前必须选一）

| 模式 | 何时 | 可写 | 禁止 | 收尾 |
|------|------|------|------|------|
| `explore` | 只读调查 | 无 | 一切写 | — |
| **`hot-dev`（默认）** | 功能 / 修编译 | 仅已声明的 `build/src` 文件 | 未 `hot-start` 就编辑、每轮 `he merge&&he push`、任何全量编译 | `run_validation.py`（可选 `syntax_check`，前提是生成依赖已在） |
| `export-patch` | 已有 hot-start 会话要交付 | guard staging 后写 `patches/` | 覆盖已有 patch、整文件回灌旧 patch | `agent_patch_guard --mode export-hotfix`，然后 `--mode cleanup` |
| `patch-fix` | apply 冲突 / 合上游 | patchwork + series | 热树当 SoT | `agent_patch_guard --mode patch-source` |
| `package` | 出包 | 平台脚本（慎） | 未过 pre-build 就 package | guard pre-build 后 `he *` |

未声明模式时按 **`hot-dev`**。`hot-dev` 结束时不得声称 patch 已交付。

## 目录职责

| 路径 | 用途 | 可写 | 交付后 |
|------|------|------|--------|
| `build/src` | 热增量开发 / 编译 | `hot-dev` | `cleanup` 删除 |
| `codex_tmp/patchwork_src` | quilt 开发与 refresh | `export-patch` / `patch-fix` | `cleanup` 删除 |
| `codex_tmp/patchcheck_src` | fresh apply 验证 | 否（每次重建） | `cleanup` 删除 |
| `chromium_src` | clean baseline 验证 | 否 | 保留 |
| `patches/` | Chromium 侧修改 SoT | 仅经 quilt-fix / guard | 保留 |
| `platform/macos/` | macOS 构建与打包 | 包装层问题 | 保留 |
| `devutils/i18n-data/` | 历史/参考，非默认打包入口 | 否（除非修它本身） | 保留 |

## 硬禁止

- 在 `chromium_src` / `patchcheck_src` 写业务或做破坏性实验。
- 手改 patch hunk 行号 / diff 正文来「对齐」。
- 未先运行 `hot-start` 就把热树修改自动导出，或把完全 applied 热树整文件复制进旧 patch。
- 只删 `.pc/` 假装干净（源码仍可能已被 patch）。
- 热树迭代中每轮 `he merge && he push`（会打烂 siso 增量）。
- **agent 运行期启动编译**：`he build` / `he auto-build` / `he auto-package` / `he configure` / `build_targets.py` / `gn gen`。只有用户显式要求构建或出包时才允许。
- 为了让 `syntax_check.py` 通过而跑 `build_targets.py` 补生成依赖。
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

# 秒级编译反馈（仅当热树已有相关生成依赖；缺依赖时放弃，不要补构建）
python3 devutils/syntax_check.py [-o build/src/out/Default] FILE...

# 定向编译：agent 禁用，仅用户排查编译错误时执行
python3 devutils/build_targets.py [--from-failed] [target...]

# 与 CI 精确一致的本地校验（pin 版本 venv；一轮报全部失败）
python3 .codex/skills/nitrous-validate/scripts/run_validation.py --ci-env --keep-going

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

# 交付完成后回收一次性树（打印回收空间；不动 patches/ 与 chromium_src）
python3 devutils/agent_patch_guard.py --mode cleanup

# 打包（用户操作；仅 pre-build 通过 + 用户显式要求时。agent 不得自行执行）
source platform/macos/build.sh
he auto-package
```

最终门禁失败时必须先修复并重跑，不得把任务报告为完成。该要求只执行与 `he auto-package` 相同的前置检查，不要求实际执行 `he auto-package`；只有用户要求构建或出包时才运行打包命令。纯只读调查不需要运行。

## 垃圾清理（交付后必做）

一次性源码树是本地磁盘的主要负担：`build/src` 约 15 G，`codex_tmp/*_src` 每棵 2–10 G。`export-hotfix` 只删自己的 `codex_tmp/hot-export` 会话，其余全部滞留，一轮任务可积累 40 G+。

```bash
python3 devutils/agent_patch_guard.py --mode cleanup
```

- 删除：`build/src`、`codex_tmp/patchcheck_src`、`codex_tmp/patchwork_src`，以及其它 `codex_tmp/*_src` 验证树。
- 保留：`patches/`、`patches/series`、`chromium_src`、`chromium_download_cache` 和一切 git 跟踪文件。
- 会先打印待删列表与合计体积，再逐棵删除并报告实际回收量。

时机：**在交付（`pre-build` 通过）之后**执行，不要插在中间验证之间——`patch-source` / `pre-build` 会自己重新解包 `patchcheck_src`，提前清理只会让下一次验证重新下载解包。

清理后热树不存在，用户下次统一编译会重建它；这与「export 发布后 root 队列已前进、热树必须重建」的要求方向一致。

## 验证边界（必须区分）

- `pre-build` 不包含 Chromium C++ 编译；它通过只代表仓库检查、patch fresh-apply 和 source-backed validation 通过，不得据此声称源码可编译。
- `GN output ready` 只代表构建图和 `compile_commands.json` 已生成，不代表 `out/Default/gen` 下的 mojom、GRIT、protobuf 等生成文件存在。
- `syntax_check.py` 直接调用编译命令，不会像 Ninja 一样先构建生成依赖。仅在热树已具备相关生成文件时使用它作为快速反馈。
- 冷树或重建后的树中，如果 `syntax_check.py` 因缺少 `out/Default/gen/...`、`*.mojom-forward.h`、`precompile.h-cc` 等生成产物失败，**这不是源码编译失败，也不要跑 `build_targets.py` 去补**。按「该文件未做编译验证」记录，留给用户的统一编译暴露。
- 只有用户显式要求构建、打包或证明可编译时，才运行定向 target 或实际构建；此时若 Ninja target 自身失败，报告最早的真实构建错误，不要用后续缺文件错误覆盖它。
- Chromium 源码任务的交付说明必须分开列出 `pre-build` 与编译证据。agent 常态下只能声明 validation 通过，并明确写出「编译未运行」；不得据此暗示源码可编译。
- 交付话术固定为「验证通过 + patch 已干净迁移回 `patches/`」，并写明「编译正确性留待用户统一编译」。**不得声称「下次编译不会出错」**——`pre-build` 证明的是 patch 可套用与仓库检查，不是可编译性。

## 本地与 CI 的等价边界

本地通过能预测 CI 通过，**仅限仓库自身可控的检查**。以下四类漂移都曾把本地绿变成 CI 红，现已各有机制兜住：

| 漂移 | 症状 | 机制 |
|------|------|------|
| 工具版本 | 本地与 pin 的 yapf/pylint 判断相反 | `--ci-env` 建 pin venv；版本不一致时告警 |
| 系统二进制 | 本地有 `quilt`，CI 没装 | `.ci_system_packages.txt` 单一来源，两侧校验 |
| 空 scope | 改动已 commit → diff 为空 → 零检查却报成功 | 默认 diff base 改为 upstream merge-base；门禁加 `--require-checks` |
| 源码树过期 | 复用的 `chromium_src` 缺新增依赖 | `--with-source` 前校验 manifest 组件齐备 |

边界之外（CI 兜底，本地无法复现）：runner 镜像漂移、`Retrieve Chromium source archive` 回退 `clone.py` 的路径。

改 `devutils` / `utils` 且本地版本与 pin 不一致时，用 `--ci-env` 取得精确一致；`--keep-going` 一轮列出全部失败，避免被 CI 的 fail-fast 逐个掩盖。

环境变量优先 `NITROUS_*`，回退 `HELIUM_*`（`NITROUS_SRC_DIR` / `NITROUS_OUT_DIR` / `NITROUS_BUILD_ROOT` / `NITROUS_MERGED_PATCHES_DIR` / `NITROUS_QUILT_SRC` 等）。

## 污染处理

发现 quilt 路径/series/applied 状态与当前合并队列不一致、重复 applied、异常 `.orig`、`check_chromium_src_clean` 失败 → **重建该树**，不要在脏树上硬推。自动 export 发布后 root 队列已前进，热树也已过期，用 `--mode cleanup` 回收后交给用户下次编译重建。

```bash
# 一次性树统一回收（等价于手工 rm -rf，并会报告回收空间）：
python3 devutils/agent_patch_guard.py --mode cleanup
# 主验证树：
rm -rf chromium_src && python3 ./utils/downloads.py unpack -i downloads.ini -c chromium_download_cache chromium_src
# 热树重建（含编译，属于用户操作；agent 只能提出需要重建，不要自己执行）：
source platform/macos/build.sh && he auto-package   # 或分步 presetup/merge/push
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

## 交付说明

成功交付时按顺序写清四件事：

1. 跑通的 guard 模式（validation 通过）
2. patch 已写回 `patches/` + `patches/series`，root 与 macOS 队列 fresh-apply 通过
3. 编译未验证，留待用户统一编译
4. `cleanup` 回收了哪些树、多少空间

验证失败时必写：

- 失败命令与原因  
- 哪棵源码树可能污染  
- 是否需要重建 `chromium_src` / `codex_tmp/*` / `build/src`  

详细逐步流程见 `$nitrous-dev` 与 `$nitrous-validate`，不要在本文件外再维护平行长规范。
