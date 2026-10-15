"""Central configuration. Every value can be overridden via .env or environment vars."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./tracker.db"

    # LLM provider: "none" | "anthropic" | "deepseek"
    llm_provider: str = "none"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-flash"
    # Optional cheaper model for the complexity check — judging thirty lines of code does
    # not need the strongest model. Empty = use deepseek_model. Interview questions and
    # answer grading always use deepseek_model.
    deepseek_complexity_model: str = ""
    # Reasoning effort for the complexity check. "low" by default: at "high", flash once
    # spent all 16k output tokens thinking about a 20-line union-find and returned nothing.
    # Empty = use deepseek_reasoning_effort.
    deepseek_complexity_effort: str = "low"
    deepseek_base_url: str = "https://api.deepseek.com"
    # Thinking mode (DeepSeek's default is on). Reasoning tokens are billed as output.
    deepseek_thinking: bool = True
    deepseek_reasoning_effort: str = "high"     # low | high | max
    llm_timeout_seconds: int = 300              # thinking replies via a relay took up to ~160s

    # Which timezone defines "today". Empty means the machine's local zone, which is what
    # you want for a personal tracker: practising at 9pm should count towards that evening,
    # not towards tomorrow. Set e.g. TIMEZONE=America/Toronto to pin it.
    timezone: str = ""

    # "local": no login; everything belongs to one automatically created user. This is
    # the default and what start.sh runs. "github": sign in with GitHub, one account each.
    auth_mode: str = "local"
    # The address people open, without a trailing slash. Builds the OAuth callback URL,
    # decides whether cookies need Secure (https), and is the only Origin allowed to send
    # state-changing requests.
    public_base_url: str = "http://localhost:5173"
    # Signs session cookies. github mode refuses to start unless it's 32+ characters:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    session_secret: str = ""
    session_max_age_days: int = 30
    # A GitHub OAuth app whose callback is {public_base_url}/api/auth/callback/github
    github_client_id: str = ""
    github_client_secret: str = ""
    # This GitHub account is the owner: it uses the server's LLM key and sees its credit.
    owner_github_login: str = ""
    # github mode only: a "Try the demo" button that signs into a shared account with
    # generated history, rebuilt every 24 hours (app/demo.py).
    demo_enabled: bool = False

    daily_review_cap: int = 4         # max reviews per day
    daily_new_cap: int = 3            # max new problems per day
    # Interleaving: at most this many reviews per chapter / per primary pattern each day.
    # 0 disables the limit. Unused slots are always backfilled, so a limit never shrinks
    # the day — it only changes which problems fill it.
    daily_per_chapter_cap: int = 2
    daily_per_pattern_cap: int = 2
    # New problems follow the tier order strictly by default (0 = no limit). Raise these to
    # spread a day's new problems across chapters / patterns instead.
    daily_new_per_chapter_cap: int = 0
    daily_new_per_pattern_cap: int = 0
    # Hold every Hard back until the Easy/Medium problems are done — the same rule as the
    # manual study plan. Set to false when you are ready to start on Hards.
    new_hard_last: bool = True
    # Finish the NeetCode 150 before the Top Interview 150 problems that aren't in it,
    # which then follow LeetCode's study-plan order.
    new_neetcode150_first: bool = True
    # Chapters whose NeetCode 150 problems wait with the Top Interview 150 ones (CSV).
    # Default: Bit Manipulation (17) and Math & Geometry (18), which were left out of the
    # original study plan. They stay flagged as NeetCode 150 everywhere else.
    new_later_chapters: str = "17,18"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def new_later_chapter_set(self) -> frozenset[int]:
        return frozenset(int(c) for c in self.new_later_chapters.split(",") if c.strip())

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
