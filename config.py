"""Configuration + lazy client construction.

Nothing here touches the network at import time, so ``import config`` is safe
in the offline smoke test. The Foundry/Claude model and the Azure clients are
built only when first requested.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _load_dotenv(path: str = ".env") -> None:
    """Load KEY=VALUE pairs from a local .env into os.environ.

    Tiny, dependency-free, and non-destructive: a variable already set in the
    real environment (e.g. injected by Docker or the shell) always wins.
    """
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            # Skip empty values — setting e.g. AZURE_CLIENT_ID="" breaks
            # DefaultAzureCredential's discovery chain.
            if key and value and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

# Self-heal retry cap (Validator).
RETRY_CAP = 3


def mock_mode() -> bool:
    """When MOCK=true, Azure writes go to a local mock_tenant/ folder and the
    pipeline run is simulated. OFF by default — real Azure is the primary path."""
    return os.environ.get("MOCK", "").strip().lower() in {"1", "true", "yes", "on"}


# Local "tenant" used only in MOCK mode.
MOCK_TENANT_DIR = os.environ.get("MOCK_TENANT_DIR", "mock_tenant")


# --------------------------------------------------------------------------- #
# Foundry / Claude
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FoundryConfig:
    api_key: str
    model: str
    resource: "str | None" = None     # e.g. 'agent-pipeline-resource'
    base_url: "str | None" = None      # full Anthropic-compatible base URL
    api_version: "str | None" = None

    @classmethod
    def from_env(cls) -> "FoundryConfig":
        api_key = os.environ.get("FOUNDRY_API_KEY")
        base_url = os.environ.get("FOUNDRY_BASE_URL")
        resource = os.environ.get("FOUNDRY_RESOURCE")
        model = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")
        api_version = os.environ.get("FOUNDRY_API_VERSION")

        # Need an endpoint (base_url or resource). The key is required only for
        # api-key auth; Entra ID auth (az login / Managed Identity) needs no key.
        if not (base_url or resource):
            raise RuntimeError(
                "Set FOUNDRY_BASE_URL (or FOUNDRY_RESOURCE) to call Claude via "
                "Azure AI Foundry."
            )

        # Derive the Foundry resource name from a *.services.ai.azure.com host so
        # users can paste the endpoint shown in the portal without trimming it.
        if resource is None and base_url:
            from urllib.parse import urlparse

            host = urlparse(base_url).netloc
            if host.endswith(".services.ai.azure.com"):
                resource = host.split(".")[0]
        return cls(
            api_key=api_key,
            model=model,
            resource=resource,
            base_url=base_url,
            api_version=api_version,
        )


def _foundry_auth_mode() -> str:
    """'entra' (Microsoft Entra ID / az login / Managed Identity) or 'key'.

    Azure AI Foundry projects authenticate model inference with Entra ID by
    default; the 'project API key' does NOT authorize the /anthropic data plane.
    Default to Entra when FOUNDRY_API_KEY is absent; force with FOUNDRY_AUTH.
    """
    mode = os.environ.get("FOUNDRY_AUTH", "").strip().lower()
    if mode in {"entra", "aad", "azure"}:
        return "entra"
    if mode in {"key", "apikey", "api_key"}:
        return "key"
    return "key" if os.environ.get("FOUNDRY_API_KEY") else "entra"


def _entra_token_provider():
    """Async bearer-token provider over DefaultAzureCredential for the
    Cognitive Services data plane. One credential instance, refreshed per call
    (the SDK caches the token until near expiry)."""
    from azure.identity.aio import DefaultAzureCredential

    scope = os.environ.get(
        "FOUNDRY_SCOPE", "https://cognitiveservices.azure.com/.default"
    )
    credential = DefaultAzureCredential()

    async def provider() -> str:
        token = await credential.get_token(scope)
        return token.token

    return provider


def _anthropic_base_url(cfg: "FoundryConfig") -> str:
    """The Anthropic-compatible endpoint root (the SDK appends /v1/messages).

    For an Azure AI Foundry resource this is https://<resource>.services.ai.
    azure.com/anthropic. If a full base_url was given that already targets a
    non-Azure endpoint, it is used as-is.
    """
    if cfg.resource:
        return f"https://{cfg.resource}.services.ai.azure.com/anthropic"
    return (cfg.base_url or "").rstrip("/")


def _build_anthropic_client(cfg: "FoundryConfig"):
    """Return an async Anthropic client wired for the configured endpoint.

    * Entra ID auth -> AsyncAnthropicFoundry(resource=...) with a token provider.
    * API-key auth  -> plain AsyncAnthropic(base_url=.../anthropic), which sends
      the ``x-api-key`` header the Foundry /anthropic route expects.
    """
    default_query = {"api-version": cfg.api_version} if cfg.api_version else None

    if _foundry_auth_mode() == "entra" and cfg.resource:
        from anthropic import AsyncAnthropicFoundry

        kwargs: dict = {
            "resource": cfg.resource,
            "azure_ad_token_provider": _entra_token_provider(),
        }
        if default_query:
            kwargs["default_query"] = default_query
        return AsyncAnthropicFoundry(**kwargs)

    from anthropic import AsyncAnthropic

    kwargs = {"base_url": _anthropic_base_url(cfg), "api_key": cfg.api_key}
    if default_query:
        kwargs["default_query"] = default_query
    return AsyncAnthropic(**kwargs)


def get_claude_model():
    """Build a Pydantic AI model backed by Claude on Azure AI Foundry.

    The key/endpoint are read from the environment, never hardcoded.
    """
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    cfg = FoundryConfig.from_env()
    client = _build_anthropic_client(cfg)
    return AnthropicModel(cfg.model, provider=AnthropicProvider(anthropic_client=client))


# --------------------------------------------------------------------------- #
# Azure
# --------------------------------------------------------------------------- #


def storage_kind() -> str:
    """'blob' (plain Azure Blob, no hierarchical namespace) or 'adls' (Data Lake
    Gen2, HNS on). Set STORAGE_KIND explicitly, or it's inferred from the account
    URL host (.blob -> blob, .dfs -> adls). Default: adls."""
    k = os.environ.get("STORAGE_KIND", "").strip().lower()
    if k in {"blob", "azureblob", "blobstorage"}:
        return "blob"
    if k in {"adls", "adls_gen2", "gen2", "datalake"}:
        return "adls"
    return "blob" if ".blob." in os.environ.get("ADLS_ACCOUNT_URL", "") else "adls"


def blob_endpoint(account_name: str) -> str:
    return f"https://{account_name}.blob.core.windows.net"


def dfs_endpoint(account_name: str) -> str:
    return f"https://{account_name}.dfs.core.windows.net"


@dataclass(frozen=True)
class AzureConfig:
    subscription_id: str
    resource_group: str
    factory_name: str          # the Data Factory
    adls_account_name: str
    adls_account_url: str      # https://<acct>.dfs(or blob).core.windows.net
    location: str = "eastus"

    @property
    def store_endpoint(self) -> str:
        """The endpoint ADF/the SDK should use, matching storage_kind()."""
        return (
            blob_endpoint(self.adls_account_name)
            if storage_kind() == "blob"
            else dfs_endpoint(self.adls_account_name)
        )

    @classmethod
    def from_env(cls) -> "AzureConfig":
        def need(key: str) -> str:
            val = os.environ.get(key)
            if not val:
                raise RuntimeError(f"Environment variable {key} is required for deploy.")
            return val

        account = need("ADLS_ACCOUNT_NAME")
        default_url = (
            blob_endpoint(account) if storage_kind() == "blob" else dfs_endpoint(account)
        )
        return cls(
            subscription_id=need("AZURE_SUBSCRIPTION_ID"),
            resource_group=need("AZURE_RESOURCE_GROUP"),
            factory_name=need("ADF_FACTORY_NAME"),
            adls_account_name=account,
            adls_account_url=os.environ.get("ADLS_ACCOUNT_URL", default_url),
            location=os.environ.get("AZURE_LOCATION", "eastus"),
        )


def get_credential():
    """DefaultAzureCredential — works with Managed Identity in Azure and with
    az-cli / env credentials locally. No account keys anywhere."""
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


def get_datafactory_client(cfg: "AzureConfig | None" = None):
    from azure.mgmt.datafactory import DataFactoryManagementClient

    cfg = cfg or AzureConfig.from_env()
    return DataFactoryManagementClient(get_credential(), cfg.subscription_id)


def get_datalake_client(cfg: "AzureConfig | None" = None):
    from azure.storage.filedatalake import DataLakeServiceClient

    cfg = cfg or AzureConfig.from_env()
    # Derive the endpoint from the account name + storage_kind (via store_endpoint)
    # so a stale/mismatched ADLS_ACCOUNT_URL (e.g. a .blob URL left in the field)
    # can never point the Gen2 client at the wrong endpoint. Mirrors the blob client.
    return DataLakeServiceClient(account_url=cfg.store_endpoint, credential=get_credential())


def get_blob_service_client(cfg: "AzureConfig | None" = None):
    """Blob client for plain (non-HNS) Azure Storage. Managed Identity, no keys."""
    from azure.storage.blob import BlobServiceClient

    cfg = cfg or AzureConfig.from_env()
    return BlobServiceClient(account_url=blob_endpoint(cfg.adls_account_name), credential=get_credential())
