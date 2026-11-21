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


def test_new_artifacts_are_private_and_never_overwritten(tmp_path,monkeypatch):
    import stat
    monkeypatch.chdir(tmp_path)
    files={'values.yml':'first','iam-policy.json':'{}'}
    m.write_review_directory('review',files)
    output=tmp_path/'review'
    assert stat.S_IMODE(output.stat().st_mode)==0o700
    for name,content in files.items():
        assert (output/name).read_text()==content
        assert stat.S_IMODE((output/name).stat().st_mode)==0o600
    with pytest.raises(FileExistsError):m.write_review_directory('review',{'values.yml':'overwrite'})
    assert (output/'values.yml').read_text()=='first'


@pytest.mark.parametrize('mode',[0o720,0o702,0o777])
def test_shared_writable_workspace_is_rejected(tmp_path,monkeypatch,mode):
    monkeypatch.chdir(tmp_path);original=tmp_path.stat().st_mode
    tmp_path.chmod(mode)
    try:
        with pytest.raises(ValueError,match='not group/world writable'):
            m.write_review_directory('review',{'values.yml':'data'})
    finally:tmp_path.chmod(original)
    assert not (tmp_path/'review').exists()


def test_preexisting_directory_symlink_is_rejected(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    protected=tmp_path/'protected';protected.mkdir();(protected/'values.yml').write_text('unchanged')
    (tmp_path/'review').symlink_to(protected,target_is_directory=True)
    with pytest.raises(FileExistsError):m.write_review_directory('review',{'values.yml':'data'})
    assert (protected/'values.yml').read_text()=='unchanged'


def test_directory_swap_after_mkdir_cannot_redirect_open(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    protected=tmp_path/'protected';protected.mkdir();(protected/'values.yml').write_text('unchanged')
    mkdir=os.mkdir
    def swap(path,*args,**kwargs):
        mkdir(path,*args,**kwargs)
        if path=='review' and kwargs.get('dir_fd') is not None:
            root=kwargs['dir_fd']
            os.rename('review','detached',src_dir_fd=root,dst_dir_fd=root)
            os.symlink(protected,'review',dir_fd=root,target_is_directory=True)
    monkeypatch.setattr(m.os,'mkdir',swap)
    with pytest.raises(OSError):m.write_review_directory('review',{'values.yml':'data'})
    assert (protected/'values.yml').read_text()=='unchanged'
    assert list((tmp_path/'detached').iterdir())==[]


def test_directory_swap_after_open_keeps_write_on_original_descriptor(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    protected=tmp_path/'protected';protected.mkdir();(protected/'values.yml').write_text('unchanged')
    open_file=os.open;swapped=False
    def swap(path,flags,*args,**kwargs):
        nonlocal swapped
        if path=='values.yml' and flags & os.O_CREAT and not swapped:
            swapped=True
            (tmp_path/'review').rename(tmp_path/'detached')
            (tmp_path/'review').symlink_to(protected,target_is_directory=True)
        return open_file(path,flags,*args,**kwargs)
    monkeypatch.setattr(m.os,'open',swap)
    with pytest.raises(OSError,match='was replaced'):
        m.write_review_directory('review',{'values.yml':'new review content'})
    assert (protected/'values.yml').read_text()=='unchanged'
    assert (tmp_path/'detached'/'values.yml').read_text()=='new review content'


@pytest.mark.parametrize('kind',['symlink','hardlink'])
def test_file_link_race_cannot_overwrite_existing_inode(tmp_path,monkeypatch,kind):
    monkeypatch.chdir(tmp_path)
    protected=tmp_path/'protected';protected.write_text('unchanged')
    open_file=os.open
    def insert_link(path,flags,*args,**kwargs):
        if path=='values.yml' and flags & os.O_CREAT:
            if kind=='symlink':os.symlink(protected,path,dir_fd=kwargs['dir_fd'])
            else:os.link(protected,path,dst_dir_fd=kwargs['dir_fd'])
        return open_file(path,flags,*args,**kwargs)
    monkeypatch.setattr(m.os,'open',insert_link)
    with pytest.raises(FileExistsError):m.write_review_directory('review',{'values.yml':'data'})
    assert protected.read_text()=='unchanged'


@pytest.mark.parametrize('name',['../outside','/etc/passwd','..','--option'])
def test_artifact_names_cannot_escape_output_directory(tmp_path,monkeypatch,name):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):m.write_review_directory('review',{name:'data'})
    assert not (tmp_path/'review').exists()


def test_concurrent_output_requests_have_one_owner(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.chdir(tmp_path)
    def attempt(owner):
        try:
            m.write_review_directory('review',{'values.yml':str(owner),'iam-policy.json':str(owner)})
            return owner
        except FileExistsError:return None
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(attempt,range(8)))
    winners=[owner for owner in results if owner is not None]
    assert len(winners)==1
    assert (tmp_path/'review'/'values.yml').read_text()==str(winners[0])
    assert (tmp_path/'review'/'iam-policy.json').read_text()==str(winners[0])
