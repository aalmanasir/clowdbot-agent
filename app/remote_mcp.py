import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.mcp_server import handle_request


router = APIRouter()

OAUTH_SCOPE = "clowdbot:read"
CODE_TTL_SECONDS = 300
TOKEN_TTL_SECONDS = 3600
_authorization_codes: dict[str, dict[str, Any]] = {}


def _base_url(request: Request) -> str:
    configured = os.getenv("MCP_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
    return str(request.base_url).rstrip("/")


def _auth_mode() -> str:
    return os.getenv("MCP_AUTH_MODE", "none").strip().lower()


def _oauth_enabled() -> bool:
    return _auth_mode() == "oauth"


def _secret() -> str:
    return os.getenv("MCP_OAUTH_TOKEN_SECRET") or os.getenv("GITHUB_WEBHOOK_SECRET") or "development-only-secret"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_json(data: dict[str, Any]) -> str:
    return _b64url(json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _sign(payload: str) -> str:
    return _b64url(hmac.new(_secret().encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest())


def _issue_token(audience: str, scope: str) -> str:
    now = int(time.time())
    header = _b64url_json({"alg": "HS256", "typ": "JWT"})
    body = _b64url_json(
        {
            "iss": audience,
            "aud": audience,
            "iat": now,
            "exp": now + TOKEN_TTL_SECONDS,
            "scope": scope,
            "sub": "chatgpt-connector",
        }
    )
    signing_input = f"{header}.{body}"
    return f"{signing_input}.{_sign(signing_input)}"


def _decode_part(part: str) -> dict[str, Any]:
    padding = "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode((part + padding).encode("ascii")))


def _verify_token(token: str, audience: str) -> bool:
    try:
        header, body, signature = token.split(".", 2)
        signing_input = f"{header}.{body}"
        if not hmac.compare_digest(signature, _sign(signing_input)):
            return False
        payload = _decode_part(body)
        if payload.get("aud") != audience:
            return False
        if int(payload.get("exp", 0)) < int(time.time()):
            return False
        return OAUTH_SCOPE in str(payload.get("scope", "")).split()
    except Exception:
        return False


def _challenge(request: Request) -> str:
    base = _base_url(request)
    return (
        "Bearer "
        f'resource_metadata="{base}/.well-known/oauth-protected-resource", '
        f'scope="{OAUTH_SCOPE}"'
    )


def _extract_bearer(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix) :].strip()
    return ""


def _with_security_schemes(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("result", {}).get("tools") is None:
        return response
    scheme = {"type": "oauth2", "scopes": [OAUTH_SCOPE]} if _oauth_enabled() else {"type": "noauth"}
    for tool in response["result"]["tools"]:
        tool["securitySchemes"] = [scheme]
    return response


def _clean_expired_codes() -> None:
    now = time.time()
    expired = [code for code, data in _authorization_codes.items() if data["expires_at"] < now]
    for code in expired:
        _authorization_codes.pop(code, None)


def _redirect_uri_allowed(redirect_uri: str) -> bool:
    allowed = (
        "https://chatgpt.com/connector/oauth/",
        "https://chatgpt.com/connector_platform_oauth_redirect",
    )
    return redirect_uri.startswith(allowed)


@router.get("/mcp")
async def mcp_info(request: Request):
    return {
        "ok": True,
        "endpoint": f"{_base_url(request)}/mcp",
        "transport": "streaming-http-json",
        "auth_mode": _auth_mode(),
        "oauth_metadata": f"{_base_url(request)}/.well-known/oauth-protected-resource",
    }


@router.post("/mcp")
async def mcp_http(request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {exc}"}},
            status_code=400,
        )

    messages = payload if isinstance(payload, list) else [payload]
    for message in messages:
        if isinstance(message, dict) and _oauth_enabled() and message.get("method") == "tools/call":
            token = _extract_bearer(request)
            if not _verify_token(token, _base_url(request)):
                raise HTTPException(status_code=401, headers={"WWW-Authenticate": _challenge(request)})

    responses: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            responses.append(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
            )
            continue
        response = await handle_request(message)
        if response is not None:
            responses.append(_with_security_schemes(response))

    if isinstance(payload, list):
        return JSONResponse(responses)
    if not responses:
        return Response(status_code=202)
    return JSONResponse(responses[0])


@router.post("/sse")
async def legacy_sse_post(request: Request):
    return await mcp_http(request)


@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource(request: Request):
    base = _base_url(request)
    return {
        "resource": base,
        "authorization_servers": [base],
        "scopes_supported": [OAUTH_SCOPE],
        "resource_documentation": f"{base}/mcp",
    }


@router.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server(request: Request):
    base = _base_url(request)
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": [OAUTH_SCOPE],
    }


@router.post("/oauth/register")
async def oauth_register(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    return {
        "client_id": f"chatgpt-{uuid.uuid4()}",
        "client_id_issued_at": int(time.time()),
        "redirect_uris": data.get("redirect_uris") or [],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": OAUTH_SCOPE,
    }


@router.get("/oauth/authorize")
async def oauth_authorize(request: Request):
    params = dict(request.query_params)
    redirect_uri = params.get("redirect_uri", "")
    state = params.get("state", "")
    code_challenge = params.get("code_challenge", "")
    code_challenge_method = params.get("code_challenge_method", "")
    resource = params.get("resource") or _base_url(request)
    expected_pin = os.getenv("MCP_OAUTH_PIN", "").strip()
    provided_pin = params.get("pin", "").strip()

    if params.get("response_type") != "code":
        raise HTTPException(status_code=400, detail="Unsupported response_type")
    if not _redirect_uri_allowed(redirect_uri):
        raise HTTPException(status_code=400, detail="Redirect URI is not allowed")
    if code_challenge_method != "S256" or not code_challenge:
        raise HTTPException(status_code=400, detail="PKCE S256 is required")
    if not expected_pin:
        return HTMLResponse(
            "<h1>OAuth not activated</h1>"
            "<p>Set MCP_OAUTH_PIN and MCP_OAUTH_TOKEN_SECRET on the server before linking this connector.</p>",
            status_code=503,
        )
    if provided_pin != expected_pin:
        action = f"{_base_url(request)}/oauth/authorize"
        hidden = "\n".join(
            f'<input type="hidden" name="{key}" value="{value}">' for key, value in params.items() if key != "pin"
        )
        return HTMLResponse(
            "<h1>Authorize Danial Command Center</h1>"
            "<p>Enter your private connector PIN to allow ChatGPT read-only access to this MCP server.</p>"
            f'<form method="get" action="{action}">{hidden}'
            '<input name="pin" type="password" autocomplete="one-time-code" autofocus>'
            '<button type="submit">Authorize</button></form>',
            status_code=200,
        )

    _clean_expired_codes()
    code = _b64url(os.urandom(32))
    _authorization_codes[code] = {
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "resource": resource.rstrip("/"),
        "scope": params.get("scope") or OAUTH_SCOPE,
        "expires_at": time.time() + CODE_TTL_SECONDS,
    }
    query = {"code": code}
    if state:
        query["state"] = state
    return RedirectResponse(f"{redirect_uri}?{urlencode(query)}", status_code=302)


@router.post("/oauth/token")
async def oauth_token(request: Request):
    raw = (await request.body()).decode("utf-8")
    form = {key: values[0] for key, values in parse_qs(raw).items()}
    if form.get("grant_type") != "authorization_code":
        raise HTTPException(status_code=400, detail="unsupported_grant_type")
    code = form.get("code", "")
    code_verifier = form.get("code_verifier", "")
    data = _authorization_codes.pop(code, None)
    if not data or data["expires_at"] < time.time():
        raise HTTPException(status_code=400, detail="invalid_grant")
    if form.get("redirect_uri") != data["redirect_uri"]:
        raise HTTPException(status_code=400, detail="invalid_redirect_uri")

    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected_challenge = _b64url(digest)
    if not hmac.compare_digest(expected_challenge, data["code_challenge"]):
        raise HTTPException(status_code=400, detail="invalid_code_verifier")

    scope = data["scope"] or OAUTH_SCOPE
    return {
        "access_token": _issue_token(data["resource"], scope),
        "token_type": "Bearer",
        "expires_in": TOKEN_TTL_SECONDS,
        "scope": scope,
    }
