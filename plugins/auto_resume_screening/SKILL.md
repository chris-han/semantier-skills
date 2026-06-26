---
name: auto-resume-screening
description: 自动简历筛选：extract uploaded resume text from PDF, DOCX, Markdown, or text files, rank candidates against a job profile, and write a workspace artifact.
metadata:
  semantier:
    route: procedural_only
---
# 自动简历筛选

Use this skill when the user asks to screen uploaded resumes, compare candidates for a role, or build a short list from resume files.

Call the registered `screen_resumes` tool with:

- `job_profile.title`
- `job_profile.required_keywords`
- `job_profile.preferred_keywords`
- `job_profile.negative_keywords`
- `job_profile.min_years_experience`
- `resume_paths`

Use `list_session_uploads` when you need to inspect which files are available in the active session. Use `resolve_uploaded_resume` when a user-provided filename may differ from the uploaded filename; it resolves filenames, `uploads/<filename>` paths, and `upload_id` values through the active session upload manifest. If resolution is ambiguous, ask the user to choose from the returned candidates instead of guessing.

Use `extract_resume_text` only when the user asks for text extraction from a single resume. Use `rank_resume_candidates` only when resume text has already been extracted.

Use `extract_role_terms` only when maintaining or auditing the role-title negative filter. It fetches the configured occupation index pages and returns terms missing from the current plugin heuristic; it does not screen resumes or update source files by itself.

Supported resume formats are `.pdf`, `.docx`, `.md`, and `.txt`. PDF extraction uses deterministic `pypdfium2` embedded-text extraction only; OCR is intentionally not used by default.

Do not use terminal, generated Python, ad hoc HTTP, unmanaged files, prompt memory, or user self-claims as substitutes for the registered tool surface. If the tool surface is not loaded, stop and report that the `auto_resume_screening` plugin must be installed or enabled in the active workspace.

Output the top candidates with scores, recommendations, and evidence from the returned artifact. Treat the score as a decision-support signal, not an employment decision by itself. If the user asks for a final hiring decision, explain that the plugin provides screening evidence and that a human reviewer should make the final decision.

Do not infer protected attributes. Do not rank by age, gender, ethnicity, marital status, health status, household registration, or other protected or irrelevant personal attributes.
