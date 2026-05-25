"""
AuditMiddleware — attaches request_id to every request for log correlation.
"""
import uuid
from django.utils.deprecation import MiddlewareMixin


class AuditMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.request_id = str(uuid.uuid4())[:8]
        return None
