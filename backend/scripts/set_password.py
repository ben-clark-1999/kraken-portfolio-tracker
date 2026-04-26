"""CLI to bcrypt-hash a password.

Usage:
    backend/.venv/bin/python -m backend.scripts.set_password

Prompts twice for a password, then prints an env line you paste into .env:
    APP_PASSWORD_HASH=$2b$12$...

To change the password later, run again and replace the line in .env.
"""

import getpass
import sys

import bcrypt


def main() -> None:
    pw = getpass.getpass("Password: ")
    if not pw:
        print("Password cannot be empty.", file=sys.stderr)
        sys.exit(1)
    confirm = getpass.getpass("Confirm: ")
    if pw != confirm:
        print("Passwords do not match.", file=sys.stderr)
        sys.exit(1)

    hashed = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    print()
    print("Add this line to your .env (replacing any existing APP_PASSWORD_HASH):")
    print()
    print(f"APP_PASSWORD_HASH={hashed}")


if __name__ == "__main__":
    main()
