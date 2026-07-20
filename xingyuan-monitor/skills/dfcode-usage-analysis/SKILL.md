---
name: dfcode-usage-analysis
description: 用 DFCode 企业 MCP 做用量分析时的方法论——部门/人员 token 用量、时间段对比、"为什么涨/跌"的根因拆解。当用户问"部门用量""谁用得多""这几天为什么下降/上升""对比两个周期"等,先读本 skill。
---

# DFCode 用量分析方法论

当用户问企业/部门/人员的 **用量、排名、趋势、对比、"为什么变了"** 时,按本方法论分析。数据来自 DFCode 企业 MCP(`query_departments` / `query_employee_detail` / `query_roster` / `query_dashboard` 等)。

**目标:让看的人一眼拿到结论,而不是一张要自己找答案的大表。**

## 0. 第一原则:先结论,后证据

- **第一行/第一句就回答用户的问题**(涨还是跌、为什么、主因是谁),再给支撑数据。
- 不要先甩 Top5 大表让用户自己看。**表格是证据,结论在前。**

## 1. 数据口径(最重要,错了全错)

- **未分配部门的人 = 非公司所属人员,直接排除。** 汇报里**不统计、不排名、不出现、也不要建议"为他们确认部门归属"** —— 他们就是噪声,当作不存在。
- **只统计已分配部门的人员。** 判定归属用 `query_roster`(按部门/状态)或 `query_departments` 的部门维度;`department=null` / 无部门 / 编外状态的人一律剔除。
- 默认**按部门聚合**;需要时再下钻到具体人(也只在已分配部门内)。
- 口径行不得手写；必须原样输出引擎的 `scope_statement`。
- ⚠️ 不要因为某未分配的人用量很高,就把他列出来或建议补归属 —— **高用量但未分配 = 仍然排除**,顶多在缺口里用一句概括"另有未分配人员用量未纳入",不点名。

## 2. 指标定义:按用户问题固定 metric

- 通用“用量”问题默认使用 `tokens`，此时排名、对比和“高用量用户”均以 token 消耗为准。
- 明确询问请求次数时允许使用 `requests` 进行对比和排名；报告必须称为“请求次数”，不得称为“用量”或“高用量”。
- **请求次数 ≠ token 用量。** 请求多但 token 低 = 高频小请求(可能是脚本/轮询/补全场景)，不能据此称为高用量用户。
- 一次对比只能选择 `requests` 或 `tokens` 之一，所有周期必须保持同一 metric，不能混排或混算。

## 3. 对比方法论(组长重点踩过的坑)

- 比较两个时间段时**必须同口径**:
  - 比**同一范围的总量随时间变化**,或**同一批人各自的所选 metric delta**。
- **禁止**把"周期A 第1名"和"周期B 第1名"纵向并排对比——他们往往是**不同的人**,维度不一致,这种对比无意义、会被一眼看穿。
- 正确做法:看同一范围的时间序列；要对比人，就使用固定 roster snapshot，逐人列出 `<metric>(周期A) → <metric>(周期B) → Δ`。

### 3.1 确定性同口径引擎(强制)

- 每次对比只允许一个 `fixed_roster_snapshot`。从 roster 中标准化部门和在职状态，排除 `未设置`、空部门、占位部门、非员工和跨部门成员后，固定人员集合不再随周期变化。
- 所有成员连接必须使用 stable user_id；姓名只作展示，重名或改名不能影响归属。固定集合中的用户在某周期没有 usage row 时按 0 处理。
- comparison 和每个周期都必须显式携带并匹配 `metric、scope_type、scope_value、timezone、cutoff_hour、population_mode、group_by、date_semantics`。`group_by` 必须为 `user`，`date_semantics` 必须为 `calendar_date_inclusive`；各周期 `from`/`to` 必须是 ISO 日期、起止有序且包含首尾日的持续天数相同。先验证全部周期，再计算 totals、deltas、百分比和 contributors。
- 周期必须按时间严格递增、互不重叠且 label 唯一；输入顺序就是顺序比较和 delta 的时间顺序，不得自动重排。
- 请求次数问题使用 `metric=requests`；token 用量问题使用 `metric=tokens`。一旦选定，所有周期必须一致。
- `requests` 行值必须是非负整数且不能是 bool；`tokens` 行值可以是非负有限整数或浮点数。整数聚合必须保持 Python 整数精度，不得先转 float。
- Internally, token values are normalized to Decimal：整数使用 `Decimal(value)`，浮点数使用 `Decimal(str(value))`；聚合、contributors delta 和 percentage 全程使用 Decimal。JSON 输出中，integral Decimal -> JSON integer 仅限 safely serializable under Python's integer digit limit，otherwise plain decimal string；non-integral Decimal -> finite plain decimal string，并保证 no exponent、`Infinity` 或 `NaN`。
- CLI 使用 `json.load` 的 parse_int hook：合理长度的数字字面量保持 `int`，超过 Python 整数数字限制的字面量解析为 `Decimal`。实现 must not change the global integer digit limit；metadata 整数仍为 `int`，超限 requests 因不是普通 `int` 而拒绝。
- `percent` 对所有非零基线输出 finite decimal string，固定 two decimal places（例如 `"-20.00"`、`"66.67"`）；zero baseline remains null。不得输出 JSON `Infinity`、`-Infinity` 或 `NaN`。
- 不得手工拼装 trend dictionary，不得将 MCP 行复制到临时字典后自行求和、排名或写“同口径”结论。
- 标准化 JSON 写入临时输入文件后，精确调用：`python skills/dfcode-usage-analysis/scripts/compare_scope.py <input.json>`。
- CLI 成功时 stdout 是结构化 JSON；必须原样输出引擎的 `scope_statement`。CLI 非零退出时 stderr 是有界结构化错误，必须停止当前计算。

### 3.2 scope-validation 确定性恢复循环（强制）

- `compare_scope.py` 的 scope-validation error 是内部 guard，不是正常最终答案；不得在首次 scope-validation error 后直接最终回答 `数据不足`。
- 收到 scope-validation error 后，丢弃所有不兼容的缓存和先前结果；锁定用户请求的 metric、scope、timezone、cutoff、date semantics、period duration，并锁定一个 roster snapshot。
- 从 MCP 重新查询每个周期，每个周期都必须使用相同的 `group_by=user` 和 hour cutoff；重新构建完整输入，只重跑一次 `compare_scope.py`。
- 不得只修补一个周期，不得复用 stale data，也不得把首次被拒绝输入中的行混入新输入。标准化完整重取数最多一次，防止无限重试。
- 重跑成功时正常回答，不得提及内部拒绝，也不得把恢复过程暴露为用户可见告警。
- 只有标准化重取数本身失败或返回不完整数据时，才使用 `状态：数据不足`；此时不得输出百分比、排名或因果判断，并在“缺口”中列出具体缺失的 MCP 调用（工具名、周期及缺失字段或失败原因）。

标准化输入合同：

```json
{
  "comparison": {
    "metric": "requests",
    "scope_type": "department",
    "scope_value": "智能视迅",
    "timezone": "Asia/Shanghai",
    "cutoff_hour": 18,
    "population_mode": "fixed_roster_snapshot",
    "group_by": "user",
    "date_semantics": "calendar_date_inclusive"
  },
  "roster": [
    {"user_id": "user_x", "name": "张三", "department": "智能视迅", "employment_status": "active"}
  ],
  "periods": [
    {
      "label": "2026-07-13",
      "from": "2026-07-13",
      "to": "2026-07-13",
      "metric": "requests",
      "scope_type": "department",
      "scope_value": "智能视迅",
      "timezone": "Asia/Shanghai",
      "cutoff_hour": 18,
      "population_mode": "fixed_roster_snapshot",
      "group_by": "user",
      "date_semantics": "calendar_date_inclusive",
      "rows": [{"user_id": "user_x", "requests": 120}]
    }
  ]
}
```

标准化完整重取数已执行一次，但重取数本身失败或返回不完整数据时，才使用以下模板；首次口径校验失败不得直接使用：

```text
状态：数据不足
诊断：标准化完整重取数失败或数据不完整，已停止计算环比。
缺口：<列出具体缺失的 MCP 调用、对应周期、缺失字段或失败原因>。
```

## 4. 根因拆解:直接回答"为什么涨/跌"

当所选范围的指标变化时,按这个链路给答案:

1. **结论先行**:<范围> 的 <metric> 环比 <涨/跌 X%>(从 A 到 B),主因是 ___。
2. **拆解到人/模型**:对比同范围两个时间段,找出 **所选 metric 变化最大的几个人 / 哪个模型迁移了**。
3. **区分两种情况**(组长想知道的就是这个):
   - **主力轮换**:部门总量基本稳定,只是活跃的人换了一批 → 说清"不是真下降,是 X 换成了 Y"。
   - **真实下降**:总量实质减少 → 找出**是谁停用/降了**(用 `query_employee_detail` 看其 daily trend 佐证),以及是否伴随**配额变化、模型下线、离岗**。
4. **可证伪**:数据缺失就说缺失(例:周期太短、某天数据不全),不要硬编因果。

## 5. 工具速查

| 你要做的事 | 用哪个工具 |
|---|---|
| 部门用量 / 对比 / 趋势 / WoW / 部门内 top | `query_departments`(带 range filters / daily trends / WoW / top employees per dept) |
| 单人深挖(概览、日趋势、模型分布、明细) | `query_employee_detail` / `query_department_employee_detail` |
| 部门归属 / 编外判定 / 按状态筛 | `query_roster` |
| 全局概览(今日/7d/月、活跃人数、模型分布) | `query_dashboard` |
| 跨维度聚合 | `query_usage` |

## 6. 输出模板(同口径对比类问题)

```
结论:<范围> 近 <周期> 的 <metric> 环比 <涨/跌 X%>,主因是 <主力轮换 / 谁降了 / 谁升了>。

变化拆解(同范围,同口径):
- <人/模型A>:<metricA> → <metricB>（Δ<±X>）
- <人/模型B>:...
（只列所选 metric 变化最大的 3-5 项）

判断:<主力轮换 / 真实下降>，依据 <…>。
<原样输出引擎的 scope_statement>
缺口:<数据不全/周期过短等，如有>
```
