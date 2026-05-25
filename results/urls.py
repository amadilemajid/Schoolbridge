from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SubjectViewSet, AssessmentViewSet, TermResultViewSet

router = DefaultRouter()
router.register('subjects', SubjectViewSet, basename='subject')
router.register('assessments', AssessmentViewSet, basename='assessment')
router.register('results', TermResultViewSet, basename='term-result')

urlpatterns = [path('', include(router.urls))]
