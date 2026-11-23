"""One-time Google Drive authorization for the CLI.

Uses Google's OAuth 2.0 device flow (the "TVs and Limited Input devices" client
type), so there is no local browser callback to wire up. The user opens a URL,
enters a short code, and VOID stores the resulting refresh token.

The OAuth client must be created by the user (or supplied through env vars):

    VOID_GDRIVE_CLIENT_ID
    VOID_GDRIVE_CLIENT_SECRET

Google Cloud Console → APIs & Services → Credentials → Create credentials →
OAuth client ID → TVs and Limited Input devices. Enable the Google Drive API.
"""

import time

import requests
from colorama import Fore

from .gdrive import GoogleDriveProvider

DEVICE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/drive"


def device_authorize(client_id: str, client_secret: str | None = None) -> dict:
    """Run the device flow and return the token payload (includes refresh_token)."""
    if not client_id:
        raise RuntimeError("a Google OAuth client id is required")

    data = {"client_id": client_id, "scope": SCOPE}
    if client_secret:
        data["client_secret"] = client_secret

    try:
        response = requests.post(DEVICE_URL, data=data, timeout=30)
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Could not reach Google: {exc}") from exc
    if response.status_code >= 400:
        raise RuntimeError(
            f"Google rejected the OAuth client ({response.status_code}): "
            f"{response.text[:200]}"
        )

    payload = response.json()
    device_code = payload.get("device_code")
    user_code = payload.get("user_code")
    verification = (
        payload.get("verification_url")
        or payload.get("verification_uri")
        or "https://www.google.com/device"
    )
    interval = int(payload.get("interval", 5))
    expires = int(payload.get("expires_in", 1800))

    print(f"{Fore.CYAN}~ Open {Fore.WHITE}{verification}")
    print(f"{Fore.CYAN}~ Enter the code: {Fore.YELLOW}{user_code}")
    print(f"{Fore.CYAN}~ Waiting for authorization...")

    deadline = time.time() + expires
    while time.time() < deadline:
        time.sleep(interval)
        token_data = {
            "client_id": client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }
        if client_secret:
            token_data["client_secret"] = client_secret
        try:
            token_response = requests.post(TOKEN_URL, data=token_data, timeout=30)
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Could not reach Google: {exc}") from exc

        try:
            token_payload = token_response.json()
        except ValueError:
            token_payload = {}

        if token_payload.get("access_token"):
            if not token_payload.get("refresh_token"):
                raise RuntimeError(
                    "Google did not return a refresh token. Revoke VOID in your "
                    "Google account permissions and try again."
                )
            return token_payload

        error = token_payload.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error == "expired_token":
            raise RuntimeError("The Google authorization code expired; try again.")
        if error == "access_denied":
            raise RuntimeError("Google authorization was denied.")
        raise RuntimeError(
            token_payload.get("error_description")
            or error
            or "Google authorization failed"
        )

    raise RuntimeError("Timed out waiting for Google authorization.")


def connect(
    client_id: str,
    client_secret: str | None = None,
    folder_name: str = "VOID",
) -> dict:
    """Authorize, create/find the VOID folder, and return a config dict."""
    tokens = device_authorize(client_id, client_secret)
    provider = GoogleDriveProvider(
        {
            "client_id": client_id,
            "client_secret": client_secret or "",
            "refresh_token": tokens["refresh_token"],
            "folder_id": "root",
        }
    )
    folder_id = provider.ensure_folder(folder_name)
    return {
        "client_id": client_id,
        "client_secret": client_secret or "",
        "refresh_token": tokens["refresh_token"],
        "folder_id": folder_id,
    }
