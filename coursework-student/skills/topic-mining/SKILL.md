---
name: topic-mining
description: Mine coursework report topics that are autonomous, feasible, and non-convergent from the student's interests, data, and literature gaps. Read this skill when the student says "没想好选题" "帮我想几个题目" "选题方向".
---

# Topic Mining Methodology

Addresses one of the pain points raised by 明学慧评: **teacher-assigned topics lead to convergent content and a lack of student autonomy**. Your task is to help the student mine topics that are **of genuine personal interest, feasible, and non-colliding** — but **the choice of topic belongs to the student**; you only provide candidates and the rationale for the trade-offs.

## 0. Three criteria (every candidate must pass)
- **Autonomy**: close to the student's own interests / experience / major direction, not a templated fill-in.
- **Feasibility**: completable within the course duration, data availability, and the student's ability.
- **Non-convergence**: differentiated from "standard-answer" topics (has its own angle / data / case).

## 1. Workflow
1. **Mine interests**: probe the student — which course content has ever made you go "huh, interesting"? Do you have your own data / experience / real-world problem you care about? (If not, guide from their major / course syllabus.)
2. **Connect materials**: look at the data/materials the student uploaded + the **literature gaps** provided by `literature-review` — a gap is often a good topic.
3. **Generate candidates**: give **3-5** topic candidates, each containing:
   - a one-sentence topic title;
   - the angle / why it is non-convergent;
   - the data/methods needed + a feasibility judgment;
   - which quality dimensions it is expected to demonstrate (创新性/数据深度/…).
4. **Guide convergence**: don't decide for them. Use questions to help them choose: "which one do you most want to pursue?" "which one do you already have data for?"

## 2. Evidence boundary for topic candidates

- Topic mining is not a literature or data-source search. Unless another skill already opened and verified a source in this same run, do not name any author, paper, journal, year, DOI, public dataset, data portal, benchmark, or literature trend. Describe external inputs generically as data that still needs discovery and verification.
- Derive differentiation from only the student's stated course, interests, available fields/materials, constraints, and methods. Without current-run evidence, do not claim that “most reports”, “recent literature”, or “few studies” use or omit a method; describe the candidate's own contrast instead.
- Treat a user-described dataset as available but uninspected until an actual uploaded file has been read. State conditional checks such as “if `temp_c` spans multiple ranges” instead of asserting its distribution or quality.
- Do not promise grades or declare one option “highest-scoring”, “best”, or “safest”. Compare observable workload, prerequisites, evidence needs, and failure modes, then let the student choose.

## 3. Scaffold, don't take over
- Don't just decree "do this one." Give candidates + criteria + follow-up questions, and let the student **decide for themselves**.
- Candidates should scale deep or shallow; label difficulty so the student can gauge their capacity.

## 4. Deterministic topic-candidate artifact

For a substantive request for 3-5 topic candidates, never hand-write `/mnt/user-data/outputs/选题候选.md`. Write one JSON ledger to `/mnt/user-data/tmp/topic_candidates.json` with this shape:

```json
{
  "course": "user-supplied course",
  "interest": "user-supplied interest",
  "requirements": ["current-run course requirement"],
  "dataset": {
    "description": "user-supplied dataset description",
    "inspected": false,
    "fields": ["exact user-supplied field names"]
  },
  "candidates": [
    {
      "title": "candidate title",
      "course_fit": "observable match to the stated course requirements",
      "differentiation": "contrast created from the stated data, method, condition, or evaluation dimension",
      "data_requirements": [
        {
          "item": "required input or prerequisite",
          "status": "stated-available|needs-inspection|needs-derivation|missing-or-external",
          "basis": "what the user or an opened file currently establishes"
        }
      ],
      "method_steps": ["bounded method step"],
      "difficulty": "low|medium|high",
      "difficulty_basis": ["observable source of work"],
      "risks": ["specific failure condition"],
      "go_no_go_checks": ["check before choosing this direction"]
    }
  ]
}
```

Set `dataset.inspected=false` unless an actual uploaded data file was read successfully in this run. Never label an OCV-SOC curve, equivalent-circuit parameter, ground truth, temperature range, sample adequacy, or train/test suitability as available merely because the user listed generic CSV fields; put it under `needs-inspection`, `needs-derivation`, or `missing-or-external` as appropriate.

Then run exactly:

```bash
python3 /mnt/skills/agent/topic-mining/scripts/render_topic_candidates.py \
  --input /mnt/user-data/tmp/topic_candidates.json \
  --output /mnt/user-data/outputs/选题候选.md
```

The renderer removes unsupported citations, prevalence claims, rankings, promises, and absolute sufficiency claims. Do not rewrite the ledger merely to restore normalized content. On `status=ok`, call `present_files` and return `safe_chat_summary` verbatim as the whole final answer. On a structural error, fix every listed issue in one edit and rerun at most once.
