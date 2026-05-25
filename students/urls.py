from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers as nested_routers
from .views import (
    StudentViewSet, ClassGroupViewSet, GuardianViewSet,
    BulkImportView, BulkImportJobDetailView, CSVTemplateView,
)

router = DefaultRouter()
router.register('classes', ClassGroupViewSet, basename='class')
router.register('', StudentViewSet, basename='student')

urlpatterns = [
    path('', include(router.urls)),
    path('<uuid:student_pk>/guardians/', GuardianViewSet.as_view({'get': 'list', 'post': 'create'}), name='guardian-list'),
    path('<uuid:student_pk>/guardians/<int:pk>/', GuardianViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='guardian-detail'),
    path('import/', BulkImportView.as_view(), name='bulk-import'),
    path('import/<uuid:pk>/', BulkImportJobDetailView.as_view(), name='bulk-import-status'),
    path('import/template/', CSVTemplateView.as_view(), name='csv-template'),
]
