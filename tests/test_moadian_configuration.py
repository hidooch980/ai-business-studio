from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.main import create_app
from backend.app.moadian.api import MoadianConnectionRequest, _serialize
from backend.app.moadian.models import MoadianConnection


def test_direct_moadian_profile_requires_taxpayer_signing_material_when_enabled() -> None:
    payload = MoadianConnectionRequest(
        tax_memory_uid="MEMORY_12345",
        taxpayer_identifier="12345678901",
        submission_mode="direct",
        environment="sandbox",
        private_key_secret_ref="secret://tenant-a/moadian/private-key",
        certificate_secret_ref="secret://tenant-a/moadian/certificate",
        is_enabled=True,
    )
    assert payload.submission_mode == "direct"
    assert payload.is_enabled is True


def test_direct_moadian_profile_cannot_enable_without_key_and_certificate_refs() -> None:
    with pytest.raises(ValidationError):
        MoadianConnectionRequest(
            tax_memory_uid="MEMORY_12345",
            taxpayer_identifier="12345678901",
            submission_mode="direct",
            is_enabled=True,
        )


def test_tsp_moadian_profile_requires_provider_credentials_when_enabled() -> None:
    payload = MoadianConnectionRequest(
        tax_memory_uid="MEMORY_12345",
        taxpayer_identifier="12345678901",
        submission_mode="tsp",
        provider_code="licensed-tsp",
        provider_credential_secret_ref="secret://tenant-a/moadian/tsp-token",
        is_enabled=True,
    )
    assert payload.submission_mode == "tsp"
    assert payload.provider_code == "licensed-tsp"


def test_tsp_profile_rejects_taxpayer_private_key_references() -> None:
    with pytest.raises(ValidationError):
        MoadianConnectionRequest(
            tax_memory_uid="MEMORY_12345",
            taxpayer_identifier="12345678901",
            submission_mode="tsp",
            provider_code="licensed-tsp",
            private_key_secret_ref="secret://tenant-a/moadian/private-key",
        )


def test_connection_response_never_discloses_secret_references() -> None:
    now = datetime.now(UTC)
    item = MoadianConnection(
        tenant_id=uuid4(),
        created_by_user_id=uuid4(),
        updated_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
        tax_memory_uid="MEMORY_12345",
        taxpayer_identifier="12345678901",
        submission_mode="direct",
        environment="sandbox",
        private_key_secret_ref="secret://tenant-a/moadian/private-key",
        certificate_secret_ref="secret://tenant-a/moadian/certificate",
        is_enabled=False,
    )
    result = _serialize(item)
    assert result["credentials_configured"] is True
    assert result["transport_status"] == "awaiting_provider_adapter"
    assert "private_key_secret_ref" not in result
    assert "certificate_secret_ref" not in result
    assert "secret://" not in str(result)


def test_moadian_routes_are_registered() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/v1/tax/moadian/connections" in paths
    assert "/api/v1/tax/moadian/connections/{connection_id}/disable" in paths
