from fastapi import APIRouter, Depends
from fastapi_versioning import version
from sqlmodel import Session

from dto.instruction_dto import InstructionDto
from infra.database import get_session
from repository import instruction_repository
from repository import tenant_repository
from scheme.tenant_scheme import TenantRead, TenantCreate

# from service.auth_service import AuthService

router = APIRouter()


@router.post("", response_model=TenantRead)
@version(1)
def create_tenant(*, session: Session = Depends(get_session), tenant: TenantCreate):
    return tenant_repository.create_tenant(session, tenant)


@router.get("/{tenant_id}/instruction", response_model=InstructionDto)
@version(1)
def get_instruction(
    tenant_id: int,
    # current_user: UserDto = Depends(AuthService.get_current_user)
):
    return instruction_repository.get_instruction_by_tenant_id(tenant_id)

