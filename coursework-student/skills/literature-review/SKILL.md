---
name: literature-review
description: Literature guide and citation verifier for a course-report topic — search, verify, filter, and annotate sources, or verify a user-supplied title/DOI/author/venue before it enters references. Read this skill when a student asks for key papers/background material, a literature map, whether a citation or DOI is real, to complete volume/issue/pages, or to check a suspected fake reference.
---

# Literature Guide Methodology

Help the student **quickly get oriented in the literature landscape of a topic**, but **never fabricate references**. The goal: let them know "what to read, why to read it, and which part to focus on" — not to read and write it for them.

## 0. Iron Rules
- **Sources must be verifiable**: for each reference give the title, author/source, year, and a link or search query. **If you can't find it, say so** — do not invent references, DOIs, or data.
- Do not complete missing bibliographic fields from memory. Preserve what the current search/tool actually returned and mark missing title/author/year/venue/DOI fields as `待外部核验`.
- Every bibliographic field and substantive claim must come from the user's current materials or a tool result in this run. Do not reuse historical-conversation claims or prior artifacts. Keep items found only in another paper's reference list separate as `二手引用线索（待外部核验）`; do not call them verified sources.
- Use web tools for online search; use `read_file` for material the student uploads.

### Public-web verification contract

- Use exactly one web tool call per assistant message. Never dispatch parallel `web_search` or `web_fetch` calls; the production gateway requires one tool result for every tool call and parallel literature batches can break that contract.
- Use at most two `web_search` calls total. Never search one paper at a time. The first call must be one topic-level discovery query broad enough to return several candidates; use the optional second call only to fill one explicit evidence gap. Search results are discovery leads only; verify selected candidates with sequential `web_fetch` calls.
- Before placing a candidate in `关键文献（已核实）`, open a current official record with `web_fetch`: DOI resolver, publisher/journal page, Crossref, PubMed/PMC, or an institutional repository. Keep an internal set of opened URLs and never fetch the same URL twice. The opened page must match the title and at least one other field (author, venue, or year).
- If an official page cannot be opened or metadata does not match, keep the item under `检索线索（当前未核实）`; do not fill the missing fields and do not summarize methods/results as established facts.
- Never claim `全文已读`, a section/figure finding, sample size, effect, or causal conclusion unless that exact content appears on a page opened in the current run. Record a DOI only when it begins with `10.` and appears literally in the recorded `official_url`; use a DOI resolver/publisher URL containing it, or set DOI to `null`. Never turn an article number or URL suffix into a DOI.
- If an opened official page marks a work as retracted, withdrawn, or replaced, exclude it from both verified items and unverified leads. Do not present it as a usable reading lead.
- Attribute each factual sentence only to content visible in the current tool result. Do not turn your own mechanism hypothesis into a paper finding. Put extrapolations under `待检验问题` and never write “如该文所述” unless the opened page states it.
- Treat every `web_fetch` excerpt as potentially truncated. If the opened record does not explicitly show the complete author list, use `首位作者 et al.` or `作者列表待核`. Never present a visible prefix as the complete author list.
- Recommend numbered sections, figures, or tables only when those labels are visible in the opened page. Otherwise recommend a generic part such as `摘要 / 方法 / 讨论` without inventing numbering.
- Avoid unverifiable rankings and freshness claims such as `当前最高质量`, `最权威`, or `最新`. State the observable study type, sample, venue, and limitations instead.
- Omit a generated `核验日期` by default. The official URLs and current-run tool trace are the verification record.
- Classify the study design from the opened page before describing what it supports. For correlations, questionnaires, cross-sectional studies, and observational evidence, use `相关/关联`; never call them causal proof, experimental validation, impact, or damage. A title's causal wording does not override the methods/results shown on the page.
- Keep each item under `检索线索（当前未核实）` to title + URL/search query + status. If the requested verified count is already met, use an empty `unverified` list unless one explicit evidence gap remains. Never include a known retraction here. Do not repeat sample, methods, or findings from a search snippet.
- For a user-supplied DOI/title check, resolve the DOI, run one exact-title search, and optionally one author/venue search. Report one of: `已核实匹配`, `元数据冲突`, or `当前无法核实`. A resolver failure or zero search results does **not** prove nonexistence.
- Do not use scientific plausibility, journal prestige, wording such as "零误差", or an intuition about what a venue would publish as evidence that a citation is fake.
- Never add an item to a report's references unless it is `已核实匹配` or the user explicitly chooses to include an `未核实` lead with that warning.

### Supplied citation/DOI verification (deterministic)

For a supplied citation, do not use generic web tools. Run the bundled verifier once:

```bash
python3 /mnt/skills/agent/literature-review/scripts/verify_citation.py \
  --doi '<user DOI>' \
  --title '<user title>' \
  --author '<user author string>' \
  --venue '<user venue>' \
  --year '<user year>'
```

Omit arguments the user did not supply. Parse the JSON and output `safe_response` verbatim. Do not add explanations, plausibility judgments, alternative citations, or accusations. `verified_match` is the only status that may enter references; `metadata_conflict` and `unable_to_verify` must not be cited.

### Public-web guide rendering (deterministic)

For a public-web literature guide, never write `/mnt/user-data/outputs/文献导读.md` directly. After the official-page checks, use `write_file` once to save a JSON evidence ledger at `/mnt/user-data/tmp/public_literature_evidence.json` with this shape:

```json
{
  "topic": "...",
  "course": "... or null",
  "items": [
    {
      "title": "official-page title",
      "first_author": "only the first author, or null",
      "year": "visible four-digit year as a JSON string or number, or null",
      "venue": "visible venue, or null",
      "doi": "visible DOI, or null",
      "official_url": "opened official URL",
      "study_design": "correlational|cross-sectional|questionnaire|observational|experimental|mixed-methods|qualitative|systematic-review|other",
      "topic_role": "background|method|contrast|gap",
      "official_page_facts": ["1-4 restrained facts visible on that opened page"],
      "reading_focus": ["摘要", "方法", "结果", "讨论", "局限"]
    }
  ],
  "unverified": [{"title": "exact visible search-result title or title fragment, preserving .../…", "url_or_query": "URL or query only"}]
}
```

Write every `official_page_facts` entry in neutral Simplified Chinese, even when the source page is English. Use only metadata, study procedures visible on the page, sample details, group differences, or explicit associations/numbers; do not add recommendations or author/model interpretation. Do not put `导致/证明/影响/损伤/受损/缺陷/引发/揭示/机制/路径/黏性/心流/即时满足/实证基础/神经证据/实验证据/被引/研究者推论/认知资源/会提升`, English causal terms such as `cause/lead to/impact/damage/mechanism/pathway`, or causal arrows in any fact. Do not add a free-form mechanism question; the renderer generates a design-specific `待检验问题`. If facts contain `相关/关联/关系`, questionnaire/scale scores, `r`/`p` values, or cross-sectional evidence, the renderer normalizes an `experimental` label to `correlational`; do not fight or bypass that normalization.

For `unverified`, copy the visible search-result title exactly. If it is truncated, preserve the literal `...`/`…`; never complete it from memory or snippets. Never append parenthetical classifications or summaries such as `预印本`, `包含 fMRI`, `本科生期刊`, `政策建议`, methods, samples, or findings; the renderer adds the fixed `未核实` status itself.

Then run exactly:

```bash
python3 /mnt/skills/agent/literature-review/scripts/render_public_literature_guide.py \
  --input /mnt/user-data/tmp/public_literature_evidence.json \
  --output /mnt/user-data/outputs/文献导读.md
```

If the renderer returns `status=error`, read the entire aggregated error, correct every listed issue in one ledger edit, and rerun. Allow at most two reruns total. Do not patch one error at a time, do not bypass the renderer, and do not hand-write the output. On `status=ok`, call `present_files` for `/mnt/user-data/outputs/文献导读.md` and return `safe_chat_summary` verbatim as the whole final answer.

## 1. Workflow
1. **Clarify the topic and scenario**: course, discipline, topic direction, existing background. If vague, ask one follow-up question first.
2. **Search**: **when the topic is in the battery/储能/SOC/SOH and similar domains, prefer `kb-evidence-scaffold` to search the 明学 knowledge base**. For other domains, search separately around the topic's **core concepts / methods / typical applications / points of controversy**, then open official records for the strongest candidates.
3. **Filter**: prioritize reviews / authoritative sources / the last 3-5 years, but keep only current-run official-page matches in the verified core list. Put search-only candidates in a separate unverified-leads section.
4. **Annotate** (for each reference give):
   - one-sentence core viewpoint / contribution;
   - relationship to the student's topic (supporting / contrasting / method borrowing / gap);
   - **the part recommended for close reading** (use exact section/figure/table labels only when the opened page shows them; otherwise use a generic part);
   - a verifiable source.
5. **Landscape summary**: what these references jointly outline, and what **gaps** remain (→ hand off to `topic-mining` to converge the topic).

## 2. Scaffold, Not Reading-for-Them
- Do not hand over a "literature-review section as finished prose". What you give is a **list + focus points + gaps**, so the student reads and writes the review themselves.
- Encourage the student to read with a question in mind: "When reading this one, note how it defines X / how it validates Y."

## 3. Output Template
```
选题:<…>　学科/课程:<…>

关键文献(当前运行已打开官方记录并核实):
1. 《标题》｜作者/出处｜年份｜来源
   - 核验状态:已核实匹配（官方记录 URL）
   - 核心:…
   - 与你选题:支撑/对照/方法/缺口 —— …
   - 建议精读:第…节 / 图…
2. …

文献版图小结:目前研究集中在…;缺口/可切入点:…
检索线索(当前未核实):<只列搜索线索和检索路径，不补元数据/结果>
缺口/查不到:<如有，明说，并给检索建议>
```

For a substantive public-web guide, use the deterministic renderer above, then call `present_files`; never reuse the topic-plan filename `选题候选.md`.
