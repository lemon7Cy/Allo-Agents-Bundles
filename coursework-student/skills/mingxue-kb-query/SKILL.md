---
name: mingxue-kb-query
description: 查询明雪知识库，面向电池、SOC、SOH、RUL、Kalman、EKF、UKF、BMS、储能问题，并返回带出处的检索答案。
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

# 明学知识库查询

## 概述

使用明学 RAGFlow 知识库 HTTP API 进行检索。默认使用答案导向检索：用证据块回答，将参考文献作为独立信号（除非用户要求文献发现）。

## 何时使用

- 用户提到 `明雪知识库`、`Mingxue`、`知识库`，或要求带引用的检索结果
- 领域问题：电池、储能、SOC、SOH、RUL、Kalman、EKF、UKF、BMS、ECM、电池数据集
- 用户要求"查一下"、"检索"、"带出处"、"根据知识库回答"

不要用于通用编码任务或与此知识库无关的问题。

## API 配置

```text
Search API: http://221.0.79.251:18091/api/search
Ask API:    http://221.0.79.251:18091/api/ask  (需额外配置 LLM)
```

Token 通过环境变量传入：

```bash
export MINGXUE_API_TOKEN="<your-token>"
```

## 检索命令（search）

```bash
curl -sS -X POST "http://221.0.79.251:18091/api/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINGXUE_API_TOKEN" \
  -d '{"question": "QUESTION", "top_k": 5}'
```

参数说明：
- `question`：检索问题（必填）
- `top_k`：返回结果数量（默认 5，快速检查用 3，广泛证据用 8）
- `mode`：`answer`（默认）或 `research`（文献发现）

## 问答命令（ask，可选）

Ask API 需要额外配置 LLM 环境变量（`MINGXUE_LLM_BASE`、`MINGXUE_LLM_MODEL`、`MINGXUE_LLM_API_KEY`），未配置时不可用。优先使用 search API。

## 内置检索规则

| 查询语言 | 检索行为 |
|----------|----------|
| 中文 | 跨语言 = 英文 |
| 英文 | 跨语言关闭 |
| 任意 | 重排序器关闭 |
| 答案模式 | 过度获取候选，从主要块中过滤 `references`/`biography` |
| 研究模式 | 保留引用/参考信号用于文献发现 |

## 检索模式规则

- 默认使用答案模式用于事实、解释、比较和技术问题
- 仅使用 `chunks` 回答；这些是主要证据通道
- 将 `reference_signals` 视为引用/文献线索，而非直接答案证据
- 当用户问"有哪些论文"、"参考文献"、"研究脉络"等时使用 `research` 模式

## 查询规划规则

不要使用用户的最终答案提示作为检索查询。将其转换为证据查询。

不好的检索查询：

```text
面向初学者解释储能锂离子电池循环实验数据分析中的 SOC SOH 容量衰减 库仑效率 能量效率 内阻 RUL OCV 安时积分 卡尔曼滤波
```

更好的证据查询（拆分为聚焦查询）：

```bash
curl -sS -X POST "http://221.0.79.251:18091/api/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINGXUE_API_TOKEN" \
  -d '{"question": "锂离子电池循环实验数据分析 SOC SOH 容量衰减 库仑效率 能量效率", "top_k": 4}'

curl -sS -X POST "http://221.0.79.251:18091/api/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINGXUE_API_TOKEN" \
  -d '{"question": "锂离子电池老化 内阻 容量衰减 SOH RUL 循环寿命", "top_k": 4}'

curl -sS -X POST "http://221.0.79.251:18091/api/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINGXUE_API_TOKEN" \
  -d '{"question": "SOC估计 OCV 安时积分 卡尔曼滤波 锂离子电池", "top_k": 4}'
```

如果用户问 5+ 个术语，拆分为 2-4 个聚焦查询。建议聚类：

| 聚类 | 术语 |
|------|------|
| 状态指标 | SOC、SOH、OCV |
| 实验指标 | 容量衰减、库仑效率、能量效率 |
| 老化与寿命 | 内阻、RUL、循环寿命 |
| 估计方法 | 安时积分、Kalman、EKF、UKF |

检索后合并证据：
- 去重高度相似的块和重复文档
- 优先 `abstract`、`method`、`result`、`table` 块而非通用 `body` 块
- 每个聚焦查询使用 `top_k 3-5` 而非一个大关键词堆砌
- 如果证据仍不足，运行一次额外的聚焦查询；不要从通用知识中填充答案

## 回答格式

返回：
1. 简短答案或结论
2. 基于证据的解释（来自返回的 `chunks`）
3. 来源列表：`rank`、`document`、`section_type`、`similarity`
4. 可选的参考信号说明（仅在对研究跟进有用时）

示例来源行：

```text
出处：rank #1, section=method, State_of_Charge_Estimation_of_Battery_Energy_Storage_Systems_Based_on_Adaptive_U.md, sim=0.671
```

如果检索到的块较弱，如实说明并避免过度声称。

## 常见错误

- 不要编造引用；只引用返回的块
- 不要在单个检索查询中堆砌许多松散相关的术语
- 不要混淆答案规划和检索规划
- 不要暴露或打印 token
- 不要声称页码；当前管道返回文档名和块，而非稳定的 PDF 页码

## 在课程报告里怎么用(学生端)

这是给课程报告找**真实证据**的检索工具(明学库覆盖电池/储能/SOC/SOH/RUL/Kalman/BMS 等)。

- **何时用**:报告选题落在上面这些领域时,**优先用本库检索**拿带出处的证据,而不是只靠模型常识或泛泛联网。选题不在覆盖范围时,回到 `literature-review` 的通用流程。
- **支架不代写**:把检索到的 `chunks` + 出处给你,帮你**理解、判断、自己写**;**绝不**用检索结果拼一段综述正文塞给你。
- **引用可核实**:只引用返回块里真实出现的文档;查不到就说查不到,不编。
- 和 `literature-review` 配合:本工具负责"检索到真证据",`literature-review` 负责"导读、筛选、搭阅读地图"。
