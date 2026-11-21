"""Reproduce fixture-only taint handling without treating JSON fields as paths."""
import base64
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('signature_fixture',ROOT/'scripts/test-release-signatures.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def bundle():
    statement={'predicate':{'revision':'a'*40,'untrusted_path':'../../outside.json'}}
    return {'dsseEnvelope':{'payload':base64.b64encode(json.dumps(statement).encode()).decode(),'signatures':[]},
            'untrusted_path':'/etc/passwd'}


def test_untrusted_payload_cannot_select_output_path(tmp_path):
    original=json.dumps(bundle());(tmp_path/'attestation.json').write_text(original)
    m.write_tampered_attestation(tmp_path)
    assert {p.name for p in tmp_path.iterdir()}=={'attestation.json','tampered-attestation.json'}
    assert (tmp_path/'attestation.json').read_text()==original
    changed=json.loads((tmp_path/'tampered-attestation.json').read_text())
    assert changed['untrusted_path']=='/etc/passwd'
    payload=json.loads(base64.b64decode(changed['dsseEnvelope']['payload']))
    assert payload['predicate']['revision']=='b'*40
    assert payload['predicate']['untrusted_path']=='../../outside.json'


def test_fixture_output_symlink_cannot_overwrite_other_files(tmp_path):
    root=tmp_path/'private';root.mkdir(mode=0o700)
    (root/'attestation.json').write_text(json.dumps(bundle()))
    protected=tmp_path/'protected';protected.write_text('unchanged')
    (root/'tampered-attestation.json').symlink_to(protected)
    with pytest.raises(FileExistsError):m.write_tampered_attestation(root)
    assert protected.read_text()=='unchanged'


def test_fixture_refuses_symlinked_input(tmp_path):
    root=tmp_path/'private';root.mkdir(mode=0o700)
    protected=tmp_path/'protected';protected.write_text(json.dumps(bundle()))
    (root/'attestation.json').symlink_to(protected)
    with pytest.raises(ValueError):m.write_tampered_attestation(root)
    assert not (root/'tampered-attestation.json').exists()
