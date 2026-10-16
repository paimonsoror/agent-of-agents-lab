"""JWT verification and token acquisition against Keycloak (ADR-0005).

- `KeycloakTokenVerifier` plugs into the MCP SDK (`MCPServer(token_verifier=..., auth=...)`)
  so every MCP request is authenticated before a tool runs, independently of the gateway.
- `verify_bearer` does the same for plain HTTP endpoints (Maestro's /api/ask).
- `client_credentials_token` lets a service mint its *own* token (the Fleet Console does;
  Maestro never does for downstream calls — it propagates the caller's token).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx2
import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from maestro_common.config import settings
from maestro_common.events import current_caller

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Caller:
    sub: str
    azp: str
    roles: tuple[str, ...]
    preferred_username: str
    raw_token: str

    def as_dict(self) -> dict[str, Any]:
        return {"sub": self.sub, "azp": self.azp, "roles": list(self.roles), "username": self.preferred_username}


class JWTError(Exception):
    pass


class _Verifier:
    """Verifies RS256 JWTs with Keycloak's JWKS; caches keys via PyJWKClient."""

    def __init__(self, jwks_url: str, issuer: str, audience: str) -> None:
        self.issuer = issuer
        self.audience = audience
        self._jwks = PyJWKClient(jwks_url, cache_keys=True, lifespan=600) if jwks_url else None

    def verify(self, token: str) -> dict[str, Any]:
        if not self._jwks:
            raise JWTError("OIDC_JWKS_URL is not configured")
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            return jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise JWTError(str(exc)) from exc


_verifier = _Verifier(settings.oidc_jwks_url, settings.oidc_issuer, settings.oidc_audience)


def caller_from_claims(claims: dict[str, Any], raw_token: str) -> Caller:
    return Caller(
        sub=str(claims.get("sub", "")),
        azp=str(claims.get("azp", claims.get("client_id", ""))),
        roles=tuple(claims.get("realm_access", {}).get("roles", [])),
        preferred_username=str(claims.get("preferred_username", "")),
        raw_token=raw_token,
    )


def verify_bearer(authorization: str | None) -> Caller:
    """For plain HTTP routes. Raises JWTError on any problem."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise JWTError("missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    caller = caller_from_claims(_verifier.verify(token), token)
    current_caller.set(caller.as_dict())
    return caller


class KeycloakTokenVerifier(TokenVerifier):
    """MCP SDK hook: called on every request with the raw bearer token."""

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = await asyncio.to_thread(_verifier.verify, token)
        except JWTError as exc:
            log.info("rejected token: %s", exc)
            return None
        caller = caller_from_claims(claims, token)
        current_caller.set(caller.as_dict())
        return AccessToken(
            token=token,
            client_id=caller.azp or caller.sub,
            scopes=str(claims.get("scope", "")).split(),
            expires_at=int(claims.get("exp", 0)) or None,
            subject=caller.sub,
            claims=claims,
        )


def auth_settings(resource_url: str) -> AuthSettings:
    """AuthSettings for an MCP server; resource validation is off because Keycloak uses an audience, not a resource URL."""
    return AuthSettings(
        issuer_url=AnyHttpUrl(settings.oidc_issuer),
        resource_server_url=AnyHttpUrl(resource_url),
        required_scopes=[],
        validate_token_resource=False,
    )


def caller_from_access_token(access: AccessToken | None) -> Caller | None:
    """Rebuild the Caller inside an MCP tool from `get_access_token()` (claims were verified already)."""
    if access is None:
        return None
    claims = jwt.decode(access.token, options={"verify_signature": False})
    return caller_from_claims(claims, access.token)


class _TokenCache:
    def __init__(self) -> None:
        self._token = ""
        self._exp = 0.0

    async def get(self, client_id: str, client_secret: str) -> str:
        if self._token and time.time() < self._exp - 60:
            return self._token
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(10.0)) as http:
            resp = await http.post(
                settings.oidc_token_url,
                data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
            )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._exp = time.time() + float(body.get("expires_in", 300))
        return self._token


_token_cache = _TokenCache()


async def client_credentials_token(client_id: str | None = None, client_secret: str | None = None) -> str:
    """Mint (and cache) this service's own token. Only the Fleet Console should need this."""
    return await _token_cache.get(client_id or settings.oidc_client_id, client_secret or settings.oidc_client_secret)
