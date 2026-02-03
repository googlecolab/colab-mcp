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
from unittest.mock import MagicMock, patch
import uuid
from dataclasses import dataclass


from colab_mcp.client import (
    Accelerator,
    AssignmentVariant,
    CcuInfo,
    ColabClient,
    ColabEnvironment,
    ListedAssignments,
    ListedAssignment,
    PostAssignmentResponse,
    Shape,
    SubscriptionState,
    SubscriptionTier,
    Variant,
    UserInfo,
)

COLAB_HOST = "https://colab.example.com"
GOOGLE_APIS_HOST = "https://colab.example.googleapis.com"
BEARER_TOKEN = "access-token"
NOTEBOOK_HASH = uuid.uuid4()

DEFAULT_ASSIGNMENT_RESPONSE = {
    "accelerator": Accelerator.A100,
    "endpoint": "mock-server",
    "fit": 30,
    "sub": SubscriptionState.UNSUBSCRIBED,
    "subTier": SubscriptionTier.NONE,
    "variant": AssignmentVariant.GPU,
    "machineShape": Shape.STANDARD,
    "runtimeProxyInfo": {
        "token": "mock-token",
        "tokenExpiresInSeconds": 42,
        "url": "https://mock-url.com",
    },
}


DEFAULT_LIST_ASSIGNMENTS_RESPONSE = ListedAssignments(
    assignments=[
        ListedAssignment(
            accelerator=DEFAULT_ASSIGNMENT_RESPONSE["accelerator"],
            endpoint=DEFAULT_ASSIGNMENT_RESPONSE["endpoint"],
            variant=DEFAULT_ASSIGNMENT_RESPONSE["variant"],
            machineShape=DEFAULT_ASSIGNMENT_RESPONSE["machineShape"],
            runtimeProxyInfo=DEFAULT_ASSIGNMENT_RESPONSE["runtimeProxyInfo"],
        )
    ]
)


DEFAULT_ASSIGNMENT = PostAssignmentResponse.model_validate(DEFAULT_ASSIGNMENT_RESPONSE)


def with_xssi(response):
    return f")]}}'\n{response}"


@dataclass
class ColabTestEnv(ColabEnvironment):
    domain: str = "https://localhost"
    api: str = "https://localhost"


class TestColabClient(unittest.TestCase):
    def setUp(self):
        self.session_mock = MagicMock()
        self.client = ColabClient(
            ColabTestEnv(COLAB_HOST, GOOGLE_APIS_HOST),
            self.session_mock,
        )

    @patch("colab_mcp.client.ColabClient._issue_request")
    def test_get_subscription_tier(self, mock_issue_request):
        mock_issue_request.return_value = UserInfo(
            subscriptionTier=SubscriptionTier.NONE
        )

        tier = self.client.get_subscription_tier()
        self.assertEqual(tier, SubscriptionTier.NONE)
        mock_issue_request.assert_called_once()

    @patch("colab_mcp.client.ColabClient._issue_request")
    def test_get_ccu_info(self, mock_issue_request):
        mock_response = CcuInfo(
            currentBalance=1,
            consumptionRateHourly=2,
            assignmentsCount=3,
        )
        mock_issue_request.return_value = mock_response

        ccu_info = self.client.get_ccu_info()
        self.assertEqual(ccu_info, mock_response)
        mock_issue_request.assert_called_once()

    @patch("colab_mcp.client.ColabClient._issue_request")
    def test_list_assignments(self, mock_issue_request):
        mock_issue_request.return_value = DEFAULT_LIST_ASSIGNMENTS_RESPONSE

        assignments = self.client.list_assignments()
        self.assertEqual(assignments, DEFAULT_LIST_ASSIGNMENTS_RESPONSE.assignments)
        mock_issue_request.assert_called_once()

    @patch("colab_mcp.client.ColabClient._post_assignment")
    @patch("colab_mcp.client.ColabClient._get_assignment")
    def test_assign_creates_new(self, mock_get_assignment, mock_post_assignment):
        mock_get_assignment.return_value = MagicMock(xsrf_token="mock-xsrf-token")
        mock_post_assignment.return_value = DEFAULT_ASSIGNMENT
        result = self.client.assign(NOTEBOOK_HASH, Variant.DEFAULT)
        self.assertEqual(result, DEFAULT_ASSIGNMENT)


if __name__ == "__main__":
    unittest.main()
