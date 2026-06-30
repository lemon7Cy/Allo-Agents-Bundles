---
name: kb-evidence-scaffold
description: 围绕课程报告选题,用明学知识库(电池/储能/SOC/SOH/RUL/Kalman/BMS 等)检索真实证据——正文证据块、论文图表、参考文献线索——给学生"读什么、重点读哪段/哪个图",支架学生自己读自己写。绝不代写、绝不杜撰。当选题落在该领域、学生要"查文献/找证据/有哪些论文/背景资料"时读本 skill。
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

# 明学知识库 · 证据脚手架(学生端)

**定位:帮学生找到真实证据 + 一张阅读地图,让他自己读、自己写——不是替他读完写完。**

## 覆盖域(用之前先判断)
明学库覆盖 **锂电池 / 储能 / SOC / SOH / RUL / 容量衰减 / Kalman·EKF·UKF / BMS / OCV / 内阻** 等。
- 选题在这些领域 → 优先用本库拿带出处的真证据。
- 选题在覆盖域外 → **不要硬查**,回到 `literature-review` 的通用文献流程。

## 三条证据通道(怎么用给学生)
1. **chunks(正文证据)**:每块带 `section_type`(abstract/method/result/table)、`document`、`similarity`。→ 告诉学生"读哪篇、重点读哪一节"。
2. **assets(论文图/表)**:`asset_type`=figure/table,带 caption / 表头 / 摘要。→ **学生端最有用**:指给他"去看这篇的 Fig3 / Table2,弄懂这个方法或趋势"。
3. **reference_signals(参考文献线索)**:`research` 模式返回。→ "顺这些参考文献还能找到哪些论文"。

## 如何调用(只用 search,不用 ask)
```bash
curl -sS -X POST "http://221.0.79.251:18091/api/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINGXUE_API_TOKEN" \
  -d '{"question": "聚焦的检索问题", "top_k": 4, "mode": "answer", "include_assets": true}'
```
- `mode`:默认 `answer`(找证据/方法);学生问"有哪些关键论文 / 研究脉络"时用 `research`。
- `top_k`:快速看 3,常规 4-5,广证据 8。中文 query 会自动跨语言搜英文论文。
- **只用 `/api/search`。绝不用 `/api/ask`** —— ask 会直接吐成段答案,等于代写,违背支架原则。

## 查询规划(别堆术语)
把学生的大问题拆成 2-4 个聚焦 query,每个 `top_k 3-5`,而不是一句塞十个术语。例:
- `SOC 估计 OCV 安时积分 卡尔曼滤波`
- `锂电池 SOH 容量衰减 内阻 循环寿命`

合并证据时:去重相似块、优先 abstract/method/result/table 段而非通用 body;证据不足就再补一次聚焦 query,**不要用模型常识填**。

## 铁律(支架不代写)
- **search-only**:不用 `/api/ask` 生成成段答案。
- **不拼综述正文**:给的是"证据块 + 出处 + 重点读哪段/哪个图 + 缺口",让学生自己消化、自己写。
- **只引真实返回的文档**;查不到就说查不到,绝不编文献 / DOI / 数据。
- 鼓励学生带问题读:"看这篇时注意它怎么定义 X、怎么验证 Y。"
- **不要打印或泄露 token。**

## 给学生的输出模板
```
选题:<…>　覆盖域:命中明学库 ✅

关键证据(来自明学库,可核实):
1. [method] 《document 名》 sim=0.67
   - 这块在讲:…(一句话)
   - 你该重点读:第…节 / 看 Fig… / Table…
   - 和你选题的关系:支撑 / 方法借鉴 / 对照
2. …

图表线索:这篇的 Fig3(SOC-SOH 联合估计流程)值得照着理解方法。
顺藤摸瓜(research 模式):还可追 [参考文献条目…]
缺口 / 查不到:<如有,明说,并给检索建议>
—— 接下来你自己读、自己写综述,我只给地图。
```
