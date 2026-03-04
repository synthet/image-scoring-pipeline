"""Tests for config.get_secret() function."""
import pytest
import json
import os
import tempfile
from unittest.mock import patch
from modules import config


class TestGetSecret:
    """Test the get_secret() function."""

    def test_missing_secrets_file_returns_none(self):
        """Should return None when secrets.json doesn't exist."""
        with patch.object(config, '_SECRETS_FILE', config.Path('/nonexistent/secrets.json')):
            result = config.get_secret('test_service')
            assert result is None

    def test_valid_secrets_file(self, tmp_path):
        """Should return credentials for known service."""
        secrets_file = tmp_path / "secrets.json"
        secrets_file.write_text(json.dumps({
            "everypixel": {"api_key": "abc123", "api_secret": "xyz789"},
            "sightengine": {"user": "user1", "secret": "s3cret"}
        }))
        with patch.object(config, '_SECRETS_FILE', secrets_file):
            result = config.get_secret('everypixel')
            assert result == {"api_key": "abc123", "api_secret": "xyz789"}

    def test_missing_service_key_returns_none(self, tmp_path):
        """Should return None for unknown service."""
        secrets_file = tmp_path / "secrets.json"
        secrets_file.write_text(json.dumps({"known_service": {"key": "val"}}))
        with patch.object(config, '_SECRETS_FILE', secrets_file):
            result = config.get_secret('unknown_service')
            assert result is None

    def test_invalid_json_returns_none(self, tmp_path):
        """Should return None when secrets.json is malformed."""
        secrets_file = tmp_path / "secrets.json"
        secrets_file.write_text("not valid json {{{")
        with patch.object(config, '_SECRETS_FILE', secrets_file):
            result = config.get_secret('test_service')
            assert result is None
