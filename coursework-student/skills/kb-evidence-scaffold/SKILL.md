---
name: kb-evidence-scaffold
description: For a coursework report topic, use the 明学 knowledge base (battery/储能/SOC/SOH/RUL/Kalman/BMS, etc.) to retrieve verifiable evidence — body-text chunks, paper figures/tables, and reference-list leads — then produce a reading map and evidence checklist. Read this skill when the topic falls in this domain and the student wants to find literature, find evidence, see which papers exist, or get background material.
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

## How to call (use the scoped MCP tool only)
Call the tool provided by the bundled `mingxue-kb` plugin (its visible name contains `mingxue_search`; runtimes may prefix the server name). Never call the REST endpoint through generic `bash`, because Web execution intentionally does not expose capability credentials to a shell.

Arguments example:
```json
{"question":"扩展卡尔曼滤波 锂电池 SOC 估计","top_k":4,"mode":"answer","include_assets":true,"dataset":"论文"}
```
- **Call budget / backpressure:** make exactly one Mingxue call at a time; never dispatch parallel Mingxue searches. Start with one focused `answer`, `top_k: 4` call. Only if that result has a clear evidence gap, make one additional focused call (or one `research` call for reference leads). Use `top_k: 3-5`; **never exceed 5** for this workflow. Stop after 1-2 calls and synthesize; do not spray near-duplicate queries.
- **This tool result is the evidence boundary.** Do not call generic `knowledge_base_list`, `knowledge_base_read`, or other knowledge-base tools to chase filenames returned by Mingxue. Do not turn a filename or reference signal into a complete citation from memory.
- `mode`: defaults to `answer` (find evidence/methods); use `research` when the student asks "which key papers / the research thread".
- `top_k`: 3 for a quick look, 4-5 for normal, 8 for broad evidence. A Chinese query automatically searches English papers cross-lingually.
- **`dataset` (which 明学 library to search — pick by the student's intent; optional):**
  - `教材` — the course textbook (《储能系统检测技术》): authoritative definitions, chapter concepts. Use it when the student needs to understand a concept or find "which chapter/section to read"; point them to the exact chapter.
  - `论文` (**default** if omitted) — research papers: methods, results, related work — the evidence layer.
  - `课件` — course slides (per-chapter PPT): how the course itself frames a topic; use for classroom-material evidence.
  - `数据` — experiment/OCV/test data. ⚠️ Currently NOT retrievable (returns 0 chunks — known infrastructure gap). For data-analysis needs, guide the student to run code on the raw data files instead; don't keep querying this library.
  - Omit `dataset` → papers, same as before. NOTE: `include_assets` (figures/tables) exists **only for the paper library**; for `教材/课件/数据` the `assets` list comes back empty — that's expected, use the body `chunks`. `reference_signals` come back in both `answer` and `research` modes for the paper library (research is richer); other libraries may occasionally return non-empty signals when paper PDFs are mixed in — ignore those for citation purposes.
- **Similarity sanity check**: chunks with `sim < 0.35` are weak / likely-irrelevant hits — do NOT present them as evidence. Say the library has no direct match, mark the gap, and suggest a sharper re-query or an external database.
- The MCP tool exposes search only; never try `/api/ask` — ask spits out a full prose answer, which equals ghostwriting and violates the scaffolding principle.

## Query planning (don't pile up jargon)
Plan 2-4 possible focused queries, but execute only the best one first and run at most one follow-up if its evidence is insufficient. Use `top_k 3-5`; don't cram ten terms into one sentence. Examples:
- `SOC 估计 OCV 安时积分 卡尔曼滤波`
- `锂电池 SOH 容量衰减 内阻 循环寿命`

When merging evidence: de-duplicate similar chunks, prefer abstract/method/result/table sections over generic body; if evidence is insufficient, run one more focused query — **do not fill in with the model's general knowledge**.

Preserve returned provenance exactly. If title/authors/year/venue/DOI or section location is missing, label it `元数据不完整，需外部核验`; never guess the missing fields, never claim "全文收录" unless the result explicitly proves it, and never relabel a paper hit as textbook/courseware merely because it is useful for teaching.

## Current-run evidence ledger (mandatory before synthesis)

For a substantive literature/evidence-map deliverable, the MCP response now contains `safe_markdown`, `safe_chat_summary`, and an `output_contract`. Treat these as renderer-owned output: write `safe_markdown` **verbatim** to `/mnt/user-data/outputs/文献导读.md`, call `present_files`, then return `safe_chat_summary` **verbatim** in chat. Do not merge two result bodies, rewrite the excerpts, add a landscape, infer limitations, or append remembered sources. One focused `answer` call with `top_k: 5` is the default and normally sufficient; make a second call only when the user asks a distinct second question, and keep its result as a separate evidence map instead of blending IDs.

Build a small internal ledger from the current Mingxue responses before writing chat or an artifact. The identifiers are mechanical and must never be reassigned:

- For each response, use the returned chunk `rank` exactly: call 1 chunk rank 6 is `R1-C6`. Use the returned asset rank/index as `R1-A…`. Number `reference_signals` separately as `R1-REF1`, `R1-REF2`, and so on.
- Never attach a `reference_signal` to a `C` identifier, never write labels such as `R1-C5 引文`, and never use one ID for content from another document.
- A claim about method, result, dataset, section, figure, or number must cite at least one current direct-hit/asset ID. If no current ID supports it, delete the claim.
- Keep `reference_signals` in a separate `二手引用线索（待外部核验）` section. A `REF` item may reproduce only what that returned signal itself says. Never count it as a directly retrieved/verified paper, never move it into `核心证据`, and never expand it with method/equation/figure details from another hit.
- Never use or mention `历史会话`, `此前对话`, model memory, a prior artifact, or remembered common values. They are not evidence for this run.
- Count unique returned `document` values as `知识库文档命中`, not as papers or verified literature. Report direct document hits and secondary reference leads separately.
- A returned filename or chunk does not by itself prove a formal title, venue, paper/document type, full-text coverage, completeness, citation counts, or landmark status. Do not write `从文档名推断`. Preserve the exact `document` filename and mark every absent bibliographic field `未提供`.
- Mention a section, equation, figure, table, dataset, or numeric result only if that exact detail appears in the cited current chunk/asset. Otherwise write `位置未提供` or omit it.
- Keep the deliverable small enough to audit: at most five direct evidence entries and at most five secondary reference leads. Prefer fewer well-grounded items over a broad landscape.

The final deliverable must preserve the renderer-owned stable `E-…` / `A-…` IDs beside every item so a reviewer can trace each statement back to the current tool output.

Before `write_file`, remove any line containing unsupported inference, any mixed `C/REF` identifier, any bibliographic field derived from a filename, and any claim that cannot be traced to the exact current chunk/asset. This provenance audit is mandatory even if it makes the guide shorter.

## Iron rules (scaffold, don't ghostwrite)
- **search-only**: use only the bundled `mingxue_search` MCP tool; don't use `/api/ask` to generate a prose answer.
- **Don't assemble the review body**: what you give is "evidence chunks + sources + which section/figure to focus on + gaps", letting the student digest and write it themselves.
- **Cite only documents actually returned**; if nothing is found, say so — never fabricate references / DOIs / data.
- Encourage the student to read with questions in mind: "while reading this paper, note how it defines X and how it validates Y."
- **Never print, echo, slice, count, inspect, or test the token/environment variable.** Do not run commands such as `echo $MINGXUE_API_TOKEN`, `${#MINGXUE_API_TOKEN}`, `env`, or `printenv`. Determine availability only from the MCP tool result. If the tool is absent or reports authentication failure, say the administrator must check the preconfigured credential and fall back to public literature search.

## Output template for the student
```
选题:<…>　覆盖域:命中明学库 ✅

关键证据(来自明学库,可核实):
1. [R1-C1][method] 《document 名》 sim=0.67
   - 这块在讲:…(一句话)
   - 你该重点读:第…节 / 看 Fig… / Table…
   - 和你选题的关系:支撑 / 方法借鉴 / 对照
2. …

图表线索:这篇的 Fig3(SOC-SOH 联合估计流程)值得照着理解方法。
二手引用线索(待外部核验):[R1-REF1 参考文献条目…]
缺口 / 查不到:<如有,明说,并给检索建议>
—— 接下来可按阅读地图继续查读，我可以继续帮你核对证据与引用。
```

For a substantive result, save it as `/mnt/user-data/outputs/文献导读.md` (or `/mnt/user-data/outputs/文献证据地图.md`) and call `present_files`. Also summarize the most useful 3-5 leads in chat.
