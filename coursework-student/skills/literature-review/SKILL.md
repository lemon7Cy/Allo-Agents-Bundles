---
name: literature-review
description: Literature guide for a course-report topic — search, filter, and annotate, producing verifiable sources and reading focus points. Read this skill when a student says "help me find / guide me through the literature", "which are the key papers", or "background material".
---

# Literature Guide Methodology

Help the student **quickly get oriented in the literature landscape of a topic**, but **never fabricate references**. The goal: let them know "what to read, why to read it, and which part to focus on" — not to read and write it for them.

## 0. Iron Rules
- **Sources must be verifiable**: for each reference give the title, author/source, year, and a link or search query. **If you can't find it, say so** — do not invent references, DOIs, or data.
- Use web tools for online search; use `read_file` for material the student uploads.

## 1. Workflow
1. **Clarify the topic and scenario**: course, discipline, topic direction, existing background. If vague, ask one follow-up question first.
2. **Search**: **when the topic is in the battery/储能/SOC/SOH and similar domains, prefer `kb-evidence-scaffold` to search the 明学 knowledge base** (returns real evidence blocks with sources), then supplement with web search + the student's uploaded material. Search separately around the topic's **core concepts / methods / typical applications / points of controversy**.
3. **Filter**: prioritize reviews / highly cited / authoritative sources / the last 3-5 years; remove clearly irrelevant or non-verifiable items.
4. **Annotate** (for each reference give):
   - one-sentence core viewpoint / contribution;
   - relationship to the student's topic (supporting / contrasting / method borrowing / gap);
   - **the part recommended for close reading** (which section, which figure/table, which method);
   - a verifiable source.
5. **Landscape summary**: what these references jointly outline, and what **gaps** remain (→ hand off to `topic-mining` to converge the topic).

## 2. Scaffold, Not Reading-for-Them
- Do not hand over a "literature-review section as finished prose". What you give is a **list + focus points + gaps**, so the student reads and writes the review themselves.
- Encourage the student to read with a question in mind: "When reading this one, note how it defines X / how it validates Y."

## 3. Output Template
```
选题:<…>　学科/课程:<…>

关键文献(可核实):
1. 《标题》｜作者/出处｜年份｜来源
   - 核心:…
   - 与你选题:支撑/对照/方法/缺口 —— …
   - 建议精读:第…节 / 图…
2. …

文献版图小结:目前研究集中在…;缺口/可切入点:…
缺口/查不到:<如有，明说，并给检索建议>
```
