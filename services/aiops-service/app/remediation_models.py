from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RemediationAction(str, Enum):
    ACKNOWLEDGE_INCIDENT = "acknowledge_incident"
    NO_ACTION = "no_action"
    RERUN_DEPLOYMENT = "rerun_deployment"
    RESTART_DEPLOYMENT = "restart_deployment"
    SCALE_DEPLOYMENT = "scale_deployment"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"


class RemediationStatus(str, Enum):
    PROPOSED = "PROPOSED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class PolicyDecision(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    REQUIRES_APPROVAL = "requires_approval"


class RemediationPreviewRequest(BaseModel):
    action: RemediationAction
    target_deployment_id: str | None = None
    reason: str | None = None
    requested_by: str = Field(min_length=1, max_length=255)


class RemediationApprovalRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=255)


class RemediationRejectionRequest(BaseModel):
    rejected_by: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=2000)


class RemediationExecutionRequest(BaseModel):
    executed_by: str = Field(min_length=1, max_length=255)


class RemediationProposal(BaseModel):
    id: str
    incident_id: str
    action: RemediationAction
    status: RemediationStatus
    policy_decision: PolicyDecision
    policy_reason: str
    reason: str | None = None
    target_deployment_id: str | None = None
    proposed_by: str
    approved_by: str | None = None
    rejected_by: str | None = None
    rejection_reason: str | None = None
    execution_requested_by: str | None = None
    result: dict | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    executed_at: datetime | None = None


class RemediationResponse(BaseModel):
    incident_id: str
    available_actions: list[dict]
    proposals: list[RemediationProposal]


class RemediationPolicyResult(BaseModel):
    action: RemediationAction
    decision: PolicyDecision
    reason: str
    requires_human_approval: bool
    executable: bool
