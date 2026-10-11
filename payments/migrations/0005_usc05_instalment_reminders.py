# Generated migration for US-C05: Instalment Plan WhatsApp Confirmation

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_defaultercampaign_reminderescalation_and_more'),
    ]

    operations = [
        # Add student field to PaymentPlan
        migrations.AddField(
            model_name='paymentplan',
            name='student',
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name='payment_plans',
                to='students.student',
                null=True
            ),
        ),
        # Add completed_at to PaymentPlan
        migrations.AddField(
            model_name='paymentplan',
            name='completed_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        
        # Rename plan to payment_plan in PaymentPlanInstalment
        migrations.RenameField(
            model_name='paymentplaninstalment',
            old_name='plan',
            new_name='payment_plan',
        ),
        # Rename amount to amount_due
        migrations.RenameField(
            model_name='paymentplaninstalment',
            old_name='amount',
            new_name='amount_due',
        ),
        # Add amount_paid field
        migrations.AddField(
            model_name='paymentplaninstalment',
            name='amount_paid',
            field=models.DecimalField(decimal_places=0, default=0, max_digits=12),
        ),
        # Rename paid_date to paid_at and change type
        migrations.RemoveField(
            model_name='paymentplaninstalment',
            name='paid_date',
        ),
        migrations.AddField(
            model_name='paymentplaninstalment',
            name='paid_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        # Add reminder tracking fields
        migrations.AddField(
            model_name='paymentplaninstalment',
            name='reminder_sent',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='paymentplaninstalment',
            name='reminder_sent_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        # Add partial status choice
        migrations.AlterField(
            model_name='paymentplaninstalment',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('partial', 'Partially Paid'),
                    ('paid', 'Paid'),
                    ('overdue', 'Overdue'),
                    ('waived', 'Waived'),
                ],
                default='pending',
                max_length=20
            ),
        ),
    ]
