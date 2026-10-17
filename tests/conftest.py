import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def con(tmp_path_factory):
    """A fresh build of the database from the raw file, so the tests check the SQL as committed."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from build import build
    os.chdir(ROOT)
    return build(tmp_path_factory.mktemp("db") / "test.duckdb")
