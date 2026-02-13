# Copyright 2026 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
import os
import tempfile
from unittest.mock import patch, MagicMock, mock_open

from colab_mcp import auth


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.token_path = os.path.join(self.test_dir, "token.json")
        self.config_path = "client_secrets.json"

        # Patch TOKEN_CONFIG_PATH to use our temp path
        self.patcher = patch("colab_mcp.auth.TOKEN_CONFIG_PATH", self.token_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        if os.path.exists(self.test_dir):
            import shutil

            shutil.rmtree(self.test_dir)

    @patch("colab_mcp.auth.Credentials")
    @patch("colab_mcp.auth.requests.AuthorizedSession")
    @patch("os.path.exists")
    def test_get_credentials_valid_existing_token(
        self, mock_exists, mock_session, mock_creds
    ):
        """Test getting credentials when a valid token already exists."""
        mock_exists.return_value = True

        mock_creds_instance = MagicMock()
        mock_creds_instance.valid = True
        mock_creds.from_authorized_user_file.return_value = mock_creds_instance

        session = auth.get_credentials(self.config_path)

        mock_creds.from_authorized_user_file.assert_called_once_with(
            self.token_path, auth.SCOPES
        )
        mock_session.assert_called_once_with(mock_creds_instance)
        self.assertEqual(session, mock_session.return_value)

    @patch("colab_mcp.auth.Request")
    @patch("colab_mcp.auth.Credentials")
    @patch("colab_mcp.auth.requests.AuthorizedSession")
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_get_credentials_expired_token_with_refresh(
        self, mock_file, mock_exists, mock_session, mock_creds, mock_request
    ):
        """Test getting credentials when token is expired but has a refresh token."""
        mock_exists.return_value = True

        mock_creds_instance = MagicMock()
        mock_creds_instance.valid = False
        mock_creds_instance.expired = True
        mock_creds_instance.refresh_token = "some_refresh_token"
        mock_creds_instance.to_json.return_value = '{"token": "new_json"}'
        mock_creds.from_authorized_user_file.return_value = mock_creds_instance

        session = auth.get_credentials(self.config_path)

        mock_creds_instance.refresh.assert_called_once()
        mock_file.assert_called_with(self.token_path, "w")
        mock_session.assert_called_once_with(mock_creds_instance)
        self.assertEqual(session, mock_session.return_value)

    @patch("colab_mcp.auth.InstalledAppFlow")
    @patch("colab_mcp.auth.requests.AuthorizedSession")
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_get_credentials_no_token_full_flow(
        self, mock_file, mock_exists, mock_session, mock_flow
    ):
        """Test getting credentials when no token exists (full OAuth flow)."""
        mock_exists.return_value = False

        mock_flow_instance = MagicMock()
        mock_creds_instance = MagicMock()
        mock_creds_instance.to_json.return_value = '{"token": "new_json"}'
        mock_flow_instance.run_local_server.return_value = mock_creds_instance
        mock_flow.from_client_secrets_file.return_value = mock_flow_instance

        session = auth.get_credentials(self.config_path)

        mock_flow.from_client_secrets_file.assert_called_once_with(
            self.config_path, auth.SCOPES
        )
        mock_flow_instance.run_local_server.assert_called_once()
        mock_file.assert_called_with(self.token_path, "w")
        mock_session.assert_called_once_with(mock_creds_instance)
        self.assertEqual(session, mock_session.return_value)


if __name__ == "__main__":
    unittest.main()
