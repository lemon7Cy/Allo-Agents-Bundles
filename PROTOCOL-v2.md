# Agent Bundle 开发协议 v2（自包含 + 按 agent 隔离）

本文件定义 Agent Bundle 的 v2 开发协议，并对比 v1（`README.md` 里的原始约定）。
目的：把"bundle = 一个可分发、装即用、能力只属于它自己的产品单元"这条初心**做彻底**。

---

## 一、v1 ↔ v2 一图对比

| 维度 | v1（原始） | v2（本次） |
|---|---|---|
| 能力源放哪 | `provision/{skills,plugins}` | **bundle 根的 `skills/` + `mcp/`** |
| 能力怎么生效 | provision **一键安装到全局**（`~/.allo/skills`、用户 MCP 配置）→ 全局共享 | **按 agent 直接加载**，只在该 agent 运行时生效，**不进全局** |
| 隔离性 | 无：装了全局，普通用户/别的 agent 也能用 | **完全隔离**：通用助手与其它 agent 看不到、用不到 |
| 设计文档 | `design/`（声明式，`runtime_loaded:false`） | 保留 `design/`（设计参考）；行为由 SOUL/skill/capabilities.policies 承载 |
| 运行时实际加载 | `config.yaml + SOUL.md + capabilities.yaml`（+ 全局装好的能力） | `config.yaml + SOUL.md + capabilities.yaml + bundle 自带 skills/mcp` |
| 外部分发 | `ALLO_BUNDLES_ROOT` 外置 | **不变**：`ALLO_BUNDLES_ROOT` + zip 导入都支持 |

**一句话**：v1 是"包里带可安装源、装到全局共享"；v2 是"包里直接带能力、只为自己 agent 加载、谁也偷不走"。

---

## 二、v2 包结构

```
<agent-name>/
├── config.yaml          # 身份/模型/dashboard(full|minimal|none)/access/observation_store
├── SOUL.md              # 人设/行为/输出风格/安全边界/跨平台与降级纪律
├── capabilities.yaml    # 能力声明(skill|plugin|mcp + workflow_step|review) + policies + display_name + entry_prompts
├── skills/              # bundle 自带 skill（含脚本/requirements/wrapper）
│   └── <skill>/SKILL.md ...
├── mcp/                 # bundle 自带 MCP（plugin.json 形态，SSE/stdio，key 用 $ENV 引用）
│   └── <plugin>.json
└── design/              # 设计参考文档（runtime_loaded:false，可选）
```

打包卫生（强约束）：**禁止**带 `.venv`、`__pycache__`、`*.pyc`、运行时状态（sessions/workspace/memory）、明文密钥。凭据一律 `$ENV` 引用，导入方自配。

---

## 三、装配加载机制（平台侧）

1. **发现** `_resolve_agent_dir(name)`：已安装 `~/.allo/agents/<name>/` > 外部 `ALLO_BUNDLES_ROOT` > 仓库源。
2. **导入** zip → 解包到 `~/.allo/agents/<name>/`（运行时真正读这里）。导入器白名单需接受 `skills/ + mcp/`。
3. **按 agent 加载（隔离）** —— 仅在该 agent 运行时：
   - `SOUL.md` → 系统提示人设；
   - `capabilities.yaml` → 能力看板（只列 skill/plugin/mcp，bundle 自带算 ready）+ workflow 声明 + policies；
   - `skills/` → `load_agent_bundle_skills(agent)` 注入为 always-on，沙箱经 `agent_skill_roots` 只读放行；
   - `mcp/` → `load_agent_bundle_mcp_servers(agent)` 合并 → MCP 缓存 scope `(user, agent)` 隔离；
   - **子 agent**：`task_tool` 透传 `agent_name`，委派出去的 general-purpose 也继承 bundle 的 MCP。
4. **隔离保证**：`agent_name` 贯穿 prompt / tools / mcp cache / 子 agent —— 通用助手和别的 agent 拿不到。

---

## 四、能力作者约定

- **能力以 agent 为隔离边界**：新能力默认"只为它的 agent 加载"，不进全局。
- **平台只做传输 + 通用渲染，内容/品牌归 bundle**：如飞书卡片标题取自 `capabilities.yaml` 的 `display_name`，渠道层不硬编码任何 agent 名。
- **跨平台 + 优雅降级（写进 SOUL）**：优先内置工具 + Python + MCP，避开 Unix-only shell；命令/脚本失败时**试一次就降级出文字结果，绝不死循环或派 subagent 暴力重试**（死循环会占住会话锁、堵住后续消息）。
- **脚本可移植**：随脚本带 `requirements.txt` + wrapper（`.venv/bin/python` → `python3` → 找不到则优雅降级），依赖缺失时仍能出 JSON/文字。

---

## 五、有没有偏离初心？

`README.md` 的初心三条 —— **外部可分发 / 自包含 / 装即用** —— v2 **全部保留**，并把"自包含 + 隔离"做得更彻底。唯一方向取舍：未沿用 v1 `design/` 的"声明式 + 平台通用 loader"路线，改走命令式（SOUL/skill/code）；`design/` 作为设计参考保留，便于对齐。
