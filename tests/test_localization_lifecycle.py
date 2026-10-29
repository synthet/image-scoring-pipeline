"""Dormant schema and explicit qualification/activation guard contracts."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from modules.localization_active import ActiveAuthority
from modules.localization_policy_approval import RUNTIME_RULE_ID, RUNTIME_RULE_SHA256, validate_qualification


def test_lifecycle_migration_bootstrap_and_test_cleanup_match():
    from modules.db_schema.authority_lifecycle import LIFECYCLE_SCHEMA_SQL
    from modules.db_postgres import POSTGRES_APP_TABLES

    path = Path(__file__).resolve().parents[1] / 'migrations/versions/0046_localization_lifecycle.py'
    spec = importlib.util.spec_from_file_location('lifecycle_0046',path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == '0046' and migration.down_revision == '0045'
    assert migration.LIFECYCLE_SCHEMA_SQL == LIFECYCLE_SCHEMA_SQL
    for table in ('localization_policy_approvals','localization_policy_events','localization_discovery_state',
                  'localization_change_journal','localization_selection_lineage'):
        assert table in POSTGRES_APP_TABLES
    assert 'selection_freshness_enabled BOOLEAN NOT NULL DEFAULT FALSE' in LIFECYCLE_SCHEMA_SQL


@pytest.mark.parametrize('change',[{'synthetic':True},{'scope':{}},{'rule_sha256':'changed'}])
def test_receipt_cannot_use_synthetic_evidence_or_a_different_scope(tmp_path,change):
    policy = {'policy_hash':'p','rule_kind':'runtime','rule_id':RUNTIME_RULE_ID,
              'rule_sha256':RUNTIME_RULE_SHA256,'scope':{'detector_version':'model/1'}}
    receipt = {'schema':'localization-qualification/1','source_kind':'real_holdout','synthetic':False,
               'policy_hash':'p','rule_sha256':RUNTIME_RULE_SHA256,'scope':policy['scope'],**change}
    raw = json.dumps(receipt).encode()
    path = tmp_path/'receipt.json'
    path.write_bytes(raw)
    with pytest.raises(ValueError,match='identity/scope'):
        validate_qualification(path,hashlib.sha256(raw).hexdigest(),policy)


def test_unknown_policy_cannot_inherit_runtime_qualification(tmp_path):
    with pytest.raises(ValueError,match='unknown qualification policy'):
        validate_qualification(tmp_path/'absent.json','anything',
                               {'rule_kind':'runtime','rule_id':RUNTIME_RULE_ID,'rule_sha256':'changed'})


def test_activation_requires_explicit_confirmation_before_accessing_database():
    from types import SimpleNamespace
    with pytest.raises(ValueError,match='explicit activation confirmation'):
        ActiveAuthority(SimpleNamespace(conn=object())).activate('policy','receipt')
