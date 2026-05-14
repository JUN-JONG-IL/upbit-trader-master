"""
MongoDB _default_uri() 테스트

quote_plus() 를 사용하여 특수문자 포함 비밀번호를 URL 인코딩하는지 검증합니다.
"""
import os
import sys
import pytest
from urllib.parse import quote_plus

# Stub pymongo so that mongo_db.py can be imported without the real driver
import types as _types

if "pymongo" not in sys.modules:
    _pymongo = _types.ModuleType("pymongo")
    _pymongo.MongoClient = None
    _pymongo.ASCENDING = 1
    _errors = _types.ModuleType("pymongo.errors")
    _errors.ConnectionFailure = Exception
    sys.modules["pymongo"] = _pymongo
    sys.modules["pymongo.errors"] = _errors
    _pymongo.errors = _errors

from mongodb.mongo_db import _default_uri  # noqa: E402  (added after sys.modules stub)


class TestDefaultUri:
    """_default_uri() 단위 테스트"""

    def _clean_env(self, monkeypatch):
        """MongoDB 관련 환경 변수를 모두 제거합니다."""
        for var in (
            "MONGO_URI",
            "MONGO_HOST",
            "MONGO_PORT",
            "MONGO_DB",
            "MONGO_INITDB_ROOT_USERNAME",
            "MONGO_INITDB_ROOT_USERNAME_CONTAINER",
            "MONGO_USER",
            "MONGO_ID",
            "MONGO_INITDB_ROOT_PASSWORD",
            "MONGO_INITDB_ROOT_PASSWORD_CONTAINER",
            "MONGO_PASSWORD",
        ):
            monkeypatch.delenv(var, raising=False)

    # ──────────────────────────────────────── 인증 없이 기본 URI ──

    def test_no_auth_default_uri(self, monkeypatch):
        """인증 정보 없을 때 기본 URI 반환"""
        self._clean_env(monkeypatch)
        uri = _default_uri()
        assert uri == "mongodb://localhost:27017/upbit_trader"

    def test_custom_host_port_db(self, monkeypatch):
        """MONGO_HOST / MONGO_PORT / MONGO_DB 환경변수 반영"""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("MONGO_HOST", "myserver")
        monkeypatch.setenv("MONGO_PORT", "27018")
        monkeypatch.setenv("MONGO_DB", "mydb")
        uri = _default_uri()
        assert uri == "mongodb://myserver:27018/mydb"

    # ──────────────────────────────────────── MONGO_URI 우선순위 ──

    def test_mongo_uri_env_returned_as_is(self, monkeypatch):
        """MONGO_URI 환경변수가 있으면 그대로 반환 (재인코딩 없음)"""
        self._clean_env(monkeypatch)
        custom = "mongodb://u:P%40ss@host:27017/db?authSource=admin"
        monkeypatch.setenv("MONGO_URI", custom)
        assert _default_uri() == custom

    # ──────────────────────────────────────── quote_plus 인코딩 ──

    def test_special_chars_in_password(self, monkeypatch):
        """비밀번호에 특수문자 포함 시 quote_plus 인코딩 적용"""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("MONGO_INITDB_ROOT_USERNAME", "admin")
        monkeypatch.setenv("MONGO_INITDB_ROOT_PASSWORD", "P@ssw0rd!")
        uri = _default_uri()
        encoded_pw = quote_plus("P@ssw0rd!")
        assert f":{encoded_pw}@" in uri
        # raw 비밀번호 문자열이 URI 에 그대로 포함되지 않아야 합니다
        assert "P@ssw0rd!" not in uri

    def test_at_sign_in_password(self, monkeypatch):
        """비밀번호에 @ 포함 시 %40 으로 인코딩"""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("MONGO_INITDB_ROOT_USERNAME", "user")
        monkeypatch.setenv("MONGO_INITDB_ROOT_PASSWORD", "p@ss")
        uri = _default_uri()
        assert "%40" in uri
        assert "p@ss" not in uri

    def test_colon_in_password(self, monkeypatch):
        """비밀번호에 : 포함 시 %3A 로 인코딩"""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("MONGO_INITDB_ROOT_USERNAME", "user")
        monkeypatch.setenv("MONGO_INITDB_ROOT_PASSWORD", "pass:word")
        uri = _default_uri()
        assert "%3A" in uri or "%3a" in uri
        # raw ':' 는 user:pass 구분자로 한 번만 나타나야 하며 비밀번호 부분에 없어야 함
        userinfo = uri.split("//")[1].split("@")[0]  # "user:encoded_pass"
        _, encoded_pass = userinfo.split(":", 1)
        assert ":" not in encoded_pass

    def test_slash_in_password(self, monkeypatch):
        """비밀번호에 / 포함 시 %2F 로 인코딩"""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("MONGO_INITDB_ROOT_USERNAME", "user")
        monkeypatch.setenv("MONGO_INITDB_ROOT_PASSWORD", "pass/word")
        uri = _default_uri()
        assert "%2F" in uri or "%2f" in uri

    def test_username_encoded(self, monkeypatch):
        """사용자명에 특수문자 포함 시 quote_plus 인코딩 적용"""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("MONGO_INITDB_ROOT_USERNAME", "user@domain")
        monkeypatch.setenv("MONGO_INITDB_ROOT_PASSWORD", "secret")
        uri = _default_uri()
        encoded_user = quote_plus("user@domain")
        assert uri.startswith(f"mongodb://{encoded_user}:")

    def test_auth_source_admin(self, monkeypatch):
        """인증 URI 에 authSource=admin 포함"""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("MONGO_INITDB_ROOT_USERNAME", "admin")
        monkeypatch.setenv("MONGO_INITDB_ROOT_PASSWORD", "secret")
        uri = _default_uri()
        assert "authSource=admin" in uri

    # ──────────────────────────────────────── 환경변수 우선순위 ──

    def test_mongo_user_fallback(self, monkeypatch):
        """MONGO_INITDB_ROOT_USERNAME 없을 때 MONGO_USER 사용; 특수문자도 인코딩"""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("MONGO_USER", "fallback_user")
        monkeypatch.setenv("MONGO_PASSWORD", "p@ss#1!")
        uri = _default_uri()
        encoded_user = quote_plus("fallback_user")
        encoded_pw = quote_plus("p@ss#1!")
        assert encoded_user in uri
        assert f":{encoded_pw}@" in uri
        # raw password must not appear in the URI
        assert "p@ss#1!" not in uri

    def test_credentials_take_precedence_over_mongo_uri(self, monkeypatch):
        """개별 인증 정보가 MONGO_URI 보다 우선"""
        self._clean_env(monkeypatch)
        monkeypatch.setenv("MONGO_INITDB_ROOT_USERNAME", "admin")
        monkeypatch.setenv("MONGO_INITDB_ROOT_PASSWORD", "secret")
        monkeypatch.setenv("MONGO_URI", "mongodb://other:other@otherhost:27017/otherdb")
        uri = _default_uri()
        # 개별 인증 정보가 우선이므로 MONGO_URI 는 무시됨
        assert "admin" in uri
        assert "otherhost" not in uri
