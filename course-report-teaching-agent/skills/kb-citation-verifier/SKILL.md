---
name: kb-citation-verifier
description: Use the 明学 knowledge base (battery/储能/SOC/SOH/RUL/Kalman/BMS, etc.) to obtain real literature evidence for teaching and evaluation — literature support for topic selection, verifying whether student citations are real / whether they support the conclusion, and using paper figures/tables to corroborate methods and data. Read this skill when recommending topics, building the corpus, or reviewing the "文献引用/数据分析" dimensions. Never fabricate.
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

# 明学 Knowledge Base · Literature Foundation + Citation Verifier (Teacher Side)

**Purpose: obtain real literature evidence during teaching/evaluation. Two main uses — ① literature support for topic selection and the corpus; ② during review, verify student citations and corroborate methods and data.**

## Coverage Domain
The 明学 base covers **lithium battery / 储能 / SOC / SOH / RUL / capacity fade / Kalman·EKF·UKF / BMS / OCV / internal resistance**, etc. Only use this base when the topic is within the domain; for out-of-domain topics, fall back to general literature methods — don't force-fit.

## Three Evidence Channels (which one to use for evaluation evidence-gathering)
1. **chunks (body-text evidence)**: abstract/method/result/table segments → check whether the student's claims about method/conclusion match the real literature.
2. **assets (paper figures/tables)**: figure/table + caption/table-header/abstract → corroborate whether the student's data analysis aligns with real methods and trends.
3. **reference_signals (references)**: returned by `research` mode → **the primary channel for verifying citations**.

## How to Call
```bash
curl -sS -X POST "http://221.0.79.251:18091/api/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINGXUE_API_TOKEN" \
  -d '{"question": "focused search question", "top_k": 5, "mode": "research", "include_assets": true, "dataset": "论文"}'
```
- For citation verification use `mode: research` (preserves citation signals); for finding method/data evidence use `answer`. A Chinese query automatically searches English papers cross-lingually.
- **`dataset` (which 明学 library to verify against — pick by the check; optional):**
  - `论文` (**default** if omitted) — verify the student's **citations** against real research papers. This is the primary channel for citation verification.
  - `教材` — the course textbook (《储能系统检测技术》): check a claim/concept against **authoritative course content** (for 选题 support and concept correctness), and cite "教材第 X 章" instead of only papers.
  - `课件` — course slides (per-chapter PPT), to check how the course itself presented a topic.
  - `数据` — experiment/OCV/test data. ⚠️ Currently NOT retrievable (returns 0 chunks — known gap); for the **数据分析** dimension, corroborate against the raw data files / the student's code instead of this library.
  - Omit `dataset` → papers. NOTE: `include_assets` (figures/tables) exists **only for the paper library** — other libraries return empty `assets`. `reference_signals` are **authoritative from the paper library only**; 教材/课件 can occasionally return non-empty signals (paper PDFs mixed into those libraries) — do NOT use them for citation verification.
  - **Similarity sanity check**: `sim < 0.35` hits are weak / likely-irrelevant — treat them as 「库里查不到」 rather than as evidence.
- The teacher is the evaluation authority and **may produce reviews/syntheses based on the search results** (not bound by the "ghostwriting" restriction). If the server has an LLM configured, use `/api/ask` for lesson preparation.

## Citation Verification Workflow (evidence-gathering means for the "文献引用" evaluation dimension)
Corresponding to the five citation-risk points in `literature-and-knowledge-guide`, gather evidence item by item from the 明学 base:
1. **Fabricated citation**: take the title/claim of the literature the student cited and search → does the base have a real match? If not found → mark "待核实 / 疑似虚构".
2. **Citation does not support the claim**: search that claim → does the conclusion of the real literature match the student's usage?
3. **Padding / circular citing**: combined with the body text, check whether the citations are actually used and whether the listed references correspond.
4. **Corroborate the data-analysis dimension**: are the student's SOC/SOH methods and degradation trends consistent with the method/result segments or figures/tables in the base?

## Iron Rules
- **Never fabricate**: only trust documents actually returned by the 明学 base; if verification fails, mark "待核实" — don't make things up for the student, and don't paper over gaps for them.
- In the evaluation conclusion, distinguish three states: **库里有据** / **库里查不到** / **库里证据相反**.
- **Do not print or leak the token.**

## Output (evaluation-evidence snippet)
```
文献引用核查(明学库取证):
- 学生引用「<观点/文献>」→ 库内检索:
    ✅ 命中《doc》sim=0.7,结论一致
    ⚠️ 查不到,疑似虚构 / 待核实
    ❌ 库内证据相反(《doc》指出…)
- 数据分析佐证:学生用 <方法>,库内 method 段 / Fig… 支持 or 不支持 —— …
口径:仅明学库(电池/储能域);域外引用未纳入核查。
```
