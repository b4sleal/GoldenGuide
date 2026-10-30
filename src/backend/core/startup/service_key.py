"""Create a key for a service client (configs/base/system_config.yml, system.service_clients).

    uv run python -m backend.core.startup.service_key github_actions_nightly

Prints a new random key and the setting to add to the server's .env. Store the key with the caller
only (e.g. a GitHub Actions secret); the server keeps just its SHA-256 hash. Nothing is written to disk.
"""
import argparse
import re
import secrets

from backend.domain.settings.service_clients import hash_key

# 32 random bytes: far beyond guessing, which is why an unsalted SHA-256 hash is enough to store.
KEY_BYTES = 32


def env_name(client: str) -> str:
    """The secret holding the client's current key hash, matching the YAML reference."""
    return f"SERVICE_CLIENT__{re.sub(r'[^A-Za-z0-9]', '_', client).upper()}__KEY_HASH"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("client", help="Service client name as configured in system.service_clients")
    client = parser.parse_args().client

    key = secrets.token_urlsafe(KEY_BYTES)
    print(f"Key for {client} (store it with the caller only, it is not shown again):\n  {key}\n")
    print(f"Add to the server's .env (to rotate: move the old hash to the PREVIOUS_ variable first):\n"
          f"  {env_name(client)}={hash_key(key)}")


if __name__ == "__main__":
    main()
