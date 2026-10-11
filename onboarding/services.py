import logging
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone
from authentication.models import User
from schools.models import School, AcademicYear, AcademicTerm
from students.models import ClassGroup
from onboarding.models import SchoolRegistrationRequest, SchoolProvisioningLog

logger = logging.getLogger('schoolbridge')


class SchoolProvisioningService:
    """
    US-F01: Atomic provisioning pipeline for self-onboarded schools.
    """

    @classmethod
    def provision_school(cls, request_obj: SchoolRegistrationRequest, admin_password: str = None) -> School:
        """
        Executes the setup pipeline atomically.
        """
        request_obj.status = 'provisioning'
        request_obj.save()

        # In-memory log collection to preserve logging details upon transaction rollback
        logs_to_persist = []

        try:
            with transaction.atomic():
                # Step 1: Create School
                logs_to_persist.append(('create_school', 'success', ''))
                school = cls._create_school(request_obj)
                logs_to_persist[-1] = ('create_school', 'success', f"School created with ID: {school.id}")
                
                # Step 2: Create Admin User (Director)
                logs_to_persist.append(('create_director_user', 'success', ''))
                director_pwd = admin_password or request_obj.payload.get('admin_password', 'Sb@Onboard123')
                director = cls._create_director_user(request_obj, school, director_pwd)
                logs_to_persist[-1] = ('create_director_user', 'success', f"Director user created with ID: {director.id}")
                
                # Step 3: Create Academic Calendar
                logs_to_persist.append(('create_calendar', 'success', ''))
                year, term = cls._create_calendar(request_obj, school, director)
                logs_to_persist[-1] = ('create_calendar', 'success', f"Calendar created: Year {year.year}, Term {term.term_number}")
                
                # Step 4: Create Class Groups
                logs_to_persist.append(('create_classes', 'success', ''))
                class_names = cls._create_classes(request_obj, school)
                logs_to_persist[-1] = ('create_classes', 'success', f"Created classes: {', '.join(class_names)}")
                
                # Step 5: Initialize Risk Engine Config
                logs_to_persist.append(('create_risk_config', 'success', ''))
                cls._create_risk_config(school)
                logs_to_persist[-1] = ('create_risk_config', 'success', 'Risk Configuration initialized successfully')
                
                # Finalize request status
                request_obj.status = 'completed'
                request_obj.save()

            # Write all logs to database on success
            for step_name, status, details in logs_to_persist:
                SchoolProvisioningLog.objects.create(
                    registration_request=request_obj,
                    step_name=step_name,
                    status=status,
                    details=details
                )
                
            logger.info(f"Successfully provisioned school: {school.name}")
            return school

        except Exception as e:
            # Mark the failing step in the memory logs
            if logs_to_persist:
                last_step = logs_to_persist[-1]
                logs_to_persist[-1] = (last_step[0], 'failed', str(e))

            # Since the transaction rolled back, write all memory logs (both success and failure)
            # outside the atomic block so they are preserved in the DB.
            for step_name, status, details in logs_to_persist:
                SchoolProvisioningLog.objects.create(
                    registration_request=request_obj,
                    step_name=step_name,
                    status=status,
                    details=details
                )

            request_obj.status = 'failed'
            request_obj.save()
            logger.error(f"Failed provisioning for request {request_obj.id}: {e}", exc_info=True)
            raise e

    @classmethod
    def _create_school(cls, request_obj):
        slug = slugify(request_obj.school_name)
        # Ensure unique slug
        base_slug = slug
        counter = 1
        while School.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        school = School.objects.create(
            name=request_obj.school_name,
            slug=slug,
            district=request_obj.district,
            sub_county=request_obj.sub_county,
            phone=request_obj.admin_phone,
            email=request_obj.admin_email,
            school_type=request_obj.school_type,
            is_active=True,
            onboarded_by='self-onboarding'
        )
        return school

    @classmethod
    def _create_director_user(cls, request_obj, school, password):
        if User.objects.filter(email=request_obj.admin_email).exists():
            raise ValueError(f"User with email {request_obj.admin_email} already exists.")

        user = User.objects.create_user(
            email=request_obj.admin_email,
            password=password,
            first_name=request_obj.admin_first_name,
            last_name=request_obj.admin_last_name,
            phone=request_obj.admin_phone,
            school=school,
            role='director',
            is_staff=True,
            is_active=True
        )
        return user

    @classmethod
    def _create_calendar(cls, request_obj, school, director):
        payload = request_obj.payload
        year_val = payload.get('academic_year', timezone.localdate().year)
        term_num = payload.get('term_number', 1)
        
        # Default dates if not provided
        today = timezone.localdate()
        start_date = payload.get('term_start_date', today.isoformat())
        end_date = payload.get('term_end_date', (today + timezone.timedelta(days=90)).isoformat())
        fee_deadline = payload.get('fee_deadline', (today + timezone.timedelta(days=30)).isoformat())

        academic_year, _ = AcademicYear.objects.get_or_create(
            school=school,
            year=year_val,
            defaults={'is_current': True}
        )

        term = AcademicTerm.objects.create(
            school=school,
            academic_year=academic_year,
            term_number=term_num,
            name=f"Term {term_num} {year_val}",
            start_date=start_date,
            end_date=end_date,
            fee_deadline=fee_deadline,
            is_current=True,
            is_active=True,
            activated_at=timezone.now(),
            activated_by=director
        )
        return academic_year, term

    @classmethod
    def _create_classes(cls, request_obj, school):
        payload = request_obj.payload
        class_names = payload.get('classes', [])
        if not class_names:
            # Default primary classes if school type is primary
            if request_obj.school_type in ('primary', 'combined'):
                class_names = ['P.1', 'P.2', 'P.3', 'P.4', 'P.5', 'P.6', 'P.7']
            else:
                class_names = ['S.1', 'S.2', 'S.3', 'S.4', 'S.5', 'S.6']

        created_classes = []
        for name in class_names:
            # Derive level and stream
            level = name.replace('.', '').replace(' ', '')
            class_obj = ClassGroup.objects.create(
                school=school,
                name=name,
                level=level,
                stream='',
                is_active=True
            )
            created_classes.append(class_obj.name)
        return created_classes

    @classmethod
    def _create_risk_config(cls, school):
        from risk.models import RiskConfiguration
        RiskConfiguration.objects.get_or_create(
            school=school,
            defaults={
                'attendance_threshold': 75.00,
                'fee_payment_ratio_threshold': 50.00,
                'outstanding_balance_threshold': 100000,
                'grace_period_days': 10,
                'enable_whatsapp_alerts': True,
                'enable_monday_briefing': True
            }
        )
