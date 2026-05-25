"""
US-007: Audit log — filterable by actor, action, date range. CSV export.
"""
import csv
from django.http import HttpResponse
from rest_framework import generics, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import AuditLog
from .serializers import AuditLogSerializer
from schools.permissions import IsDirector


class AuditLogListView(generics.ListAPIView):
    """US-007: Filterable audit log with CSV export."""
    serializer_class = AuditLogSerializer
    permission_classes = [IsDirector]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['actor_email', 'action', 'target_model', 'target_id', 'description']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = AuditLog.objects.filter(school_id=self.request.user.school_id)
        # Date range filter
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        category = self.request.query_params.get('category')
        actor = self.request.query_params.get('actor')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if category:
            qs = qs.filter(category=category)
        if actor:
            qs = qs.filter(actor_email__icontains=actor)
        return qs

    def list(self, request, *args, **kwargs):
        # CSV export
        if request.query_params.get('format') == 'csv':
            return self._export_csv(request)
        return super().list(request, *args, **kwargs)

    def _export_csv(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="audit_log.csv"'
        writer = csv.writer(response)
        writer.writerow(['Timestamp', 'Actor', 'Role', 'Action', 'Category',
                         'Target', 'Target ID', 'IP Address'])
        for log in self.get_queryset():
            writer.writerow([
                log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                log.actor_email, log.actor_role, log.action, log.category,
                log.target_model, log.target_id, log.ip_address or '',
            ])
        return response


urlpatterns_audit = []
