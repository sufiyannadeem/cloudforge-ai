from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict, computed_field


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
    VERIFYING = "VERIFYING"
    EXPIRED = "EXPIRED"


class PolicyDecision(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    REQUIRES_APPROVAL = "requires_approval"


class RemediationPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: RemediationAction
    target_deployment_id: str | None = None
    reason: str | None = Field(default=None, max_length=2000)
    requested_by: str = Field(min_length=1, max_length=255)


class RemediationApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)
    expected_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_by: str = Field(min_length=1, max_length=255)


class RemediationRejectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rejected_by: str = Field(min_length=1, max_length=255)
    reason: str | None = Field(default=None, max_length=2000)


class RemediationExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    executed_by: str = Field(min_length=1, max_length=255)
    idempotency_key: str = Field(min_length=8, max_length=255)


class RemediationProposal(BaseModel):
    recommendation_version: int = 0
    project_id: str | None = None
    resource_scope: str | None = None
    action_fingerprint: str | None = None
    alternative_of: str | None = None
    parameters: dict = Field(default_factory=dict)
    state_snapshot: dict | None = None
    approved_role: str | None = None
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
    expires_at: datetime | None = None
    verification_started_at: datetime | None = None
    verified_at: datetime | None = None
    verification_result: dict | None = None
    execution_idempotency_key: str | None = None

    @computed_field
    @property
    def recommendation_kind(self) -> str:
        if self.action == RemediationAction.ACKNOWLEDGE_INCIDENT:return 'acknowledgement'
        if self.action == RemediationAction.NO_ACTION:return 'investigation'
        return 'infrastructure_remediation'

    @computed_field
    @property
    def execution_supported(self) -> bool:
        return self.action in {RemediationAction.ACKNOWLEDGE_INCIDENT,RemediationAction.NO_ACTION,RemediationAction.RERUN_DEPLOYMENT} and self.policy_decision != PolicyDecision.BLOCKED


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
