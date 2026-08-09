"""Prepare a usable install.

Creates the accounts, turns on password sign-in, and fills the catalog with
REAL titles fetched from the configured provider. There is no invented
sample data: if no provider key is configured the catalog simply stays
empty until one is added.

    python -m app.seed              accounts plus catalog
    python -m app.seed --catalog    catalog only
    python -m app.seed --accounts   accounts only
"""

import asyncio
import logging
import sys

from sqlalchemy import func, select

from app.catalog import bootstrap, omdb_source
from app.db import get_sessionmaker
from app.models import Title, User

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("watchpile.seed")

SEED_PASSWORD = "watchpile-local"


async def _seed_user(db, username: str, role: str, country: str, languages: list[str]) -> User:
    from app.auth.service import get_default_tenant

    user = (
        await db.execute(select(User).where(func.lower(User.username) == username.lower()))
    ).scalar_one_or_none()
    if user is None:
        tenant = await get_default_tenant(db)
        user = User(
            tenant_id=tenant.id,
            username=username,
            email=f"{username.lower()}@localhost",
            role=role,
            services=[8, 337],
            prefs={"languages": languages},
            api_enabled=True,
            is_active=True,
        )
        db.add(user)
        await db.flush()
    # Seeded accounts need an address like any other, or the dev instance
    # has two people who cannot be clicked on or written to.
    from app.social import handles

    await handles.assign(db, user)
    if user.country_code is None:
        user.country_code = country
    return user


async def seed_accounts() -> None:
    async with get_sessionmaker()() as db:
        from app.auth import passwords

        owner = await _seed_user(db, "Lordo", "admin", "EG", ["ar", "en"])
        friend = await _seed_user(db, "Nadia", "member", "MA", ["fr", "ar"])

        auth_settings = await passwords.get_auth_settings(db)
        auth_settings.password_enabled = True
        for person in (owner, friend):
            if not person.password_hash:
                await passwords.set_password(db, person, SEED_PASSWORD)
        await db.commit()
        logger.info("accounts ready: Lordo (admin) and Nadia, password %s", SEED_PASSWORD)


async def seed_catalog() -> None:
    async with get_sessionmaker()() as db:
        if not omdb_source.configured():
            logger.warning("no OMDb key configured, skipping catalog import")
            return
        before = (await db.execute(select(func.count(Title.id)))).scalar_one()
        logger.info(
            "importing %d real titles, this uses cached responses on reruns", len(bootstrap.TITLES)
        )
        await omdb_source.import_titles(db, bootstrap.TITLES)
        after = (await db.execute(select(func.count(Title.id)))).scalar_one()
        logger.info("catalog now holds %d titles (%d new)", after, after - before)


async def main() -> None:
    args = set(sys.argv[1:])
    if not args or "--accounts" in args:
        await seed_accounts()
    if not args or "--catalog" in args:
        await seed_catalog()


if __name__ == "__main__":
    asyncio.run(main())
