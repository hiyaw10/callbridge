from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db import Base


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    owner_email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    owner_phone: Mapped[str] = mapped_column(String(20))  # weekly summary text destination
    password_hash: Mapped[str] = mapped_column(String(255))
    twilio_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    plan_tier: Mapped[str] = mapped_column(String(20), default="starter")
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly")
    trial_ends_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # NULL means "use the default template" — see app/services/templates.py
    missed_call_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_request_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Forgot-password: single-use SMS code, cleared after use or when a new one is requested.
    password_reset_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    calls: Mapped[list["Call"]] = relationship(back_populates="business")
    text_messages: Mapped[list["TextMessage"]] = relationship(back_populates="business")
    jobs: Mapped[list["Job"]] = relationship(back_populates="business")

    __table_args__ = (
        CheckConstraint("plan_tier IN ('starter','growth','pro')", name="ck_business_plan_tier"),
        CheckConstraint("billing_cycle IN ('monthly','annual')", name="ck_business_billing_cycle"),
    )


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    caller_number: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))  # missed / answered
    twilio_call_sid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    business: Mapped["Business"] = relationship(back_populates="calls")
    text_messages: Mapped[list["TextMessage"]] = relationship(back_populates="call")

    __table_args__ = (
        CheckConstraint("status IN ('missed','answered')", name="ck_call_status"),
    )


class TextMessage(Base):
    __tablename__ = "text_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    call_id: Mapped[int | None] = mapped_column(ForeignKey("calls.id"), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(10))  # outbound / inbound
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))  # sent / delivered / failed
    twilio_message_sid: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    business: Mapped["Business"] = relationship(back_populates="text_messages")
    call: Mapped["Call | None"] = relationship(back_populates="text_messages")

    __table_args__ = (
        CheckConstraint("direction IN ('outbound','inbound')", name="ck_textmessage_direction"),
        CheckConstraint("status IN ('sent','delivered','failed')", name="ck_textmessage_status"),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    customer_phone: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)  # set when marked done; starts the 24h review-request countdown
    review_text_sent_at: Mapped[datetime | None] = mapped_column(nullable=True)

    business: Mapped["Business"] = relationship(back_populates="jobs")
