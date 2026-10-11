import csv
from django.http import HttpResponse
from rest_framework.decorators import action

class ExportMixin:
    """
    Mixin to add a CSV export action to a ViewSet.
    Generates a CSV based on the viewset's serializer fields.
    """
    @action(detail=False, methods=['get'])
    def export(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(qs, many=True)
        
        response = HttpResponse(content_type='text/csv')
        model_name = getattr(self.get_queryset().model, '_meta', None)
        filename = f"{model_name.model_name if model_name else 'export'}_export.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        if not serializer.data:
            writer.writerow(['No data available'])
            return response
            
        # Get headers from the first row keys
        headers = list(serializer.data[0].keys())
        writer.writerow(headers)
        
        for row in serializer.data:
            writer.writerow([row.get(key, '') for key in headers])
            
        return response
