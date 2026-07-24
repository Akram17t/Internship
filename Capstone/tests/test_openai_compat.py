from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.openai_compat import (
    is_no_auth_9router_base_url,
    openai_client_kwargs,
    openai_request_kwargs,
    resolve_openai_compatible_api_key,
)


class OpenAICompatTests(unittest.TestCase):
    def test_detects_local_and_compose_9router_urls_as_no_auth(self) -> None:
        self.assertTrue(is_no_auth_9router_base_url("http://localhost:20128/v1"))
        self.assertTrue(is_no_auth_9router_base_url("http://9router:20129/v1"))
        self.assertFalse(is_no_auth_9router_base_url("https://api.openai.com/v1"))

    def test_detects_configured_no_auth_base_url(self) -> None:
        with patch.dict(
            os.environ,
            {"OPENAI_COMPAT_NO_AUTH_BASE_URLS": "http://127.0.0.1:45678/v1"},
            clear=True,
        ):
            self.assertTrue(is_no_auth_9router_base_url("http://127.0.0.1:45678/v1"))

    def test_no_auth_9router_ignores_global_openai_key_when_primary_key_is_blank(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CHAT_API_KEY": "",
                "OPENAI_API_KEY": "wrong-global-key",
            },
            clear=True,
        ):
            api_key = resolve_openai_compatible_api_key(
                base_url="http://9router:20129/v1",
                primary_env="CHAT_API_KEY",
                fallback_envs=("OPENAI_API_KEY",),
            )

        self.assertEqual(api_key, "")

    def test_non_9router_provider_uses_fallback_key(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CHAT_API_KEY": "",
                "OPENAI_API_KEY": "external-provider-key",
            },
            clear=True,
        ):
            api_key = resolve_openai_compatible_api_key(
                base_url="https://api.openai.com/v1",
                primary_env="CHAT_API_KEY",
                fallback_envs=("OPENAI_API_KEY",),
            )

        self.assertEqual(api_key, "external-provider-key")

    def test_no_auth_client_kwargs_disable_openai_sdk_credential_enforcement(self) -> None:
        from openai import Omit

        kwargs = openai_client_kwargs(
            api_key="",
            base_url="http://localhost:20128/v1",
            timeout=240,
        )

        self.assertEqual(kwargs["api_key"], "")
        self.assertFalse(kwargs["_enforce_credentials"])
        self.assertIsInstance(kwargs["default_headers"]["Authorization"], Omit)

    def test_no_auth_request_kwargs_omit_authorization_header(self) -> None:
        from openai import Omit

        kwargs = openai_request_kwargs(
            api_key="",
            base_url="http://9router:20129/v1",
        )

        self.assertIsInstance(kwargs["extra_headers"]["Authorization"], Omit)

    def test_authenticated_provider_does_not_omit_authorization_header(self) -> None:
        kwargs = openai_request_kwargs(
            api_key="external-provider-key",
            base_url="https://api.openai.com/v1",
        )

        self.assertEqual(kwargs, {})


if __name__ == "__main__":
    unittest.main()
