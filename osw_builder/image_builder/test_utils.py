from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from .utils import compute_sha1sum


@pytest.fixture
def test_file():
    with NamedTemporaryFile() as temp_file:
        temp_file.write(b"This is a test file.")
        temp_file.flush()
        yield Path(temp_file.name)


def test_compute_sha1sum(test_file):
    # Compute the SHA1 sum for the test file
    result = compute_sha1sum(test_file)
    # Compare it to the expected SHA1 sum
    expected_sha1sum = "26d82f1931cbdbd83c2a6871b2cecd5cbcc8c26b"
    assert result == expected_sha1sum
