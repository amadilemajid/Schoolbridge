"""
WhatsApp Command Simulation API + Simulator Contacts endpoint.

WhatsAppSimulateView:
    POST /api/v1/messaging/simulate/
    Allows developers, testers, and frontend UI to simulate parent WhatsApp
    inbound commands and receive synchronous replies without Meta Cloud API credentials.

SimulatorContactsView:
    GET /api/v1/messaging/simulator-contacts/
    Returns a curated list of real guardians from the requesting user's school tenant,
    so the simulator always uses live DB contacts instead of hardcoded dummy data.
    Supports ?search= for filtering by guardian or student name.
    Requires IsAuthenticated (session or JWT).
"""
import hashlib

from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_spectacular.utils import extend_schema, inline_serializer

from messaging.services import InboundCommandProcessor


class WhatsAppSimulateSerializer(serializers.Serializer):
    phone = serializers.CharField(
        max_length=30,
        required=True,
        help_text="Parent phone number in Ugandan or international format (e.g. '0701234567' or '256701234567')"
    )
    message = serializers.CharField(
        max_length=500,
        required=True,
        help_text="Command text or numeric shortcut (e.g. 'BALANCE', 'RESULTS', 'ATTEND', 'TIMETABLE', '1', '2', etc.)"
    )
    school_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Optional school UUID to explicitly bind the simulation to a tenant"
    )


class WhatsAppSimulateView(APIView):
    """
    POST /api/v1/messaging/simulate/
    Simulates a parent sending a WhatsApp message to SchoolBridge.
    Runs the command synchronously through InboundCommandProcessor and returns the formatted response.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Simulate WhatsApp Inbound Command",
        description=(
            "Executes an inbound command (BALANCE, RESULTS, ATTEND, TIMETABLE, PAY, "
            "RECEIPT, PLAN, ABSENT, MENU, HELP, LUGANDA, ENGLISH or numeric shortcuts 1-8) "
            "and returns the exact response text without contacting Meta Cloud API."
        ),
        request=WhatsAppSimulateSerializer,
        responses={
            200: inline_serializer(
                name="WhatsAppSimulateResponse",
                fields={
                    "success": serializers.BooleanField(),
                    "phone": serializers.CharField(),
                    "command": serializers.CharField(),
                    "args": serializers.DictField(),
                    "reply": serializers.CharField(),
                    "buttons": serializers.ListField(child=serializers.CharField()),
                    "header": serializers.CharField(allow_blank=True),
                    "school": serializers.CharField(allow_null=True),
                    "school_id": serializers.CharField(allow_null=True),
                    "inbound_id": serializers.CharField(),
                }
            )
        },
        tags=["Messaging"]
    )
    def post(self, request):
        serializer = WhatsAppSimulateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        target_school = None
        school_id = data.get('school_id')
        if school_id:
            from schools.models import School
            target_school = School.objects.filter(id=school_id).first()
        elif getattr(request, 'user', None) and getattr(request.user, 'school', None):
            target_school = request.user.school

        result = InboundCommandProcessor.simulate(
            from_phone=data['phone'],
            message_text=data['message'],
            school=target_school,
        )

        return Response(result, status=status.HTTP_200_OK)


class SimulatorContactsView(APIView):
    """
    GET /api/v1/messaging/simulator-contacts/

    Returns real guardians for the requesting user's school tenant so the WhatsApp
    simulator UI can populate a live contact list instead of showing hardcoded dummy data.

    Query parameters:
        ?search=<name>   — Filter by guardian first/last name or student name (case-insensitive)
        ?limit=<n>       — Max contacts to return (default 20, max 50)

    Requires: IsAuthenticated (session or JWT). School is derived from request.user.school.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="WhatsApp Simulator — Live Contacts",
        description=(
            "Fetches real guardian contacts for the active school tenant. "
            "Used by the WhatsApp Simulator modal to populate live parent contacts "
            "for testing inbound commands. Returns guardian name, normalised phone, "
            "student name, class, and current-term fee balance."
        ),
        tags=["Messaging"],
    )
    def get(self, request):
        user = request.user
        school = getattr(user, 'school', None)
        if not school:
            return Response(
                {"detail": "No school associated with this account."},
                status=status.HTTP_403_FORBIDDEN
            )

        search = request.query_params.get('search', '').strip()
        try:
            limit = min(int(request.query_params.get('limit', 20)), 50)
        except (ValueError, TypeError):
            limit = 20

        from students.models import Guardian
        from payments.services import FeeService

        # Base queryset for guardians in this school
        qs = Guardian.objects.filter(
            student__school=school,
            is_primary=True,
        ).select_related(
            'student',
            'student__current_class',
        ).exclude(
            phone_hash=''
        ).order_by('first_name', 'last_name')

        # Search by guardian name or student name (decrypted in Python since fields are encrypted)
        if search:
            search_lower = search.lower()
            filtered = []
            for g in qs[:200]:  # Load up to 200 for search (they're encrypted so can't SQL filter)
                full_name = f"{g.first_name} {g.last_name}".lower()
                student_name = g.student.get_full_name().lower() if g.student else ''
                if search_lower in full_name or search_lower in student_name:
                    filtered.append(g)
                    if len(filtered) >= limit:
                        break
            guardians = filtered
        else:
            guardians = list(qs[:limit])

        current_term = school.terms.filter(is_current=True).first()

        contacts = []
        for g in guardians:
            student = g.student
            if not student:
                continue

            # Normalise phone — phone_normalised is decrypted by EncryptedCharField.from_db_value
            norm_phone = g.phone_normalised or ''
            if not norm_phone and g.phone:
                from config.validators import normalise_uganda_phone
                norm_phone = normalise_uganda_phone(g.phone) or ''

            if not norm_phone:
                continue

            # Get fee balance
            balance_ugx = 0
            if current_term:
                try:
                    balance_obj = FeeService.get_student_balance(student)
                    balance_ugx = int(balance_obj.balance) if balance_obj else 0
                except Exception:
                    balance_ugx = 0

            contacts.append({
                'id': str(g.id),
                'name': f"{g.first_name} {g.last_name} ({g.relationship})",
                'phone': norm_phone,
                'student_name': student.get_full_name(),
                'class_name': student.current_class.name if student.current_class else 'N/A',
                'balance': balance_ugx,
                'balance_display': f"UGX {balance_ugx:,}",
                'is_primary': g.is_primary,
            })

        return Response({
            'school': school.name,
            'school_id': str(school.id),
            'count': len(contacts),
            'contacts': contacts,
        })
