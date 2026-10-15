import pytest

from shortlist import db
from shortlist.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite+pysqlite:///:memory:", mcp_shared_secret="test-secret")


@pytest.fixture
def engine(settings):
    return db.configure(settings.database_url)
