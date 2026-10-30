"""Vendor-independent storage wire format. Versions live in physical key layouts."""
import json
from datetime import datetime

from backend.domain.entities.auth.storage import AuthSession, OAuthTransaction


def encode_session(session: AuthSession) -> bytes:
    return json.dumps({"subject": session.subject, "roles": list(session.roles),
                       "expires_at": session.expires_at.isoformat()}, separators=(",", ":")).encode()

def decode_session(raw: bytes) -> AuthSession:
    value = json.loads(raw)
    return AuthSession(
        subject=value["subject"], roles=tuple(value["roles"]), expires_at=datetime.fromisoformat(value["expires_at"]),
    )

def encode_oauth(transaction: OAuthTransaction) -> bytes:
    return json.dumps({"redirect_uri": transaction.redirect_uri,
                       "code_verifier": transaction.code_verifier,
                       "nonce": transaction.nonce}, separators=(",", ":")).encode()

def decode_oauth(raw: bytes) -> OAuthTransaction:
    value = json.loads(raw)
    return OAuthTransaction(
        redirect_uri=value["redirect_uri"], code_verifier=value["code_verifier"], nonce=value["nonce"],
    )
