
import os
import sys
import kagglehub
import logging
import tensorflow as tf
import tensorflow_hub as hub

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure GPU
gpus = tf.config.experimental.list_physical_devices('GPU')
if gpus:
    for gpu in gpus:
        tf.config.experimental.set_memory_growth(gpu, True)
    print("GPU Configured")

print("1. Loading SPAQ (TFHub)...")
spaq = hub.load("https://tfhub.dev/google/musiq/spaq/1")
print("SPAQ Loaded.")

print("2. Loading AVA (TFHub)...")
ava = hub.load("https://tfhub.dev/google/musiq/ava/1")
print("AVA Loaded.")

print("3. Loading KONIQ (KaggleHub)...")
try:
    path = kagglehub.model_download("google/musiq/tensorFlow2/koniq-10k")
    print(f"Koniq Downloaded to: {path}")
    
    koniq = tf.saved_model.load(path)
    print("Koniq Loaded into TF.")
except Exception as e:
    print(f"Caught exception: {e}")
    
print("Done.")
