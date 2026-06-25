"""
Data Operations API Router
---------------------------
REST endpoints for batch CRUD, SQL file management,
batch execution, and execution history.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from backend.services import data_ops_service

router = APIRouter(prefix="/api/data-ops", tags=["data-ops"])


# ═══════════════════════════════════════════════════════════════
#  BATCH CRUD
# ═══════════════════════════════════════════════════════════════

@router.get("/batches")
def list_batches():
    return data_ops_service.list_batches()


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str):
    batch = data_ops_service.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found.")
    return batch


@router.post("/batches", status_code=status.HTTP_201_CREATED)
def create_batch(
    name: str = Form(...),
    description: str = Form(default=""),
    environment: str = Form(default="DEV"),
):
    valid_envs = {"DEV", "QA", "UAT", "PROD"}
    if environment.upper() not in valid_envs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid environment. Must be one of: {', '.join(sorted(valid_envs))}",
        )
    return data_ops_service.create_batch(
        name=name.strip(),
        description=description.strip() or None,
        environment=environment.upper(),
    )


@router.put("/batches/{batch_id}")
def update_batch(
    batch_id: str,
    name: str = Form(default=None),
    description: str = Form(default=None),
    environment: str = Form(default=None),
):
    if environment is not None:
        valid_envs = {"DEV", "QA", "UAT", "PROD"}
        if environment.upper() not in valid_envs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid environment. Must be one of: {', '.join(sorted(valid_envs))}",
            )
    batch = data_ops_service.update_batch(
        batch_id=batch_id,
        name=name.strip() if name else None,
        description=description.strip() if description is not None else None,
        environment=environment,
    )
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found.")
    return batch


@router.delete("/batches/{batch_id}")
def delete_batch(batch_id: str):
    deleted = data_ops_service.delete_batch(batch_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found.")
    return {"message": "Batch deleted successfully."}


# ═══════════════════════════════════════════════════════════════
#  SQL FILE MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@router.post("/batches/{batch_id}/files", status_code=status.HTTP_201_CREATED)
async def upload_sql_file(
    batch_id: str,
    file: UploadFile = File(...),
):
    # Verify batch exists
    batch = data_ops_service.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found.")

    file_bytes = await file.read()
    file_name = file.filename or "unknown.sql"

    try:
        result = data_ops_service.upload_sql_file(
            batch_id=batch_id,
            file_name=file_name,
            file_bytes=file_bytes,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/files/{file_id}")
def get_sql_file(file_id: str):
    sql_file = data_ops_service.get_sql_file(file_id)
    if sql_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SQL file not found.")
    return sql_file


@router.delete("/files/{file_id}")
def delete_sql_file(file_id: str):
    deleted = data_ops_service.delete_sql_file(file_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SQL file not found.")
    return {"message": "SQL file removed."}


@router.put("/files/{file_id}/reorder")
def reorder_sql_file(file_id: str, new_order: int = Form(...)):
    result = data_ops_service.reorder_sql_file(file_id, new_order)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SQL file not found.")
    return result


# ═══════════════════════════════════════════════════════════════
#  BATCH EXECUTION
# ═══════════════════════════════════════════════════════════════

@router.post("/batches/{batch_id}/execute")
def execute_batch(batch_id: str):
    try:
        result = data_ops_service.execute_batch(batch_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution error: {exc}",
        )


@router.get("/batches/{batch_id}/executions")
def list_executions(batch_id: str):
    return data_ops_service.list_executions(batch_id)


@router.get("/executions/{execution_id}")
def get_execution(execution_id: str):
    execution = data_ops_service.get_execution(execution_id)
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found.")
    return execution
