import logging
from django.db import connection
from django.utils import timezone
from rest_framework import viewsets, status, generics, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers

from audit.mixins import AuditMixin
from schools.permissions import IsSystemAdmin
from onboarding.models import SchoolRegistrationRequest, SchoolProvisioningLog
from onboarding.serializers import (
    SchoolRegistrationRequestSerializer,
    SchoolRegistrationRequestCreateSerializer,
    SchoolProvisioningLogSerializer
)
from onboarding.services import SchoolProvisioningService

logger = logging.getLogger('schoolbridge')


class SchoolRegistrationRequestViewSet(AuditMixin, viewsets.ModelViewSet):
    """
    Manage registration requests (SystemAdmin only).
    """
    queryset = SchoolRegistrationRequest.objects.all().prefetch_related('logs')
    serializer_class = SchoolRegistrationRequestSerializer
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def perform_destroy(self, instance):
        self.log_action('ONBOARDING_REQUEST_DELETED', instance, {'school_name': instance.school_name})
        super().perform_destroy(instance)


class SchoolOnboardingRegisterView(AuditMixin, generics.CreateAPIView):
    """
    Public self-onboarding endpoint.
    SEC-001: Rate limited to 2/hour per IP to prevent DoS and spam provisioning.
    """
    permission_classes = [AllowAny]
    serializer_class = SchoolRegistrationRequestCreateSerializer
    throttle_scope = 'registration'  # SEC-001: 2/hour — defined in settings.DEFAULT_THROTTLE_RATES

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Save request record first
        validated_data = serializer.validated_data
        admin_password = validated_data.pop('admin_password', None)
        
        request_obj = SchoolRegistrationRequest.objects.create(
            school_name=validated_data['school_name'],
            admin_email=validated_data['admin_email'],
            admin_first_name=validated_data['admin_first_name'],
            admin_last_name=validated_data['admin_last_name'],
            admin_phone=validated_data['admin_phone'],
            district=validated_data['district'],
            sub_county=validated_data.get('sub_county', ''),
            school_type=validated_data.get('school_type', 'primary'),
            payload=validated_data.get('payload', {})
        )

        try:
            # Provision school atomically
            school = SchoolProvisioningService.provision_school(request_obj, admin_password)
            
            # Log action
            self.log_action(
                action='SCHOOL_ONBOARDED',
                target=school,
                extra={'school_name': school.name, 'admin_email': request_obj.admin_email}
            )

            # Response includes details
            return Response({
                'message': 'School onboarded successfully.',
                'school_id': str(school.id),
                'school_slug': school.slug,
                'admin_email': request_obj.admin_email,
                'status': 'completed'
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                'error': 'Provisioning failed.',
                'detail': str(e),
                'status': 'failed',
                'request_id': str(request_obj.id)
            }, status=status.HTTP_400_BAD_REQUEST)


class HealthCheckView(views.APIView):
    """
    US-F02: Health check and system status endpoint for deployment monitoring.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: inline_serializer(
                name='HealthCheckResponse',
                fields={
                    'status': serializers.CharField(),
                    'timestamp': serializers.DateTimeField(),
                    'version': serializers.CharField(required=False),
                    'services': serializers.DictField(required=False)
                }
            )
        }
    )
    def get(self, request):
        status_data = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'services': {}
        }
        
        # 1. Test Database
        try:
            connection.ensure_connection()
            # Simple query to check readability
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            status_data['services']['database'] = {'status': 'healthy'}
        except Exception as e:
            status_data['status'] = 'unhealthy'
            status_data['services']['database'] = {
                'status': 'unhealthy',
                'detail': str(e)
            }

        # 2. Test Redis / Cache
        try:
            from django.core.cache import cache
            cache.set('health_check', 'ok', timeout=5)
            if cache.get('health_check') == 'ok':
                status_data['services']['redis'] = {'status': 'healthy'}
            else:
                raise ValueError("Cache read/write mismatch")
        except Exception as e:
            status_data['status'] = 'unhealthy'
            status_data['services']['redis'] = {
                'status': 'unhealthy',
                'detail': str(e)
            }

        # 3. Test Celery Broker
        try:
            from django.conf import settings
            import redis
            broker_url = getattr(settings, 'CELERY_BROKER_URL', '')
            if 'redis' in broker_url:
                r = redis.from_url(broker_url)
                r.ping()
                status_data['services']['celery_broker'] = {'status': 'healthy'}
            else:
                # If non-redis or not configured, check connection or default channels
                from config.celery import app as celery_app
                with celery_app.connection_or_acquire() as conn:
                    conn.default_channel.connection.client.ping()
                status_data['services']['celery_broker'] = {'status': 'healthy'}
        except Exception as e:
            status_data['status'] = 'unhealthy'
            status_data['services']['celery_broker'] = {
                'status': 'unhealthy',
                'detail': str(e)
            }

        # 4. Check WhatsApp API Status
        try:
            from django.conf import settings
            from messaging.services import WhatsAppService
            whatsapp_configured = bool(
                getattr(settings, 'WHATSAPP_API_URL', None) and 
                getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', None)
            )
            if whatsapp_configured:
                if WhatsAppService.is_paused():
                    status_data['services']['whatsapp_api'] = {
                        'status': 'paused',
                        'detail': 'Sending queue paused due to business account lock.'
                    }
                else:
                    status_data['services']['whatsapp_api'] = {'status': 'healthy'}
            else:
                status_data['services']['whatsapp_api'] = {
                    'status': 'unconfigured',
                    'detail': 'Credentials not found in settings.'
                }
        except Exception as e:
            status_data['services']['whatsapp_api'] = {
                'status': 'unhealthy',
                'detail': str(e)
            }

        # Mask details for public requests to prevent information leakage
        is_admin = request.user and request.user.is_authenticated and getattr(request.user, 'role', None) == 'system_admin'
        if not is_admin:
            status_data = {
                'status': status_data['status'],
                'timestamp': status_data['timestamp']
            }

        http_status = status.HTTP_200_OK if status_data['status'] == 'healthy' else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(status_data, status=http_status)

