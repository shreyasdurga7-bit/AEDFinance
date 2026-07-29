import pytest

from dues_automation import config, db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(config, "DB_PATH", str(db_path))
    db.init_db()
    conn = db.get_connection()
    yield conn
    conn.close()
