from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HomeworkAssignmentViewSet, HomeworkSubmissionViewSet

router = DefaultRouter()
router.register('assignments', HomeworkAssignmentViewSet, basename='homework-assignment')
router.register('submissions', HomeworkSubmissionViewSet, basename='homework-submission')

urlpatterns = [
    path('', include(router.urls)),
]
