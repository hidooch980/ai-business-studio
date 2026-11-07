from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.identity.models import Membership, Tenant, User
from backend.app.identity.security import hash_password, hash_session_token, issue_session_token, verify_password


def test_identity_schema_creates_and_enforces_membership_uniqueness() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            tenant = Tenant(name="Example", slug="example")
            user = User(email="person@example.test", password_hash="test-hash", display_name="Person")
            session.add_all([tenant, user])
            session.flush()
            membership = Membership(tenant_id=tenant.id, user_id=user.id)
            session.add(membership)
            session.commit()
            assert membership.id is not None
    finally:
        engine.dispose()


def test_password_hashing_and_session_tokens() -> None:
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)
    raw, digest = issue_session_token()
    assert len(raw) > 40
    assert digest == hash_session_token(raw)
    assert raw != digest
