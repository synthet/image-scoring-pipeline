
import tensorflow as tf
import tensorflow_hub as hub
import os

def check_gpu():
    gpus = tf.config.experimental.list_physical_devices('GPU')
    if gpus:
        try:
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
            print(f"GPU detected: {len(gpus)} device(s) available")
        except RuntimeError as e:
            print(f"GPU setup failed: {e}")
    else:
        print("No GPU detected")

def load_paq2piq():
    print("Loading PAQ2PIQ...")
    url = "https://tfhub.dev/google/musiq/paq2piq/1"
    try:
        model = hub.load(url)
        print("Success!")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    check_gpu()
    load_paq2piq()
