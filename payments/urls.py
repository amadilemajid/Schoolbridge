from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FeeStructureViewSet, FeeRecordViewSet, PaymentViewSet,
    PaymentPlanViewSet, FeeWaiverViewSet, ReconciliationQueueViewSet,
)

router = DefaultRouter()
router.register('fee-structures', FeeStructureViewSet, basename='fee-structure')
router.register('fee-records', FeeRecordViewSet, basename='fee-record')
router.register('payments', PaymentViewSet, basename='payment')
router.register('payment-plans', PaymentPlanViewSet, basename='payment-plan')
router.register('waivers', FeeWaiverViewSet, basename='fee-waiver')
router.register('reconciliation', ReconciliationQueueViewSet, basename='reconciliation')

urlpatterns = [path('', include(router.urls))]
