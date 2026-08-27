"""M8 request/response schemas. Extra request fields are forbidden."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class DecideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str
    failure_type: str
    amount: float
    attempt_number: int
    risk_score: float
    contact_fatigue: float
    hours_since_failure: float
    current_discount_percent: float
    customer_segment: Literal["b2c_new", "b2c_returning", "b2b"]
    already_recovered: bool

    customer_name: Optional[str] = None
    communication_channel: Optional[Literal["email", "sms", "whatsapp", "none"]] = None
    payment_link_url: Optional[str] = None


class CommunicationOut(BaseModel):
    sendable: bool
    channel: Optional[str] = None
    message_body: Optional[str] = None
    fallback_used: bool


class DecideResponse(BaseModel):
    transaction_id: str
    trace_id: Optional[str] = None
    selected_action: str
    decision_type: str
    decision_reason: str
    escalation_required: bool
    terminal: bool
    selected_ev: Optional[float] = None
    selected_probability: Optional[float] = None
    policy_version: str
    communication: CommunicationOut


class HealthResponse(BaseModel):
    status: str


class AuditRecordOut(BaseModel):
    trace_id: str
    timestamp: str
    transaction_id: str
    selected_action: str
    decision_type: str
    decision_reason: str
    policy_version: str
    model_version: str
    decision_engine_version: str
    rules_fired: list
    escalation_required: bool
    terminal: bool
    selected_ev: Optional[float] = None
    selected_probability: Optional[float] = None
    m6_sendable: bool
    m6_channel: Optional[str] = None
    m6_fallback_used: bool


class AuditLookupResponse(BaseModel):
    transaction_id: str
    records: list[AuditRecordOut] = Field(default_factory=list)
