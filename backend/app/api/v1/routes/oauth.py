import logging
import secrets
from urllib.parse import urlencode

from authlib.integrations.base_client import OAuthError
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import EmailStr, TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.frontend import get_frontend_settings
from app.core.oauth import oauth
from app.services.auth.oauth import finish_oauth_login
from app.services.auth.security import COOKIE_NAME, set_session_cookie

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/oauth", tags=["OAuth"])
email_adapter = TypeAdapter(EmailStr)
SUPPORTED_PROVIDERS = {"google", "github"}


def frontend_error(code: str, provider: str = "") -> RedirectResponse:
    params = {"auth_error": code}
    if provider in SUPPORTED_PROVIDERS:
        params["provider"] = provider
    return RedirectResponse(
        f"{get_frontend_settings().frontend_url}/login?{urlencode(params)}",
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


def get_provider_client(provider: str):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(404, "Unknown authentication provider")
    client = oauth.create_client(provider)
    if client is None:
        raise HTTPException(503, "Provider not configured")
    return client


async def read_provider_identity(client, provider: str, token: dict):
    if provider == "google":
        info = token.get("userinfo")
        if not info or info.get("email_verified") is not True:
            raise HTTPException(400, "Google must provide a verified email address")
        subject = info.get("sub")
        email = info.get("email")
        name = info.get("name")
    else:
        response = await client.get("user", token=token)
        response.raise_for_status()
        profile = response.json()
        github_id = profile.get("id")
        if type(github_id) is not int or github_id <= 0:
            raise HTTPException(400, "Invalid GitHub identity")
        subject = str(github_id)
        name = profile.get("name") or profile.get("login")
        email = None
        page = 1
        while email is None:
            response = await client.get(
                "user/emails", token=token,
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
            addresses = response.json()
            if not isinstance(addresses, list):
                raise HTTPException(400, "Invalid GitHub email response")
            for address in addresses:
                if address.get("primary") is True and address.get("verified") is True:
                    email = address.get("email")
                    break
            if email is not None or len(addresses) < 100:
                break
            page += 1
        if not email:
            raise HTTPException(400, "GitHub needs a verified primary email address")
    if not isinstance(subject, str) or not 1 <= len(subject) <= 255:
        raise HTTPException(400, "Invalid provider account identifier")
    try:
        email = str(email_adapter.validate_python(email)).lower()
    except ValidationError:
        raise HTTPException(400, "Invalid provider email") from None
    if len(email) > 320:
        raise HTTPException(400, "Provider email is too long")
    display_name = name.strip() if isinstance(name, str) else ""
    return subject, email, (display_name or email.split("@", 1)[0])[:100]


@router.get("/{provider}/login")
async def start_oauth_login(provider: str, request: Request):
    try:
        client = get_provider_client(provider)
        request.session.clear()
        callback_url = (
            f"{get_settings().backend_url.rstrip('/')}"
            f"/api/v1/auth/oauth/{provider}/callback"
        )
        options = {"code_verifier": secrets.token_urlsafe(48)}
        if provider == "google":
            options["nonce"] = secrets.token_urlsafe(32)
        return await client.authorize_redirect(request, callback_url, **options)
    except HTTPException as exc:
        code = "provider_unavailable" if exc.status_code == 503 else "unsupported_provider"
        return frontend_error(code, provider)
    except Exception:
        request.session.clear()
        logger.warning("OAuth start failed: %s", provider if provider in SUPPORTED_PROVIDERS else "unknown")
        return frontend_error("provider_error", provider)


@router.get("/{provider}/callback")
async def oauth_callback(provider: str, request: Request):
    try:
        client = get_provider_client(provider)
        token = await client.authorize_access_token(request)
        subject, email, name = await read_provider_identity(client, provider, token)
        session_token = await run_in_threadpool(
            finish_oauth_login, provider, subject, email, name,
            request.cookies.get(COOKIE_NAME),
        )
    except OAuthError as exc:
        code = "oauth_cancelled" if exc.error == "access_denied" else "oauth_invalid"
        return frontend_error(code, provider)
    except HTTPException as exc:
        code = {
            409: "account_exists",
            401: "account_unavailable",
            503: "provider_unavailable",
            404: "unsupported_provider",
        }.get(exc.status_code, "oauth_invalid")
        return frontend_error(code, provider)
    except Exception:
        logger.warning("OAuth callback failed: %s", provider if provider in SUPPORTED_PROVIDERS else "unknown")
        return frontend_error("provider_error", provider)
    finally:
        request.session.clear()
    response = RedirectResponse(
        f"{get_frontend_settings().frontend_url}/app",
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
    set_session_cookie(response, session_token)
    return response
