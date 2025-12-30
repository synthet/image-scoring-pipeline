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

def get_config_value(key, default=None):
    """
    Get a config value with fallback to default.
    Supports nested keys using dot notation (e.g., 'scoring.force_rescore_default').
    """
    data = load_config()
    if '.' in key:
        # Handle nested keys
        parts = key.split('.')
        value = data
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value
    else:
        return data.get(key, default)

def get_config_section(section):
    """
    Get all keys in a section (for organization).
    Returns a dictionary of all keys under the given section.
    """
    data = load_config()
    if section in data and isinstance(data[section], dict):
        return data[section]
    return {}

def save_config_section(section, section_data):
    """
    Save an entire section of configuration.
    """
    data = load_config()
    data[section] = section_data
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Failed to save config section: {e}")


def get_export_templates():
    """
    Get all export templates.
    Returns a dictionary of template_name -> template_config.
    """
    data = load_config()
    return data.get('export_templates', {})


def save_export_template(template_name, template_config):
    """
    Save an export template.
    
    Args:
        template_name: Name of the template
        template_config: Dictionary with export configuration:
            - format: export format (csv/xlsx/json)
            - columns_basic: list
            - columns_scores: list
            - columns_metadata: list
            - columns_other: list
            - filter_rating: list
            - filter_label: list
            - filter_keyword: str
            - filter_folder: str
            - filter_min_gen: float
            - filter_min_aes: float
            - filter_min_tech: float
            - filter_date_start: str
            - filter_date_end: str
    """
    data = load_config()
    if 'export_templates' not in data:
        data['export_templates'] = {}
    
    data['export_templates'][template_name] = template_config
    
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logging.error(f"Failed to save export template: {e}")
        return False


def delete_export_template(template_name):
    """
    Delete an export template.
    """
    data = load_config()
    if 'export_templates' in data and template_name in data['export_templates']:
        del data['export_templates'][template_name]
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            logging.error(f"Failed to delete export template: {e}")
            return False
    return False


def get_export_template(template_name):
    """
    Get a specific export template by name.
    Returns None if not found.
    """
    templates = get_export_templates()
    return templates.get(template_name)