"""Read review inputs through bounded, no-follow descriptors in a private workspace."""
import argparse
import json
import os
from pathlib import Path
import re
import stat

MAX_JSON_BYTES = 8 * 1024 * 1024


def read_review_json(value):
    """Never follow a path supplied by a caller outside the current workspace."""
    root = Path.cwd().resolve()
    path = Path(value)
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError as exc:
            raise argparse.ArgumentTypeError('Input is outside the review workspace') from exc
    if not path.parts or any(part in {'.', '..'} for part in path.parts):
        raise argparse.ArgumentTypeError('Invalid review input path')
    descriptors = []
    try:
        current = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(current)
        for part in path.parts[:-1]:
            current = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            descriptors.append(current)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
        descriptors.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JSON_BYTES:
            raise ValueError('Review input must be bounded regular JSON')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            data = stream.read(MAX_JSON_BYTES + 1)
        if len(data) > MAX_JSON_BYTES:
            raise ValueError('Review JSON exceeds size limit')
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError('Review input must be a JSON object')
        return result
    except (OSError, ValueError) as exc:
        raise argparse.ArgumentTypeError('Invalid review JSON file or unsafe path') from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def output_directory(value):
    """A new private output directory must be a single child of the workspace."""
    path = Path(value)
    if path.is_absolute():
        try:
            path = path.relative_to(Path.cwd().resolve())
        except ValueError as exc:
            raise argparse.ArgumentTypeError('Output is outside the review workspace') from exc
    match = re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', str(path))
    if not match:
        raise argparse.ArgumentTypeError('Output must be a new directory name in the review workspace')
    return Path.cwd() / match.group(0)


def write_review_directory(value, files):
    """Create new review artifacts without following replaced directory/file paths."""
    directory = output_directory(value)
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', name)
           or not isinstance(content, str) for name, content in files.items()):
        raise ValueError('Invalid review artifact name or content')
    root_fd = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    directory_fd = None
    try:
        workspace = os.fstat(root_fd)
        if workspace.st_uid != os.geteuid() or workspace.st_mode & 0o022:
            raise ValueError('Review workspace must be caller-owned and not group/world writable')
        os.mkdir(directory.name, mode=0o700, dir_fd=root_fd)
        directory_fd = os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        created = os.fstat(directory_fd)
        if created.st_uid != os.geteuid() or created.st_mode & 0o077:
            raise ValueError('Review output directory must remain private')

        def check_directory():
            current = os.stat(directory.name, dir_fd=root_fd, follow_symlinks=False)
            if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (created.st_dev, created.st_ino):
                raise OSError('Review output directory was replaced')

        for name, content in files.items():
            check_directory()
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory_fd)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(content)
        check_directory()
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        os.close(root_fd)
