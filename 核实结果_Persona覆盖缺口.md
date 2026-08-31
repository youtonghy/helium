# Persona 覆盖缺口核实结果

日期：2024 年（基于 Chrome 149 / Nitrous 当前源码）

## 核实方法

1. 查看 `docs/persona-fingerprint-lifecycle.md` 了解 Persona 覆盖范围声明
2. 查看 `patches/helium/core/persona-*.patch` 验证实际实现
3. 对照用户列出的 10 个"仍能关联设备或拆穿 OS"的问题逐项核实

## 核实结论

**用户列出的问题清单基本真实**，但需要区分三个层次：

### A 类：确认存在且影响大（高优先级）

| # | 问题 | 核实结果 | 证据 |
|---|------|----------|------|
| 1 | **WebGL/WebGPU 真实能力** | ✅ **部分真实** | `persona-webgl-readpixels-noise.patch` 只对 `GL_ALIASED_LINE_WIDTH_RANGE` / `GL_ALIASED_POINT_SIZE_RANGE` / `GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT` / `getShaderPrecisionFormat` 加了 `kHardware` 噪声，**但未覆盖 `getSupportedExtensions()`**。WebGPU 有 `adapter.info` 覆盖（architecture/device/description）和 capability profile 限制（只暴露 core-features-and-limits / portable baseline limits），**但 `getSupportedExtensions()` 返回的扩展列表仍是真实 GPU 的** |
| 2 | **CSS `matchMedia`** | ✅ **完全真实** | 未找到任何 patch 覆盖 `matchMedia` / `prefers-color-scheme` / `prefers-reduced-motion` / `hover` / `pointer` / `color-gamut` / `dynamic-range` / `forced-colors`。`persona-state-management.patch` 只有 `screen.colorGamut` / `screen.dynamicRange` **存储字段**，但没有接入 CSS 媒体查询 |
| 5 | **字体像素** | ✅ **真实** | `persona-local-fonts-access.patch` / `persona-font-probing-virtualization.patch` 只控制了**字体名称列表**和 font metric token（度量噪声）。光栅化仍是本机 CoreText / DirectWrite，用 canvas 测 emoji / CJK 像素哈希可以区分 macOS / Windows / Linux 渲染引擎 |

### B 类：存在但已有部分缓解（中优先级）

| # | 问题 | 核实结果 | 证据 |
|---|------|----------|------|
| 3 | **真实视口** | ✅ **部分真实** | `persona-navigator-runtime-overrides.patch` **覆盖了 `outerWidth/Height`**（`:1619` / `:1624`），但 **`innerWidth/Height` / `visualViewport` / `screenX/Y` 未覆盖**。滚动条宽度（`innerWidth - clientWidth`）仍暴露操作系统 |
| 4 | **音频硬件** | ✅ **部分真实** | `persona-runtime-capability-assurance.patch` **覆盖了 `baseLatency` / `outputLatency`**（`:942` 验证它们与 snapshot 一致），**但 `AudioContext.sampleRate` / `destination.maxChannelCount` 未覆盖**。`persona-state-management.patch:3480` 只从 preset 读取 `audio_base_latency` / `audio_output_latency`，没有 `sampleRate` 字段 |

### C 类：存在且完全未覆盖（需评估优先级）

| # | 问题 | 核实结果 | 证据 |
|---|------|----------|------|
| 6 | **键盘布局** | ✅ **真实** | 未找到覆盖 `navigator.keyboard.getLayoutMap()` 的 patch |
| 7 | **编解码能力** | ✅ **真实** | 未找到覆盖 `MediaSource.isTypeSupported` / `MediaCapabilities` / WebCodecs 的 patch |
| 8 | **系统主题色** | ✅ **真实** | 未找到覆盖 CSS 系统色（`ButtonFace` / `Highlight`）或原生控件观感的 patch |
| 9 | **外设枚举** | ✅ **部分真实** | `persona-interface-binder-fail-closed.patch` **未找到 Bluetooth / USB / HID / Serial 的 fail-closed 门控**（搜索这些关键词无结果）。摄像头/麦克风有 `persona-media-devices-override.patch` 的合成设备 + fail-closed，相对安全 |
| 10 | **其它边角** | ✅ **真实** | `Screen.orientation` / `storage.estimate()` / `getDisplayMedia` / Apple Pay / File System Access / Compute Pressure / Wake Lock / WebSensor binder 均未找到覆盖 patch |

## 不在问题清单但需注意的发现

### 已有覆盖但实现尚待完善

1. **WebGL `getSupportedExtensions()` 漏网**：`persona-webgl-readpixels-noise.patch` 只覆盖了部分数值参数和 shader precision，但 **`getSupportedExtensions()` 返回的字符串数组仍是真实 GPU 的**，这是 WebGL fingerprinting 的经典手法（Apple GPU 支持的扩展集与 Intel / NVIDIA / AMD 明显不同）

2. **`kHardware` token 生成但未完整消费**：`plans/persona-defects-fix-plan-v2.md` 已经发现 `kHardware` 是"生成了 token 但零消费者"，当前 patch 只在 4 个 WebGL 数值读取点用了它，**`getSupportedExtensions()` / 其它 GPU 能力查询仍然漏网**

3. **音频采样率与声道数漏网**：只覆盖了 `baseLatency` / `outputLatency`，**`AudioContext.sampleRate` 和 `destination.maxChannelCount` 仍是真实硬件**。macOS 常见 44100/48000 Hz，Windows 可能不同

### 文档已声明的限制（不算缺口）

1. **字体光栅化像素**：`persona-fingerprint-lifecycle.md` 明确写明"font rasterization, GPU drivers, TCP stack, and platform authenticators cannot be reproduced 100% on a macOS Chromium host"，字体度量有噪声但像素仍是本机渲染

2. **WebGPU shader 执行**：文档写明"WebGPU shader execution and subgroup behavior...require separate, opt-in observation. The overall probe therefore remains partial"

3. **`getDisplayMedia`**：文档明确说"keeps normal Chromium behavior"

## 与计划修复的对应关系

### 已在修复计划中

- **`kHardware` token 补齐**：`plans/persona-defects-fix-plan-v2.md` 的 P1-2 已计划补齐 WebGL 参数/精度噪声（当前实现只覆盖了 4 个点，需要扩展到 `getSupportedExtensions()` 等更多面）

- **20+ `allow*` 权限开关**：P1-3 计划分批实现，其中包括：
  - 批次 A：通过 `PermissionType` 门控 `GEOLOCATION` / `NOTIFICATIONS` / `MIDI` / `CLIPBOARD` / `IDLE_DETECTION` / `WINDOW_MANAGEMENT` / `SENSORS` / `NFC`（对应问题 #9 的部分）
  - 批次 B-2：`allow_real_battery_status` / `allow_platform_credentials` / `allow_web_printing` / `allow_shape_detection` / `allow_web_otp` / `allow_web_xr`（对应问题 #10 的部分）

### 不在当前修复计划中

1. **CSS `matchMedia`**（问题 #2）：虽然 `persona-state-management.patch` 有 `screen.colorGamut` / `screen.dynamicRange` 字段，但**未接入 CSS 媒体查询引擎**，没有计划补齐
2. **`innerWidth/Height` / `visualViewport`**（问题 #3）：只覆盖了 `outerWidth/Height`，内部视口仍漏网
3. **音频采样率与声道数**（问题 #4）：只覆盖了 latency，`sampleRate` / `maxChannelCount` 不在计划
4. **键盘布局**（问题 #6）：无计划
5. **编解码能力**（问题 #7）：无计划
6. **系统主题色**（问题 #8）：无计划
7. **Bluetooth / USB / HID / Serial**（问题 #9）：不在 P1-3 的 20 项清单

## 推荐优先级

基于"最低成本拆穿声称 OS"的标准，建议优先级：

### P0（最容易拆穿，成本最低）

1. **CSS `matchMedia`**：一行 JS 读 `prefers-color-scheme` / `hover` / `pointer` 就能拆穿声称 Windows 实际是 macOS
2. **WebGL `getSupportedExtensions()`**：Apple GPU 的扩展集与 Intel / NVIDIA / AMD 完全不同，FingerprintJS / CreepJS 都在用

### P1（成本较低，覆盖面大）

3. **音频采样率**：`AudioContext.sampleRate` 是单行 JS，44100 vs 48000 能区分平台
4. **`innerWidth/Height`**：已有 `outerWidth/Height` 实现，补齐成本低
5. **编解码能力**：HEVC / AC-3 是平台相关，但需要逐个 codec 测试

### P2（成本较高或影响面小）

6. **字体像素**：名称列表已覆盖，光栅化需要深度改 Skia / CoreText，成本极高
7. **键盘布局**：需要用户主动调用 `getLayoutMap()`，被动暴露面小
8. **系统主题色**：CSS 系统色需要改渲染引擎，成本高
9. **外设枚举**：需要用户授权，被动暴露面小

## 总结

用户的问题清单**基本准确**，10 个问题中：

- **3 个已部分覆盖但仍有漏网**（WebGL 能力、真实视口、音频硬件）
- **7 个完全未覆盖**（CSS matchMedia、字体像素、键盘布局、编解码、主题色、外设、其它边角）

最容易拆穿"声称 Windows 实际是 macOS"的是：

1. CSS `matchMedia('(prefers-color-scheme: dark)')` 或 `matchMedia('(hover: hover)')`
2. WebGL `getSupportedExtensions()` 返回 Apple GPU 独有的扩展
3. `AudioContext.sampleRate` 暴露真实采样率

建议优先补齐 CSS `matchMedia` 和 WebGL `getSupportedExtensions()`，它们成本低、覆盖面大、拆穿效果最明显。
