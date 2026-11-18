import io
from datetime import date
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .forms import ProductionRecordForm
from .models import ImportLog, ProductionRecord
from .utils import import_csv

HEADER = 'PO_Number,serial_number,STB_Mac,produce_dt\n'


def csv_file(body):
    return io.BytesIO((HEADER + body).encode())


class ImportDuplicateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u', password='pw-123456789')
        ProductionRecord.objects.create(serial_number='SN001', po_number='ORIGINAL', produce_dt=date(2026, 1, 1))

    def test_existing_serial_is_skipped_not_overwritten(self):
        created, errors, skipped = import_csv(csv_file('NEW,SN001,,2026-02-01\nNEW,SN002,,2026-02-01\n'), self.user)
        self.assertEqual((created, errors, len(skipped)), (1, [], 1))
        self.assertEqual(ProductionRecord.objects.get(serial_number='SN001').po_number, 'ORIGINAL')
        self.assertTrue(ProductionRecord.objects.filter(serial_number='SN002').exists())

    def test_case_and_whitespace_variants_are_duplicates(self):
        created, _, skipped = import_csv(csv_file('X, sn001 ,,2026-02-01\n'), self.user)
        self.assertEqual((created, len(skipped)), (0, 1))
        self.assertEqual(ProductionRecord.objects.count(), 1)

    def test_repeats_within_file_keep_first(self):
        created, _, skipped = import_csv(csv_file('A,SN010,,2026-02-01\nB,SN010,,2026-02-02\nC,sn010,,2026-02-03\n'), self.user)
        self.assertEqual((created, len(skipped)), (1, 2))
        self.assertEqual(ProductionRecord.objects.get(serial_number='SN010').po_number, 'A')

    def test_reimporting_same_file_adds_nothing(self):
        body = 'A,SN020,,2026-02-01\nA,SN021,,2026-02-01\n'
        import_csv(csv_file(body), self.user)
        created, _, skipped = import_csv(csv_file(body), self.user)
        self.assertEqual((created, len(skipped)), (0, 2))

    def test_invalid_rows_abort_whole_import_when_not_skipping(self):
        with self.assertRaises(ValueError):
            import_csv(csv_file('A,SN030,,2026-02-01\nA,,,2026-02-01\n'), self.user, skip_errors=False)
        self.assertFalse(ProductionRecord.objects.filter(serial_number='SN030').exists())

    def test_import_view_logs_skipped(self):
        self.client.force_login(self.user)
        f = SimpleUploadedFile('r.csv', (HEADER + 'A,SN001,,2026-02-01\nA,SN040,,2026-02-01\n').encode())
        self.client.post(reverse('import_records'), {'file': f, 'file_format': 'csv', 'skip_errors': 'on'})
        log = ImportLog.objects.get()
        self.assertEqual((log.success_rows, log.skipped_rows, log.error_rows, log.status), (1, 1, 0, 'success'))
        self.assertContains(self.client.get(reverse('import_logs')), 'already exists')


class RecordFormDuplicateTests(TestCase):
    def setUp(self):
        self.rec = ProductionRecord.objects.create(serial_number='SN001', produce_dt=date(2026, 1, 1))

    def test_form_rejects_existing_serial_any_case(self):
        form = ProductionRecordForm(data={'serial_number': ' sn001 ', 'produce_dt': '2026-01-02'})
        self.assertFalse(form.is_valid())
        self.assertIn('serial_number', form.errors)

    def test_editing_own_record_is_allowed(self):
        form = ProductionRecordForm(data={'serial_number': 'SN001', 'produce_dt': '2026-01-02'}, instance=self.rec)
        self.assertTrue(form.is_valid(), form.errors)


class SidebarTests(TestCase):
    def test_no_manage_columns_or_admin_link(self):
        u = User.objects.create_superuser('admin', password='pw-123456789')
        self.client.force_login(u)
        html = self.client.get(reverse('record_list')).content.decode()
        self.assertNotIn('Manage Columns', html)
        self.assertNotIn('Admin Panel', html)
        self.assertEqual(self.client.get('/columns/').status_code, 404)
