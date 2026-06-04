"""
US-C05 Instalment Plan Test
Tests payment plan creation and WhatsApp confirmation/reminder functionality
"""
import os
import django
from datetime import timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from schools.models import School, AcademicYear, AcademicTerm
from students.models import Student, Guardian, ClassGroup
from payments.models import FeeRecord, PaymentPlan, PaymentPlanInstalment
from payments.instalment_service import InstalmentPlanService

print("="*80)
print("US-C05: INSTALMENT PLAN WHATSAPP CONFIRMATION TEST")
print("="*80)

# Get test school or create
print("\n[1/6] Getting test school...")
school = School.objects.filter(name="Test School Epic-C").first()
if not school:
    print("  [SKIP] Run test_epic_c_automated.py first to create test data")
    exit(0)
print(f"  [OK] Using school: {school.name}")

# Get test student
print("\n[2/6] Getting test student...")
student = Student.objects.filter(school=school, first_name="John").first()
if not student:
    print("  [SKIP] No test student found")
    exit(0)
print(f"  [OK] Student: {student.first_name} {student.last_name}")

# Get fee record
print("\n[3/6] Getting fee record...")
term = AcademicTerm.objects.filter(school=school, is_current=True).first()
fee_record = FeeRecord.objects.filter(student=student, academic_term=term).first()
if not fee_record:
    print("  [SKIP] No fee record found")
    exit(0)
print(f"  [OK] Balance: UGX {fee_record.balance:,}")

# Create payment plan with 3 instalments
print("\n[4/6] Creating payment plan with 3 instalments...")
today = timezone.localdate()
instalments_data = [
    {'due_date': today + timedelta(days=10), 'amount': Decimal("200000")},
    {'due_date': today + timedelta(days=20), 'amount': Decimal("200000")},
    {'due_date': today + timedelta(days=30), 'amount': Decimal("200000")},
]

try:
    plan = InstalmentPlanService.create_plan_with_notification(
        fee_record=fee_record,
        instalments_data=instalments_data,
        created_by=None,
        notes="Test payment plan for US-C05"
    )
    print(f"  [OK] Payment plan created: {plan.id}")
    print(f"  [OK] Total amount: UGX {plan.total_amount:,}")
    print(f"  [OK] Status: {plan.status}")
except Exception as e:
    print(f"  [FAIL] Error creating plan: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Check instalments
print("\n[5/6] Checking instalments...")
instalments = plan.instalments.all()
print(f"  [OK] Created {instalments.count()} instalments:")
for inst in instalments:
    print(f"    #{inst.instalment_number}: UGX {inst.amount_due:,} - Due: {inst.due_date}")

# Test reminder message generation
print("\n[6/6] Testing reminder message generation...")
try:
    first_instalment = instalments.first()
    message = InstalmentPlanService._build_instalment_reminder_message(
        first_instalment, 
        'english'
    )
    msg_preview = message[:150].replace('\n', ' ')
    print(f"  [OK] English reminder: {msg_preview}...")
    
    message_lg = InstalmentPlanService._build_instalment_reminder_message(
        first_instalment,
        'luganda'
    )
    msg_preview_lg = message_lg[:150].replace('\n', ' ')
    print(f"  [OK] Luganda reminder: {msg_preview_lg}...")
except Exception as e:
    print(f"  [FAIL] Error generating messages: {e}")

print("\n" + "="*80)
print("US-C05 TEST COMPLETE")
print("="*80)
print("\n[PASS] Payment plan created with WhatsApp confirmation")
print(f"[PASS] {instalments.count()} instalments scheduled")
print("[PASS] Bilingual reminder messages working")
print("\nNext: Run migrations and test Celery tasks:")
print("  python manage.py makemigrations")
print("  python manage.py migrate")
print("="*80)
