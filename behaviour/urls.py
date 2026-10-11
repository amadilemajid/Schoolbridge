from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BehaviourIncidentViewSet, BehaviourSuspensionViewSet, StudentBehaviourSummaryView

router = DefaultRouter()
router.register('incidents', BehaviourIncidentViewSet, basename='behaviour-incident')
router.register('suspensions', BehaviourSuspensionViewSet, basename='behaviour-suspension')

urlpatterns = [
    path('students/<uuid:student_id>/summary/', StudentBehaviourSummaryView.as_view(), name='student-behaviour-summary'),
    path('', include(router.urls)),
]
