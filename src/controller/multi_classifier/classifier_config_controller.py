from fastapi import APIRouter
from fastapi import Depends
from fastapi_versioning import version
from sqlmodel import Session

from infra.database import get_session
from model import classifier_config_model
from model.auth_model import get_current_user
from scheme.classifier_config_scheme import ClassifierConfig, ClassifierConfigBase
from scheme.user_scheme import UserRead

router = APIRouter()


@router.get("", response_model=ClassifierConfig)
@version(1)
def get_classifier_config_by_user_id(
    session: Session = Depends(get_session),
    current_user: UserRead = Depends(get_current_user)
) -> ClassifierConfig | None:
    """
    Получает конфиг классификатора для текущего юзера.
    """
    user_id = current_user.id
    return classifier_config_model.get_classifier_config_by_user_id(session, user_id)


@router.post("", response_model=ClassifierConfig)
@version(1)
def create_classifier_config(
    body: ClassifierConfigBase,
    session: Session = Depends(get_session),
    current_user: UserRead = Depends(get_current_user)
) -> ClassifierConfig:
    """
    Создаёт конфиг классификатора для текущего юзера.
    """
    user_id = current_user.id
    return classifier_config_model.create_classifier_config(session, body, user_id)


@router.put("", response_model=ClassifierConfig | None)
@version(1)
def update_classifier_config_by_user_id(
    body: ClassifierConfigBase,
    session: Session = Depends(get_session),
    current_user: UserRead = Depends(get_current_user)
) -> ClassifierConfig | None:
    """
    Обновляет параметры в конфиге классификатора для текущего юзера.
    """
    user_id = current_user.id
    return classifier_config_model.update_classifier_config_by_user_id(session, body, user_id)


@router.delete("", response_model=None)
@version(1)
def delete_classifier_config_by_user_id(
    session: Session = Depends(get_session),
    current_user: UserRead = Depends(get_current_user)
) -> None:
    """
    Удаляет конфиг классификатора для текущего юзера.
    """
    user_id = current_user.id
    return classifier_config_model.delete_classifier_config_by_user_id(session, user_id)
