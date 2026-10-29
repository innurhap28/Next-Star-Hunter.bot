"""Opt-in real PostgreSQL test using a fresh test-only schema, never public tables."""
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base, build_engine
from app.main import create_app


def test_real_postgres_register_login_and_persistence():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL is not set; real PostgreSQL is unverified")
    engine = build_engine(url)
    schema = "nsh_test_" + uuid4().hex
    try:
        with engine.connect() as connection:
            connection.execute(text('CREATE SCHEMA "' + schema + '"'))
            connection.execute(text('SET search_path TO "' + schema + '"'))
            Base.metadata.create_all(connection)
            connection.commit()
            settings = Settings(
                _env_file=None,
                SECRET_KEY="postgres-test-secret-of-at-least-32-characters",
                DATABASE_URL=url,
            )
            factory = sessionmaker(bind=connection, expire_on_commit=False)
            with TestClient(create_app(settings, factory)) as c:
                credentials = {"email":"postgres-test@example.com","password":"test-password-123"}
                assert c.post("/api/auth/register", json=credentials).status_code == 201
                assert c.post("/api/auth/login", json=credentials).status_code == 200
                assert c.get("/api/me").json()["email"] == credentials["email"]
                assert c.post("/api/auth/logout").status_code == 204
            assert connection.scalar(text('SELECT count(*) FROM "' + schema + '".users')) == 1
            connection.rollback()
    finally:
        with engine.begin() as cleanup:
            cleanup.execute(text('DROP SCHEMA IF EXISTS "' + schema + '" CASCADE'))
        engine.dispose()
