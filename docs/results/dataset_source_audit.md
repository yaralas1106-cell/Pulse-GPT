# Dataset Source Audit

Date: 2026-05-04

## Source-Specific Files

| Label | Path | Exists | Rows | Bytes |
| --- | --- | --- | ---: | ---: |
| gated_public_gigamidi | `dataset/processed/gigamidi_sequences.jsonl` | True | 117145 | 1380484530 |
| public_lakh | `dataset/processed/lakh_sequences.jsonl` | True | 6012 | 83799152 |
| restricted_proprietary_daw | `dataset/processed/pulse_dataset_v5_clean.jsonl` | True | 3647 | 57270379 |
| restricted_als_daw_aux_small | `dataset/als_data/pulse_dataset_als.jsonl` | True | 18 | 707107 |
| restricted_als_daw_aux_full | `dataset/pulse_dataset_als.jsonl` | True | 73 | 4879534 |

## Visible Source Proportions

- Using `restricted_proprietary_daw`, visible restricted DAW rows are 3647 / 126804 = 2.876%.
- Auxiliary `restricted_als_daw_aux_small` rows are 18 / 123175 = 0.015% if treated as the only restricted source.
- Auxiliary `restricted_als_daw_aux_full` rows are 73 / 123230 = 0.059% if treated as the only restricted source.
- The source-specific row counts sum exactly to the current `pulse_dataset_v6` row count when `restricted_proprietary_daw` is used: 117,145 + 6,012 + 3,647 = 126,804.
- GigaMIDI is gated rather than fully open public data, so it should be described as externally obtainable under access terms, not simply open.

## Combined Files

| Label | Path | Exists | Rows | Row-level source metadata |
| --- | --- | --- | ---: | --- |
| pulse_dataset_v6 | `dataset/processed/pulse_dataset_v6.jsonl` | True | 126804 | False |
| pulse_dataset_v6_gzip | `dataset/processed/pulse_dataset_v6.jsonl.gz` | True | 126804 | False |
| pulse_dataset | `dataset/processed/pulse_dataset.jsonl` | True | 7694 | False |

## Submission Interpretation

This audit supports the manuscript's source-count statement for the visible local files, but it does not complete the required public-only/source-ablation evidence. The combined training files do not preserve per-row provenance, and no public-only model checkpoint or controlled source-ablation metric table is present in the workspace.
