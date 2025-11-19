#!/usr/bin/env python3
"""
Utility script to hash passwords for production use.

Usage:
    python scripts/hash_password.py

This will prompt for a password and output the bcrypt hash
that can be used in the ADMIN_PASSWORD environment variable.
"""

import getpass
from passlib.context import CryptContext


def main():
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    print("=" * 60)
    print("Trading Arena - Password Hash Generator")
    print("=" * 60)
    print()
    print("This script will hash your password using bcrypt.")
    print("Use the output as your ADMIN_PASSWORD in .env file.")
    print()

    # Get password from user
    password = getpass.getpass("Enter password to hash: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("\n❌ Error: Passwords do not match!")
        return 1

    if len(password) < 8:
        print("\n❌ Error: Password must be at least 8 characters long!")
        return 1

    # Hash the password
    hashed = pwd_context.hash(password)

    print("\n" + "=" * 60)
    print("✅ Password hashed successfully!")
    print("=" * 60)
    print()
    print("Add these to your .env file:")
    print()
    print(f"ADMIN_PASSWORD={hashed}")
    print("PASSWORD_MODE=hashed")
    print()
    print("⚠️  IMPORTANT: Keep this hash secret!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    exit(main())
