import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.auth.dev import assert_safe_configuration
from app.mcp_server import mcp_app
from app.routers import (
    admin,
    ai,
    auth,
    catalog,
    cinema,
    comments,
    discovery,
    episodes,
    expenses,
    exports,
    extension,
    fresh,
    friends,
    health,
    imports,
    me,
    messages,
    nights,
    notifications,
    password_auth,
    profile,
    profiles,
    quotes,
    signals,
    stats,
    tokens,
    tracking,
)

EXTENSION_ORIGINS = re.compile(r"^(chrome-extension|moz-extension|safari-web-extension)://")


def create_app() -> FastAPI:
    # Fail fast rather than ever serving passwordless logins in production.
    assert_safe_configuration()
    application = FastAPI(
        title="Watchpile API",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=mcp_app.lifespan,
    )
    # Mount with the trailing slash too: without it, clients pointed at
    # /api/mcp get a 307 they may not follow with the Authorization header.
    application.mount("/api/mcp/", mcp_app)
    application.mount("/api/mcp", mcp_app)
    # Only the extension routes, and only for extension origins. Everything
    # else stays same origin with cookies and CSRF.
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=EXTENSION_ORIGINS.pattern,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(password_auth.router)
    application.include_router(me.router)
    application.include_router(admin.router)
    application.include_router(catalog.router)
    application.include_router(discovery.router)
    application.include_router(tracking.router)
    application.include_router(profile.router)
    application.include_router(exports.router)
    application.include_router(imports.router)
    application.include_router(notifications.router)
    application.include_router(ai.router)
    application.include_router(ai.admin_router)
    application.include_router(tokens.router)
    application.include_router(stats.router)
    application.include_router(signals.router)
    application.include_router(signals.admin_router)
    application.include_router(fresh.router)
    application.include_router(cinema.router)
    application.include_router(episodes.router)
    application.include_router(expenses.router)
    application.include_router(comments.router)
    application.include_router(profiles.router)
    application.include_router(quotes.router)
    application.include_router(extension.router)
    application.include_router(messages.router)
    application.include_router(friends.router)
    application.include_router(nights.router)

    @application.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    return application


app = create_app()
