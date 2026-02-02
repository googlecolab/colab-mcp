import unittest
import os
import tempfile
import shutil
from unittest.mock import patch

from colab_mcp import auth


class NetrcTestCase(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()
        self.netrc_path = os.path.join(self.test_dir, ".netrc")

        # Patch _get_netrc_path to return our temp path
        self.patcher = patch(
            "colab_mcp.auth._get_netrc_path", return_value=self.netrc_path
        )
        self.mock_get_netrc_path = self.patcher.start()

    def tearDown(self):
        # Stop the patcher
        self.patcher.stop()
        # Remove the temporary directory
        shutil.rmtree(self.test_dir)


class TestAuthNetrcFunctions(NetrcTestCase):
    def test_save_and_read_refresh_token(self):
        """Test saving a token and then reading it back."""
        test_token = "fake-refresh-token-12345"

        # 1. Test reading when file doesn't exist
        self.assertIsNone(auth._read_refresh_token_from_netrc())

        # 2. Test saving the token
        auth._save_refresh_token_to_netrc(test_token)
        self.assertTrue(os.path.exists(self.netrc_path))

        # 3. Test reading the saved token
        read_token = auth._read_refresh_token_from_netrc()
        self.assertEqual(read_token, test_token)

        # Verify file content
        with open(self.netrc_path, "r") as f:
            content = f.read()
            self.assertIn(f"machine {auth.NETRC_MACHINE}", content)
            self.assertIn(f"login {auth.NETRC_LOGIN}", content)
            self.assertIn(f"password {test_token}", content)

    def test_remove_refresh_token(self):
        """Test removing a token from the .netrc file."""
        test_token = "another-fake-token"

        # 1. Save a token first
        auth._save_refresh_token_to_netrc(test_token)
        self.assertIsNotNone(auth._read_refresh_token_from_netrc())

        # 2. Remove the token
        auth._remove_refresh_token_from_netrc()

        # 3. Verify it's gone
        self.assertIsNone(auth._read_refresh_token_from_netrc())

        # Verify file content is now empty or doesn't contain the machine
        with open(self.netrc_path, "r") as f:
            content = f.read()
            self.assertNotIn(f"machine {auth.NETRC_MACHINE}", content)

    def test_save_preserves_other_entries(self):
        """Test that saving a token doesn't wipe other netrc entries."""
        other_machine = "another.service.com"
        other_login = "user"
        other_password = "password123"

        # 1. Create a .netrc file with another entry
        initial_content = f"machine {other_machine}\n\tlogin {other_login}\n\tpassword {other_password}\n"
        with open(self.netrc_path, "w") as f:
            f.write(initial_content)

        # 2. Save our refresh token
        test_token = "our-token"
        auth._save_refresh_token_to_netrc(test_token)

        # 3. Verify our token is there
        self.assertEqual(auth._read_refresh_token_from_netrc(), test_token)

        # 4. Verify the other entry is still there
        with open(self.netrc_path, "r") as f:
            content = f.read()
            self.assertIn(other_machine, content)
            self.assertIn(other_login, content)
            self.assertIn(other_password, content)


class TestGoogleOAuthClient(NetrcTestCase):
    @patch("colab_mcp.auth._save_refresh_token_to_netrc")
    @patch("colab_mcp.auth.InstalledAppFlow")
    @patch("colab_mcp.auth._read_refresh_token_from_netrc", return_value=None)
    def test_get_session_full_flow(self, mock_read_token, mock_flow, mock_save_token):
        """Test the full OAuth flow when no refresh token is present."""

        # Configure mocks
        mock_flow_instance = mock_flow.from_client_config.return_value
        mock_flow_instance.credentials.refresh_token = "new-refresh-token"
        mock_authorized_session = mock_flow_instance.authorized_session.return_value

        # Call the method
        session = auth.GoogleOAuthClient.get_session()

        # Assertions
        mock_read_token.assert_called_once()
        mock_flow.from_client_config.assert_called_once()
        mock_flow_instance.run_local_server.assert_called_once()
        mock_save_token.assert_called_once_with("new-refresh-token")
        self.assertEqual(session, mock_authorized_session)

    @patch("colab_mcp.auth.requests.AuthorizedSession")
    @patch("colab_mcp.auth.Credentials")
    @patch(
        "colab_mcp.auth._read_refresh_token_from_netrc", return_value="existing-token"
    )
    def test_get_session_with_valid_refresh_token(
        self, mock_read_token, mock_credentials, mock_auth_session
    ):
        """Test session retrieval with a valid refresh token from .netrc."""

        # Configure mocks
        mock_creds_instance = mock_credentials.return_value

        # Call the method
        session = auth.GoogleOAuthClient.get_session()

        # Assertions
        mock_read_token.assert_called_once()
        mock_credentials.assert_called_once()
        mock_creds_instance.refresh.assert_called_once()
        mock_auth_session.assert_called_once_with(mock_creds_instance)
        self.assertEqual(session, mock_auth_session.return_value)

    @patch("colab_mcp.auth._remove_refresh_token_from_netrc")
    @patch("colab_mcp.auth.InstalledAppFlow")
    @patch("colab_mcp.auth.Credentials")
    @patch(
        "colab_mcp.auth._read_refresh_token_from_netrc", return_value="invalid-token"
    )
    def test_get_session_with_invalid_refresh_token(
        self, mock_read_token, mock_credentials, mock_flow, mock_remove_token
    ):
        """Test fallback to full flow when refresh token is invalid."""

        # Configure mocks
        mock_creds_instance = mock_credentials.return_value
        mock_creds_instance.refresh.side_effect = Exception("Invalid token")
        mock_flow_instance = mock_flow.from_client_config.return_value
        mock_authorized_session = mock_flow_instance.authorized_session.return_value

        # Call the method
        session = auth.GoogleOAuthClient.get_session()

        # Assertions
        mock_read_token.assert_called_once()
        mock_credentials.assert_called_once()
        mock_creds_instance.refresh.assert_called_once()
        mock_remove_token.assert_called_once()
        mock_flow.from_client_config.assert_called_once()  # Fallback to full flow
        mock_flow_instance.run_local_server.assert_called_once()
        self.assertEqual(session, mock_authorized_session)


if __name__ == "__main__":
    unittest.main()
