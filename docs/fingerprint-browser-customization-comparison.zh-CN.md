# 指纹浏览器自定义参数与 API 横向对比

日期：2026-08-19

对比对象：CloakBrowser、OpenBrowser、Nitrous

## 结论摘要

三者的优势不在同一层面：

- **CloakBrowser 的优势是接入效率。** Playwright、Puppeteer、Python 和
  .NET 包装层较薄，固定 seed、代理 GeoIP 对齐和 humanize 能快速进入
  自动化流程。公开参数不算最多，但学习成本低。
- **OpenBrowser 的优势是自定义参数覆盖面。** UA/CH、GPU、屏幕、媒体、
  WebRTC、字体、音频、Canvas、ClientRects、稳定策略等均有入口，并提供
  本地 HTTP API、MCP 和 Profile 隔离。
- **Nitrous 的优势应定位为一致性和失败语义。** 当前源码把 Persona、
  Device Pack、网络协议身份和命名 route 放入同一条事务化激活链，提供
  validate、resolve、effective、audit、CDP 和 ChromeDriver 接口。它比
  “逐字段随机化”更适合长期身份，并已能核验 live frame/worker 的 snapshot、
  噪声 token、WebGPU capability profile 与默认音频输出证据；参数易用性和完整
  字段 schema 仍有差距。

因此，Nitrous 不应复制 OpenBrowser 的大量独立噪声开关，也不应退回
CloakBrowser 的无结构 CLI 参数。更合适的产品方向是：以一致性 preset 和
Device Pack 为主，自定义字段为受校验的高级覆盖层，再用 SDK/CLI 降低接入
成本。

## 证据边界

本报告只把仓库中的说明当作说明，把可读源码当作可审计实现，两者不混用。

- CloakBrowser HEAD 为 `24883110729d69acda958470cf6e9067ee0dbc01`。
  Chromium patch、构建配置和二进制被仓库明确列为 proprietary，因此公开
  仓库只能审计包装层，无法验证其“71 个 C++ patch”或检测站通过率。
- OpenBrowser HEAD 为 `cb9842a8b0d63475d96f7dd3b9948b949996c501`。
  当前工作区是非完整快照：HEAD 约 5497 个条目，本地约 154 个普通文件。
  下文引用的核心文件与 HEAD blob 一致，但不能据此判断完整 UI、打包和测试
  质量。
- Nitrous 结论基于当前 patch queue 与本次修改。它描述的是源码设计
  和静态检查结果，不代表已经编译、打包或发布。

## 总体对比

| 维度 | CloakBrowser | OpenBrowser | Nitrous 当前源码 |
| --- | --- | --- | --- |
| 自定义参数广度 | 中等，约 15 类 CLI flag 加任意 Chromium args | 最宽，覆盖多数常见浏览器 surface | 广泛且结构化，偏向相关联的完整身份 |
| 一致性模型 | 固定 seed 可复现，显式覆盖缺少跨字段校验 | seed + device persona，一致性冲突主要作为诊断 | Device Pack + 原生 snapshot + 网络身份；错误阻止激活 |
| 注入方式 | 声称 Chromium 原生，核心实现不可公开审计 | flag + native init + CDP/document-start JS | Chromium 原生 snapshot 与 NetworkContext 传播 |
| 失败语义 | GeoIP 失败后继续启动 | 多处注入失败后继续导航 | quiesce、回执屏障、CAS、回滚、无法证明时 fail-closed |
| 代理模型 | 每次 launch 传入，GeoIP 自动对齐 | Profile proxy CRUD、出口检测和地理解析 | Profile 级命名 route、加密凭据、Persona 事务绑定 |
| 自动化 API | Playwright/Puppeteer/Python/.NET 易用 | HTTP API、MCP、RPA | 受控 CDP domain、ChromeDriver capability、Settings API |
| 自省能力 | 无 schema/validate/effective/audit | 可读取生成结果，缺版本化契约和 live assurance | contract/validate/resolve/effective/audit；frame/worker snapshot 与 token、WebGPU identity/capability profile、默认媒体输出均有运行时证据，总体仍 partial |
| 隔离 | 依赖调用者正确管理 `userDataDir` | Profile 根目录、锁、端口、软链接检查较强 | 浏览器 Profile/storage partition 原生边界和事务隔离 |

## 自定义参数能力

### CloakBrowser

公开包装层支持固定 fingerprint seed、操作系统/屏幕/硬件类参数、代理、
timezone、locale、WebRTC 地址、Canvas/WebGL/音频等常见控制，并允许继续传入
任意 Chromium args。其核心优势有三点：

1. Playwright/Puppeteer 的 launch 和 persistent context 封装直接，迁移现有
   自动化脚本的成本低。
2. 固定 seed 容易获得跨启动可复现性。
3. 代理 GeoIP 可自动推导 timezone、locale 和 WebRTC 出口地址，减少人工
   填写冲突。

主要限制：

- 参数是 CLI flag 集合，不是版本化、机器可读的字段 contract。
- 没有 validate-only、requested/effective diff 或 surface audit。
- GeoIP 查询失败会继续启动，属于可用性优先的 fail-open。
- 部分代理凭据进入进程参数，需要额外考虑进程列表和诊断日志暴露。
- 代理轮换不内置，需要调用方自己编排。

### OpenBrowser

OpenBrowser 的参数覆盖最完整，包括 UA/Client Hints、CPU/RAM、屏幕、DPR、
色深、WebGL 元信息、Canvas/WebGL/Audio/ClientRects 噪声、WebRTC、本地与
公网地址、媒体设备、Battery、WebGPU、Speech、字体、语言、时区、地理位置、
端口扫描和站点稳定策略。

它还具备几项值得 Nitrous 借鉴的设计：

- 以稳定 seed 区分静态身份和随出口 IP 变化的动态字段。
- device persona 不是逐字段独立随机，而是从 CPU、内存、GPU、screen、DPR
  的相容组合中选取。
- 同时处理 document-start、当前文档、iframe 和 worker，并避免 native 与
  JS 重复加噪。
- Profile 数据根、锁、CDP 端口和符号链接检查比较完整。

主要风险：

- 一致性检查产生诊断，但 `ok:false` 不一定阻止创建或启动。
- native init、预注入和 worker 注入存在继续导航的 fail-open 路径。
- live probe 主要覆盖 UA、platform、CPU、RAM 和 WebGL，不能证明字体、音频、
  WebRTC、WebGPU、媒体设备等全部生效。
- HTTP API 缺少正式 schema、validate-only、PATCH/upsert、requested/effective
  差异和 live assurance；MCP 的写接口也不完整。
- persona 池较小，规模化使用可能形成聚类。

### Nitrous

Nitrous 当前覆盖 UA/CH、平台、GPU、硬件、屏幕、字体、媒体设备、语言/地区、
权限、地理位置、网络观测字段、WebRTC、渲染 seed 和 Device Pack。相比单纯
增加开关，当前设计的关键区别是：

- enabled 非默认 Persona 必须绑定可验证的 Device Pack，不能只改
  navigator claim 而保留不相容的 TLS/H2/H3 身份。
- renderer 和 worker 使用原生 Persona snapshot，不依赖页面脚本 monkey
  patch 作为主路径。
- 激活会隔离旧执行上下文，向已加载和事务中新增的 NetworkContext 下发候选，
  先阻断并取消 Profile/system context 的 URLLoader、WebSocket、WebTransport、
  直接 socket、DNS/proxy lookup、OHTTP 与证书 AIA/OCSP 请求，再等待 proxy、
  SOCKS、网络 Persona 和 system proxy 回执，最后 CAS 提交 Persona 与 route。
- 回滚后还会核对旧 prefs、seed、last-used id 和 active route；无法证明恢复
  时保持 Persona unavailable。
- audit 会向 live top frame/iframe 查询 renderer 实际持有的完整 snapshot，并
  核对 Canvas、Audio、hardware、font metric 和 ClientRect token 是否存在。

需要强调：这些 Mojo 更新不是 NetworkService 内部的单条原子操作。因此准确
表述是“请求 gate 保护下、带回执屏障和补偿回滚的事务化收敛”，不是严格瞬时
原子。HTTP(S)、WebSocket、WebTransport、直接 TCP/UDP、DNS/proxy lookup、
OHTTP、新 preconnect、证书 AIA/OCSP、P2P/mDNS、reporting 和 PAC/WPAD 已
形成旧/新 epoch 边界；内核在 gate ACK 前已经接受的数据报仍不可撤回。

## API 与产品设计改进

### 本轮已经落到 patch queue

1. **版本化格式**

   当前导出 schema 为 `Nitrous.persona/v2`，旧
   `helium.persona/v1` 只作为导入兼容格式。导出不包含 live seed、已打开连接
   或 TLS session。

2. **结构化自省 API**

   - `getContract`：schema、模式、事务 outcome 和 capability 元数据。
   - `validate`：不落盘地校验并规范化输入。
   - `resolve`：解析已保存 Persona 与当前状态。
   - `getEffective`：requested/effective、diff、assurance、transition。
   - `getAudit`：保守报告 surface 与 route binding 状态。
   - `activate`：只在 commit 与 execution-context restart 均完成后成功。

3. **统一激活事务**

   Persona、fingerprint seed、last-used id、Device Pack 网络身份和 active route
   使用同一条激活链。候选失败、commit 失败、reload 派发失败和回滚失败具有
   不同 outcome，不再用一个布尔值隐藏实际状态。

4. **命名 network route**

   Persona 只保存稳定 `routeId`，endpoint 和密文留在 Profile route registry。
   UI、导出、CDP、effective 和 audit 不回显密码。活动 route 不允许原地编辑或
   删除。HTTP/HTTPS 不接受预存凭据；SOCKS5 凭据按 RFC 1929 长度约束校验，
   并通过系统加密器持久化。

5. **受控自动化入口**

   `NitrousPersona` CDP domain 只注册给可信 browser-target client；当前只支持
   `default` 原始 Profile。ChromeDriver 增加 `nitrous:personaId` 和
   `nitrous:browserContextId` capability，并把 startup picker continuation 与
   自动化激活合并。

6. **WebRTC 模式**

   `disabled`、`altered` 和 `real` 进入 contract 与校验。enforced route 会在
   浏览器偏好读取点强制禁用 non-proxied UDP，避免 ICE 绕过 HTTP/SOCKS route。

7. **NetworkService 请求 gate**

   Persona 候选下发前先阻断 Profile 与共享 system NetworkContext。阻断 ACK 在
   活动 URLLoader、WebSocket、WebTransport、直接 socket、DNS/proxy lookup 和
   OHTTP 请求被取消后返回；新 covered request 与 preconnect 被拒绝，事务期间
   新建的 NetworkContext 从参数继承 blocked 状态。成功重启后执行两轮释放收敛，
   失败则重新封闭并保持 degraded。并发 Profile 共享 system gate 时，回调会等待
   聚合状态的实际 ACK，不会把“另一个 Profile 正在阻断”误当成本次已确认。
   证书验证也进入同一代际边界：旧 CertNetFetcher 永久关闭，等待更新的旧验证
   队列被拒绝；新 generation 的 AIA/OCSP factory 在 gate 内预绑定，只有
   CertVerifierService 回执后才真正放行 NetworkContext。

8. **live execution-context runtime evidence**

   `getAudit` 已异步枚举普通标签页的 active primary frame tree，以及 dedicated、
   shared、service worker，对 renderer-held snapshot 和适用的噪声 token 做完整
   比对。此前 ClientRect token 只声明未生成的问题也已修复。WebGPU 最终公开
   identity、完整 capability profile 和默认音频输出也进入被动证据链；总 probe
   因其它未观测输出仍正确标为 `partial`。

9. **异常与自动化回归测试**

   新增 ProxyConfig flush 的 delayed ACK、断管、超时、配置 mismatch/pin 和
   match/release 单测；新增 ChromeDriver fresh-profile `always_ask` 完整 New
   Session 路径与未知 Persona 拒绝测试。源码测试已加入目标，但本报告生成时尚未
   运行 Chromium 编译或测试二进制。

10. **媒体设备默认值不再穿透宿主机**

    启用 Persona 后，默认 `1/1/1 + 空 labels` 现在明确表示三类合成设备，
    不再退回真实设备枚举；自定义 count/label 只作用于请求的设备类型，audio
    input/output 使用不同 id、默认 label 和 group。system-real 保持 Chromium
    原生行为。audit 不主动调用 `enumerateDevices`，因此这里是实现保证，不冒充
    live-observed evidence。

### 仍应优先改进

#### P0：完整机器可读字段 schema

当前 `getContract` 是能力 contract，还不是完整字段 schema。下一步应为每个
字段返回：

- path、类型、枚举、范围、默认值和 nullable 规则；
- 作用域是 site、Profile 还是 global；
- 是否需要 reload、execution-context restart 或完整 identity rotation；
- assurance 等级和可验证 surface；
- 与其他字段的依赖和互斥关系。

这样 SDK、Settings 和第三方控制面才能由同一份 contract 生成表单和错误提示。

#### P0：跨 surface 一致性 resolver

现有严格类型/范围校验还应扩展为 cohort 语义校验，至少覆盖：

- UA、UA-CH、platform、Chrome major 和 Device Pack；
- GPU backend、vendor/renderer 与平台；
- CPU/RAM、screen/DPR/color depth 的可信组合；
- locale、timezone、geolocation、route 出口和 WebRTC；
- 字体、媒体设备和 speech voice 与平台/语言。

建议 API 返回 `errors` 与 `warnings` 两层：非法或会泄漏的冲突阻止激活，少见但
可能真实的组合只提示。

#### P1：继续补齐输出级 live surface probe

当前 audit 已能验证 top frame、iframe、三类 worker、完整 snapshot 与五类
frame/四类 worker 噪声 token；WebGPU core 模式只保留强制
`core-features-and-limits`，compatibility 模式不暴露可选 feature，并使用确定性的
portable limit profile。`requestDevice` 不允许越过公开能力，audit 会精确核对全部
capability 值。默认 speaker 还要求同一执行上下文里的 Persona latency getter 与
实时音频回调同时成立。
`WebGLOnWebGPU` 也有独立保护回归。总体仍保持 `partial`，后续重点是：

- request headers 和 Client Hints；
- Canvas、Audio、字体的结果级观测与跨平台 oracle；
- WebGPU shader、subgroup 与 device 行为的非主动观测；
- WebRTC policy/candidate；
- media devices、timezone、locale 和 geolocation；
- 当前 route、观测出口 IP 和 Device Pack 网络身份。

`activate` 的事务成功与 probe assurance 应保持两个概念：前者证明配置收敛，
后者证明观测 surface 符合预期。

#### P1：全网络出口 fail-closed

事务 request gate 已覆盖相关 NetworkContext 内的新旧 HTTP(S) URLLoader、
WebSocket、WebTransport、直接 TCP/UDP、DNS/proxy lookup、OHTTP 与新
preconnect，包括 browser-side URLLoader 和证书 AIA/OCSP fetch。要进一步承诺
“所有 enforced route 流量都不直连”，还要把 P2P、mDNS responder、
NetworkService 内部 reporting 等出口纳入同一 gate 或明确禁止。

#### P1：route subversion 的持续网络层封锁

事务窗口已经会取消在途 loader，但事务完成后若 policy、extension 或命令行接管
代理，现有导航 throttle 仍不是所有网络入口的持续 kill switch。enforced route
应持续 pin 已验证配置，或让 NetworkContext 在检测到 subversion 后重新关闭 gate。
带凭据 system route 继续保持不支持，直到 SOCKS credential 生命周期也进入
system context。

#### P1：活动 Persona 编辑也要走事务

当前普通 `save` 只阻止活动 Persona 改动 `network.routeId`；UA、屏幕、GPU、
语言等其他字段仍可直接持久化。这样已存在的执行上下文与随后新建的上下文可能
短时读取不同配置。应把活动 Persona 的全部身份字段编辑改为 staged
validate-and-activate，或要求先复制/编辑非活动 Persona 再激活；展示名称等纯元数据
可以继续原地修改。

#### P1：SDK 与 CLI

CloakBrowser 的主要易用性优势来自包装层。Nitrous 应提供 TypeScript/Python
SDK 或 CLI，串联 contract、validate、resolve、activate、effective 和 audit，
并把 `commitState=committed` 与 `restartResult=restarted` 固化为唯一成功条件。
不建议把任意 raw Chromium flags 重新定义为主 API。

#### P1：route 出口与健康信息

route 应增加出口 IP、GeoIP 结果、数据来源、观测时间、最近错误和健康状态。
Persona activation 可选择要求 timezone/locale/geolocation/WebRTC 与最近一次
出口观测一致。代理池、自动轮换、负载均衡和故障转移应作为 route registry
上层策略，不进入 Persona 基础 schema。

#### P2：多 Profile context 与协议集成测试

当前 CDP `browserContextId` 只支持 `default`。若产品需要同时控制多个 regular
Profile，应使用显式 Profile/context registry，不能以 last-used Profile 猜测。
ChromeDriver fresh-profile session、startup `always_ask` 恢复、业务失败和
capability echo 已有 Python 完整路径测试；仍应补 CDP handler trusted/page
target、OTR/default context 以及真实二进制执行证据。

#### P2：humanize/RPA 分层

humanize 能降低脚本行为的机械性，但不属于指纹 Persona。建议作为 SDK
middleware 或自动化策略层实现，避免让行为模拟参数污染身份 schema 和 seed
生命周期。

## 建议路线图

| 阶段 | 目标 | 完成标准 |
| --- | --- | --- |
| 1. Contract 收口 | 完整字段 schema、语义 resolver、SDK 类型生成 | UI、SDK、CDP 使用同一 schema 和错误码 |
| 2. Assurance 闭环 | 扩展 worker 与输出级 live probe | audit 能对 frame、worker、network 分别表达 verified/unknown/blocked |
| 3. 网络与编辑强制 | 全出口 gate、route subversion 持续封锁、活动 Persona staged edit | raw socket/policy 接管和普通保存都不会产生身份分叉 |
| 4. 运营能力 | route health、exit IP/GeoIP、pool/failover | 不破坏 Persona 事务和凭据边界的可观测路由编排 |
| 5. 接入体验 | TypeScript/Python SDK、CLI、集成示例 | 自动化调用者无需理解内部 prefs 或 CDP response 细节 |

## 关键源码依据

### CloakBrowser

- 闭源边界：`/Volumes/BIGDISK/github/3p/CloakBrowser/BINARY-LICENSE.md:7`
- Playwright 接入：`/Volumes/BIGDISK/github/3p/CloakBrowser/js/src/playwright.ts:194`
- CLI 参数：`/Volumes/BIGDISK/github/3p/CloakBrowser/js/src/args.ts:10`
- GeoIP 行为：`/Volumes/BIGDISK/github/3p/CloakBrowser/js/src/geoip.ts:73`
- 代理凭据路径：`/Volumes/BIGDISK/github/3p/CloakBrowser/js/src/proxy.ts:236`

### OpenBrowser

- 指纹构建：`/Volumes/BIGDISK/github/3p/OpenBrowser/Browserapp/automation/fingerprint.js:632`
- device persona：`/Volumes/BIGDISK/github/3p/OpenBrowser/Browserapp/automation/device-personas.js:228`
- 一致性诊断：`/Volumes/BIGDISK/github/3p/OpenBrowser/Browserapp/automation/fingerprint.js:948`
- 注入与 probe：`/Volumes/BIGDISK/github/3p/OpenBrowser/Browserapp/engine.js:949`
- 本地 API 安全边界：`/Volumes/BIGDISK/github/3p/OpenBrowser/Browserapp/automation/local-api-server.js:61`

### Nitrous

- contract/effective/audit：`chrome/browser/helium_persona/persona_service.cc`
- route registry：`chrome/browser/nitrous_proxy/nitrous_proxy_service.cc`
- NetworkContext gate/fanout：`services/network/network_context.cc`、
  `chrome/browser/net/profile_network_context_service.cc`
- 证书 fetch 代际：`services/cert_verifier/cert_verifier_service.cc`、
  `services/cert_verifier/cert_net_url_loader/cert_net_fetcher_url_loader.cc`
- CDP domain：`third_party/blink/public/devtools_protocol/domains/NitrousPersona.pdl`
- ChromeDriver capability：`chrome/test/chromedriver/session_commands.cc`
- 生命周期说明：`docs/persona-fingerprint-lifecycle.md`
