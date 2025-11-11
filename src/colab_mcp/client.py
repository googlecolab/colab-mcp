import json
import logging
from enum import Enum
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse

import requests
from pydantic import BaseModel, Field, TypeAdapter

# From src/colab/headers.ts
ACCEPT_JSON_HEADER = {"key": "Accept", "value": "application/json"}
AUTHORIZATION_HEADER = {"key": "Authorization", "value": ""}
COLAB_CLIENT_AGENT_HEADER = {
    "key": "X-Goog-Colab-Client-Agent",
    "value": "python-colab-client",
}


class SubscriptionTier(str, Enum):
    NONE = "SUBSCRIPTION_TIER_NONE"
    PAY_AS_YOU_GO = "SUBSCRIPTION_TIER_PAY_AS_YOU_GO"
    COLAB_PRO = "SUBSCRIPTION_TIER_PRO"
    COLAB_PRO_PLUS = "SUBSCRIPTION_TIER_PRO_PLUS"


class SubscriptionState(str, Enum):
    SUBSCRIBED = "SUBSCRIBED"
    UNSUBSCRIBED = "UNSUBSCRIBED"


class CcuInfo(BaseModel):
    current_balance: float = Field(..., alias="currentBalance")
    consumption_rate_hourly: float = Field(..., alias="consumptionRateHourly")
    assignments_count: int = Field(..., alias="assignmentsCount")


class UserInfo(BaseModel):
    subscription_tier: SubscriptionTier = Field(..., alias="subscriptionTier")


XSSI_PREFIX = ")]}'\n"
TUN_ENDPOINT = "/tun/m"


class InvalidSchemaError(Exception):
    """Raised if the given schema for the request is invalid/missing."""


class ColabRequestError(Exception):
    def __init__(self, message, request, response, response_body=None):
        super().__init__(message)
        self.request = request
        self.response = response
        self.response_body = response_body


class ColabClient:
    def __init__(
        self, colab_domain: str, colab_api_domain: str, get_access_token, logger=None
    ):
        self.colab_domain = colab_domain
        self.colab_api_domain = colab_api_domain
        self.get_access_token = get_access_token
        self.session = requests.Session()
        if "localhost" in self.colab_domain:
            self.session.verify = False
        self.logger = logger or logging.getLogger(__name__)

    def _strip_xssi_prefix(self, v: str) -> str:
        if not v.startswith(XSSI_PREFIX):
            self.logger.debug(f"XSSI prefix not found in response: {v}")
            return v
        stripped_v = v[len(XSSI_PREFIX) :]
        self.logger.debug(f"Stripped XSSI prefix, returning: {stripped_v}")
        return stripped_v

    def _issue_request(
        self,
        endpoint: str,
        method: str = "GET",
        headers: Dict[str, str] = None,
        params: Dict[str, str] = None,
        schema: Optional[BaseModel] = None,
        **kwargs,
    ):
        if not schema:
            raise InvalidSchemaError()

        parsed_endpoint = urlparse(endpoint)
        if parsed_endpoint.hostname in urlparse(self.colab_domain).hostname:
            if params is None:
                params = {}
            params["authuser"] = "0"

        token = self.get_access_token()
        request_headers = headers.copy() if headers else {}
        request_headers[ACCEPT_JSON_HEADER["key"]] = ACCEPT_JSON_HEADER["value"]
        request_headers[AUTHORIZATION_HEADER["key"]] = f"Bearer {token}"
        request_headers[COLAB_CLIENT_AGENT_HEADER["key"]] = COLAB_CLIENT_AGENT_HEADER[
            "value"
        ]

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"Request: {method} {endpoint}")
            self.logger.debug(f"Headers: {request_headers}")
            self.logger.debug(f"Params: {params}")

        response = self.session.request(
            method, endpoint, headers=request_headers, params=params, **kwargs
        )

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"Response: {response.status_code} {response.reason}")
            self.logger.debug(f"Response Body: {response.text}")

        if not response.ok:
            raise ColabRequestError(
                f"Failed to issue request {method} {endpoint}: {response.reason}",
                request=response.request,
                response=response,
                response_body=response.text,
            )

        body = self._strip_xssi_prefix(response.text)
        if not body:
            return
        return TypeAdapter(schema).validate_python(json.loads(body))

    def get_subscription_tier(self) -> SubscriptionTier:
        url = urljoin(self.colab_api_domain, "v1/user-info")
        user_info = self._issue_request(url, schema=UserInfo)
        return user_info.subscription_tier

    def get_ccu_info(self) -> CcuInfo:
        url = urljoin(self.colab_domain, f"{TUN_ENDPOINT}/ccu-info")
        return self._issue_request(url, schema=CcuInfo)
