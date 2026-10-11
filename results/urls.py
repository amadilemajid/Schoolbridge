from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SubjectViewSet, AssessmentViewSet, TermResultViewSet,
    ReportCardUploadView, MarksEntryView, MarksEntryBulkSaveView,
    MarksCSVTemplateView, MarksCSVImportView,
)

router = DefaultRouter()
router.register('subjects', SubjectViewSet, basename='subject')
router.register('assessments', AssessmentViewSet, basename='assessment')
router.register('results', TermResultViewSet, basename='term-result')

urlpatterns = [
    path('', include(router.urls)),
    path('upload-report-card/', ReportCardUploadView.as_view(), name='upload-report-card'),
    # Frontend-compatible marks entry endpoints
    path('marks-entry/', MarksEntryView.as_view(), name='marks-entry'),
    path('marks-entry/bulk-save/', MarksEntryBulkSaveView.as_view(), name='marks-entry-bulk-save'),
    path('marks-entry/csv-template/', MarksCSVTemplateView.as_view(), name='marks-entry-csv-template'),
    path('marks-entry/csv-import/', MarksCSVImportView.as_view(), name='marks-entry-csv-import'),
]
