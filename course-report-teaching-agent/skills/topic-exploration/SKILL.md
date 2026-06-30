---
name: topic-exploration
description: Read this skill when a user (teacher or student) asks to "推荐选题", "帮我想课程报告题目", or "评估这个选题行不行". From course objectives + student interests + available materials + literature gaps, converge on topic candidates that are self-directed and non-convergent (not look-alike), and evaluate each one on 创新性 / 可行性 / 数据可得性 / 课程匹配度 / 风险.
---

# Exploration and Topic-Selection Methodology (Teacher Perspective)

**Goal: help the student find a topic that "has something of their own, does not converge with peers, and is actually doable".** Do not decide the topic for the student; instead, provide several candidates + the rationale for choosing among them, keeping the decision in the student's hands (明学慧评's principle of "giving students the autonomy to explore their interests").

## Inputs (if missing, ask the user; do not fabricate)
- Course objectives / report requirements (scope, credit hours, submission specs).
- Student interest areas, existing data/materials (asset library), and reference literature/textbooks (corpus).

## Output: 3–5 topic candidates, each scored on five dimensions
| Dimension | What to look at |
|---|---|
| 创新性 | Whether the angle/method has something of its own; avoid duplicating topics with the rest of the class. |
| 可行性 | Whether it can be completed within an undergraduate's credit hours and ability. |
| 数据可得性 | Whether the required data/experiments can be obtained (prefer data the student already has or public datasets). |
| 课程匹配度 | Whether it stays anchored to the course's core knowledge points and objectives. |
| 风险 | Topic too broad/too vague, data unobtainable, methods beyond the syllabus, etc. |

## Hard Rules
- **No convergence**: explicitly avoid the pain point where "a uniform teacher-assigned topic leads to near-identical content"; encourage individualization.
- **No fabrication**: do not invent dataset availability or assume resources the student does not have; mark anything uncertain as "待确认".
- **Give the rationale**: for every candidate, spell out "why it is recommended / where the trade-off lies" so the student can judge for themselves.

## Output Template
```
选题候选(按推荐度排序):
1.《…》创新性: … 可行性: … 数据: … 匹配: … 风险: … → 适合你如果…
2.《…》…
建议:你更看重 X 就选 1,更想稳就选 2;还缺 <某数据/文献> 需要先确认。
```
