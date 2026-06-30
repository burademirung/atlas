from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str
    redis_url: str
    jwt_secret: str

    jwt_issuer: str = "atlas"
    jwt_audience: str = "atlas-api"
    jwt_algorithm: str = "HS256"
    access_ttl_seconds: int = 600
    refresh_ttl_seconds: int = 1_209_600  # 14 days

    argon2_memory_kib: int = 19_456
    argon2_time_cost: int = 2
    argon2_parallelism: int = 1

    environment: str = "dev"

    # Agentic AI (LangGraph + Claude) ---------------------------------------
    anthropic_api_key: str | None = None
    tavily_api_key: str | None = None
    research_model: str = "claude-opus-4-8"
    max_subquestions: int = 4
    max_sources_per_q: int = 3

    # Denial-of-wallet guardrails (OWASP LLM10: Unbounded Consumption) -------
    # A global kill-switch: when true every POST /v1/runs returns 503 so a
    # runaway client or upstream incident can be contained without a redeploy.
    service_paused: bool = False
    # Per-run output budget handed to the model and a cumulative token ceiling
    # enforced across graph supersteps; a run that exceeds it is truncated.
    max_output_tokens: int = 4096
    max_run_tokens: int = 50_000
    # Hard cap on the number of search/tool calls a single run may fan out to.
    max_tool_calls: int = 12
    # Daily run quotas, enforced per authenticated user and per source IP.
    daily_run_quota: int = 50
    daily_run_quota_ip: int = 200
    # How long an Idempotency-Key dedupes repeat POST /v1/runs submissions.
    idempotency_ttl_seconds: int = 86_400
    # Number of *trusted* reverse proxies that append to X-Forwarded-For (e.g. the
    # ALB = 1). The client IP is read as the Nth value from the right; left-most
    # entries are attacker-controlled and MUST NOT be trusted. 0 => ignore XFF
    # entirely and use the socket peer (request.client.host).
    trusted_proxy_count: int = 1

    # Observability (OpenTelemetry GenAI semconv + Prometheus) ---------------
    # Traces/metrics are exported only when this OTLP endpoint is configured;
    # otherwise the OTel SDK stays a no-op so nothing breaks offline/in tests.
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "atlas-api"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
