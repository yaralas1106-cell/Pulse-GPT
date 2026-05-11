#!/usr/bin/env bash
# =============================================================================
# run_decomp_ablation.sh
# Full cloud pipeline: train FiLM → generate 5 ablation conditions → evaluate
#
# Usage (from project root):
#   chmod +x scripts/run_decomp_ablation.sh
#   ./scripts/run_decomp_ablation.sh
#
# To skip training (if m_film_v6_best.pt already exists):
#   SKIP_TRAIN=1 ./scripts/run_decomp_ablation.sh
#
# Environment variables:
#   SKIP_TRAIN   : set to 1 to skip training step
#   SKIP_GEN     : set to 1 to skip generation step (only run eval)
#   OUT_DIR      : output directory (default: output/decomp_ablation)
#   EPOCHS       : FiLM training epochs (default: 100)
#   BATCH_SIZE   : training batch size (default: 16)
# =============================================================================

set -euo pipefail

OUT_DIR="${OUT_DIR:-output/decomp_ablation}"
EPOCHS="${EPOCHS:-100}"
BATCH_SIZE="${BATCH_SIZE:-16}"
FILM_CKPT="dataset/processed/m_film_v6_best.pt"
VOCAB_PATH="dataset/processed/pulse_cp_vocab_5d_v6.json"
JSONL_PATH="dataset/processed/pulse_dataset_v6.jsonl"

echo "============================================================"
echo "  PulseFormer Pipeline Decomposition Ablation"
echo "  Output dir : $OUT_DIR"
echo "============================================================"
echo ""

# ── Step 1: Train FiLM model ─────────────────────────────────────────────────
if [[ "${SKIP_TRAIN:-0}" == "1" ]]; then
    echo "[SKIP] Training (SKIP_TRAIN=1)"
    if [[ ! -f "$FILM_CKPT" ]]; then
        echo "[ERROR] SKIP_TRAIN=1 but $FILM_CKPT not found. Aborting."
        exit 1
    fi
else
    echo ">>> Step 1/3: Training FiLM model ($EPOCHS epochs, batch=$BATCH_SIZE)"
    python training/train_film.py \
        --jsonl_path "$JSONL_PATH" \
        --save_prefix "dataset/processed/m_film_v6" \
        --epochs "$EPOCHS" \
        --batch_size "$BATCH_SIZE"
    echo ""
    echo "    FiLM training complete. Checkpoint: $FILM_CKPT"
fi

echo ""

# ── Step 2: Generate MIDI for all 5 conditions ───────────────────────────────
if [[ "${SKIP_GEN:-0}" == "1" ]]; then
    echo "[SKIP] Generation (SKIP_GEN=1)"
else
    echo ">>> Step 2/3: Generating 128-bar MIDI (5 conditions × 8 prompts)"
    python scripts/run_decomp_ablation.py \
        --step generate \
        --out_dir "$OUT_DIR" \
        --film_ckpt "$FILM_CKPT" \
        --vocab_path "$VOCAB_PATH"
    echo ""
    echo "    Generation complete. Output: $OUT_DIR/"
fi

echo ""

# ── Step 3: Evaluate ─────────────────────────────────────────────────────────
echo ">>> Step 3/3: Computing decomposition metrics"
python eval/clean_ablation_eval.py \
    --sweep_dir "$OUT_DIR" \
    --latex

echo ""
echo "============================================================"
echo "  Done. Paste the LaTeX table rows above into Table IX."
echo "============================================================"
