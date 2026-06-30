---
name: kb-citation-verifier
description: 用明学知识库(电池/储能/SOC/SOH/RUL/Kalman/BMS 等)给教学与评价取真实文献证据——选题文献支撑、核查学生引用是否真实/是否支撑结论、用论文图表佐证方法与数据。当推荐选题、整理语料库、或评审"文献引用/数据分析"维度时读本 skill。绝不杜撰。
tools: []
version: "1.0.0"
author: allo-official
required_env:
  - MINGXUE_API_TOKEN
optional_env: []
credentials:
  - key: MINGXUE_API_TOKEN
    label: 明学知识库 API Token
    description: 用于查询明学 RAGFlow 知识库的认证 token。
    required: true
    secret: true
---

# 明学知识库 · 文献底座 + 引用核查仪(教师端)

**定位:教学/评价时拿真实文献证据。两大用途——① 选题与语料库的文献支撑;② 评审时核查学生引用、佐证方法与数据。**

## 覆盖域
明学库覆盖 **锂电池 / 储能 / SOC / SOH / RUL / 容量衰减 / Kalman·EKF·UKF / BMS / OCV / 内阻** 等。选题在域内才用本库;域外回到通用文献方法,别硬套。

## 三条证据通道(评价取证用哪条)
1. **chunks(正文证据)**:abstract/method/result/table 段 → 核对学生的方法/结论说法是否和真实文献对得上。
2. **assets(论文图/表)**:figure/table + caption/表头/摘要 → 佐证学生数据分析是否符合真实方法与趋势。
3. **reference_signals(参考文献)**:`research` 模式返回 → **核查引用的主通道**。

## 如何调用
```bash
curl -sS -X POST "http://221.0.79.251:18091/api/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINGXUE_API_TOKEN" \
  -d '{"question": "聚焦检索问题", "top_k": 5, "mode": "research", "include_assets": true}'
```
- 核查引用用 `mode: research`(保留 citation 信号);找方法/数据证据用 `answer`。中文 query 自动跨语言搜英文论文。
- 教师是评价权威,**可以基于检索结果做综述/合成**(不受"代写"约束)。若服务端配了 LLM,可用 `/api/ask` 备课。

## 引用核查流程(评价"文献引用"维度的取证手段)
对应 `literature-and-knowledge-guide` 的引用风险五条,逐项拿明学库取证:
1. **虚构引用**:把学生引用的文献标题/观点拿去检索 → 库里有没有真实对应?查不到 → 标"待核实 / 疑似虚构"。
2. **引用不支撑观点**:检索该观点 → 真实文献的结论和学生用法对不对得上?
3. **堆砌 / 闭环**:结合正文,看引用是否真用到、列引是否对应。
4. **佐证数据分析维度**:学生的 SOC/SOH 方法、衰减趋势,和库里 method/result 段或图表是否一致。

## 铁律
- **不杜撰**:只认明学库真实返回的文档;核查不到就标"待核实",不替学生编、也不替学生圆。
- 评价结论里区分三态:**库里有据** / **库里查不到** / **库里证据相反**。
- **不要打印或泄露 token。**

## 输出(评价取证片段)
```
文献引用核查(明学库取证):
- 学生引用「<观点/文献>」→ 库内检索:
    ✅ 命中《doc》sim=0.7,结论一致
    ⚠️ 查不到,疑似虚构 / 待核实
    ❌ 库内证据相反(《doc》指出…)
- 数据分析佐证:学生用 <方法>,库内 method 段 / Fig… 支持 or 不支持 —— …
口径:仅明学库(电池/储能域);域外引用未纳入核查。
```
