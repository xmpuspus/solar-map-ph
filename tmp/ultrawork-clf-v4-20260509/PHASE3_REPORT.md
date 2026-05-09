# Phase 3 — Encoder Ablation (COMPLETE)

## Setup

Same training set, same head (LR with C=1.0, class_weight=balanced), same group-aware 5-fold CV, same 20% Platt holdout split. The only thing that changes between runs is the image encoder. Each encoder produces a different feature dim:

| Encoder | Feature dim | Image size | Backbone params |
|---|---|---|---|
| openai/clip-vit-large-patch14 | 768 | 224 | ~300M |
| facebook/dinov2-large | 1024 | 224 | ~300M |
| satlas:Aerial_SwinB_SI | 1024 | 512 | ~88M (Swin-B) |

Embedding times on M-series MPS, 3040 augmented images, batch=4-8:

| Encoder | Embed time |
|---|---|
| CLIP-ViT-L | ~210s |
| DINOv2-large | 208s |
| satlas Aerial_SwinB_SI | 323s |

## Decision criterion

> Keep CLIP-ViT-L unless an alternative gains >2pts F1 OR >1pt precision at calibrated t=0.85.

## Results — calibrated holdout @ t=0.85

| Encoder | Precision | Recall | F1 | Δ F1 vs CLIP | Δ P vs CLIP |
|---|---|---|---|---|---|
| **openai/clip-vit-large-patch14** | **0.959** | **0.797** | **0.870** | (baseline) | (baseline) |
| facebook/dinov2-large | 0.936 | 0.746 | 0.830 | -4.0 pt | -2.3 pt |
| satlas:Aerial_SwinB_SI | 0.900 | 0.610 | 0.727 | -14.3 pt | -5.9 pt |

## Results — LOSO @ t=0.85

| Encoder | Precision | Recall | F1 |
|---|---|---|---|
| CLIP-ViT-L | 0.988 | 0.772 | 0.867 |
| DINOv2-large | 0.980 | 0.718 | 0.829 |
| satlas Aerial_SwinB_SI | 0.958 | 0.500 | 0.657 |

## Why CLIP wins

The task is whole-tile semantic classification ("does this 240m × 240m aerial tile contain at least one rooftop solar installation?"). CLIP's vision encoder was trained on a massive scale of diverse web imagery with paired text — this gives it an unusually strong "what kind of thing is this?" signal that transfers cleanly to a binary classifier.

DINOv2 is also strong on general images but trained without text supervision. On a "shape + color" recognition task like this, the text-grounded CLIP features carry more discriminative information per dim.

satlas Aerial_SwinB_SI was specifically pretrained on aerial imagery, so the underperformance is the most surprising. Likely reasons: the satlas pretraining task (multi-modal masked modeling on Maxar imagery) is tuned for downstream segmentation / object detection where spatial localization matters, not whole-image classification. Esri World Imagery at zoom-19 is also a different source than the satlas training corpus, so there's a domain shift on top of the task mismatch.

## Decision

**Lock openai/clip-vit-large-patch14 as the encoder for all downstream work.** No retraining of clf_v4 with a different encoder.

## Artifacts

| Path | Purpose |
|---|---|
| `detection/train/v4_calibrated/encoder_ablation.py` | Parametric encoder runner |
| `detection/train/v4_calibrated/ablation/facebook_dinov2-large/metrics.json` | DINOv2 results |
| `detection/train/v4_calibrated/ablation/satlas_Aerial_SwinB_SI/metrics.json` | satlas results |
| `detection/train/v4_calibrated/ablation/facebook_dinov2-large/embeddings.npz` | DINOv2 embeddings (preserved) |
| `detection/train/v4_calibrated/ablation/satlas_Aerial_SwinB_SI/embeddings.npz` | satlas embeddings (preserved) |

The CLIP baseline is the existing dataset_v4.npz from Phase 1.
