  - 用 Context7 查最新文档。
- 先把架构方向和功能目标用通俗方式对齐。
- 尽量简化代码，避免过度防御。
- 能并行的地方优先用 subagents。
- 先确认“做什么、实现什么”，再动手改代码。
- 对适合并行的工作，subagents 优先用于 read-heavy 的探索、日志分析、测试分析、代码审查和候选方案生成；不要让多个 agent 同时修改同一批文件。
- subagent 可以并行生成候选 patch 或修改建议，但最终只能由主 agent 统一应用、统一刷新 patch、统一验证。

## 通用验证规范

- 改 `devutils` / `utils` 时，按 CI 同款格式检查：

  ```bash
  python -m yapf --style .style.yapf -e '*/third_party/*' -rpd devutils
  python -m yapf --style .style.yapf -e '*/third_party/*' -rpd utils
  ```

- 每次编辑代码、配置、补丁、i18n、脚本或项目说明后，使用项目 skill `$helium-validate` 收尾验证：

  ```bash
  python3 .codex/skills/helium-validate/scripts/run_validation.py
  ```

- 影响面不明确、跨模块、CI 配置、source list、i18n、脚本或交付前，运行：

  ```bash
  python3 .codex/skills/helium-validate/scripts/run_validation.py --full
  ```

- 改补丁或 source list，且本地有 Chromium source tree 时，补跑：

  ```bash
  python3 .codex/skills/helium-validate/scripts/run_validation.py --with-source --source-tree chromium_src
  ```

- 需要复刻 CI 下载/解包源码时，才显式加：

  ```bash
  python3 .codex/skills/helium-validate/scripts/run_validation.py --prepare-source
  ```

- 如果验证失败，交付时必须说明：

  - 失败命令
  - 具体阻塞原因
  - 当前源码树是否可能污染
  - 是否需要重建 `chromium_src`、`codex_tmp/patchwork_src`、`codex_tmp/patchcheck_src` 或 `devutils/i18n-data/macos/build/src`

- 不要把会自动改文件的 `devutils/check_all_code.sh` 当作默认收尾验证。

## Patch 规范

### 核心原则

- 当前仓库 `/Users/youtonghy/github/Project/Nitrous/helium` 是补丁、`patches/series`、校验脚本和 Chromium 侧源码修改的 source of truth。
- macOS 最终集成、`he *` 工作流、产物构建与打包必须在 `/Users/youtonghy/github/Project/Nitrous/helium-macos` 仓库中进行，不要在当前仓库内直接起最终打包。
- 当前仓库中的 `devutils/i18n-data/macos` 仅可作为参考脚本、历史兼容入口或排障样本，不作为今后默认的 macOS 打包入口；除非明确说明是在修这里本身，否则不要从这里启动最终编译。
- `chromium_src` 是 pristine / clean source tree，只作为补丁验证基准，不作为日常 quilt 开发树。
- `devutils/i18n-data/macos/build/src`、`/Users/youtonghy/github/3p/helium-macos/build/src` 这类已打补丁或构建流程生成的源码树，只能用于观察最终目标状态、排查编译错误、对比代码结果，不能作为 patch source of truth，也不能作为 source-backed 验证源。
- 所有长期有效修改必须落到 `patches/**/*.patch`、`patches/series` 或仓库源文件中。
- 禁止在污染状态下继续运行 `he merge`、`he push`、`he configure` 或 `he build`。
- 如果 quilt 状态和源码内容不一致，必须先重建对应源码树，不能继续硬推 patch。

### 仓库分工

- 在 `helium` 仓库中做：

  - 维护 `patches/**/*.patch`、`patches/series`、`devutils`、`utils`、校验脚本与相关文档。
  - 进行 fresh source patch apply 验证、source-backed 验证和 cheap validation。
  - 调整 Chromium 侧逻辑、品牌、资源或补丁顺序。

- 在 `helium-macos` 仓库中做：

  - 运行 `source dev.sh`、`he presetup`、`he merge`、`he push`、`he configure`、`he build`。
  - 检查 `.app`、签名、DMG、entitlements、bundle id、macOS 打包脚本和最终产物命名。
  - 处理 macOS 仓库自身的包装层问题；如果问题根源在 Chromium patch，则回到当前仓库修补丁，再重新同步到 `helium-macos`。

- 默认工作顺序：

  1. 先在当前 `helium` 仓库完成补丁修改与验证。
  2. 确认 cheap validation / source-backed validation 通过。
  3. 再切到 `/Users/youtonghy/github/Project/Nitrous/helium-macos` 执行 `he *` 构建流程。
  4. 不要在当前仓库里直接把 `devutils/i18n-data/macos` 当作最终打包工作区。

### 目录职责

- `chromium_src/`

  - 只用于 clean baseline 验证。

  - 必须保持未打补丁状态。

  - 不允许长期保留 `.pc/`、`*.orig`、已应用 patch 内容或手动修改。

  - 进入 patch 验证前必须通过：

    ```bash
    python3 devutils/check_chromium_src_clean.py --source-tree chromium_src
    ```

- `codex_tmp/patchwork_src/`

  - 专门用于 quilt 开发、修补和 refresh patch。
  - 可以被 `quilt push`、源码编辑、临时编译尝试、`quilt refresh`、`quilt pop` 使用。
  - 可以随时删除重建，不作为最终产物。

- `codex_tmp/patchcheck_src/`

  - 专门用于 fresh source patch apply 验证。
  - 每次验证前删除并重新解包。
  - 不允许手动修改。

- `devutils/i18n-data/macos/build/src`

  - 只作为 macOS i18n / Helium 构建流程生成的构建树。
  - 可以读取、搜索、对比、排查错误。
  - 禁止把这里的修改直接当作最终 patch 结果。
  - 禁止在这里手动修 quilt 状态。

### 修改 patch 的标准流程

1. 开始前先确认主验证树干净：

   ```bash
   python3 devutils/check_chromium_src_clean.py --source-tree chromium_src
   ```

   如果失败，先重建：

   ```bash
   rm -rf chromium_src
   python3 ./utils/downloads.py unpack -i downloads.ini -c chromium_download_cache chromium_src
   python3 devutils/check_chromium_src_clean.py --source-tree chromium_src
   ```

2. 创建独立 quilt 开发树：

   ```bash
   rm -rf codex_tmp/patchwork_src
   python3 ./utils/downloads.py unpack -i downloads.ini -c chromium_download_cache codex_tmp/patchwork_src
   ```

3. 在独立开发树中载入 quilt 环境：

   ```bash
   source devutils/set_quilt_vars.sh
   ```

   如果脚本默认指向 `chromium_src`，必须调整环境变量或脚本参数，使 quilt 操作目标指向 `codex_tmp/patchwork_src`，而不是主 `chromium_src`。

4. 使用 quilt 应用到目标 patch：

   ```bash
   quilt push <patch-name>
   ```

   或应用到目标 patch 前一层后新增修改。

5. 只在 `codex_tmp/patchwork_src` 中编辑源码。

   禁止直接通过文本替换或普通编辑器手改 `.patch` 文件里的 diff 代码块，除非只是修补元信息、注释或明显不涉及 hunk 的非代码内容。

6. 修改完成后 refresh patch。

   优先使用仓库封装脚本：

   ```bash
   ./devutils/quilt-fix.sh <patch-name>
   ```

   不要直接使用裸 `quilt refresh`，除非确认仓库当前流程明确接受它生成的路径前缀和元信息。

7. quilt 操作完成后，清理开发树状态：

   ```bash
   quilt pop -a || true
   find codex_tmp/patchwork_src -name '*.orig' -delete
   rm -rf codex_tmp/patchwork_src/.pc
   ```

8. 检查 `patches/series`：

   - 新增 patch 必须加入 `patches/series`。
   - 删除 patch 必须从 `patches/series` 移除。
   - 移动 patch 顺序时必须确认没有重复覆盖同一段代码。
   - 避免 orphan patch 留在树里。
   - 避免同一修改被两个 patch 重复覆盖。

### Fresh source 验证流程

每次 patch 变更后，先用全新临时树验证，不要直接信任当前工作树：

```bash
rm -rf codex_tmp/patchcheck_src
python3 ./utils/downloads.py unpack -i downloads.ini -c chromium_download_cache codex_tmp/patchcheck_src
python3 devutils/check_chromium_src_clean.py --source-tree codex_tmp/patchcheck_src
./devutils/validate_patches.py -l codex_tmp/patchcheck_src -v
```

这一步通过后，再运行项目 skill 验证：

```bash
python3 .codex/skills/helium-validate/scripts/run_validation.py --with-source --source-tree chromium_src
```

影响面不明确、跨模块、涉及 CI 配置、source list、i18n、脚本或交付前，继续运行：

```bash
python3 .codex/skills/helium-validate/scripts/run_validation.py --full
```

### macOS i18n / Helium 构建验证流程

只有在 cheap validation 全部通过后，才允许进入 macOS 构建流程。

macOS 最终构建必须在 `/Users/youtonghy/github/Project/Nitrous/helium-macos` 仓库执行，不要在当前仓库中直接运行下面这些命令。

推荐顺序：

```bash
cd /Users/youtonghy/github/Project/Nitrous/helium-macos
source dev.sh
he presetup
he merge
he push
```

在 `he merge && he push` 之后，先检查构建树 quilt 状态是否合理。若出现以下任意情况，禁止继续 `he configure` 或 `he build`：

- `.pc/` 存在但 quilt 显示 `No patches applied`
- 源码内容明显已经带有 patch 结果，但 quilt 状态为空
- `applied-patches` 中出现重复 patch
- 构建树中存在未解释的 `*.orig`
- `he push`、`validate_patches.py` 或 `run_validation.py --with-source` 失败

只有前置状态正常后，才允许继续：

```bash
he configure
he build
```

如果需要签名、封装、DMG 或最终 `.app` 检查，也应继续留在 `helium-macos` 仓库处理，不要切回当前仓库里的 `devutils/i18n-data/macos`。

### 污染树处理规则

如果发现任一源码树出现 patch 状态污染，不要继续在原树上修。

典型污染状态包括：

- 源码已经包含旧 patch 结果，但 quilt 显示 `No patches applied`
- `.pc/` 仍存在，但 `applied-patches` 不可信
- `applied-patches` 有重复条目
- `validate_patches.py` 报 patch 已应用、反向 patch、hunk 偏移异常或 source tree 不干净
- `check_chromium_src_clean.py` 失败
- 构建树和 patch 队列内容无法对应

处理方式：

```bash
rm -rf codex_tmp/patchwork_src codex_tmp/patchcheck_src
```

如果是主验证树污染：

```bash
rm -rf chromium_src
python3 ./utils/downloads.py unpack -i downloads.ini -c chromium_download_cache chromium_src
python3 devutils/check_chromium_src_clean.py --source-tree chromium_src
```

如果是 macOS 构建树污染：

```bash
cd /Users/youtonghy/github/Project/Nitrous/helium-macos
rm -rf build/src
source dev.sh
he presetup
he merge
he push
```

禁止通过手动删除 `.pc/` 来“假装干净”，除非该树会被立即删除或完整重建。删除 `.pc/` 不能修复已经被 patch 改过的源码内容。

### Agent 行为约束

- 不要在 `chromium_src` 上做破坏性 patch 实验。
- 不要在 `devutils/i18n-data/macos/build/src` 中直接修最终代码。
- 不要在当前 `helium` 仓库里直接启动最终 macOS 打包；默认应切到 `/Users/youtonghy/github/Project/Nitrous/helium-macos` 后再运行 `he *`。
- 不要把 `.pc/` 删除当成清理完成；必须同时确保源码内容回到 pristine。
- 不要在 cheap validation 失败时启动完整编译。
- 不要为了修 hunk 行号直接手改 patch diff 代码块。
- 不要同时让多个 subagent 修改同一组 patch 或同一批源码文件。
- 可以让 subagent 并行阅读、定位问题、生成候选 patch 方案，但最终只能由主 agent 统一应用和刷新 patch。

### 完整编译前的最低验证门槛

完整编译前必须至少通过：

```bash
python3 devutils/check_chromium_src_clean.py --source-tree chromium_src
rm -rf codex_tmp/patchcheck_src
python3 ./utils/downloads.py unpack -i downloads.ini -c chromium_download_cache codex_tmp/patchcheck_src
python3 devutils/check_chromium_src_clean.py --source-tree codex_tmp/patchcheck_src
./devutils/validate_patches.py -l codex_tmp/patchcheck_src -v
python3 .codex/skills/helium-validate/scripts/run_validation.py --with-source --source-tree chromium_src
```

只有这些通过后，才允许运行：

```bash
cd /Users/youtonghy/github/Project/Nitrous/helium-macos
source dev.sh
he presetup
he merge
he push
he configure
he build
```
