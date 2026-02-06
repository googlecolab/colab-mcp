import os
import netrc
import logging
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport import requests
from google.oauth2.credentials import Credentials
from typing import Optional, Dict

logger = logging.getLogger(__name__)

CLIENT_ID = "366568267421-7o7krvn9105p1ba0p3ahnnf8upt09m7h.apps.googleusercontent.com"
CLIENT_SECRET = "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"

CLIENT_SECRETS_DICT = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8200"],
    }
}

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/colaboratory",
]

NETRC_MACHINE = "colab-mcp"
NETRC_LOGIN = "google-oauth-refresh-token"


def _get_netrc_path() -> str:
    """Returns the full path to the .netrc file."""
    return os.path.expanduser("~/.netrc")


def _write_netrc_authenticators(authenticators: Dict[str, tuple], netrc_path: str):
    """Writes the authenticators dictionary to a .netrc file, ensuring correct permissions."""
    netrc_content = ""
    for machine, auth_info in authenticators.items():
        login, account, password = auth_info
        netrc_content += f"machine {machine}\n"
        if login:
            netrc_content += f"\tlogin {login}\n"
        if account:
            netrc_content += f"\taccount {account}\n"
        if password:
            netrc_content += f"\tpassword {password}\t\n"  # Added \t to ensure newline and proper formatting

    try:
        # Set umask to ensure 0o600 permissions (read-write for owner only)
        original_umask = os.umask(0o177)
        with open(netrc_path, "w") as f:
            f.write(netrc_content)
    except Exception as e:
        logger.error(f"Failed to write .netrc: {e}")
    finally:
        os.umask(original_umask)  # Restore original umask


def _read_refresh_token_from_netrc() -> Optional[str]:
    """Reads the refresh token from the .netrc file."""
    netrc_path = _get_netrc_path()
    if not os.path.exists(netrc_path):
        return None
    try:
        n = netrc.netrc(netrc_path)
        auth_info = n.hosts.get(NETRC_MACHINE)
        if auth_info and auth_info[0] == NETRC_LOGIN:
            return auth_info[2]  # password field is the refresh token
    except Exception as e:
        logger.warning(f"Error reading .netrc: {e}")
    return None


def _save_refresh_token_to_netrc(refresh_token: str):
    """Saves the refresh token to the .netrc file."""
    netrc_path = _get_netrc_path()
    authenticators = {}
    if os.path.exists(netrc_path):
        try:
            n = netrc.netrc(netrc_path)
            authenticators = n.hosts
        except Exception as e:
            logger.warning(
                f"Error reading existing .netrc for update: {e}. Creating new .netrc entries."
            )

    authenticators[NETRC_MACHINE] = (NETRC_LOGIN, None, refresh_token)
    _write_netrc_authenticators(authenticators, netrc_path)
    logger.info(f"Refresh token saved to {netrc_path}")


def _remove_refresh_token_from_netrc():
    """Removes the refresh token entry from the .netrc file."""
    netrc_path = _get_netrc_path()
    if not os.path.exists(netrc_path):
        return

    authenticators = {}
    try:
        n = netrc.netrc(netrc_path)
        authenticators = n.hosts
        if NETRC_MACHINE in authenticators:
            del authenticators[NETRC_MACHINE]
            _write_netrc_authenticators(authenticators, netrc_path)
            logger.info(f"Removed .netrc entry for {NETRC_MACHINE}.")
    except Exception as e:
        logger.warning(f"Error removing .netrc entry: {e}")


class _GoogleOAuthClient:
    """A client for Google OAuth2 flow, simplified with google-auth-oauthlib."""

    def get_session(self) -> requests.AuthorizedSession:
        """
        Retrieves an authorized session, initiating OAuth flow if necessary.
        Attempts to load credentials from .netrc first to avoid re-authentication.

        Returns:
            google.auth.transport.requests.AuthorizedSession
        """
        refresh_token = _read_refresh_token_from_netrc()

        if refresh_token:
            logger.info("Attempting to use refresh token from .netrc")
            try:
                creds = Credentials(
                    token=None,  # Access token will be refreshed
                    refresh_token=refresh_token,
                    token_uri=CLIENT_SECRETS_DICT["installed"]["token_uri"],
                    client_id=CLIENT_SECRETS_DICT["installed"]["client_id"],
                    client_secret=CLIENT_SECRETS_DICT["installed"]["client_secret"],
                    scopes=SCOPES,
                )

                # Refresh token to get a new access token
                creds.refresh(requests.Request())
                logger.info(
                    "Successfully refreshed access token using .netrc credentials."
                )
                return requests.AuthorizedSession(creds)
            except Exception as e:
                logger.warning(
                    f"Failed to refresh token from .netrc: {e}. Removing invalid entry and initiating full OAuth flow."
                )
                _remove_refresh_token_from_netrc()  # Clean up invalid token

        # If no refresh token or refresh failed, initiate full OAuth flow
        flow = InstalledAppFlow.from_client_config(
            CLIENT_SECRETS_DICT,
            SCOPES,
        )
        flow.run_local_server(port=8200)

        # After successful authentication, save the refresh token if available
        if flow.credentials and flow.credentials.refresh_token:
            _save_refresh_token_to_netrc(flow.credentials.refresh_token)
            logger.info("New refresh token saved to .netrc.")
        else:
            err = "No refresh token obtained during full OAuth flow. Credentials will not be persisted."
            logging.warning(err)
            raise PermissionError(err)

        return flow.authorized_session()


# Create a singleton instance
GoogleOAuthClient = _GoogleOAuthClient()
