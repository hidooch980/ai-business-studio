from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.identity.models import Role, Tenant, User
from backend.app.identity.service import (
    assign_role_to_membership,
    authenticate_user,
    create_user_session,
    get_active_session,
    normalize_email,
    register_user,
    revoke_session,
)


def test_email_normalization_and_registration() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            user, tenant, membership = register_user(
                db,
                tenant_name="Example",
                tenant_slug="Example",
                email="  Person@Example.Test ",
                password="correct horse battery staple",
                display_name="Person",
            )
            db.commit()
            assert user.email == "person@example.test"
            assert tenant.slug == "example"
            assert membership.tenant_id == tenant.id
            assert authenticate_user(db, email="PERSON@example.test", password="correct horse battery staple") is not None
            assert authenticate_user(db, email="person@example.test", password="wrong password") is None
            with pytest.raises(ValueError):
                normalize_email("not-an-email")
    finally:
        engine.dispose()


def test_session_token_is_hashed_and_revocable() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            user = User(
                email="session@example.test",
                password_hash="unused",
                display_name="Session User",
            )
            db.add(user)
            db.flush()
            raw_token, record = create_user_session(db, user=user, lifetime=timedelta(minutes=5))
            db.commit()
            assert raw_token not in record.token_hash
            assert get_active_session(db, raw_token) is record
            assert revoke_session(db, raw_token)
            db.commit()
            assert get_active_session(db, raw_token) is None
            assert not revoke_session(db, raw_token)
    finally:
        engine.dispose()


def test_role_assignment_rejects_cross_tenant_role() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            user = User(email="member@example.test", password_hash="unused", display_name="Member")
            tenant_a = Tenant(name="A", slug="a")
            tenant_b = Tenant(name="B", slug="b")
            db.add_all([user, tenant_a, tenant_b])
            db.flush()
            from backend.app.identity.models import Membership

            membership = Membership(tenant_id=tenant_a.id, user_id=user.id)
            role = Role(tenant_id=tenant_b.id, name="admin")
            db.add_all([membership, role])
            db.flush()
            with pytest.raises(ValueError, match="same tenant"):
                assign_role_to_membership(db, membership=membership, role_id=role.id)
    finally:
        engine.dispose()
