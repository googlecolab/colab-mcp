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


import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.transport import requests

OAUTH_SERVER_PORT = 53919

SCOPES = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/colaboratory",
    "openid",
]

TOKEN_CONFIG_PATH = os.path.expanduser("~/.colab-mcp-auth-token.json")


def get_credentials(config):
    creds = None
    if os.path.exists(TOKEN_CONFIG_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_CONFIG_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(config, SCOPES)
            creds = flow.run_local_server(port=OAUTH_SERVER_PORT)

        with open(TOKEN_CONFIG_PATH, "w") as token:
            token.write(creds.to_json())

    return requests.AuthorizedSession(creds)
