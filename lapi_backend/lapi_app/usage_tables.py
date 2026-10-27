"""Provider-reported token usage and versioned model prices (one row per model call).

Both tables are created by Base.metadata.create_all, so SQLite, PostgreSQL and
Oracle deployments get them without a separate migration. Identifiers are plain
strings, not foreign keys: usage history and price history outlive deleted
datasets, conversations, users and model registrations. Prices are decimal
strings so Decimal arithmetic stays exact on every database.
"""
import time
from sqlalchemy import String, Integer, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from . import core
from .database import timestamp_type


class TokenUsage(core.Base):
    __tablename__ = 'lapi_token_usage'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    created_at: Mapped[float] = mapped_column(timestamp_type(), default=time.time, index=True)
    owner_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    dataset_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    message_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    model_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    provider_model: Mapped[str | None] = mapped_column(String(250), nullable=True)
    protocol: Mapped[str | None] = mapped_column(String(40), nullable=True)
    stage: Mapped[str] = mapped_column(String(32), default='chat', index=True)
    # Normalized counts: input includes cache reads and writes; output includes
    # reasoning. NULL means the provider did not report the value.
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reported: Mapped[bool] = mapped_column(Boolean, default=False)
    parameters_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_version_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)


class ModelPrice(core.Base):
    __tablename__ = 'lapi_model_prices'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(80), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    # Price per 1M tokens, stored as exact decimal strings.
    input_price: Mapped[str] = mapped_column(String(40))
    cached_input_price: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cache_write_price: Mapped[str | None] = mapped_column(String(40), nullable=True)
    output_price: Mapped[str] = mapped_column(String(40))
    reasoning_price: Mapped[str | None] = mapped_column(String(40), nullable=True)
    effective_at: Mapped[float] = mapped_column(timestamp_type(), index=True)
    created_at: Mapped[float] = mapped_column(timestamp_type(), default=time.time)
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
