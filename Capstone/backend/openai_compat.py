from __future__ import annotations

from urllib.parse import urlparse

from backend.settings import get_env


NO_AUTH_9ROUTER_HOSTS = {
    "localhost:20128",
    "127.0.0.1:20128",
    "localhost:20129",
    "127.0.0.1:20129",
    "9router:20128",
    "9router:20129",
}


def is_no_auth_9router_base_url(base_url: str) -> bool:
    parsed = urlparse(str(base_url).rstrip("/"))
    host = parsed.netloc.lower()
    configured_urls = {
        item.strip().rstrip("/")
        for item in get_env("OPENAI_COMPAT_NO_AUTH_BASE_URLS", "").split(",")
        if item.strip()
    }
    if str(base_url).strip().rstrip("/") in configured_urls:
        return True
    return parsed.scheme in {"http", "https"} and host in NO_AUTH_9ROUTER_HOSTS


def first_env_value(names: tuple[str, ...]) -> str:
    for env_name in names:
        value = get_env(env_name, "")
        if value:
            return value
    return ""


def resolve_openai_compatible_api_key(
    *,
    base_url: str,
    primary_env: str,
    fallback_envs: tuple[str, ...],
) -> str:
    primary_value = get_env(primary_env, "")
    if primary_value:
        return primary_value
    if is_no_auth_9router_base_url(base_url):
        return ""
    return first_env_value(fallback_envs)


def openai_client_kwargs(
    *,
    api_key: str,
    base_url: str,
    timeout: int,
) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "api_key": api_key,
        "base_url": base_url,
        "timeout": timeout,
    }
    if not api_key and is_no_auth_9router_base_url(base_url):
        from openai import Omit

        kwargs["default_headers"] = {"Authorization": Omit()}
        kwargs["_enforce_credentials"] = False
    return kwargs


def openai_request_kwargs(*, api_key: str, base_url: str) -> dict[str, object]:
    if api_key or not is_no_auth_9router_base_url(base_url):
        return {}

    from openai import Omit

    return {"extra_headers": {"Authorization": Omit()}}
