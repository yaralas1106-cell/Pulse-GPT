# MTAP Revision Audit for `paper_draft.pdf`

Date: 2026-05-04

## Submission Gate

Target journal: Multimedia Tools and Applications (Springer Nature).

Official checks used:

- MTAP submission guidelines: https://link.springer.com/journal/11042/submission-guidelines
- MTAP aims and scope: https://link.springer.com/journal/11042/aims-and-scope
- Springer Nature LaTeX author support: https://www.springernature.com/gp/authors/campaigns/latex-author-support

Current source file: `docs/paper_draft.tex`
Current compiled PDF target: `docs/paper_draft.pdf`

## Changes Already Applied

- Shortened the abstract from 269 words to 223 words, bringing it into the Springer/MTAP 150--250 word range.
- Kept 6 keywords, which matches the required 4--6 keyword range.
- Renamed the final declarations section from `Declarations` to `Statements and Declarations`.

## Immediate Blocking Issues

1. Ethics approval placeholder remains.
   - File: `docs/paper_draft.tex`
   - Current text contains `SHU-REC-2024-XXXX` and `replace with actual number before submission`.
   - Risk: editorial compliance failure before peer review.
   - Required action: insert the actual Shanghai University ethics approval number, or revise the statement if the study was exempt.

2. Code/data release statement is not submission-ready.
   - Current text says the checkpoint, pipeline, tokenizer, and evaluation scripts "will be released ... upon acceptance" and has no repository or DOI.
   - Risk: reproducibility concern and possible MTAP data/code availability query.
   - Required action: create an anonymized repository or archival package before submission; include a stable URL or DOI.

3. TeX build environment is blocked.
   - `pdflatex` and `bibtex` fail before compiling because MiKTeX reports a fresh setup/update state and registry access is denied.
   - Risk: cannot currently verify the modified PDF.
   - Required action: finish MiKTeX setup/update outside the sandbox, or use a portable TeX Live/Tectonic build path.

4. Source comments contain mojibake near the declaration block.
   - They do not affect PDF content, but the source file should be cleaned before submission.
   - Required action: remove the garbled comment lines once the final source cleanup pass is done.

5. Full `J_DM` evidence is not yet at the promised sample size.
   - The reproducible script now runs on the available generated MIDI samples, but the workspace currently contains only 10 PulseFormer and 10 MMM samples in `outputs/`.
   - Required action: generate or recover the full `N=64` sample set before rewriting the paper's `J_DM` claim as an `N=64` result.

## Scientific Risks for Review

1. Claims depend heavily on deterministic rules.
   - The paper now acknowledges this, but reviewers may still object to headline results such as 100% monotonicity and `r=0.982`.
   - Improvement: separate "model capability" and "pipeline enforcement" visually in the abstract, tables, and conclusion.

2. PulseFormer loses on GPS against Track-Major.
   - The text provides a plausible explanation, but the key claim needs stronger evidence.
   - Improvement experiment: report drum-pattern diversity and within-bar drum-melody co-activation across all `N=64`, not only 10 sequences.

3. MOS reliability is weak.
   - ICC values are low, especially structural coherence.
   - Improvement experiment: add bootstrap confidence intervals by prompt and listener group; consider a second listening round with clearer rubrics.

4. Dataset reproducibility remains partly closed.
   - 3% proprietary DAW data is defensible, but trained checkpoints and scripts must let reviewers reproduce the public-data portion.
   - Improvement: add a public-only ablation or sensitivity check showing the proprietary subset is not the main source of gains.

5. Zero-shot baselines are not strong enough for SOTA claims.
   - Current framing is careful, but the table still visually suggests comparison against incomplete systems.
   - Improvement: move zero-shot probes to a secondary table or add fine-tuned public baselines if compute allows.

## Highest-Value Experiment Queue

1. Expand `J_DM` from 10 sequences to the full `N=64` SOTA sample set.
2. Add public-only training/evaluation or at least leave-one-source-out analysis.
3. Add bootstrap confidence intervals for objective metrics and MOS dimensions.
4. Recompute ablation metrics from saved artifacts and store raw CSVs under `docs/results/`.
5. Package reproducibility artifacts: tokenizer, config, checkpoint card, evaluation scripts, sample prompts, and anonymized generated MIDI/audio.

## Current Experiment Update

`eval/compute_jdm.py` was rewritten as a reproducible CSV-producing script. Running it on the currently available 10-vs-10 MIDI sample set produced:

- PulseFormer: 10 files, 142 drum-active bars, per-file mean `0.5593 +/- 0.1923`.
- MMM-Transformer: 10 files, 98 drum-active bars, per-file mean `0.4286 +/- 0.3185`.
- Per-bar Mann-Whitney U: `p=5.7648e-03`.
- Per-file Mann-Whitney U: `p=2.8479e-01`.

Interpretation: the per-bar result supports the direction of the paper's co-activation claim on the available samples, but the per-file result is not significant and the sample count is below the desired `N=64`. The manuscript should not present this as full-scale evidence until more generated samples are available.

Manuscript update: the `J_DM` paragraph in `docs/paper_draft.tex` now uses these recomputed values and explicitly states that the per-file result is not significant, so the evidence is framed as preliminary rather than distribution-level.

Bootstrap update: `docs/results/bootstrap_confidence_intervals_current.csv` now reports 10,000-sample bootstrap 95% CIs for the current `J_DM` per-file and per-bar means, and the manuscript includes these CIs in the `J_DM` paragraph.

## Claim-Tone Revision Update

Several high-risk absolute claims in `docs/paper_draft.tex` were softened to better match the evidence:

- `perfect structural monotonicity` is now framed as deterministic monotonicity under the Ramp Scheduler.
- `eliminates cross-track misalignment` is now framed as reducing measured cross-track onset deviation under the quantized evaluation protocol.
- `mechanical guarantee` is now framed as a representation-level consequence rather than learned micro-timing evidence.
- `perfect BAS` in the attention-map caption is now `high BAS`.
- The ablation-heatmap caption now says the ablation supports component contributions, not that it confirms independent necessity.

## Data Availability Update

The manuscript now names the primary GigaMIDI source explicitly as `Metacreation/GigaMIDI` on Hugging Face and notes that it is gated and subject to its stated access/license terms. This is more accurate than the earlier generic statement that the dataset is simply available via the Hugging Face datasets hub.

Follow-up consistency edit: the dataset section and limitations section now avoid calling the corpus fully "open" or "publicly accessible"; they instead describe the GigaMIDI and Lakh portions as externally obtainable, with GigaMIDI subject to gated access/license terms.

## Editorial Revision Queue

1. Add a short "Availability of Code and Data" paragraph with concrete links.
2. Replace ethics approval placeholder.
3. Clean garbled source comments and remaining TODO markers.
4. Shorten overlong table notes, especially Table SOTA GPS footnotes.
5. Tighten the Discussion into explicit "model contribution / pipeline contribution / limitations" paragraphs.
6. Verify all figures are readable at journal column width.
7. Rebuild PDF and inspect pages after TeX setup is fixed.
