"""
Custom pagination class for SchoolBridge API.
Respects the ?page_size= query parameter sent by the frontend dashboard.
"""
from rest_framework.pagination import PageNumberPagination


class SchoolBridgePagination(PageNumberPagination):
    """
    Supports ?page_size= query parameter.
    Default: 25 rows per page.
    Max: 200 rows per page (guards against accidental large dumps).
    """
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200
    page_query_param = 'page'
