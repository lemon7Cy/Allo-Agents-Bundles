---
name: kb-evidence-scaffold
description: For a coursework report topic, use the 明学 knowledge base (battery/储能/SOC/SOH/RUL/Kalman/BMS, etc.) to retrieve real evidence — body-text evidence chunks, paper figures/tables, reference-list leads — and tell the student what to read and which section/figure to focus on, scaffolding them to read and write on their own. Never ghostwrite, never fabricate. Read this skill when the topic falls in this domain and the student wants to find literature, find evidence, see which papers exist, or get background material.
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

# 明学 Knowledge Base · Evidence Scaffold (Student Side)

**Purpose: help the student find real evidence + a reading map so they read and write it themselves — not read it through and write it for them.**

## Coverage domain (judge before using)
The 明学 knowledge base covers **lithium batteries / 储能 / SOC / SOH / RUL / capacity fade / Kalman·EKF·UKF / BMS / OCV / internal resistance**, etc.
- Topic falls in these areas → prefer this knowledge base for real, sourced evidence.
- Topic outside the coverage domain → **don't force a query**; fall back to the general literature flow in `literature-review`.

## Three evidence channels (how to use them for the student)
1. **chunks (body-text evidence)**: each chunk carries `section_type` (abstract/method/result/table), `document`, `similarity`. → Tell the student "which paper to read, which section to focus on".
2. **assets (paper figures/tables)**: `asset_type`=figure/table, with caption / table header / abstract. → **Most useful on the student side**: point them to "go look at this paper's Fig3 / Table2 and grasp the method or trend".
3. **reference_signals (reference-list leads)**: returned in `research` mode. → "what other papers you can find by following these references".

## How to call (use search only, not ask)
```bash
curl -sS -X POST "http://221.0.79.251:18091/api/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINGXUE_API_TOKEN" \
  -d '{"question": "focused retrieval question", "top_k": 4, "mode": "answer", "include_assets": true, "dataset": "论文"}'
```
- `mode`: defaults to `answer` (find evidence/methods); use `research` when the student asks "which key papers / the research thread".
- `top_k`: 3 for a quick look, 4-5 for normal, 8 for broad evidence. A Chinese query automatically searches English papers cross-lingually.
- **`dataset` (which 明学 library to search — pick by the student's intent; optional):**
  - `教材` — the course textbook (《储能系统检测技术》): authoritative definitions, chapter concepts. Use it when the student needs to understand a concept or find "which chapter/section to read"; point them to the exact chapter.
  - `论文` (**default** if omitted) — research papers: methods, results, related work — the evidence layer.
  - `课件` — course slides (per-chapter PPT): how the course itself frames a topic; use for classroom-material evidence.
  - `数据` — experiment/OCV/test data. ⚠️ Currently NOT retrievable (returns 0 chunks — known infrastructure gap). For data-analysis needs, guide the student to run code on the raw data files instead; don't keep querying this library.
  - Omit `dataset` → papers, same as before. NOTE: `include_assets` (figures/tables) exists **only for the paper library**; for `教材/课件/数据` the `assets` list comes back empty — that's expected, use the body `chunks`. `reference_signals` come back in both `answer` and `research` modes for the paper library (research is richer); other libraries may occasionally return non-empty signals when paper PDFs are mixed in — ignore those for citation purposes.
- **Similarity sanity check**: chunks with `sim < 0.35` are weak / likely-irrelevant hits — do NOT present them as evidence. Say the library has no direct match, mark the gap, and suggest a sharper re-query or an external database.
- **Use `/api/search` only. Never use `/api/ask`** — ask spits out a full prose answer, which equals ghostwriting and violates the scaffolding principle.

## Query planning (don't pile up jargon)
Break the student's big question into 2-4 focused queries, each `top_k 3-5`, instead of cramming ten terms into one sentence. Examples:
- `SOC 估计 OCV 安时积分 卡尔曼滤波`
- `锂电池 SOH 容量衰减 内阻 循环寿命`

When merging evidence: de-duplicate similar chunks, prefer abstract/method/result/table sections over generic body; if evidence is insufficient, run one more focused query — **do not fill in with the model's general knowledge**.

## Iron rules (scaffold, don't ghostwrite)
- **search-only**: don't use `/api/ask` to generate a prose answer.
- **Don't assemble the review body**: what you give is "evidence chunks + sources + which section/figure to focus on + gaps", letting the student digest and write it themselves.
- **Cite only documents actually returned**; if nothing is found, say so — never fabricate references / DOIs / data.
- Encourage the student to read with questions in mind: "while reading this paper, note how it defines X and how it validates Y."
- **Do not print or leak the token.**

## Output template for the student
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
