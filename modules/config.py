import json
import logging
import os
import sys
from pathlib import Path
import platform
import string

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"

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
    Supports nested keys using dot notation (e.g., 'scoring.force_rescore_default').
    """
    data = load_config()
    if '.' in key:
        parts = key.split('.')
        target = data
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value
    else:
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


def get_database_engine() -> str:
    """Resolve ``database.engine`` from ``config.json``.

    When the key is missing or blank:

    - If ``IMAGE_SCORING_DB_ENGINE_DEFAULT`` is ``firebird`` or ``postgres``, that value
      wins (used by ``scripts/setup_test_db.py`` subprocesses where pytest is not loaded).
    - Under pytest (``pytest`` in ``sys.modules`` or ``PYTEST_CURRENT_TEST``), default is
      ``firebird`` so the existing ``scoring_history_test.fdb`` workflow works without
      setting ``engine`` in every config.
    - Otherwise default is ``postgres`` (Docker stack and new installs).

    Any non-empty explicit value is returned lowercased (e.g. ``api`` for ``DbConnector``).

    When ``IMAGE_SCORING_FORCE_FIREBIRD_TEST_SETUP`` is set to a truthy value, returns
    ``firebird`` (used by ``scripts/setup_test_db.py`` regardless of config).
    """
    # Priority:
    # 1. Force firebird (test setup)
    if os.environ.get("IMAGE_SCORING_FORCE_FIREBIRD_TEST_SETUP", "").strip().lower() in ("1", "true", "yes"):
        return "firebird"

    # 2. Pytest override (only if not explicitly set to something else)
    # If we're under pytest, we want to default to firebird unless explicitly told otherwise
    # via IMAGE_SCORING_DB_ENGINE_DEFAULT=postgres.
    is_pytest = "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST")
    forced = os.environ.get("IMAGE_SCORING_DB_ENGINE_DEFAULT", "").strip().lower()

    if is_pytest:
        if forced in ("firebird", "postgres"):
            return forced
        # Previously we forced firebird here. Now we fall through to the config/default.
        pass

    # 3. Explicit config.json setting
    sec = get_config_section("database") or {}
    raw = sec.get("engine")
    if raw is not None and str(raw).strip():
        return str(raw).strip().lower()

    # 4. Environment default (non-pytest)
    if forced in ("firebird", "postgres"):
        return forced

    return "postgres"

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


def get_system_drives():
    """
    Get a list of available system drives/root paths.
    
    Returns:
        List of strings (e.g. ['C:/', 'D:/'] on Windows, ['/'] on Linux)
    """
    drives = []
    system = platform.system()
    
    if system == "Windows":
        # Get logical drives
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drives.append(f"{letter}:/")
            bitmask >>= 1
    else:
        # Linux/Unix/MacOS
        drives.append("/")
        # Add WSL mounts if applicable
        if os.path.isdir("/mnt"):
            try:
                for item in os.listdir("/mnt"):
                    mount_point = f"/mnt/{item}"
                    if os.path.isdir(mount_point):
                        drives.append(mount_point + "/")
            except OSError:
                pass
                
    return drives


_SECRETS_FILE = BASE_DIR / "secrets.json"

def get_secret(service_name: str):
    """Load API credentials from secrets.json for a specific service.

    Returns:
        dict or None: Credentials dict for the service, or None if not found.
    """
    try:
        if not _SECRETS_FILE.exists():
            return None
        with open(_SECRETS_FILE, 'r') as f:
            secrets = json.load(f)
        return secrets.get(service_name)
    except Exception as e:
        logging.warning("Failed to load secret for '%s': %s", service_name, e)
        return None


def get_default_allowed_paths():
    """
    Get default allowed paths based on system configuration.
    
    Returns:
        List of paths safe to allow by default.
    """
    allowed = [os.path.abspath("."), os.path.abspath("thumbnails")]
    
    # Add all detected system drives
    drives = get_system_drives()
    allowed.extend(drives)
    
    return allowed


def validate_config() -> dict:
    """
    Structural validation of config.json (no DB connection).
    Returns dict with ok (bool), issues (list of str), and optional warnings.
    """
    issues = []
    warnings = []

    if not CONFIG_FILE.exists():
        return {
            "ok": False,
            "issues": [f"Configuration file not found: {CONFIG_FILE}"],
            "warnings": warnings,
        }

    data = load_config()
    if not data:
        issues.append("config.json is missing, empty, or failed to parse")

    proc = data.get("processing") or {}
    for key in ("prep_queue_size", "scoring_queue_size", "result_queue_size"):
        v = proc.get(key)
        if v is not None and (not isinstance(v, int) or v <= 0):
            issues.append(f"processing.{key} must be a positive integer (got {v!r})")

    cb = proc.get("clustering_batch_size")
    if cb is not None and (not isinstance(cb, int) or cb <= 0):
        issues.append(f"processing.clustering_batch_size must be a positive integer (got {cb!r})")

    db_sec = data.get("database") or {}
    engine = get_database_engine()

    if engine == "firebird":
        if not str(db_sec.get("filename") or "").strip():
            issues.append("database.filename should be set to the Firebird database file name")
    elif engine == "postgres":
        for k in ["host", "port", "dbname", "user"]:
            if not db_sec.get("postgres", {}).get(k):
                issues.append(f"database.postgres.{k} is required when engine is postgres")
    else:
        issues.append(f"database.engine must be 'firebird' or 'postgres' (got {engine!r})")

    for path_key in ("scoring_input_path", "tagging_input_path", "stacks_input_path", "culling_input_path", "selection_input_path"):
        p = data.get(path_key)
        if isinstance(p, str) and p.strip() and not os.path.exists(p):
            warnings.append(f"{path_key} path does not exist on this machine: {p}")

    log_dir = (data.get("system") or {}).get("log_dir")
    if log_dir and not os.path.isdir(os.path.abspath(log_dir)):
        warnings.append(f"system.log_dir is not an existing directory: {log_dir}")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }