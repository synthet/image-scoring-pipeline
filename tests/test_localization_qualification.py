"""Qualification parser proofs use generated files and never create database approvals."""
import hashlib
import json

import pytest

from modules.localization_policy_approval import RUNTIME_RULE_ID, RUNTIME_RULE_SHA256, validate_qualification


def bundle(tmp_path):
    policy = {'policy_hash':'policy','rule_kind':'runtime','rule_id':RUNTIME_RULE_ID,
              'rule_sha256':RUNTIME_RULE_SHA256,'scope':{'detector_version':'m','detector_config_hash':'c','rendition_version':'r'}}
    controls = [{'id':str(i),'expected':i<10,'predicted':i<10} for i in range(20)]
    labels = [{'image_id':i,'run_id':i+1000,'region_id':i+2000,'rendition_hash':str(i),
               'band':'large','votes':{j:'usable' for j in ('a','b','c')}} for i in range(1,131)]
    files = {}
    def write(name,value):
        raw=json.dumps(value,sort_keys=True).encode()
        (tmp_path/name).write_bytes(raw)
        files[name]=hashlib.sha256(raw).hexdigest()
    write('manifest.json',{'rule_sha256':RUNTIME_RULE_SHA256,'scope':policy['scope'],
                           'frames':[{k:v for k,v in r.items() if k!='votes'} for r in labels],
                           'controls':[{k:v for k,v in c.items() if k!='predicted'} for c in controls]})
    judges=[]
    for j in ('a','b','c'):
        write(j+'.json',{'schema':'localization-judge-receipt/1','judge':j,'controls':controls,
                         'votes':{str(r['image_id']):r['votes'][j] for r in labels}})
        judges.append({'name':j,'controls':controls,'raw_file':j+'.json'})
    receipt={'schema':'localization-qualification/1','source_kind':'real_holdout','synthetic':False,
             'policy_hash':'policy','rule_sha256':RUNTIME_RULE_SHA256,'scope':policy['scope'],
             'source_receipts':files,'validation_manifest':'manifest.json','judges':judges,
             'labels':labels,'geometry_bands':['large'],'species_allowed':True,'species_bands':['large']}
    return policy,receipt


def validate(tmp_path,policy,receipt):
    raw=json.dumps(receipt).encode()
    p=tmp_path/'receipt.json'
    p.write_bytes(raw)
    return validate_qualification(p,hashlib.sha256(raw).hexdigest(),policy)


def test_complete_scoped_receipt_is_accepted(tmp_path):
    policy,receipt=bundle(tmp_path)
    assert validate(tmp_path,policy,receipt)['species_bands']==['large']


@pytest.mark.parametrize('change',['raw_votes','identities','controls','species_band','unhashed_raw'])
def test_self_reported_passes_cannot_override_bound_evidence(tmp_path,change):
    policy,receipt=bundle(tmp_path)
    if change=='raw_votes':
        receipt['labels'][0]['votes']['a']='poor_crop'
    elif change=='identities':
        receipt['labels'][0]['run_id']+=1
    elif change=='controls':
        receipt['judges'][0]['controls']=[dict(c,expected=not c['expected']) for c in receipt['judges'][0]['controls']]
    elif change=='species_band':
        receipt['species_bands']=['small']
    else:
        receipt['judges'][0]['raw_file']='other.json'
    with pytest.raises(ValueError):
        validate(tmp_path,policy,receipt)
