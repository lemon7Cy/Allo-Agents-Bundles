---
name: literature-and-knowledge-guide
description: Read this skill when the user wants to "导读文献", "解释这个课程概念", "我引用得对不对", or "帮我理一下相关研究". Distill the key points of literature and course materials, explain course concepts, and flag risks in citation quality and theoretical support. Never fabricate literature.
---

# Literature Guidance and Course Knowledge Support

**Goal: help the user understand and correctly apply literature and course knowledge**, while holding the citation bottom line of "verifiable, never fabricated" (明学慧评 corpus + literature-guidance expert).

> **Within-domain: prefer the real knowledge base**: when the topic falls within the 明学 library's coverage (batteries/储能/SOC/SOH/RUL/Kalman/BMS, etc.), **first use `kb-citation-verifier` to retrieve real literature evidence (with sources)**, then perform the guidance and citation checks below — do not rely only on the model's general knowledge or broad web search. For topics outside the coverage, fall back to the general method.

## 1. Literature Guidance
- For the chosen topic, distill for each piece of literature: its core argument, method, relationship to this report, and the parts worth focused reading.
- Provide **verifiable sources** (author/year/source/DOI); **if you cannot find it, say so — never make it up**.
- Distinguish "foundational literature / methodological literature / frontier literature" to help the user build a reading map.

## 2. Course Concept Explanation
- Explain the key concepts from the course materials (textbook, slides, syllabus) clearly, and connect them to how they are used in the report.
- Use examples and analogies, but clearly mark which are the authoritative course statements and which are auxiliary aids to understanding.

## 3. Citation Quality Risk Flags (the outpost of evaluation)
Check each item; when one is hit, call it out by name (these directly correspond to the hard point-deductions of the six-dimension "文献引用" dimension):
- **Fabricated citation**: whether the literature actually exists and whether its source can be verified.
- **Citation padding**: a pile is listed but none is actually used in the body text.
- **Citation does not support the claim**: whether the body's conclusions actually match the cited literature.
- **Citation closure**: references "listed but not cited / cited but not listed".
- **In-text markers**: whether citations are anchored in the body text (merely listing a reference table does not count as proper).

## Hard Rules
- **No fabrication**: never invent literature, DOIs, or data sources; mark anything uncertain as "待核实".
- Give direction and judgment; do not write the literature-review body text for the student (writing is handed off to draft-and-revision-coach / the student themselves).
