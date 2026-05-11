# JASM Revision Audit

Date: 2026-05-04

Target journal: Journal on Audio, Speech, and Music Processing.

Official pages consulted:

- `https://asmp-eurasipjournals.springeropen.com/`
- `https://asmp-eurasipjournals.springeropen.com/submission-guidelines`
- `https://link.springer.com/journal/13636/submission-guidelines`

## Official Journal Fit

The journal positions itself around theory and applications in speech, audio, and music processing. The manuscript is therefore being reframed from a purely symbolic-generation architecture paper into a hybrid music-processing and DAW-production workflow paper.

Observed official submission requirements relevant to the current source package:

- The submitted review manuscript may use line numbering and double-line spacing, but the user-provided JASM reference article uses the final Springer Nature two-column publication layout.
- LaTeX source files should be included at submission.
- The journal supports article types including empirical research, methodology, and software-style work, which is the best fit for this manuscript after reframing.

## Review-Derived Revision Tasks

| Review issue | Current action | Remaining gap |
| --- | --- | --- |
| Cross-track synchronization claim is too strong. | Title, abstract, introduction, related work, attention caption, and ablation wording now describe Time-Major as reducing the representational burden for cross-track coordination. Added a conservative output-level kick--bass/chord co-activation diagnostic to `docs/paper_draft.tex` using the current 8-prompt MOS MIDI set. | Full output-level synchronization evidence still needs N=64 and validated track labels/audio assets. |
| Scheduler/rule contribution is overexposed as model learning. | Abstract and ablation caption now call PR=0.982 hybrid target adherence; ablation prose distinguishes local FiLM response from deterministic macro scheduling. | Counterfactual Elevel intervention is still missing. |
| Baselines lack similarly controlled competitors. | Existing text acknowledges the controlled protocol limits. | Need CP + Scheduler, CP + Prefix, and/or Track-Major + Energy/Scheduler baselines. |
| MOS evidence should be downgraded. | MOS procedure now explicitly says results are perceptual support, not standalone proof of general musical quality. | MOS raw rating labels, audio/MIDI assets, and manuscript labels remain inconsistent. |
| JASM needs stronger audio/music-processing framing. | Title/abstract/introduction now emphasize rendered-audio validation, DAW workflow, and music-processing pipeline. Added Section `Rendered-Audio and Production Workflow Protocol`. | Signal-level audio descriptors are not yet computed. |
| Submission formatting. | Switched `docs/paper_draft.tex` to the Springer Nature `iicol` two-column layout to match the user-provided JASM reference article. | PDF compile and visual inspection are still blocked by the local TeX environment. |

## New Evidence Files

- `docs/results/dataset_source_audit.md`: verifies visible source counts: 117,145 GigaMIDI + 6,012 Lakh + 3,647 restricted DAW = 126,804.
- `docs/results/mos_audio_audit.md`: inventories rendered MOS MP3 files and flags label mismatches/small REMI audio files.
- `docs/results/mos_source_inventory.md`: inventories MOS MIDI/rating/manuscript label mismatches.
- `docs/results/cross_track_coactivation_current_summary.csv`: current 8-prompt output-level kick--bass/chord co-activation summary.
- `docs/results/cross_track_coactivation_current_per_file.csv`: per-file support for the co-activation diagnostic.

## Current Blocking Items

- The active manuscript PDF is stale because local MiKTeX cannot compile the edited source.
- `analysis/mos_results.csv`, `docs/mos_samples`, and manuscript MOS labels do not align.
- Several REMI MP3 files are only 671 bytes and require re-rendering or exclusion.
- Ethics approval number remains `SHU-REC-2024-XXXX`.
- Final artifact repository/DOI is still absent.
- Full N=64 direct synchronization experiment and public-only/source-ablation evidence remain missing.
- Current co-activation evidence is useful as a diagnostic but not sufficient for a strong synchronization superiority claim.

## Completion Decision

The paper is closer to JASM positioning after this pass, but it is not yet publication-ready for Journal on Audio, Speech, and Music Processing.
