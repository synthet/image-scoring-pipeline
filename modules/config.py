import json
import os
import logging

CONFIG_FILE = "config.json"

def load_config():
    """
    Loads configuration from config.json.
    Returns a dictionary.
    """
    if not os.path.exists(CONFIG_FILE):
        return {}
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
        return {}

def save_config_value(key, value):
    """
    Updates a single key in the config and saves it.
    """
    data = load_config()
    data[key] = value
    
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Failed to save config: {e}")
