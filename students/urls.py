from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    StudentViewSet, ClassGroupViewSet, GuardianViewSet,
    BulkImportView, BulkImportJobDetailView, CSVTemplateView,
    GuardianListView,
)

router = DefaultRouter()
router.register('', StudentViewSet, basename='student')

urlpatterns = [
    path('classes/', ClassGroupViewSet.as_view({'get': 'list', 'post': 'create'}), name='class-list'),
    path('classes/<int:pk>/', ClassGroupViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='class-detail'),
    path('class-groups/', ClassGroupViewSet.as_view({'get': 'list', 'post': 'create'}), name='class-group-list'),
    path('class-groups/<int:pk>/', ClassGroupViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='class-group-detail'),
    path('import/template/', CSVTemplateView.as_view(), name='csv-template'),
    path('import/<uuid:pk>/', BulkImportJobDetailView.as_view(), name='bulk-import-status'),
    path('import/', BulkImportView.as_view(), name='bulk-import'),
    path('guardians/', GuardianListView.as_view(), name='guardian-list-all'),
    path('<uuid:student_pk>/guardians/', GuardianViewSet.as_view({'get': 'list', 'post': 'create'}), name='guardian-list'),
    path('<uuid:student_pk>/guardians/<int:pk>/', GuardianViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='guardian-detail'),
    path('', include(router.urls)),
]