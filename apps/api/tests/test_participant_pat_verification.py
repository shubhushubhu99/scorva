import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from apps.api.config import settings
from apps.api.core.database import AsyncSessionLocal
from apps.api.core.exceptions import AppException
from apps.api.core.security import encrypt_value, decrypt_value
from apps.api.modules.evaluations.participant_router import (
    _verify_github_pat,
    _verify_github_repo_access,
    _fetch_participant_github_settings,
    save_participant_pat,
    get_participant_pat_status,
    delete_participant_pat,
    SaveParticipantPatRequest,
)


@pytest.mark.asyncio
async def test_verify_github_pat_valid_test_token():
    is_valid, login, prefix, masked = await _verify_github_pat("ghp_test_mock_octocat", "user@scorva.io")
    assert is_valid is True
    assert login == "octocat"
    assert prefix == "ghp_"
    assert masked.startswith("ghp_...")


@pytest.mark.asyncio
async def test_verify_github_pat_live_github_api_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"login": "torvalds", "id": 1024025}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with patch.object(settings, "SCORVA_ENV", "production"):
            is_valid, login, prefix, masked = await _verify_github_pat("ghp_realvalidtoken1234567890", "user@scorva.io")
            assert is_valid is True
            assert login == "torvalds"
            assert prefix == "ghp_"
            assert masked.endswith("7890")


@pytest.mark.asyncio
async def test_verify_github_pat_invalid_token_raises_app_exception():
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"message": "Bad credentials"}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with patch.object(settings, "SCORVA_ENV", "production"):
            with pytest.raises(AppException) as exc_info:
                await _verify_github_pat("ghp_invalidbadtoken1234567890", "user@scorva.io")
            assert exc_info.value.status_code == 400
            assert "401 Unauthorized" in exc_info.value.message


@pytest.mark.asyncio
async def test_verify_github_repo_access_success():
    mock_repo_resp = MagicMock()
    mock_repo_resp.status_code = 200
    mock_repo_resp.json.return_value = {"default_branch": "main", "private": False}

    mock_commits_resp = MagicMock()
    mock_commits_resp.status_code = 200
    mock_commits_resp.json.return_value = [{"sha": "a1b2c3d4e5f67890abcdef1234567890abcdef12"}]

    async def mock_get(url, **kwargs):
        if "/commits" in url:
            return mock_commits_resp
        return mock_repo_resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        with patch.object(settings, "SCORVA_ENV", "production"):
            is_accessible, branch, commit_sha = await _verify_github_repo_access(
                "ghp_validpattoken123456789", "testorg", "testrepo"
            )
            assert is_accessible is True
            assert branch == "main"
            assert commit_sha == "a1b2c3d4e5f67890abcdef1234567890abcdef12"


@pytest.mark.asyncio
async def test_pat_aes256_gcm_cipher_encryption():
    raw_token = "ghp_super_secret_pat_token_for_participant"
    encrypted = encrypt_value(raw_token, settings.ENCRYPTION_MASTER_KEY)
    assert encrypted != raw_token.encode("utf-8")
    decrypted = decrypt_value(encrypted, settings.ENCRYPTION_MASTER_KEY)
    assert decrypted == raw_token


@pytest.mark.asyncio
async def test_save_and_retrieve_pat_lifecycle(create_user_helper):
    user = await create_user_helper("pat_lifecycle_participant@scorva.io")

    async with AsyncSessionLocal() as session:
        # Save PAT
        req = SaveParticipantPatRequest(pat_token="ghp_test_mock_developer1")
        save_res = await save_participant_pat(req, user=user, db=session)
        assert save_res.status == "success"
        assert save_res.is_verified is True
        assert save_res.verified_username == "developer1"
        assert save_res.token_masked.startswith("ghp_...")

        # Get PAT status
        status_res = await get_participant_pat_status(user=user, db=session)
        assert status_res.has_token is True
        assert status_res.is_verified is True
        assert status_res.verified_username == "developer1"

        # Delete PAT
        del_res = await delete_participant_pat(user=user, db=session)
        assert del_res["status"] == "success"

        # Check status again
        status_after = await get_participant_pat_status(user=user, db=session)
        assert status_after.has_token is False
        assert status_after.token_masked is None
