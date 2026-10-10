"""Persist server-only credentials without exposing their value in responses or logs."""
import os
from pathlib import Path
import re
import tempfile
from threading import Lock

_lock = Lock()


def save_api_key(path: Path, key: str):
    with _lock:
        contents = path.read_text() if path.exists() else ''
        lines = contents.splitlines()
        assignment = re.compile(r'^\s*(?:export\s+)?OPENAI_API_KEY\s*=')
        lines = [line for line in lines if not assignment.match(line)]
        lines.append(f"OPENAI_API_KEY='{key}'")
        fd, temporary = tempfile.mkstemp(prefix='.openai-config-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as output:
                output.write('\n'.join(lines) + '\n')
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            os.environ['OPENAI_API_KEY'] = key
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
