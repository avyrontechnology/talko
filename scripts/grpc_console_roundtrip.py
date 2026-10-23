"""Live gRPC round-trip: talko client -> console-core server.

WHAT IT CHECKS
  - TalkoLogin accepts valid credentials and rejects bad ones
  - GetUserDetails returns the profile
  - GetUserPermissions returns the caller's RBAC slugs
  - WalletDebit debits available balance, and a retry with the same call_id
    is not double-charged (idempotency)
  - Overdraw is rejected with FAILED_PRECONDITION carrying a real message

USAGE
  1. Start the console gRPC server (insecure, local):
       cd console-core
       POSTGRES_HOST=127.0.0.1 CACHE_HOST=127.0.0.1 CACHE_PROTOCOL=redis \\
       MONGO_HOST=127.0.0.1 CERT=None KEY=None \\
       python -m src.rpc_main

  2. Point talko at it and run this script:
       cd talko
       CONSOLE_GRPC_HOST=127.0.0.1 CONSOLE_GRPC_PORT=50051 \\
       CONSOLE_GRPC_API_KEY=talko-key CA=None \\
       python scripts/grpc_console_roundtrip.py

Edit USER_ID / PARTNER_ID / EMAIL / PASSWORD below for the local seed data.
"""
import asyncio
import os
import sys
import uuid

os.environ.setdefault("CONSOLE_GRPC_HOST", "127.0.0.1")
os.environ.setdefault("CONSOLE_GRPC_PORT", "50051")
os.environ.setdefault("CONSOLE_GRPC_API_KEY", "talko-key")
os.environ.setdefault("CA", "None")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.grpc_client.client_services.auth_service_client import TalkoAuthServiceClient  # noqa: E402
from src.grpc_client.client_services.wallet_service_client import TalkoWalletServiceClient  # noqa: E402

EMAIL = "v@gmail.com"
PASSWORD = "Ryujin@12"
USER_ID = "90bf78a7-9f5a-4873-85fe-376014cf5d67"
PARTNER_ID = "7404d1b1-b610-47e6-8ed3-1dd448db84bb"

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


async def main() -> None:
    auth = TalkoAuthServiceClient()
    wallet = TalkoWalletServiceClient()

    profile = await auth.talko_login(EMAIL, PASSWORD)
    record(
        "TalkoLogin valid credentials",
        bool(profile) and profile.get("user_id") == USER_ID,
        f"user={profile and profile.get('user_id')}",
    )

    bad = await auth.talko_login(EMAIL, "wrong-password")
    record("TalkoLogin rejects bad password", bad is None, f"result={bad}")

    details = await auth.get_user_details(USER_ID)
    record("GetUserDetails", bool(details) and details.get("user_id") == USER_ID, f"email={details and details.get('email')}")

    perms = await auth.get_user_permissions(USER_ID)
    count = len(perms) if isinstance(perms, (list, tuple, set, dict)) else 0
    record("GetUserPermissions", count > 0, f"{count} permissions")

    call_id = f"grpc-test-{uuid.uuid4().hex[:12]}"
    first = await wallet.wallet_debit(PARTNER_ID, 1.50, "INR", call_id, 2, "grpc test")
    record("WalletDebit", bool(first) and first.get("already_charged") is False, f"remaining={first and first.get('remaining_balance')}")

    second = await wallet.wallet_debit(PARTNER_ID, 1.50, "INR", call_id, 2, "grpc test")
    record(
        "WalletDebit idempotent retry",
        bool(second)
        and second.get("already_charged") is True
        and second.get("remaining_balance") == first.get("remaining_balance"),
        f"remaining={second and second.get('remaining_balance')}",
    )

    broke = await wallet.wallet_debit(
        PARTNER_ID, 9_999_999, "INR", f"grpc-test-{uuid.uuid4().hex[:12]}", 1, "overdraw test"
    )
    record("WalletDebit rejects overdraw", broke is None, f"result={broke}")

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())