import hashlib
from pathlib import Path

BLOCKSIZE = 65536


def compute_sha1sum(source_path: Path) -> str:
    sha1sum = hashlib.sha1()
    with open(source_path, "rb") as source_file:
        buf = source_file.read(BLOCKSIZE)
        while len(buf) > 0:
            sha1sum.update(buf)
            buf = source_file.read(BLOCKSIZE)
    return sha1sum.hexdigest()
