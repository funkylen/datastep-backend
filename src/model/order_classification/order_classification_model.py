import re
import time

from openai import RateLimitError
import requests
from fastapi import HTTPException, status
from loguru import logger

from datastep.chains.order_classification_chain import get_order_classification_chain
from infra.env import (
    DOMYLAND_AUTH_EMAIL,
    DOMYLAND_AUTH_PASSWORD,
    DOMYLAND_AUTH_TENANT_NAME,
)
from infra.vysota_uds_list import UDS_LIST
from model.order_classification.order_classification_history_model import (
    get_saved_record_by_order_id,
    save_order_classification_record,
)
from repository.order_classification.order_classification_config_repository import (
    get_default_config,
    DEFAULT_CONFIG_USER_ID,
)
from scheme.order_classification.order_classification_history_scheme import (
    OrderClassificationRecord,
)
from scheme.order_classification.order_classification_scheme import (
    AlertTypeID,
    OrderClassificationRequest,
    OrderDetails,
    OrderFormUpdate,
    OrderStatusID,
    SummaryTitle,
    SummaryType,
)
from scheme.order_classification.uds_scheme import UDS

DOMYLAND_API_BASE_URL = "https://sud-api.domyland.ru"
DOMYLAND_APP_NAME = "Datastep"

RESPONSIBLE_UDS_LIST = [UDS(**uds_data) for uds_data in UDS_LIST]

# "Администрация" - DEPT ID 38
RESPONSIBLE_DEPT_ID = 38

# DataStep AI User ID - 15698
AI_USER_ID = 15698

# Message to mark AI processed orders (in internal chat)
ORDER_PROCESSED_BY_AI_MESSAGE = "ИИ классифицировал эту заявку как аварийную"

# Timeout for Rate Limit Error (TPM)
WAIT_TIME_IN_SEC = 60


def _normalize_resident_request_string(query: str) -> str:
    # Remove \n symbols
    removed_line_breaks_query = query.replace("\n", " ")

    # Remove photos
    removed_photos_query = removed_line_breaks_query.replace("Прикрепите фото:", " ")

    # Remove urls
    removed_urls_query = re.sub(r"http\S+", " ", removed_photos_query)

    # Replace multiple spaces with one
    fixed_spaces_query = re.sub(r"\s+", " ", removed_urls_query)

    return fixed_spaces_query


def _get_domyland_headers(auth_token: str | None = None):
    if auth_token is None:
        return {
            "AppName": DOMYLAND_APP_NAME,
        }

    return {
        "AppName": DOMYLAND_APP_NAME,
        "Authorization": auth_token,
    }


def _get_auth_token() -> str:
    req_body = {
        "email": DOMYLAND_AUTH_EMAIL,
        "password": DOMYLAND_AUTH_PASSWORD,
        "tenantName": DOMYLAND_AUTH_TENANT_NAME,
    }

    response = requests.post(
        url=f"{DOMYLAND_API_BASE_URL}/auth",
        json=req_body,
        headers=_get_domyland_headers(),
    )

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Domyland Auth: {response.text}",
        )

    auth_token = response.json()["token"]
    return auth_token


def _get_order_details_by_id(order_id: int) -> OrderDetails:
    # Authorize in Domyland API
    auth_token = _get_auth_token()

    # Update order status
    response = requests.get(
        url=f"{DOMYLAND_API_BASE_URL}/initial-data/dispatcher/order-info/{order_id}",
        headers=_get_domyland_headers(auth_token),
    )
    response_data = response.json()
    # logger.debug(f"Order {order_id} details:\n{response_data}")

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"OrderDetails GET: {response_data}",
        )

    order_details = OrderDetails(**response_data)
    return order_details


def _update_order_emergency_status(
    order_id: int,
    customer_id: int,
    place_id: int,
    event_id: int,
    building_id: int,
    order_data: list[OrderFormUpdate],
):
    # Authorize in Domyland API
    auth_token = _get_auth_token()

    order_data_dict = [data.dict() for data in order_data]

    req_body = {
        "customerId": customer_id,
        "placeId": place_id,
        "eventId": event_id,
        "buildingId": building_id,
        "orderData": order_data_dict,
        # serviceTypeId == 1 is Аварийная заявка
        "serviceTypeId": 1,
    }

    # Update order status
    response = requests.put(
        url=f"{DOMYLAND_API_BASE_URL}/orders/{order_id}",
        json=req_body,
        headers=_get_domyland_headers(auth_token),
    )
    response_data = response.json()

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Order UPDATE: {response_data}",
        )

    return response_data, req_body


def _get_responsible_users_ids_by_order_address(order_address: str) -> list[int] | None:
    # Search responsible UDS for order
    for uds_data in RESPONSIBLE_UDS_LIST:
        uds_user_id = int(uds_data.user_id)
        uds_address_list = uds_data.address_list

        # Check if order address contains UDS address
        # It means that UDS is responsible for this order
        for uds_address in uds_address_list:
            if uds_address.lower() in order_address.lower():
                return [uds_user_id]

    return None


def _get_order_status_details(order_id: int) -> dict:
    # Authorize in Domyland API
    auth_token = _get_auth_token()

    # Update responsible user
    response = requests.get(
        url=f"{DOMYLAND_API_BASE_URL}/orders/{order_id}/status",
        headers=_get_domyland_headers(auth_token),
    )
    response_data = response.json()

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Order status GET: {response_data}",
        )

    return response_data


def _update_order_status_details(
    order_id: int,
    responsible_dept_id: int,
    order_status_id: int,
    responsible_users_ids: list[int],
    inspector_users_ids: list[int],
) -> tuple[dict, dict]:
    # # Just save prev params in order status details
    # prev_order_status_details = _get_order_status_details(order_id)

    # Authorize in Domyland API
    auth_token = _get_auth_token()

    req_body = {
        # # Save all prev params from order status details (not needed to update)
        # **prev_order_status_details,
        # Update necessary params
        "responsibleDeptId": responsible_dept_id,
        "orderStatusId": order_status_id,
        "responsibleUserIds": responsible_users_ids,
        "inspectorIds": inspector_users_ids,
    }

    # Update responsible user
    response = requests.put(
        url=f"{DOMYLAND_API_BASE_URL}/orders/{order_id}/status",
        json=req_body,
        headers=_get_domyland_headers(auth_token),
    )
    response_data = response.json()

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Order status UPDATE: {response_data}",
        )

    return response_data, req_body


def _send_message_to_internal_chat(order_id: int, message: str) -> tuple[dict, dict]:
    # Authorize in Domyland API
    auth_token = _get_auth_token()

    req_body = {
        "orderId": order_id,
        "text": message,
        "isImportant": False,
    }

    # Send message to internal chat
    response = requests.post(
        url=f"{DOMYLAND_API_BASE_URL}/order-comments",
        json=req_body,
        headers=_get_domyland_headers(auth_token),
    )
    response_data = response.json()

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Order internal chat POST: {response_data}",
        )

    return response_data, req_body


def _get_order_emergency(
    prompt: str,
    client: str,
    query: str,
) -> str:
    try:
        chain = get_order_classification_chain(
            prompt_template=prompt,
            client=client,
        )
        order_emergency: str = chain.run(query=query)
        return order_emergency
    except RateLimitError:
        logger.info(f"Wait {WAIT_TIME_IN_SEC} seconds and try again")
        time.sleep(WAIT_TIME_IN_SEC)
        logger.info(
            f"Timeout passed, try to classify order '{query}' of '{client}' again"
        )

        return _get_order_emergency(
            prompt=prompt,
            client=client,
            query=query,
        )


def get_emergency_class(
    body: OrderClassificationRequest,
    client: str,
) -> OrderClassificationRecord:
    alert_id = body.alertId
    alert_type_id = body.alertTypeId
    alert_timestamp = body.timestamp

    order_id = body.data.orderId
    order_status_id = body.data.orderStatusId

    # Init order classification history record to save later
    history_record = OrderClassificationRecord(
        alert_id=alert_id,
        alert_type_id=alert_type_id,
        alert_timestamp=alert_timestamp,
        order_id=order_id,
        order_status_id=order_status_id,
    )

    try:
        # Check if order was already classified
        saved_record = get_saved_record_by_order_id(
            order_id=order_id,
            client=client,
        )
        is_saved_record_exists = saved_record is not None
        if is_saved_record_exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Order with ID {order_id} was already classified, history record ID {saved_record.id}",
            )

        # Check if order status is not "in progress"
        if order_status_id != OrderStatusID.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Order with ID {order_id} has status ID {order_status_id}, but status ID {OrderStatusID.PENDING} required",
            )

        order_classification_config = get_default_config(
            client=client,
        )
        # Check if default config exists
        if order_classification_config is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Default order classification config (for user with ID {DEFAULT_CONFIG_USER_ID} and client {client}) not found",
            )

        user_id = order_classification_config.user_id
        # Is need to classify order emergency
        is_use_emergency_classification = (
            order_classification_config.is_use_emergency_classification
        )
        # Is need to update order emergency in Domyland (blocked by is_use_emergency_classification)
        is_use_order_updating = (
            order_classification_config.is_use_order_updating
            and is_use_emergency_classification
        )

        # Message for response fields disabled by config
        disabled_field_msg = (
            f"skipped by emergency classification config of user with ID {user_id}"
        )

        # Check if order is new (created)
        if is_use_emergency_classification:
            if body.alertTypeId != AlertTypeID.NEW_ORDER:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Order with ID {order_id} has alert type ID {body.alertTypeId}, but status ID {AlertTypeID.NEW_ORDER} required",
                )

        # Get order details
        order_details = _get_order_details_by_id(order_id)
        history_record.order_details = order_details.dict()

        # Get resident comment
        order_query: str | None = None
        for order_form in order_details.service.orderForm:
            if (
                order_form.type == SummaryType.TEXT
                and order_form.title == SummaryTitle.COMMENT
            ):
                order_query = order_form.value

        history_record.order_query = order_query

        # Check if resident comment exists and not empty if enabled
        if is_use_emergency_classification:
            is_order_query_exists = order_query is not None
            is_order_query_empty = is_order_query_exists and not bool(
                order_query.strip()
            )

            if not is_order_query_exists or is_order_query_empty:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Order with ID {order_id} has no comment, cannot classify emergency",
                )

        # Get resident address
        order_address: str | None = None
        for summary in order_details.order.summary:
            if summary.title == SummaryTitle.OBJECT:
                order_address = summary.value
        # logger.debug(f"Order {order_id} address: {order_address}")

        history_record.order_address = order_address

        # Check if resident address exists and not empty if enabled
        if is_use_emergency_classification:
            is_order_address_exists = order_address is not None
            is_order_address_empty = is_order_address_exists and not bool(
                order_address.strip()
            )

            if not is_order_address_exists or is_order_address_empty:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Order with ID {order_id} has no address, cannot find responsible UDS",
                )

        # Run LLM to classify order
        if is_use_emergency_classification:
            # Normalize order query for LLM chain
            normalized_query = _normalize_resident_request_string(order_query)
            history_record.order_normalized_query = normalized_query

            # Get order emergency
            prompt = order_classification_config.emergency_prompt
            order_emergency = _get_order_emergency(
                prompt=prompt,
                client=client,
                query=normalized_query,
            )
        else:
            order_emergency = disabled_field_msg
        history_record.order_emergency = order_emergency

        is_emergency = None
        if is_use_emergency_classification:
            is_emergency = order_emergency.lower().strip() == "аварийная"
        history_record.is_emergency = is_emergency

        # Update order emergency class in Domyland
        # order_update_request = None
        # update_order_response_data = None
        if is_emergency and is_use_emergency_classification:
            # Get responsible UDS user id
            responsible_users_ids = _get_responsible_users_ids_by_order_address(
                order_address=order_address,
            )
            # Convert list to str
            history_record.uds_id = str(responsible_users_ids)

            if responsible_users_ids is None:
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail=f"Cannot find responsible UDS for order with ID {order_id} and address '{order_address}'",
                )

            # Update order responsible user is enabled
            if is_use_order_updating:
                response, request_body = _update_order_status_details(
                    order_id=order_id,
                    responsible_dept_id=RESPONSIBLE_DEPT_ID,
                    # Update order status to "В работе"
                    order_status_id=OrderStatusID.IN_PROGRESS,
                    responsible_users_ids=responsible_users_ids,
                    # Update order inspector to AI Account
                    inspector_users_ids=[AI_USER_ID],
                )

                # Mark order as processed by AI
                _send_message_to_internal_chat(
                    order_id=order_id,
                    message=ORDER_PROCESSED_BY_AI_MESSAGE,
                )
            else:
                request_body = {"result": disabled_field_msg}
                response = {"result": disabled_field_msg}

            history_record.order_update_request = request_body
            history_record.order_update_response = response

        # For changing emergency status
        # customer_id = order.customerId
        # place_id = order.placeId
        # service_id = order.serviceId
        # event_id = order.eventId
        # building_id = order.buildingId

        # order_data = [
        #     OrderFormUpdate(**order_form.dict())
        #     for order_form in order_details.service.orderForm
        # ]

        # update_order_response_data, order_update_request = _update_order_emergency_status(
        #     order_id=order_id,
        #     customer_id=customer_id,
        #     place_id=place_id,
        #     service_id=service_id,
        #     event_id=event_id,
        #     building_id=building_id,
        #     order_data=order_data,
        # )

    except (HTTPException, Exception) as error:
        history_record.is_error = True

        # Получаем текст ошибки из атрибута detail для HTTPException
        if isinstance(error, HTTPException):
            comment = error.detail
        # Для других исключений используем str(error)
        else:
            comment = str(error)
        history_record.comment = comment

        # Print error to logs
        logger.error(comment)

    # logger.debug(f"History record:\n{history_record}")
    history_record = save_order_classification_record(
        record=history_record,
        client=client,
    )

    return history_record


if __name__ == "__main__":
    # Test order id - 3196509
    # Real order id - 3191519
    order_id = 3197122

    # order_details = _get_order_details_by_id(order_id)
    # logger.debug(f"Order {order_id} details: {order_details}")

    # order_query: str | None = None
    # for order_form in order_details.service.orderForm:
    #     if (
    #         order_form.type == SummaryType.TEXT
    #         and order_form.title == SummaryTitle.COMMENT
    #     ):
    #         order_query = order_form.value
    # print(f"Order query: {order_query}")

    # order_address = None
    # for summary in order_details.order.summary:
    #     if summary.title == SummaryTitle.OBJECT:
    #         order_address = summary.value
    # logger.debug(f"Order {order_id} address: {order_address}")
    #
    # users_ids_list = _get_responsible_users_ids_by_order_address(order_address)
    # logger.debug(f"Responsible users IDs: {users_ids_list}")
