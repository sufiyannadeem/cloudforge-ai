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
