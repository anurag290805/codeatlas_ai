"""Agent task API, kept separate from the backward-compatible query routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.models import AgentTaskResult
from app.agents.patching import PatchConflictError, PatchRejectedError
from app.agents.router import route_task
from app.agents.service import AgentOrchestrator, PlannedModification
from app.api.routes_query import get_llm_service, get_retriever_service
from app.core.auth import get_workspace_id
from app.core.approvals import get_approval_store
from app.core.llm import LLMRateLimitError, LLMService, LLMServiceError, LLMTimeoutError
from app.core.retriever import RetrievalError, RepositoryNotIndexedError, RetrieverService
from app.core.workspace import ensure_workspace
from app.db import crud
from app.db.database import get_db
from app.models import schemas

router = APIRouter(tags=["agent"], dependencies=[Depends(ensure_workspace)])

_PENDING_APPROVAL = "pending_approval"


@router.post("/agent/tasks", response_model=schemas.AgentTaskResponse, summary="Run a routed agent task")
async def run_agent_task(
    payload: schemas.AgentTaskRequest,
    db: Session = Depends(get_db),
    retriever: RetrieverService = Depends(get_retriever_service),
    llm_service: LLMService = Depends(get_llm_service),
    workspace_id: str = Depends(get_workspace_id),
) -> schemas.AgentTaskResponse:
    repository = crud.get_repository(db, payload.repository_id, workspace_id=workspace_id)
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Repository not found: {payload.repository_id}")
    if repository.status not in {schemas.RepositoryStatus.READY, schemas.RepositoryStatus.INDEXED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Repository is not ready for querying (status: {repository.status}).")

    if payload.mode == "modify":
        # Two-phase flow: plan only (no writes), then require explicit human approval.
        planned = await AgentOrchestrator(retriever, llm_service).plan_modify(
            payload.repository_id, payload.task, payload.top_k, payload.route, payload.acceptance_criteria, repository, workspace_id=workspace_id,
        )
        return _pending_approval_response(payload, planned, workspace_id)

    try:
        result: AgentTaskResult = await AgentOrchestrator(retriever, llm_service).run(
            payload.repository_id,
            payload.task,
            payload.top_k,
            payload.acceptance_criteria,
            payload.image_data_url,
            payload.route,
            payload.mode,
            repository,
            workspace_id=workspace_id,
        )
    except RepositoryNotIndexedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository is not yet indexed.") from exc
    except RetrievalError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to retrieve repository context.") from exc
    except LLMRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Gemini rate limit or quota was exceeded.") from exc
    except LLMTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Gemini generation timed out.") from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Agent generation failed. Please retry.") from exc
    except PatchConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PatchRejectedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _response(result)


@router.post("/agent/tasks/approve", response_model=schemas.AgentTaskResponse, summary="Approve and apply a pending modify-mode patch")
async def approve_agent_task(
    payload: schemas.AgentApprovalRequest,
    db: Session = Depends(get_db),
    retriever: RetrieverService = Depends(get_retriever_service),
    llm_service: LLMService = Depends(get_llm_service),
    workspace_id: str = Depends(get_workspace_id),
) -> schemas.AgentTaskResponse:
    pending = get_approval_store().consume(payload.approval_token, workspace_id)
    if pending is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approval token is invalid, expired, or belongs to another workspace.")
    repository = crud.get_repository(db, pending.repository_id, workspace_id=workspace_id)
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Repository not found: {pending.repository_id}")
    if repository.status not in {schemas.RepositoryStatus.READY, schemas.RepositoryStatus.INDEXED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository is no longer ready for modification.")
    try:
        result: AgentTaskResult = await AgentOrchestrator(retriever, llm_service).apply_modify(
            pending.repository_id,
            pending.task,
            pending.context,
            pending.proposal,
            pending.changed_paths,
            pending.route,
            pending.acceptance_criteria,
            repository,
        )
    except PatchConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PatchRejectedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RepositoryNotIndexedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository is not yet indexed.") from exc
    except RetrievalError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to retrieve repository context.") from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Agent compliant generation failed. Please retry.") from exc
    return _response(result)


def _pending_approval_response(payload: schemas.AgentTaskRequest, planned: PlannedModification, workspace_id: str) -> schemas.AgentTaskResponse:
    token = get_approval_store().create(
        workspace_id,
        planned.repository_id,
        planned.proposal,
        planned.changed_paths,
        planned.task,
        planned.context,
        planned.route,
        planned.acceptance_criteria,
    )
    operations = [
        schemas.AgentOperationResponse(path=item.path, operation=item.operation, old_content_hash=item.old_content_hash)
        for item in planned.proposal.patches
    ]
    diff = "\n".join(item.diff for item in planned.proposal.patches)
    modification = schemas.AgentModificationResponse(
        status=_PENDING_APPROVAL,
        files_changed=planned.changed_paths,
        operations=operations,
        validation=schemas.AgentValidationResponse(status="planned", checks=[]),
        attempts=1,
        summary="Patch is proposed. It will not be written or executed until a human approves it.",
        errors=[],
        approval_token=token,
        diff=diff,
    )
    return schemas.AgentTaskResponse(
        task=payload.task,
        selected_skills=[skill.value for skill in route_task(payload.task)],
        status=_PENDING_APPROVAL,
        final_result="Modify-mode patch is pending human approval; nothing has been applied.",
        skill_results=[],
        duration_seconds=0,
        errors=[],
        modification=modification,
        mode="modify",
    )


def _response(result: AgentTaskResult) -> schemas.AgentTaskResponse:
    return schemas.AgentTaskResponse(
        task=result.task,
        selected_skills=[skill.value for skill in result.selected_skills],
        status=result.status.value,
        final_result=result.final_result,
        skill_results=[schemas.AgentSkillResult(skill=item.skill.value, status=item.status.value, summary=item.summary, output=item.output, errors=item.errors, duration_seconds=item.duration_seconds) for item in result.skill_results],
        duration_seconds=result.duration_seconds,
        errors=result.errors,
        modification=result.modification,
        mode=result.mode,
    )