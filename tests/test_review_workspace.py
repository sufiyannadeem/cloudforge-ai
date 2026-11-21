"""Malicious review inputs must never acquire authority over paths outside cwd."""
import argparse
import importlib.util
import json
from pathlib import Path
import os
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('review_workspace',ROOT/'scripts/review_workspace.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_reads_bounded_json_from_workspace_without_treating_content_as_paths(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    content={'value':'../../outside','nested':{'path':'/etc/passwd'}}
    (tmp_path/'input.json').write_text(json.dumps(content))
    assert m.read_review_json('input.json')==content
    assert m.read_review_json(tmp_path/'input.json')==content


@pytest.mark.parametrize('path',['../outside.json','/etc/passwd','nested/../../outside.json'])
def test_path_traversal_rejected(tmp_path,monkeypatch,path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(argparse.ArgumentTypeError):m.read_review_json(path)


def test_symlink_files_and_parent_directories_rejected(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    actual=tmp_path/'actual';actual.mkdir();(actual/'input.json').write_text('{}')
    (tmp_path/'alias').symlink_to(actual,target_is_directory=True)
    (tmp_path/'file.json').symlink_to(actual/'input.json')
    for path in ['alias/input.json','file.json']:
        with pytest.raises(argparse.ArgumentTypeError):m.read_review_json(path)


@pytest.mark.parametrize('content',['[]','null','{invalid'])
def test_nonobject_and_invalid_json_rejected(tmp_path,monkeypatch,content):
    monkeypatch.chdir(tmp_path);(tmp_path/'input.json').write_text(content)
    with pytest.raises(argparse.ArgumentTypeError):m.read_review_json('input.json')


def test_oversized_and_fifo_inputs_rejected_without_blocking(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(m,'MAX_JSON_BYTES',8)
    (tmp_path/'large.json').write_text('{"large":true}')
    os.mkfifo(tmp_path/'fifo')
    for path in ['large.json','fifo']:
        with pytest.raises(argparse.ArgumentTypeError):m.read_review_json(path)


@pytest.mark.parametrize('value',['../escape','nested/output','.','--option','/tmp/escape'])
def test_output_directory_cannot_escape_or_use_options(tmp_path,monkeypatch,value):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(argparse.ArgumentTypeError):m.output_directory(value)


def test_output_directory_is_a_workspace_child(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert m.output_directory('review')==tmp_path/'review'
    assert m.output_directory(tmp_path/'review')==tmp_path/'review'
