"""
UiPath Orchestrator API Schemas

Pydantic models for request/response validation and serialization.
All field names follow the UiPath OData API conventions.
"""

from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

# ──────────────────────────────────────────────────────────────
# Authentication & Configuration
# ──────────────────────────────────────────────────────────────

AuthStrategy = Literal["on-prem", "cloud-oauth", "cloud-pat"]


class OrchestratorSettings(BaseModel):
    """Connection settings for a UiPath Orchestrator instance."""

    auth_strategy: AuthStrategy = Field(
        "cloud-oauth",
        description="How to authenticate: on-prem (user/pass), cloud-oauth (client credentials), cloud-pat (personal access token)",
    )
    base_url: str = Field(..., description="Root URL of the Orchestrator instance")
    tenant: str = Field("Default", description="Orchestrator tenant name")

    # cloud-oauth
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

    # on-prem
    username: Optional[str] = None
    password: Optional[str] = None

    # cloud-pat
    access_token: Optional[str] = None

    # optional defaults
    folder_id: Optional[int] = Field(None, description="Default Organizational Unit ID")
    skip_tls_verify: bool = Field(False, description="Bypass TLS certificate checks")


class OAuthTokenPayload(BaseModel):
    """Token response from the UiPath Identity Server."""

    access_token: str
    expires_in: int
    token_type: str
    scope: str


# ──────────────────────────────────────────────────────────────
# Orchestrator domain objects
# ──────────────────────────────────────────────────────────────


class Folder(BaseModel):
    Id: int
    DisplayName: str
    FullyQualifiedName: Optional[str] = None
    ParentId: Optional[int] = None
    Description: Optional[str] = None
    IsPersonal: bool = False
    ProvisionType: Optional[str] = None
    CreationTime: Optional[str] = None


class Robot(BaseModel):
    Id: int
    Name: str
    Type: str
    Username: Optional[str] = None
    MachineName: Optional[str] = None
    MachineId: Optional[int] = None
    HostingType: Optional[str] = None
    IsEnabled: bool = True
    Version: Optional[str] = None


class Machine(BaseModel):
    Id: int
    Name: str
    Type: Optional[str] = None
    IsOnline: Optional[bool] = None
    Description: Optional[str] = None
    Key: Optional[str] = None
    LicenseKey: Optional[str] = None
    Version: Optional[str] = None


class Asset(BaseModel):
    Id: int
    Name: str
    ValueType: str
    StringValue: Optional[str] = None
    BoolValue: Optional[bool] = None
    IntValue: Optional[int] = None
    Value: Optional[str] = None
    ValueScope: Optional[str] = None
    HasDefaultValue: bool = False
    Description: Optional[str] = None
    CanBeDeleted: bool = True
    FolderId: Optional[int] = None


class RobotLog(BaseModel):
    Id: int
    TimeStamp: str
    Level: str
    Message: str
    ProcessName: Optional[str] = None
    JobKey: Optional[str] = None
    RobotName: Optional[str] = None
    MachineName: Optional[str] = None


class QueueDefinition(BaseModel):
    Id: int
    Name: str
    Description: Optional[str] = None
    MaxNumberOfRetries: int = 0
    AcceptAutomaticallyRetry: bool = False
    EnforceUniqueReference: bool = False
    CreationTime: Optional[str] = None
    SpecificDataJsonSchema: Optional[str] = None


ItemStatus = Literal["New", "InProgress", "Successful", "Failed", "Abandoned", "Retried", "Deleted"]


class QueueItem(BaseModel):
    Id: int
    QueueDefinitionId: int
    Status: ItemStatus
    Reference: Optional[str] = None
    SpecificContent: Optional[Dict[str, Any]] = None
    Output: Optional[Dict[str, Any]] = None
    CreationTime: Optional[str] = None
    StartProcessing: Optional[str] = None
    EndProcessing: Optional[str] = None
    RetryNumber: int = 0
    Progress: Optional[str] = None
    Priority: Literal["Low", "Normal", "High"] = "Normal"
    DeferDate: Optional[str] = None
    DueDate: Optional[str] = None
    ExceptionType: Optional[str] = None
    ExceptionReason: Optional[str] = None


JobState = Literal[
    "Pending", "Running", "Successful", "Faulted",
    "Stopping", "Terminated", "Stopped", "Suspended", "Resumed",
]


class Job(BaseModel):
    Id: int
    Key: str
    State: JobState
    Source: Optional[str] = None
    SourceType: Optional[str] = None
    BatchExecutionKey: Optional[str] = None
    Info: Optional[str] = None
    JobError: Optional[str] = None
    CreationTime: Optional[str] = None
    StartTime: Optional[str] = None
    EndTime: Optional[str] = None
    ReleaseName: Optional[str] = None
    ReleaseVersionId: Optional[int] = None
    HostMachineName: Optional[str] = None
    InputArguments: Optional[str] = None
    OutputArguments: Optional[str] = None


class Release(BaseModel):
    Key: str
    ProcessKey: str
    ProcessVersion: Optional[str] = None
    Name: str
    Description: Optional[str] = None
    IsLatestVersion: bool = True


class Session(BaseModel):
    Id: int
    MachineId: Optional[int] = None
    MachineName: Optional[str] = None
    HostMachineName: Optional[str] = None
    RobotId: Optional[int] = None
    RobotName: Optional[str] = None
    State: Optional[str] = None
    IsUnresponsive: bool = False
    ReportingTime: Optional[str] = None
    ServiceUserName: Optional[str] = None
    RuntimeType: Optional[str] = None
    FolderId: Optional[int] = None


class ProcessSchedule(BaseModel):
    Id: int
    Name: str
    ReleaseId: Optional[int] = None
    ReleaseName: Optional[str] = None
    ReleaseKey: Optional[str] = None
    StartProcessCron: Optional[str] = None
    StartProcessCronDetails: Optional[str] = None
    StartStrategy: Optional[int] = None
    StopStrategy: Optional[str] = None
    StopAfterMinutes: Optional[int] = None
    Enabled: bool = True
    TimeZoneId: Optional[str] = None
    NextExecutionTime: Optional[str] = None
    CalendarId: Optional[int] = None
    CalendarName: Optional[str] = None
    InputArguments: Optional[str] = None


class AuditLog(BaseModel):
    Id: int
    ServiceName: Optional[str] = None
    MethodName: Optional[str] = None
    Parameters: Optional[str] = None
    ExecutionTime: Optional[str] = None
    UserName: Optional[str] = None
    Action: Optional[str] = None
    Component: Optional[str] = None
    EntityId: Optional[int] = None
    EntityName: Optional[str] = None


# ──────────────────────────────────────────────────────────────
# Computed / aggregated models
# ──────────────────────────────────────────────────────────────


class QueueMetrics(BaseModel):
    """Breakdown of queue item counts by status."""

    queue_id: int
    queue_name: str
    total: int = 0
    new: int = 0
    in_progress: int = 0
    successful: int = 0
    failed: int = 0
    abandoned: int = 0
    success_rate_pct: Optional[float] = None


class JobMetrics(BaseModel):
    """Breakdown of job counts by state."""

    total: int = 0
    pending: int = 0
    running: int = 0
    successful: int = 0
    faulted: int = 0
    stopped: int = 0
    success_rate_pct: Optional[float] = None


class FolderSummary(BaseModel):
    """High-level health snapshot of an Orchestrator folder."""

    folder_id: int
    folder_name: str
    jobs: Dict[str, int]
    total_jobs: int
    queues: int
    releases: int
    robots: int
