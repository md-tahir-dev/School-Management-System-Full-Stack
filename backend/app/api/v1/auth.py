from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status

from app.core.config import settings
from app.core.deps import CurrentUserAllowPending, DbSession
from app.core.errors import AppError, error_response
from app.core.ratelimit import client_ip, rate_limit
from app.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse, UserOut
from app.services import auth as auth_service
from app.services.auth import IssuedTokens

router = APIRouter(prefix="/auth", tags=["auth"])

API_PREFIX = "/api/v1"
REFRESH_COOKIE = "sms_refresh"  # httpOnly, only sent to /api/v1/auth/*
ROLE_COOKIE = "sms_role"  # httpOnly, read by Next.js middleware for route gating (UX only, not security)


def _set_cookies(response: Response, issued: IssuedTokens) -> None:
    max_age = settings.refresh_token_days * 86400
    common = {
        "max_age": max_age,
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
    }
    response.set_cookie(REFRESH_COOKIE, issued.refresh_token, path=f"{API_PREFIX}/auth", **common)
    response.set_cookie(ROLE_COOKIE, issued.user.role.value, path="/", **common)


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=f"{API_PREFIX}/auth")
    response.delete_cookie(ROLE_COOKIE, path="/")


def _token_response(issued: IssuedTokens) -> TokenResponse:
    return TokenResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        user=UserOut.model_validate(issued.user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[
        Depends(rate_limit("login", lambda: settings.login_ip_limit, lambda: settings.login_window_minutes * 60))
    ],
)
async def login(body: LoginRequest, request: Request, response: Response, db: DbSession):
    issued = await auth_service.login(
        db, body.username, body.password, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    _set_cookies(response, issued)
    return _token_response(issued)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: DbSession,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
):
    try:
        issued = await auth_service.refresh(
            db, refresh_token, ip=client_ip(request), user_agent=request.headers.get("user-agent")
        )
    except AppError as exc:
        # build the error response ourselves so we can also drop the dead cookies
        failure = error_response(request, exc)
        _clear_cookies(failure)
        return failure
    _set_cookies(response, issued)
    return _token_response(issued)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: DbSession,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
):
    await auth_service.logout(db, refresh_token)
    _clear_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/change-password", response_model=TokenResponse)
async def change_password(
    body: ChangePasswordRequest, request: Request, response: Response, user: CurrentUserAllowPending, db: DbSession
):
    issued = await auth_service.change_password(
        db,
        user,
        body.current_password,
        body.new_password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    _set_cookies(response, issued)
    return _token_response(issued)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUserAllowPending):
    return user
