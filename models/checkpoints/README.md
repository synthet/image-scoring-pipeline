# MUSIQ Model Checkpoints

This directory should contain the pre-trained model checkpoints for the MUSIQ (Multi-scale Image Quality Transformer) model.

**Note:** Large checkpoint files are **NOT** included in the repository to save bandwidth and storage. You must download them manually.

## Required Files

Please download the following files and place them in this directory (`models/checkpoints/`):

1.  **`ava_ckpt.npz`** (~163 MB) - Aesthetic Quality (AVA dataset)
2.  **`koniq_ckpt.npz`** (~163 MB) - Technical Quality (KonIQ-10k dataset)
3.  **`paq2piq_ckpt.npz`** (~163 MB) - Technical Quality (PaQ-2-PiQ dataset)
4.  **`spaq_ckpt.npz`** (~163 MB) - Smartphone Photo Quality (SPAQ dataset)
5.  **`imagenet_pretrain.npz`** - Pre-trained weights (optional, for training)

## Download Links

Download from the official Google Research Cloud Storage bucket:

*   **Browser:** [https://console.cloud.google.com/storage/browser/gresearch/musiq](https://console.cloud.google.com/storage/browser/gresearch/musiq)
*   **Direct Links (if available):**
    *   [ava_ckpt.npz](https://storage.googleapis.com/gresearch/musiq/ava_ckpt.npz)
    *   [koniq_ckpt.npz](https://storage.googleapis.com/gresearch/musiq/koniq_ckpt.npz)
    *   [paq2piq_ckpt.npz](https://storage.googleapis.com/gresearch/musiq/paq2piq_ckpt.npz)
    *   [spaq_ckpt.npz](https://storage.googleapis.com/gresearch/musiq/spaq_ckpt.npz)

## Alternative: VILA Model

If you are using the VILA model, it can be downloaded automatically via TensorFlow Hub or Kaggle Hub. Use the `test_model_sources.py` script to verify availability.
