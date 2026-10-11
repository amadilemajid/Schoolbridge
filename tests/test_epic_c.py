"""
Epic-C Integration Tests
Tests all 4 implemented features with real database operations.
"""
import pytest
from datetime import timedelta, date
from decimal import Decimal
from django.utils import timezone
from django.test import TestCase
from django.contrib.auth import get_user_model

from schools.models import School, AcademicYear, AcademicTerm
from students.models import Student, Guardian, ClassGroup
from payments.models import FeeRecord, FeeStructure, Payment
from payments.escalation_models import ReminderEscalation, ReminderEscalationLog
from payments.escalation_service import EscalationEngine
from payments.payment_link_models import PaymentLink
from payments.payment_link_service import PaymentLinkService
from payments.campaign_models import DefaulterCampaign, DefaulterCampaignTarget
from payments.campaign_service import DefaulterCampaignService
from payments.services import FeeService

User = get_user_model()


class EpicCIntegrationTest(TestCase):
    """Test all Epic-C features end-to-end."""
    
    def setUp(self):
        """Create test data."""
        # Create school
        self.school = School.objects.create(
            name='Test School',
            slug='test-school',
            address='Test Address',
            phone='+256700000000',
            email='test@school.com'
        )
        
        # Create academic year and term
        self.year = AcademicYear.objects.create(
            school=self.school,
            year=2024,
            is_current=True
        )
        
        # Create current term with future deadline (for escalations)
        future_deadline = timezone.localdate() + timedelta(days=30)
        self.term = AcademicTerm.objects.create(
            school=self.school,
            academic_year=self.year,
            name='Term 1 2024',
            term_number=1,
            start_date=timezone.localdate() - timedelta(days=10),
            end_date=timezone.localdate() + timedelta(days=80),
            fee_deadline=future_deadline,
            is_current=True
        )
        
        # Create class
        self.class_group = ClassGroup.objects.create(
            school=self.school,
            name='P7A',
            level='P7'
        )
        
        # Create fee structure
        self.fee_structure = FeeStructure.objects.create(
            school=self.school,
            academic_term=self.term,
            name='P7 Term 1 Fees',
            is_active=True
        )
        # Create item so total_amount is 600,000
        from payments.models import FeeStructureItem
        FeeStructureItem.objects.create(
            fee_structure=self.fee_structure,
            name='Tuition',
            amount=600000,
            is_mandatory=True
        )
        
        # Create students with guardians
        self.students = []
        self.guardians = []
        self.fee_records = []
        
        for i in range(5):
            # Create student first
            student = Student.objects.create(
                school=self.school,
                first_name=f'Student{i}',
                last_name=f'Test{i}',
                student_id=f'STU{i:03d}',
                admission_date=date(2024, 1, 1),
                academic_year_admitted=2024,
                date_of_birth=date(2010, 1, 1),
                gender='M' if i % 2 == 0 else 'F',
                current_class=self.class_group,
                is_active=True
            )
            self.students.append(student)
            
            # Create guardian and link to student
            guardian = Guardian.objects.create(
                student=student,
                first_name=f'Parent{i}',
                last_name=f'Test{i}',
                phone=f'+25670000000{i}',
                phone_normalised=f'+25670000000{i}',
                preferred_language='english',
                is_primary=True
            )
            self.guardians.append(guardian)
            
            # Create fee record with varying balances
            balance_amounts = [600000, 450000, 200000, 100000, 0]  # Different balance levels
            target_balance = balance_amounts[i]
            amount_paid = 600000 - target_balance
            
            fee_record = FeeRecord.objects.create(
                school=self.school,
                student=student,
                academic_term=self.term,
                fee_structure=self.fee_structure,
                amount_paid=amount_paid,
                amount_waived=0
            )
            self.fee_records.append(fee_record)
        
        # Create siblings relationship for sibling aggregation test
        self.students[0].siblings.add(self.students[1])
        
        # Create test user
        self.user = User.objects.create_user(
            email='test@admin.com',
            password='testpass123',
            role='bursar'
        )
    
    def test_01_escalation_initialization(self):
        """US-C01: Test escalation schedule creation."""
        print("\n=== TEST 1: Escalation Initialization ===")
        
        # Initialize escalations for term
        count = EscalationEngine.initialize_escalations_for_term(self.term)
        
        # Should create 5 levels × 4 students with balance (excluding fully paid)
        expected_count = 5 * 4  # 20 escalations
        self.assertEqual(count, expected_count, 
                        f"Expected {expected_count} escalations, got {count}")
        
        # Verify escalations exist
        escalations = ReminderEscalation.objects.filter(
            school=self.school,
            academic_term=self.term
        )
        self.assertEqual(escalations.count(), expected_count)
        
        # Verify all 5 levels exist for first student
        student_escalations = escalations.filter(
            fee_record=self.fee_records[0]
        ).order_by('level')
        
        self.assertEqual(student_escalations.count(), 5)
        
        # Verify escalation dates are correct
        deadline = self.term.fee_deadline
        for escalation in student_escalations:
            days_before = EscalationEngine.ESCALATION_SCHEDULE[escalation.level]
            expected_date = deadline - timedelta(days=days_before)
            self.assertEqual(escalation.scheduled_date, expected_date)
        
        print(f"[OK] Created {count} escalation reminders")
        print(f"[OK] 5 levels per student verified")
        print(f"[OK] Escalation dates calculated correctly")
    
    def test_02_escalation_messages(self):
        """US-C01: Test escalation message templates."""
        print("\n=== TEST 2: Escalation Messages ===")
        
        student = self.students[0]
        balance = self.fee_records[0].balance
        deadline_str = self.term.fee_deadline.strftime('%d %b %Y')
        days_remaining = (self.term.fee_deadline - timezone.localdate()).days
        
        # Test English messages for all 5 levels
        for level in range(1, 6):
            emoji, message = EscalationEngine.get_message_template(
                level=level,
                language='english',
                student_name=student.get_full_name(),
                balance=balance,
                deadline_str=deadline_str,
                days_remaining=days_remaining,
                school_name=self.school.name
            )
            
            self.assertIsNotNone(message)
            self.assertIn(student.get_full_name(), message)
            self.assertIn(f"{int(balance):,}", message)
            
            # Verify urgency increases with level
            if level == 1:
                self.assertIn('Gentle', message)
            elif level == 5:
                self.assertIn('FINAL', message)
        
        # Test Luganda messages
        emoji, message_lg = EscalationEngine.get_message_template(
            level=3,
            language='luganda',
            student_name=student.get_full_name(),
            balance=balance,
            deadline_str=deadline_str,
            days_remaining=days_remaining,
            school_name=self.school.name
        )
        self.assertIsNotNone(message_lg)
        
        print(f"[OK] All 5 escalation levels have valid templates")
        print(f"[OK] English and Luganda messages generated")
        print(f"[OK] Messages contain student data and urgency markers")
    
    def test_03_escalation_suppression(self):
        """US-C01: Test escalation suppression when paid."""
        print("\n=== TEST 3: Escalation Suppression ===")
        
        # Initialize escalations
        EscalationEngine.initialize_escalations_for_term(self.term)
        
        fee_record = self.fee_records[0]
        
        # Verify escalations are scheduled
        escalations_before = ReminderEscalation.objects.filter(
            fee_record=fee_record,
            status='scheduled'
        ).count()
        self.assertEqual(escalations_before, 5)
        
        # Make payment to clear balance
        Payment.objects.create(
            school=self.school,
            fee_record=fee_record,
            student=fee_record.student,
            method='cash',
            amount=fee_record.balance,
            status='completed',
            payment_date=timezone.now()
        )
        fee_record.amount_paid += fee_record.balance
        fee_record.save()
        
        # Suppress escalations
        suppressed_count = EscalationEngine.suppress_escalations_for_payment(fee_record)
        
        self.assertEqual(suppressed_count, 5)
        
        # Verify all escalations are suppressed
        escalations_after = ReminderEscalation.objects.filter(
            fee_record=fee_record,
            status='suppressed'
        ).count()
        self.assertEqual(escalations_after, 5)
        
        print(f"[OK] {suppressed_count} escalations suppressed after payment")
        print(f"[OK] Status changed from 'scheduled' to 'suppressed'")
    
    def test_04_sibling_aggregation(self):
        """US-C02: Test sibling fee aggregation."""
        print("\n=== TEST 4: Sibling Fee Aggregation ===")
        
        # Student 0 and Student 1 are siblings
        student = self.students[0]
        
        summary = FeeService.get_sibling_balance_summary(student, self.term)
        
        self.assertIsNotNone(summary)
        self.assertEqual(summary['sibling_count'], 2)
        self.assertEqual(len(summary['siblings']), 2)
        
        # Verify total balance is sum of both siblings
        expected_total = self.fee_records[0].balance + self.fee_records[1].balance
        self.assertEqual(summary['total_balance'], expected_total)
        
        # Verify individual sibling data
        for sibling_data in summary['siblings']:
            self.assertIn('student_name', sibling_data)
            self.assertIn('balance', sibling_data)
            self.assertIn('class', sibling_data)
        
        print(f"[OK] Sibling aggregation working")
        print(f"[OK] Found {summary['sibling_count']} siblings")
        print(f"[OK] Total family balance: UGX {summary['total_balance']:,}")
    
    def test_05_payment_link_generation(self):
        """US-C03: Test payment link generation."""
        print("\n=== TEST 5: Payment Link Generation ===")
        
        fee_record = self.fee_records[0]
        amount = Decimal('100000')
        
        # Generate payment link
        link = PaymentLinkService.generate_link(
            fee_record=fee_record,
            amount=amount,
            description='Test payment',
            created_by=self.user
        )
        
        self.assertIsNotNone(link)
        self.assertEqual(link.amount, amount)
        self.assertEqual(link.status, 'active')
        self.assertIsNotNone(link.token)
        self.assertEqual(len(link.token), 43)  # URL-safe base64 token length
        
        # Verify expiry is set
        self.assertIsNotNone(link.expires_at)
        expected_expiry = timezone.now() + timedelta(hours=72)
        self.assertTrue(abs((link.expires_at - expected_expiry).total_seconds()) < 60)
        
        # Verify link is usable
        self.assertTrue(link.is_usable)
        
        # Test token validation
        validated_link = PaymentLinkService.validate_and_get_link(link.token)
        self.assertEqual(validated_link.id, link.id)
        
        # Test full URL generation
        self.assertIn('/pay/', link.full_url)
        self.assertIn(link.token, link.full_url)
        
        print(f"[OK] Payment link generated with token: {link.token[:16]}...")
        print(f"[OK] Amount: UGX {link.amount:,}")
        print(f"[OK] Expires in 72 hours")
        print(f"[OK] Link is usable and validates correctly")
    
    def test_06_payment_link_expiry(self):
        """US-C03: Test payment link expiry logic."""
        print("\n=== TEST 6: Payment Link Expiry ===")
        
        fee_record = self.fee_records[0]
        
        # Generate link with short expiry
        link = PaymentLinkService.generate_link(
            fee_record=fee_record,
            amount=Decimal('50000'),
            expiry_hours=1,
            created_by=self.user
        )
        
        # Manually expire it
        link.expires_at = timezone.now() - timedelta(hours=1)
        link.save()
        
        # Test is_expired property
        self.assertTrue(link.is_expired)
        self.assertFalse(link.is_usable)
        
        # Test validation returns None for expired
        validated = PaymentLinkService.validate_and_get_link(link.token)
        self.assertIsNone(validated)
        
        print(f"[OK] Expired link correctly identified")
        print(f"[OK] Expired link marked as not usable")
        print(f"[OK] Validation rejects expired link")
    
    def test_07_campaign_creation_high_balance(self):
        """US-C04: Test defaulter campaign creation with high balance segment."""
        print("\n=== TEST 7: Defaulter Campaign - High Balance ===")
        
        campaign = DefaulterCampaignService.create_campaign(
            school=self.school,
            term=self.term,
            name='High Balance Test Campaign',
            segment_type='high_balance',
            message_template_en=(
                "🚨 URGENT\n\n"
                "{student_name} ({class_name}) has balance: UGX {balance}\n"
                "Deadline: {deadline}\n\n"
                "Please pay urgently.\n— {school_name}"
            ),
            scheduled_at=timezone.now(),
            created_by=self.user
        )
        
        self.assertIsNotNone(campaign)
        
        # Should target only Student 0 (600k) and Student 1 (450k) - both > 500k or near
        # Actually only Student 0 with 600k is > 500k
        self.assertGreaterEqual(campaign.target_count, 1)
        self.assertLessEqual(campaign.target_count, 2)
        
        # Verify targets were created
        targets = DefaulterCampaignTarget.objects.filter(campaign=campaign)
        self.assertEqual(targets.count(), campaign.target_count)
        
        # Verify message personalization
        for target in targets:
            self.assertIn(target.student.get_full_name(), target.message_sent)
            self.assertIn(f"{int(target.balance_at_send):,}", target.message_sent)
        
        print(f"[OK] Campaign created: {campaign.name}")
        print(f"[OK] Targets: {campaign.target_count} students")
        print(f"[OK] Total balance targeted: UGX {campaign.total_balance_targeted:,}")
    
    def test_08_campaign_segmentation_zero_payment(self):
        """US-C04: Test campaign segmentation - zero payment."""
        print("\n=== TEST 8: Campaign Segmentation - Zero Payment ===")
        
        campaign = DefaulterCampaignService.create_campaign(
            school=self.school,
            term=self.term,
            name='Zero Payment Campaign',
            segment_type='zero_payment',
            message_template_en="Pay your fees: {student_name} - UGX {balance}",
            scheduled_at=timezone.now(),
            created_by=self.user
        )
        
        # Should target student 0 only (has amount_paid=0)
        self.assertEqual(campaign.target_count, 1)
        
        # Verify all targets have zero payment
        targets = DefaulterCampaignTarget.objects.filter(campaign=campaign)
        for target in targets:
            fee_record = target.fee_record
            self.assertEqual(fee_record.amount_paid, 0)
        
        print(f"[OK] Zero payment segment identified {campaign.target_count} students")
        print(f"[OK] All targets confirmed with zero payments")
    
    def test_09_campaign_segmentation_specific_class(self):
        """US-C04: Test campaign segmentation - specific class."""
        print("\n=== TEST 9: Campaign Segmentation - Specific Class ===")
        
        campaign = DefaulterCampaignService.create_campaign(
            school=self.school,
            term=self.term,
            name='P7A Campaign',
            segment_type='specific_class',
            target_classes=[self.class_group],
            message_template_en="Class reminder: {student_name} - UGX {balance}",
            scheduled_at=timezone.now(),
            created_by=self.user
        )
        
        # Should target all students in P7A with balance (4 students)
        self.assertEqual(campaign.target_count, 4)
        
        # Verify all targets are from P7A
        targets = DefaulterCampaignTarget.objects.filter(campaign=campaign)
        for target in targets:
            self.assertEqual(target.student.current_class, self.class_group)
        
        print(f"[OK] Class-specific segment targeted {campaign.target_count} students")
        print(f"[OK] All targets from {self.class_group.name}")
    
    def test_10_all_features_integration(self):
        """Test all Epic-C features working together."""
        print("\n=== TEST 10: Full Integration ===")
        
        # 1. Initialize escalations
        escalation_count = EscalationEngine.initialize_escalations_for_term(self.term)
        
        # 2. Create sibling aggregation
        sibling_summary = FeeService.get_sibling_balance_summary(
            self.students[0], self.term
        )
        
        # 3. Generate payment links for all defaulters
        links = []
        for fee_record in self.fee_records[:4]:  # Exclude fully paid
            link = PaymentLinkService.generate_link(
                fee_record=fee_record,
                amount=fee_record.balance,
                created_by=self.user
            )
            links.append(link)
        
        # 4. Create comprehensive campaign
        campaign = DefaulterCampaignService.create_campaign(
            school=self.school,
            term=self.term,
            name='Comprehensive Campaign',
            segment_type='all',
            message_template_en="Fee reminder: {student_name} - UGX {balance}",
            scheduled_at=timezone.now(),
            created_by=self.user
        )
        
        # Verify all systems operational
        self.assertEqual(escalation_count, 20)  # 5 levels × 4 students
        self.assertEqual(sibling_summary['sibling_count'], 2)
        self.assertEqual(len(links), 4)
        self.assertEqual(campaign.target_count, 4)
        
        print(f"[OK] Escalations: {escalation_count} reminders scheduled")
        print(f"[OK] Sibling aggregation: {sibling_summary['sibling_count']} siblings")
        print(f"[OK] Payment links: {len(links)} links generated")
        print(f"[OK] Campaign: {campaign.target_count} targets")
        print(f"\n [OK] ALL EPIC-C FEATURES WORKING TOGETHER!")


def run_tests():
    """Run all Epic-C tests and print results."""
    import django
    django.setup()
    
    from django.test.runner import DiscoverRunner
    
    runner = DiscoverRunner(verbosity=2, interactive=False, keepdb=False)
    failures = runner.run_tests(['tests.test_epic_c'])
    
    return failures


if __name__ == '__main__':
    run_tests()
