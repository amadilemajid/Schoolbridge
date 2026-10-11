"""
Tests for ReportCardUploadView and distribute_report_cards Celery task.
US-B03/US-B04: PDF report card distribution to parents.
"""
import os
import tempfile
from unittest.mock import patch, MagicMock
from django.test import TestCase
from rest_framework.test import APITestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from schools.models import School
from authentication.models import User
from students.models import Student, Guardian
from messaging.models import MessageLog
from messaging.tasks import distribute_report_cards


class ReportCardDistributionTests(APITestCase):
    """Tests for ReportCardUploadView API endpoint."""

    def setUp(self):
        self.school = School.objects.create(
            name='Report Card School', slug='report-card',
            district='Kampala', phone='0700000000',
            email='admin@report.ug', school_type='primary'
        )
        self.user = User.objects.create_user(
            email='bursar@report.ug', password='password123',
            role='bursar', school=self.school
        )
        self.client.force_authenticate(user=self.user)
        
        self.student = Student.objects.create(
            school=self.school, first_name='Billy', last_name='Kid',
            gender='M', student_id='STU-999',
            admission_date='2024-01-01', academic_year_admitted=2024
        )
        self.guardian = Guardian.objects.create(
            student=self.student, first_name='Papa', last_name='Kid',
            phone='+256701112223', phone_normalised='+256701112223',
            is_primary=True, preferred_language='en'
        )

    @patch('messaging.tasks.distribute_report_cards.delay')
    def test_upload_report_card_api(self, mock_delay):
        """Uploading report card PDF triggers Celery task dispatch."""
        pdf_file = SimpleUploadedFile("report_card_billy.pdf", b"%PDF-1.4 dummy content", content_type="application/pdf")
        
        response = self.client.post(
            '/api/v1/results/upload-report-card/',
            {
                'student_id': str(self.student.id),
                'report_card': pdf_file
            },
            format='multipart'
        )
        
        self.assertEqual(response.status_code, 202)
        self.assertIn('uploaded and distribution queued', response.data['message'])
        
        # Verify the celery task was triggered
        mock_delay.assert_called_once()
        args = mock_delay.call_args[0]
        self.assertEqual(args[0], str(self.school.id))
        self.assertEqual(args[1][0]['student_id'], str(self.student.id))
        self.assertEqual(args[1][0]['parent_phone'], '+256701112223')
        self.assertIn('.pdf', args[1][0]['file_path'])


class DistributeReportCardsTaskTests(TestCase):
    """Tests for distribute_report_cards Celery task."""

    def setUp(self):
        self.school = School.objects.create(
            name='Report Task School', slug='report-task',
            district='Kampala', phone='0700000000',
            email='admin@report-task.ug', school_type='primary'
        )
        self.student = Student.objects.create(
            school=self.school, first_name='Billy', last_name='Kid',
            gender='M', student_id='STU-999',
            admission_date='2024-01-01', academic_year_admitted=2024
        )
        self.guardian = Guardian.objects.create(
            student=self.student, first_name='Papa', last_name='Kid',
            phone='+256701112223', phone_normalised='+256701112223',
            is_primary=True, preferred_language='en'
        )

    @patch('messaging.services.WhatsAppService.upload_media')
    @patch('messaging.services.WhatsAppService.send_document_message')
    def test_distribute_report_cards_task_flow(self, mock_send, mock_upload):
        # Mock media upload response
        media_mock = MagicMock()
        media_mock.id = 'dummy_media_id'
        media_mock.whatsapp_media_id = 'meta_pdf_999'
        media_mock.is_ready = True
        mock_upload.return_value = media_mock
        
        # Mock sending document response
        mock_send.return_value = ('msg_waba_doc_id', True)
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'%PDF-1.4 dummy content')
            temp_pdf_path = f.name
            
        try:
            report_cards_list = [{
                'student_id': str(self.student.id),
                'parent_phone': '+256701112223',
                'file_path': temp_pdf_path,
                'filename': 'BillyKidReport.pdf'
            }]
            
            distribute_report_cards(str(self.school.id), report_cards_list)
            
            # Verify upload was called with application/pdf mime type
            mock_upload.assert_called_once_with(
                school=self.school,
                file_path=temp_pdf_path,
                mime_type='application/pdf',
                media_type='document',
                original_filename='BillyKidReport.pdf',
                description=f"Report Card for Billy Kid"
            )
            
            # Verify send was called
            mock_send.assert_called_once_with(
                to_phone='+256701112223',
                media_id='meta_pdf_999',
                filename='BillyKidReport.pdf',
                school=self.school
            )
            
            # Verify MessageLog is created
            log = MessageLog.objects.get(school=self.school, student=self.student)
            self.assertEqual(log.status, 'sent')
            self.assertEqual(log.channel, 'whatsapp')
            self.assertEqual(log.template_type, 'report_card_ready')
            
        finally:
            if os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)
