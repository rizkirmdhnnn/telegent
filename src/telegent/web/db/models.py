"""Model ORM untuk seluruh data web panel (spesifikasi §5)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from telegent.web.db.base import Base, utcnow


class TimestampMixin:
    """Kolom waktu yang diisi otomatis."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class AdminUser(TimestampMixin, Base):
    """Akun admin tunggal (single-tenant)."""

    __tablename__ = "admin_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    totp_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locale: Mapped[str] = mapped_column(String(8), default="id", nullable=False)
    theme: Mapped[str] = mapped_column(String(16), default="system", nullable=False)


class AppSetting(TimestampMixin, Base):
    """Satu baris per setting; `value` berupa JSON (atau ciphertext bila secret)."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TelegramAccount(TimestampMixin, Base):
    """Akun Telegram yang dipakai bot (satu baris aktif)."""

    __tablename__ = "telegram_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tg_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tg_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tg_first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: Nama sesi (`*.session`) yang dipakai saat login berhasil; dipakai untuk
    #: mendeteksi perubahan `telegram_session_name` setelah login (butuh login ulang).
    session_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="not_configured", nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    logged_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LoginFlow(Base):
    """State sementara proses login Telegram (dibersihkan berkala)."""

    __tablename__ = "login_flow"

    # `autoincrement` → SQLite memakai AUTOINCREMENT sehingga id tidak pernah
    # dipakai ulang setelah flow dihapus; `flow_id` dari API selalu unik.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    phone_code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="code_sent", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (Index("ix_login_flow_expires_at", "expires_at"),)


class CallRecord(TimestampMixin, Base):
    """Satu baris per panggilan (diterima maupun ditolak)."""

    __tablename__ = "call_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_call_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_display: Mapped[str | None] = mapped_column(String(128), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    end_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transcript_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    transcripts: Mapped[list[TranscriptEntry]] = relationship(
        back_populates="call", cascade="all, delete-orphan", passive_deletes=True
    )
    tool_calls: Mapped[list[ToolCallRecord]] = relationship(
        back_populates="call", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_call_record_tg_call_id", "tg_call_id"),
        Index("ix_call_record_user_id", "user_id"),
        Index("ix_call_record_started_at", "started_at"),
        Index("ix_call_record_outcome", "outcome"),
    )


class TranscriptEntry(Base):
    """Baris transkrip (penelpon atau AI)."""

    __tablename__ = "transcript_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_record_id: Mapped[int] = mapped_column(
        ForeignKey("call_record.id", ondelete="CASCADE"), nullable=False
    )
    speaker: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    call: Mapped[CallRecord] = relationship(back_populates="transcripts")

    __table_args__ = (Index("ix_transcript_entry_call_record_id", "call_record_id"),)


class ToolCallRecord(Base):
    """Riwayat pemanggilan tool AI."""

    __tablename__ = "tool_call_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_record_id: Mapped[int] = mapped_column(
        ForeignKey("call_record.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    args_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ok", nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    call: Mapped[CallRecord] = relationship(back_populates="tool_calls")

    __table_args__ = (Index("ix_tool_call_record_call_record_id", "call_record_id"),)


class ToolConfig(TimestampMixin, Base):
    """Konfigurasi per tool bawaan (aktif/nonaktif + parameter)."""

    __tablename__ = "tool_config"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    """Jejak perubahan konfigurasi & aksi administratif."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str | None] = mapped_column(String(128), nullable=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_audit_log_at", "at"),
        Index("ix_audit_log_action", "action"),
    )