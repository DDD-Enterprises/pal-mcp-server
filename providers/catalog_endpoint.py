"""Fixed upstream endpoints that accept OpenAI-compatible chat completions."""

from utils.env import get_env

from .openai_compatible import OpenAICompatibleProvider
from .registries.base import CapabilityModelRegistry
from .shared import ProviderType


class CatalogEndpointProvider(OpenAICompatibleProvider):
    """Resolve only names and aliases present in the endpoint's own catalog."""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, base_url=self.BASE_URL, **kwargs)
        self.registry = CapabilityModelRegistry(
            env_var_name=f"{self.PROVIDER.value.upper()}_MODELS_CONFIG_PATH",
            default_filename=f"{self.PROVIDER.value}_models.json",
            provider=self.PROVIDER,
            friendly_prefix="{model}",
        )
        if not self.registry.model_map:
            raise ValueError(f"Empty model catalog for {self.FRIENDLY_NAME}")

    def get_provider_type(self):
        return self.PROVIDER

    def get_all_model_capabilities(self):
        return self.registry.model_map

    def _resolve_model_name(self, model_name: str) -> str:
        entry = self.registry.resolve(model_name)
        return entry.model_name if entry else model_name


class CheaperInferenceProvider(CatalogEndpointProvider):
    PROVIDER = ProviderType.CHEAPERINFERENCE
    FRIENDLY_NAME = "CheaperInference"
    BASE_URL = "https://api.cheaperinference.com/v1"

    def get_preferred_model(self, category, allowed_models):
        return "gpt-6-luna" if "gpt-6-luna" in allowed_models else None


class AnthropicProvider(CatalogEndpointProvider):
    PROVIDER = ProviderType.ANTHROPIC
    FRIENDLY_NAME = "Anthropic"
    BASE_URL = "https://api.anthropic.com/v1"

    def __init__(self, api_key: str, **kwargs):
        workspace = get_env("ANTHROPIC_WORKSPACE_ID")
        if workspace:
            self.DEFAULT_HEADERS = {"anthropic-workspace-id": workspace}
        super().__init__(api_key, **kwargs)
