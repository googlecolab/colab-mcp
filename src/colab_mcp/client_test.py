import json
import unittest
from unittest.mock import MagicMock, patch


from colab_mcp.client import CcuInfo, ColabClient, SubscriptionTier

COLAB_HOST = "https://colab.example.com"
GOOGLE_APIS_HOST = "https://colab.example.googleapis.com"
BEARER_TOKEN = "access-token"


def with_xssi(response):
    return f")]}}'\n{response}"


class TestColabClient(unittest.TestCase):
    def setUp(self):
        self.session_mock = MagicMock()
        self.session_mock.get.return_value = BEARER_TOKEN
        self.client = ColabClient(
            colab_domain=COLAB_HOST,
            colab_api_domain=GOOGLE_APIS_HOST,
            get_access_token=self.session_mock.get,
        )

    @patch("requests.Session.request")
    def test_get_subscription_tier(self, mock_request):
        mock_response = {
            "subscriptionTier": "SUBSCRIPTION_TIER_NONE",
            "paidComputeUnitsBalance": 0,
        }
        mock_request.return_value.ok = True
        mock_request.return_value.text = with_xssi(json.dumps(mock_response))

        tier = self.client.get_subscription_tier()
        self.assertEqual(tier, SubscriptionTier.NONE)
        mock_request.assert_called_once()

    @patch("requests.Session.request")
    def test_get_ccu_info(self, mock_request):
        mock_response = {
            "currentBalance": 1,
            "consumptionRateHourly": 2,
            "assignmentsCount": 3,
        }
        mock_request.return_value.ok = True
        mock_request.return_value.text = with_xssi(json.dumps(mock_response))

        ccu_info = self.client.get_ccu_info()
        self.assertEqual(ccu_info, CcuInfo(**mock_response))
        mock_request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
