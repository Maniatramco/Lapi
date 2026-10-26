---
name: candidate-shortlist
description: Rank resumes or profiles against stated requirements (skills, years, location) and explain each pick.
allowed_tools: describe_results, aggregate_results, find_extractions, read_extraction_results, search_knowledge, search_documents, update_plan
output_format: A ranked table (name, matched requirements, gaps) followed by one sentence per candidate on why.
---
1. Restate the requirements as a checklist with update_plan.
2. Use describe_results to find the saved fields that hold skills, experience and location.
3. Filter with read_extraction_results filters or aggregate_results; use search_knowledge only for requirements that are not saved fields.
4. Rank by number of requirements met, then by the most important one the user named.
5. Show gaps honestly. Do not infer skills that are not written in the source. Cite every candidate row.
