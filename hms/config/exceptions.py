"""
Global DRF exception handler — normalises all error responses to a
consistent shape:  { "error": { "code": "...", "detail": "..." } }
"""
import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger("hms.exceptions")


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        error_payload = {
            "error": {
                "status_code": response.status_code,
                "detail": response.data,
            }
        }
        response.data = error_payload
    else:
        logger.exception("Unhandled exception in view %s", context.get("view"))
        response = Response(
            {"error": {"status_code": 500, "detail": "Internal server error"}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response
