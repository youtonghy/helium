# Persona 运行期注入完善计划

## 问题诊断

### 核心病因：UI 暴露了 80+ 字段，但 runtime 只实现了一小部分

```
设置页 (persona-settings-ui.patch)
    ↓ SavePersona → prefs["helium.persona.state"]
    ↓ GetActiveSnapshot() ← 只提取 UA/UA-CH 字段
    ↓ HeliumPersonaSnapshot (struct) ← 只有 15 个字段
    ↓ 唯一消费者: SharedWorker 创建路径
    ↓ (主框架/普通页面: 无任何 hook)
```

### 三个问题的根因

#### 1. Persona 设置不生效

| 层级 | 状态 | 证据 |
|------|------|------|
| UI 保存 | ✅ 正常 | `SavePersona()` 写入 prefs，`SetActivePersona()` 切换 active ID |
| Snapshot 结构 | ❌ 缺字段 | `persona-state-management.patch:200` — 只有 `user_agent`, `accept_language`, `ua_ch_*`，缺 `timezone`, `locale`, `platform`, `hardwareConcurrency`, `deviceMemory`, `screen.*`, `gpu.*`, `font.*` |
| `GetActiveSnapshot()` | ❌ 不提取 | `:1216-1299` — 只读 UA 相关字段，其余 UI 字段被丢弃 |
| Mojom 序列化 | ❌ 缺字段 | `persona_snapshot_mojom_traits.h` 只序列化 struct 里已有的字段 |
| 主框架注入 | ❌ 不存在 | 无任何 patch hook 了 `NavigatorBase::platform`, `NavigatorLanguage`, `TimeZoneController`, `Screen`, `NavigatorBase::hardwareConcurrency` 等 |
| SharedWorker 注入 | ⚠️ 部分 | `persona-background-worker-snapshot-propagation.patch` 只覆盖 UA + UA-CH metadata |
| `persona_runtime_override.cc` | ❌ 空壳 | `ApplyGlobal() {}` / `ClearGlobal() {}` — 纯 stub |

`persona-privacy-sandbox-runtime-gates.patch` 开头的 `NavigatorLanguage::EnsureUpdatedLanguage`、`TimeZoneController::SetTimeZoneOverride`、`NavigatorBase::hardwareConcurrency`、`Screen::width()` 等全是 **validate_config token 注释**（`:1-13`），不是实现。

#### 2. Canvas 指纹未随机化

| 层级 | 状态 | 证据 |
|------|------|------|
| UI 开关 | ✅ 存在 | `persona-settings-ui.patch:693` — `canvasNoise: true` |
| Snapshot 传递 | ❌ 未传递 | `canvasNoise` 不在 `HeliumPersonaSnapshot` 中 |
| Noise token 基础设施 | ❌ 不存在 | 测试引用 `content/browser/helium_noise/noise_token_data.h` 和 `third_party/blink/public/common/helium_noise/noise_token.h`，但**没有任何 patch 创建这些文件** |
| Blink hook | ❌ 不存在 | Token 注释 `BaseRenderingContext2D::measureText` 只是注释，无实际代码 hook canvas readback |
| 测试 | ❌ 无法编译 | `persona-noise-token-determinism-test.patch` 引用了不存在的头文件和 snapshot 字段 |

#### 3. Audio 指纹未随机化

| 层级 | 状态 | 证据 |
|------|------|------|
| UI 开关 | ✅ 存在 | `persona-settings-ui.patch:694` — `audioNoise: true` |
| Snapshot 传递 | ❌ 未传递 | `audioNoise` 不在 `HeliumPersonaSnapshot` 中 |
| Blink hook | ❌ 不存在 | Token 注释 `BaseAudioContext::JitterAudioData` 只是注释 |
| 测试 | ❌ 同上 | 与 canvas 共用不存在的 noise token 基础设施 |

#### 4. 附加问题：测试 patch 引用了目标态代码

`persona-noise-token-determinism-test.patch` 的 `MakeSeededPersona()` 使用了 `snapshot.platform`, `snapshot.timezone`, `snapshot.locale`, `snapshot.navigator_languages`, `snapshot.gpu_vendor`, `snapshot.screen_width`, `snapshot.hardware_concurrency`, `snapshot.device_memory`, `snapshot.font_pack_id`, `snapshot.noise_seed`, `snapshot.passthrough`, `snapshot.id`, `snapshot.name`, `snapshot.device`, `snapshot.os` — **这些字段在当前 struct 中全部不存在**。

---

## 执行计划

### Phase 0: 准备工作

**目标**：建立干净的 quilt 开发环境

1. 确认 `chromium_src` 干净：
   ```bash
   cd helium
   python3 devutils/check_chromium_src_clean.py --source-tree chromium_src
   ```
2. 创建 quilt 开发树：
   ```bash
   rm -rf codex_tmp/patchwork_src
   python3 ./utils/downloads.py unpack -i downloads.ini -c chromium_download_cache codex_tmp/patchwork_src
   source devutils/set_quilt_vars.sh
   ```
3. quilt push 到 `persona-state-management`：
   ```bash
   quilt push persona-state-management.patch
   ```

---

### Phase 1: 扩展 Snapshot 结构（基础层）

**目标**：让 `HeliumPersonaSnapshot` 承载 UI 暴露的所有运行期字段

**修改文件**：`patches/helium/core/persona-state-management.patch`

#### 1.1 扩展 `HeliumPersonaSnapshot` struct

在 `third_party/blink/public/common/helium_persona/persona_snapshot.h` 中新增字段：

```cpp
struct HeliumPersonaSnapshot {
  // --- 现有字段保持不变 ---
  bool enabled = false;
  bool client_hints_enabled = true;
  // ... (现有 bool + UA 字段) ...

  // --- 新增：标识 ---
  std::string id;
  std::string name;
  bool passthrough = false;

  // --- 新增：Navigator ---
  std::string platform;           // navigator.platform (Win32 / MacIntel)
  std::string navigator_vendor;   // navigator.vendor
  std::string navigator_product_sub; // navigator.productSub
  std::string timezone;           // Intl timezone
  std::string locale;             // navigator.language
  std::vector<std::string> navigator_languages; // navigator.languages
  int hardware_concurrency = 0;   // navigator.hardwareConcurrency
  int device_memory = 0;          // navigator.deviceMemory
  int max_touch_points = 0;       // navigator.maxTouchPoints

  // --- 新增：Screen ---
  int screen_width = 0;
  int screen_height = 0;
  int avail_width = 0;
  int avail_height = 0;
  int outer_width = 0;
  int outer_height = 0;
  int color_depth = 0;
  int pixel_depth = 0;
  double device_scale_factor = 0;
  std::string orientation_type;

  // --- 新增：GPU ---
  std::string gpu_vendor;
  std::string gpu_renderer;
  std::string webgpu_adapter;

  // --- 新增：Font ---
  std::string font_pack_id;
  std::string font_rendering_engine;

  // --- 新增：Noise ---
  std::string noise_seed;
  bool canvas_noise = false;
  bool audio_noise = false;
  bool font_metric_noise = false;

  // --- 新增：Media ---
  double audio_base_latency = 0;
  double audio_output_latency = 0;

  // --- 新增：Network ---
  std::string network_type;
  double network_downlink_max = 0;
};
```

#### 1.2 扩展 `GetActiveSnapshot()` 提取逻辑

在 `persona_service.cc` 的 `GetActiveSnapshot()` 中，现有 UA 提取逻辑之后，新增：

- `snapshot.platform` ← `persona["platform"]`（注意：这是 navigator.platform，不是 uaCh.platform）
- `snapshot.timezone` ← `persona["region"]["timezone"]`
- `snapshot.locale` ← `persona["region"]["locale"]`
- `snapshot.accept_language` ← `persona["region"]["acceptLanguage"]`（已有）
- `snapshot.navigator_languages` ← 从 locale 派生 `["en-US", "en"]`
- `snapshot.hardware_concurrency` ← `persona["hardware"]["hardwareConcurrency"]`
- `snapshot.device_memory` ← `persona["hardware"]["deviceMemory"]`
- `snapshot.max_touch_points` ← `persona["hardware"]["maxTouchPoints"]`
- `snapshot.screen_*` ← `persona["screen"]["*"]`
- `snapshot.gpu_*` ← `persona["gpu"]["*"]`
- `snapshot.font_*` ← `persona["fonts"]["*"]` / `persona["fontRendering"]["*"]`
- `snapshot.canvas_noise` ← `persona["advanced"]["canvasNoise"]`
- `snapshot.audio_noise` ← `persona["advanced"]["audioNoise"]`
- `snapshot.noise_seed` ← `persona["id"]`（用 persona ID 作为确定性种子）
- `snapshot.audio_base_latency` ← `persona["mediaDevices"]["audioBaseLatency"]`
- `snapshot.network_type` ← `persona["network"]["type"]`

#### 1.3 扩展 Mojom traits

在 `persona_snapshot_mojom_traits.h` 中为每个新字段添加 `StructTraits` 特化。

在 `persona_snapshot.mojom` 中添加对应的 mojom struct 字段。

#### 1.4 验证

```bash
# Refresh patch
./devutils/quilt-fix.sh persona-state-management.patch

# Cheap validation
python3 .codex/skills/helium-validate/scripts/run_validation.py
```

---

### Phase 2: 主框架 Navigator 级覆盖（用户可见层）

**目标**：让 `navigator.platform`、`navigator.language`、`timezone`、`hardwareConcurrency` 等在普通页面中生效

**新建文件**：`patches/helium/core/persona-navigator-runtime-overrides.patch`（新 patch，插入 series 中 `persona-state-management` 之后）

#### 2.1 Navigator.platform 覆盖

Hook 点：`third_party/blink/renderer/core/frame/navigator_base.cc`

```cpp
// NavigatorBase::platform()
String NavigatorBase::platform() const {
  // Helium: check persona snapshot
  const auto& snapshot = GetHeliumPersonaSnapshot(GetExecutionContext());
  if (snapshot.IsEnabled() && !snapshot.platform.empty()) {
    return String::FromUTF8(snapshot.platform);
  }
  return RuntimeEnabledFeatures::WebComponentsV0Enabled() ? ... ;
}
```

需要确认 `GetExecutionContext()` → `GetBrowserContext()` → `GetHeliumPersonaSnapshot()` 的调用链在 renderer 侧可用。如果不可用，需要通过 `RenderThread::Get()->GetBrowserClient()` 或在 `RenderFrameImpl` 初始化时缓存 snapshot。

#### 2.2 Navigator.language / languages 覆盖

Hook 点：`third_party/blink/renderer/core/frame/navigator_language.cc`

```cpp
// NavigatorLanguage::EnsureUpdatedLanguage
void NavigatorLanguage::EnsureUpdatedLanguage() {
  // Helium: override with persona locale
  const auto& snapshot = ...;
  if (snapshot.IsEnabled() && !snapshot.locale.empty()) {
    languages_ = {String::FromUTF8(snapshot.locale)};
    // derive secondary from navigator_languages
    return;
  }
  // ... original code ...
}
```

#### 2.3 Timezone 覆盖

Hook 点：`third_party/blink/renderer/core/frame/time_zone_controller.cc`

在 `TimeZoneController::SetTimeZoneOverride` 或页面初始化时，如果 persona 启用，用 persona 的 timezone 覆盖 V8 的 timezone：

```cpp
// When persona is active, override timezone before page scripts run
if (snapshot.IsEnabled() && !snapshot.timezone.empty()) {
  // Set V8 timezone override
  isolate->DateTimeConfigurationChangeNotification(
      v8::Isolate::TimeZoneDetection::kSkip,
      snapshot.timezone);
}
```

#### 2.4 hardwareConcurrency / deviceMemory 覆盖

Hook 点：`third_party/blink/renderer/core/frame/navigator_base.cc`

```cpp
int NavigatorBase::hardwareConcurrency() const {
  const auto& snapshot = ...;
  if (snapshot.IsEnabled() && snapshot.hardware_concurrency > 0) {
    return snapshot.hardware_concurrency;
  }
  return ...;
}

float NavigatorBase::deviceMemory() const {
  const auto& snapshot = ...;
  if (snapshot.IsEnabled() && snapshot.device_memory > 0) {
    return static_cast<float>(snapshot.device_memory);
  }
  return ...;
}
```

#### 2.5 Screen 属性覆盖

Hook 点：`third_party/blink/renderer/core/frame/screen.cc`

覆盖 `width()`, `height()`, `availWidth()`, `availHeight()`, `colorDepth()`, `pixelDepth()`, `devicePixelRatio`。

#### 2.6 maxTouchPoints 覆盖

Hook 点：`third_party/blink/renderer/core/frame/navigator_events.cc`

```cpp
int NavigatorEvents::maxTouchPoints() const {
  const auto& snapshot = ...;
  if (snapshot.IsEnabled()) {
    return snapshot.max_touch_points;
  }
  return ...;
}
```

#### 2.7 Renderer 侧 snapshot 获取机制

**关键设计决策**：renderer 侧如何获取 persona snapshot？

方案 A（推荐）：在 `RenderFrameImpl::DidCreateNewDocument()` 或 `NavigationCommit` 时，从 browser 侧获取 snapshot 并缓存在 `ExecutionContext` / `LocalFrame` 上。

方案 B：通过 `RenderThread` 的 `ContentBrowserClient` 远程调用（开销大，不推荐）。

方案 C：在 `RenderViewImpl` 初始化时，通过 `browser_client->GetHeliumPersonaSnapshot()` 一次性获取并缓存。

**推荐方案 C**：在 `RenderViewImpl::Initialize()` 中调用一次，缓存在 `RenderViewImpl` 成员变量上，通过 `GetRenderView()->GetPersonaSnapshot()` 访问。

#### 2.8 验证

```bash
./devutils/quilt-fix.sh persona-navigator-runtime-overrides.patch
# 添加到 patches/series（在 persona-state-management 之后）
python3 .codex/skills/helium-validate/scripts/run_validation.py --with-source --source-tree chromium_src
```

---

### Phase 3: Canvas 指纹噪声

**目标**：对 canvas readback 结果注入确定性噪声，使指纹哈希随 persona 变化

**新建文件**：`patches/helium/core/persona-canvas-noise.patch`

#### 3.1 创建 noise token 基础设施

新建 `third_party/blink/public/common/helium_noise/noise_token.h`：

```cpp
namespace blink {

enum class HeliumNoiseFeature {
  kCanvas,
  kAudio,
  kHardware,
};

// Deterministic per-origin, per-persona noise token
class HeliumNoiseToken {
 public:
  static uint64_t Generate(const std::string& persona_seed,
                           const url::Origin& origin,
                           HeliumNoiseFeature feature);
  uint64_t Value() const { return value_; }
 private:
  explicit HeliumNoiseToken(uint64_t v) : value_(v) {}
  uint64_t value_;
};

using HeliumNoiseTokenMap = std::map<HeliumNoiseFeature, HeliumNoiseToken>;

}  // namespace blink
```

新建 `content/browser/helium_noise/noise_token_data.h` / `.cc`：

```cpp
namespace content {

class HeliumNoiseTokenData {
 public:
  static blink::HeliumNoiseTokenMap GetTokens(
      BrowserContext* context,
      const url::Origin& origin,
      const blink::HeliumPersonaSnapshot& persona);
  static void RegenerateTokens(BrowserContext* context);
};

}  // namespace content
```

实现要点：
- 有 `noise_seed`（persona ID）→ 用 `HMAC-SHA256(seed || origin || feature)` 生成确定性 token
- 无 `noise_seed` → 用 session-level 随机盐（`RegenerateTokens` 可刷新）
- 同 origin + 同 persona → 同一 token（跨会话稳定）
- 不同 origin 或不同 persona → 不同 token

#### 3.2 Hook canvas readback

Hook 点：`third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.cc`

在 `GetImageDataInternal()`、`ToDataURL()`、`ToBlob()` 等 readback 路径上：

```cpp
// Before returning pixel data, apply per-pixel noise
if (persona_snapshot.IsEnabled() && persona_snapshot.canvas_noise) {
  uint64_t noise_token = HeliumNoiseToken::Generate(
      persona_snapshot.noise_seed, origin, HeliumNoiseFeature::kCanvas);
  ApplyCanvasNoise(pixel_data, width, height, noise_token);
}
```

`ApplyCanvasNoise` 策略：
- 对像素 RGB 通道的最低位注入伪随机扰动
- 噪声由 `noise_token` 作为 PRNG 种子确定性地生成
- 同一 persona + 同一 origin → 同一噪声模式 → 指纹哈希稳定但与宿主不同
- 视觉影响极小（仅最低位变化）

#### 3.3 也可考虑 hook `measureText()`

Token 注释提到 `BaseRenderingContext2D::measureText`，但 text metric noise 属于 `fontMetricNoise`，与 `canvasNoise` 分开。如果 `fontMetricNoise` 启用，对 `measureText()` 返回的 `TextMetrics` 注入微小偏移。

#### 3.4 验证

```bash
./devutils/quilt-fix.sh persona-canvas-noise.patch
python3 .codex/skills/helium-validate/scripts/run_validation.py --with-source --source-tree chromium_src
```

---

### Phase 4: Audio 指纹噪声

**目标**：对 `OfflineAudioContext` / `AudioContext` 的输出数据注入确定性噪声

**新建文件**：`patches/helium/core/persona-audio-noise.patch`

#### 4.1 Hook audio processing

Hook 点：`third_party/blink/renderer/modules/webaudio/base_audio_context.cc`

在 audio buffer copy / readback 路径上：

```cpp
if (persona_snapshot.IsEnabled() && persona_snapshot.audio_noise) {
  uint64_t noise_token = HeliumNoiseToken::Generate(
      persona_snapshot.noise_seed, origin, HeliumNoiseFeature::kAudio);
  JitterAudioData(channel_data, length, noise_token);
}
```

`JitterAudioData` 策略：
- 对 float32 audio sample 的最低有效位注入 ±1 ULP 的确定性扰动
- 噪声由 `noise_token` 作为 PRNG 种子生成
- 听觉影响为零（远低于人耳可感知阈值），但改变哈希

具体 hook 位置需确认：
- `AnalyserNode::getFloatFrequencyData` / `getByteFrequencyData`
- `AudioBuffer::copyFromChannel` / `getChannelData`
- `OfflineAudioContext` 的 `startRendering` 完成回调

#### 4.2 验证

```bash
./devutils/quilt-fix.sh persona-audio-noise.patch
python3 .codex/skills/helium-validate/scripts/run_validation.py --with-source --source-tree chromium_src
```

---

### Phase 5: 主框架 Snapshot 传播

**目标**：确保普通页面（非 SharedWorker）也能获取 persona snapshot

**修改文件**：`patches/helium/core/persona-navigator-runtime-overrides.patch`（Phase 2 的同一 patch）

#### 5.1 NavigationRequest 注入

在 `content/browser/renderer_host/navigation_request.cc` 中，commit navigation 时获取 snapshot 并传入 `RenderFrameImpl`：

```cpp
// In NavigationRequest::OnCommitNavigationInternal or similar:
blink::HeliumPersonaSnapshot persona_snapshot =
    GetContentClient()->browser()->GetHeliumPersonaSnapshot(
        frame_tree_node_->navigator().controller().GetBrowserContext());
// Pass via mojom::CommitNavigationParams or CreateViewParams
```

#### 5.2 RenderFrameImpl 缓存

在 `RenderFrameImpl` 中缓存 persona snapshot：

```cpp
// In RenderFrameImpl::DidCommitNavigation or DidCreateNewDocument:
persona_snapshot_ = params->persona_snapshot;
```

通过 `RenderFrameImpl::GetPersonaSnapshot()` 暴露给 Blink 层。

#### 5.3 验证

```bash
python3 .codex/skills/helium-validate/scripts/run_validation.py --with-source --source-tree chromium_src
```

---

### Phase 6: 修复测试 & 清理

#### 6.1 修复 `persona-noise-token-determinism-test.patch`

现在 Phase 1 和 Phase 3 完成后，测试引用的头文件和字段将存在。需要：
- 确认 `MakeSeededPersona()` 中的字段名与实际 struct 一致
- 确认 `HeliumNoiseTokenData::GetTokens()` 签名与实现一致
- 确认 `content/test/BUILD.gn` 包含新源文件依赖

#### 6.2 清理 `persona_runtime_override.cc`

删除 stub 或替换为实际调用：
- 如果 Phase 2-5 的 hook 不需要全局 override，删除空壳类
- 如果需要全局初始化（如 V8 timezone override），实现 `ApplyGlobal()`

#### 6.3 更新 `persona-privacy-sandbox-runtime-gates.patch` token 注释

移除已实现的 token 注释（`NavigatorLanguage`, `TimeZoneController`, `hardwareConcurrency`, `Screen::width` 等），避免 validate_config 误报。这些 token 应该移到实际实现它们的 patch 中。

#### 6.4 全量验证

```bash
# Cheap validation
python3 .codex/skills/helium-validate/scripts/run_validation.py

# Source-backed validation
python3 .codex/skills/helium-validate/scripts/run_validation.py --with-source --source-tree chromium_src

# Full validation
python3 .codex/skills/helium-validate/scripts/run_validation.py --full

# Fresh source patch apply
rm -rf codex_tmp/patchcheck_src
python3 ./utils/downloads.py unpack -i downloads.ini -c chromium_download_cache codex_tmp/patchcheck_src
python3 devutils/check_chromium_src_clean.py --source-tree codex_tmp/patchcheck_src
./devutils/validate_patches.py -l codex_tmp/patchcheck_src -v
```

---

## Patch 依赖关系

```
persona-state-management.patch (Phase 1: 扩展 snapshot)
    ↓
persona-navigator-runtime-overrides.patch (Phase 2 + 5: navigator hook + 主框架传播)  [NEW]
    ↓
persona-canvas-noise.patch (Phase 3: canvas 噪声)  [NEW]
    ↓
persona-audio-noise.patch (Phase 4: audio 噪声)  [NEW]
    ↓
persona-noise-token-determinism-test.patch (Phase 6.1: 修复测试)
    ↓
persona-background-worker-snapshot-propagation.patch (现有: 适配新 snapshot)
    ↓
persona-contacts-background-fetch-runtime-gating.patch (现有)
    ↓
persona-privacy-sandbox-runtime-gates.patch (Phase 6.3: 清理 token)
```

`patches/series` 中新 patch 插入位置：
- `persona-navigator-runtime-overrides.patch` → 在 `persona-state-management.patch` 之后、`persona-settings-ui.patch` 之前
- `persona-canvas-noise.patch` → 在 `persona-navigator-runtime-overrides.patch` 之后
- `persona-audio-noise.patch` → 在 `persona-canvas-noise.patch` 之后

---

## 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| Renderer 侧获取 snapshot 的调用链不直接可用 | Phase 2 阻塞 | 方案 C（RenderViewImpl 初始化时缓存）可绕过 |
| V8 timezone override 时机问题 | 页面首帧可能用旧 timezone | 在 `DidCreateNewDocument` 之前设置 |
| Canvas 噪声影响 WebGL/WebGPU 正常渲染 | 功能回归 | 只 hook 2D canvas readback，不动 WebGL |
| Audio 噪声影响音频播放质量 | 听觉退化 | 仅 ±1 ULP，远低于可感知阈值 |
| Patch 数量增加导致升级维护成本 | 长期维护 | 每个 patch 职责单一，可独立 revert |
| 测试 patch 编译失败 | CI 阻塞 | Phase 6.1 统一修复 |

---

## 执行顺序总结

1. **Phase 0** — 建 quilt 开发树
2. **Phase 1** — 扩展 snapshot struct + `GetActiveSnapshot()` + mojom traits
3. **Phase 2** — Navigator 覆盖（platform / language / timezone / hardware / screen / touch）
4. **Phase 5** — 主框架 snapshot 传播（与 Phase 2 同一 patch）
5. **Phase 3** — Canvas 噪声 + noise token 基础设施
6. **Phase 4** — Audio 噪声
7. **Phase 6** — 修复测试 + 清理 stub + token 注释 + 全量验证
8. 每个 Phase 完成后运行 cheap validation
9. 全部完成后运行 source-backed + full validation
10. 最后切到 `helium-macos` 执行 `he merge && he push && he configure && he build`
