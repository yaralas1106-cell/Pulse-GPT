# JASM Completion Audit

Date: 2026-05-04

## Objective Restatement

Revise `docs/paper_draft.tex` and the stale `docs/paper_draft.pdf` according to `docs/review.md` until the paper is suitable for Journal on Audio, Speech, and Music Processing.

Concrete success criteria:

1. Address the review critique about overclaiming Time-Major synchronization.
2. Separate learned model response from Scheduler/rule enforcement.
3. Reframe the manuscript for an audio/music-processing journal rather than only symbolic generation.
4. Add or document audio-facing evidence and workflow validation.
5. Improve JASM/SpringerOpen submission compliance.
6. Rebuild and inspect the PDF.
7. Resolve remaining scientific, ethics, data, and artifact blockers.

## Prompt-to-Artifact Checklist

| Requirement | Evidence | Status |
| --- | --- | --- |
| Read review comments | `docs/review.md` was decoded as UTF-8 and reviewed; key issues are summarized in `docs/results/jasm_revision_audit.md`. | Pass |
| Reframe for JASM | Title, abstract, keywords, introduction, and `docs/results/jasm_revision_audit.md` now frame the paper as a hybrid music-processing/DAW workflow pipeline. | Partial pass |
| Weaken cross-track synchronization claims | Abstract, introduction, Time-Major contribution, related-work distinction, attention caption, and ablation prose now use "representational burden" and conservative output-level language. | Partial pass |
| Separate model and rules | Abstract and ablation table caption now describe PR as hybrid target adherence; ablation prose distinguishes FiLM local response from deterministic Scheduler. | Partial pass |
| Add audio-facing workflow evidence | Added `Rendered-Audio and Production Workflow Protocol` section; generated `docs/results/mos_audio_audit.md`. | Partial pass |
| JASM formatting | Switched the source to Springer Nature published-style two-column layout with the `iicol` class option to match the reference JASM article. | Partial pass |
| JASM declaration structure | `\section*{Declarations}`, `Availability of data and materials`, and `Authors' contributions` are present. | Partial pass |
| Static source consistency | `docs/results/static_latex_check.md`: 0 missing refs, 0 missing figures, 0 missing citations, brace balance 0. | Pass as static check |
| Compile current PDF | `pdflatex` still fails before compilation due local MiKTeX first-run/update setup. | Fail / blocked |
| MOS raw-data alignment | `docs/results/mos_source_inventory.md` and `docs/results/mos_audio_audit.md` show label mismatches among manuscript, ratings, MIDI, and MP3 assets. | Fail |
| Audio asset sanity | `docs/results/mos_audio_audit.md` flags six REMI MP3 files at 671 bytes. | Fail |
| Stronger baselines requested by review | CP + Scheduler, CP + Prefix, Track-Major + Energy/Scheduler have not been run. | Fail |
| Stronger output-level synchronization metrics | Added current 8-prompt kick--bass/chord co-activation and conditional onset diagnostics to `docs/paper_draft.tex`; outputs are in `docs/results/cross_track_coactivation_current_summary.csv` and `docs/results/cross_track_coactivation_current_per_file.csv`. | Partial pass |
| Counterfactual Elevel intervention | Not run. | Fail |
| Public-only/source-ablation evidence | Not run; `docs/results/dataset_source_audit.md` only supports source-count transparency. | Fail |
| Ethics approval | `SHU-REC-2024-XXXX` remains. | Fail / blocked |
| Artifact repository/DOI | Missing from manuscript. | Fail / blocked |

## Current Decision

The paper is not yet publication-ready for Journal on Audio, Speech, and Music Processing.

Reason: the manuscript now better matches the journal positioning and review critique, and it includes a preliminary output-level synchronization diagnostic. Publication readiness still requires a clean compiled PDF, resolved MOS/audio label inconsistencies, valid audio assets, full N=64 synchronization evidence or a further reduction in claims, stronger controllability baselines, ethics approval, and a final artifact repository/DOI.
