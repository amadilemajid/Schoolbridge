"""
Custom exception handler — consistent JSON error responses for all API errors.
Production requirement: clients must always receive structured errors.
"""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger('schoolbridge')


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        # Unhandled exception — log it, return 500
        logger.exception(f"Unhandled exception in {context.get('view')}: {exc}")
        return Response(
            {'error': 'Internal server error. Our team has been notified.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    # Normalise all DRF errors to: {"error": "...", "detail": {...}}
    if isinstance(response.data, dict) and 'detail' in response.data:
        error_msg = str(response.data['detail'])
    elif isinstance(response.data, list):
        error_msg = response.data[0] if response.data else 'Unknown error'
    else:
        error_msg = 'Validation error'
    response.data = {
        'error': error_msg,
        'detail': response.data,
        'status_code': response.status_code,
    }
    return response
