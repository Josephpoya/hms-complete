"""
Core auth tests — register, login, logout, role checks, lockout.
"""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from accounts.models import User, Role


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(email="admin@hospital.com", password="StrongPass123!")


@pytest.fixture
def doctor_user(db):
    return User.objects.create_user(email="doctor@hospital.com", password="StrongPass123!", role=Role.DOCTOR)


@pytest.fixture
def admin_tokens(client, admin_user):
    res = client.post(reverse("auth-login"), {"email": "admin@hospital.com", "password": "StrongPass123!"})
    return res.data


@pytest.mark.django_db
class TestLogin:
    def test_valid_login_returns_tokens(self, client, admin_user):
        res = client.post(reverse("auth-login"), {"email": "admin@hospital.com", "password": "StrongPass123!"})
        assert res.status_code == 200
        assert "access" in res.data
        assert "refresh" in res.data

    def test_invalid_password_returns_401(self, client, admin_user):
        res = client.post(reverse("auth-login"), {"email": "admin@hospital.com", "password": "wrongpassword"})
        assert res.status_code == 401

    def test_jwt_contains_role_claim(self, client, admin_user):
        import jwt
        res = client.post(reverse("auth-login"), {"email": "admin@hospital.com", "password": "StrongPass123!"})
        payload = jwt.decode(res.data["access"], options={"verify_signature": False})
        assert payload["role"] == Role.ADMIN

    def test_account_locks_after_5_failures(self, client, admin_user):
        for _ in range(5):
            client.post(reverse("auth-login"), {"email": "admin@hospital.com", "password": "wrong"})
        res = client.post(reverse("auth-login"), {"email": "admin@hospital.com", "password": "StrongPass123!"})
        assert res.status_code == 401
        assert "locked" in str(res.data).lower()


@pytest.mark.django_db
class TestLogout:
    def test_logout_blacklists_refresh_token(self, client, admin_tokens):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_tokens['access']}")
        res = client.post(reverse("auth-logout"), {"refresh": admin_tokens["refresh"]})
        assert res.status_code == 200

        # Using the blacklisted refresh token should now fail
        res2 = client.post(reverse("auth-token-refresh"), {"refresh": admin_tokens["refresh"]})
        assert res2.status_code == 401


@pytest.mark.django_db
class TestPermissions:
    def test_doctor_cannot_register_users(self, client, doctor_user):
        res = client.post(
            reverse("auth-login"), {"email": "doctor@hospital.com", "password": "StrongPass123!"}
        )
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        register_res = client.post(
            reverse("auth-register"),
            {"email": "new@hospital.com", "password": "StrongPass123!", "password2": "StrongPass123!", "role": "nurse"},
        )
        assert register_res.status_code == 403

    def test_unauthenticated_access_denied(self, client):
        res = client.get(reverse("auth-me"))
        assert res.status_code == 401
