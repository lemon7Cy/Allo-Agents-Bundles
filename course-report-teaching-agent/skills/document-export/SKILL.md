---
name: document-export
description: Export a completed teaching plan, course-report draft, literature guide, revision plan, evaluation, or other text deliverable as a real PDF or editable Word DOCX file. Always use, alongside any needed content-writing skill, when the user explicitly asks for PDF, Word, DOCX, a printable file, an editable Word document, or a specific final document format. Do not trigger merely because a downloadable Markdown artifact is being produced.
---

# Document Export

Convert finished content to the exact document format requested by the user. The renderer supports headings, paragraphs, lists, block quotes, code blocks, and Markdown tables.

Use this skill whenever the user explicitly requests PDF, Word, or DOCX, including when another content skill is also needed. Finish the substantive document first, then use this renderer to create the real requested file in the same turn.

## Workflow

1. Finish the substantive content first. Do not replace the requested deliverable with an outline unless the user asked for an outline.
2. Select the output from the explicit request:
   - `PDF` / printable / archive-ready -> `.pdf`
   - `Word` / `DOCX` / editable document -> `.docx`
   - both formats -> render both files
   - no explicit PDF or Word request -> keep the agent's existing Markdown artifact behavior
3. Write the complete Markdown source to `/mnt/user-data/tmp/<clear-name>.md`. Keep this temporary source out of the成果文件 panel unless the user also requested Markdown.
4. Render each requested file with the direct top-level command below:

```bash
bash /mnt/skills/agent/document-export/scripts/render_document.sh \
  --input "/mnt/user-data/tmp/<clear-name>.md" \
  --out "/mnt/user-data/outputs/<clear-name>.pdf"
```

For Word, use the same command with an output ending in `.docx`. Add `--title "<document title>"` when the source has no clear top-level heading.
5. Require the renderer's final JSON line to contain `"status": "ok"`. In a separate top-level shell call, confirm the exact output path exists and is non-empty, then call `present_files` with the real `.pdf` or `.docx` path.
6. In chat, state which formats were produced. Never describe Markdown as Word/PDF and never change only the filename extension.

## Boundaries

- Prefer a specialized renderer when one exists. In particular, a course-evaluation PDF with radar data or video key frames must use `report-pdf-export`; use this generic exporter for teaching plans, drafts, guides, ordinary reports, and Word output.
- Preserve evidence boundaries, citations, `待补充`, and `待核实` markers from the completed source. Rendering must not add claims or scores.
- Do not check for or install Pandoc, `python-docx`, ReportLab, or any other converter dependency. Do not create a one-off conversion script, and do not embed `/mnt/user-data/outputs/...` as a literal path inside custom Python. The bundled command above is the only generic PDF/Word conversion route.
- Use a concise, content-based Chinese filename. Sanitize `/`, `\\`, and `..`; never use a student's name when an existing evaluation policy requires naming by report/topic title.
- Write final files only under `/mnt/user-data/outputs/`.
- If rendering fails, do not loop. Report the failure briefly and provide the completed content in chat or Markdown instead of claiming that a PDF/DOCX exists.
