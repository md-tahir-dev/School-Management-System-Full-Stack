"""Account recovery from the server shell, e.g. when the only admin forgot their password:

    docker compose exec api python -m scripts.reset_password admin

Sets a new random password, unlocks and re-activates the account, signs it out everywhere and prints the
password once. The user must change it at next sign-in.
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.security import ahash_password, generate_temp_password
from app.db.session import SessionLocal
from app.models import User
from app.services.users import revoke_sessions


async def main(username: str) -> None:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == username.strip().lower()))
        if user is None:
            sys.exit(f"No user named {username!r}.")
        password = generate_temp_password()
        user.password_hash = await ahash_password(password)
        user.must_change_password = True
        user.is_active = True
        user.failed_login_count, user.first_failed_at, user.locked_until = 0, None, None
        await revoke_sessions(db, user.id)
        await db.commit()
    print(f"username: {user.username}\npassword: {password}\n(change it after signing in)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m scripts.reset_password <username>")
    asyncio.run(main(sys.argv[1]))
