import sys
import pytest


@pytest.fixture(autouse=True, scope="module")
def _isolated_test_db(tmp_path_factory):
    """Gives each test module an isolated SQLite database file."""
    import backend.database as db_mod

    db_file = tmp_path_factory.mktemp("db") / "test.db"
    orig_db_path = db_mod.DB_PATH
    db_mod.DB_PATH = db_file

    for mod_name in ("backend.test_chat_system", "backend.test_d1_adapter"):
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "DB_PATH"):
            setattr(mod, "DB_PATH", db_file)

    db_mod.init_db()
    yield db_file
    db_mod.DB_PATH = orig_db_path
