import io
from datetime import date
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .forms import ProductionRecordForm
from .models import ImportLog, ProductionRecord
from .utils import import_csv

HEADER = ('PO_Number,palletNumber,cartonNumber,pcb_label,chip_id,serial_number,STB_Mac,BT_Mac,'
          'Wifi_AP_5G,Wifi_AP_2G,Wifi_Client_5G,Wifi_Client_2G,produce_dt\n')


def full(body):
    """Expand short 'po,serial,stb_mac,date' lines into complete rows (other columns filled in).
    A blank po/serial/date stays blank so error cases still fail."""
    out = []
    for line in body.strip('\n').split('\n'):
        po, serial, stb, dt = line.split(',')
        out.append(','.join([po, 'PAL1', 'CTN1', 'PCB1', 'CHIP1', serial, stb or 'AA:00:00:00:00:01',
                             'AA:00:00:00:00:02', 'AA:00:00:00:00:03', 'AA:00:00:00:00:04',
                             'AA:00:00:00:00:05', 'AA:00:00:00:00:06', dt]))
    return HEADER + '\n'.join(out) + '\n'


def csv_file(body):
    return io.BytesIO(full(body).encode())


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
        f = SimpleUploadedFile('r.csv', full('A,SN001,,2026-02-01\nA,SN040,,2026-02-01\n').encode())
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


class PageRenderTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user('v', password='pw-123456789'))
        self.rec = ProductionRecord.objects.create(serial_number='SN900', stb_mac='AA:BB:CC:DD:EE:01', produce_dt=date(2026, 1, 1))

    def test_all_pages_render(self):
        for url in ['/', '/records/create/', f'/records/{self.rec.pk}/', f'/records/{self.rec.pk}/edit/',
                    f'/records/{self.rec.pk}/delete/', '/import/', '/import/logs/']:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get(f'/records/{self.rec.pk}/'), 'AA:BB:CC:DD:EE:01')

    def test_theme_switch_and_post_logout(self):
        html = self.client.get('/').content.decode()
        self.assertIn('data-theme-choice="dark"', html)
        self.assertEqual(self.client.post('/logout/').status_code, 302)


class ExportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('exp', password='pw-123456789')
        self.client.force_login(self.user)
        self.a = ProductionRecord.objects.create(serial_number='EXA', produce_dt=date(2026, 1, 1))
        self.b = ProductionRecord.objects.create(serial_number='EXB', produce_dt=date(2026, 1, 2))
        self.c = ProductionRecord.objects.create(serial_number='EXC', produce_dt=date(2026, 1, 3))

    def test_export_all_csv(self):
        r = self.client.get(reverse('export_records') + '?format=csv')
        self.assertIn('attachment', r['Content-Disposition'])
        body = r.content.decode('utf-8-sig')
        for sn in ('EXA', 'EXB', 'EXC'):
            self.assertIn(sn, body)

    def test_export_respects_filter(self):
        r = self.client.get(reverse('export_records') + '?format=csv&search=EXB')
        body = r.content.decode('utf-8-sig')
        self.assertIn('EXB', body)
        self.assertNotIn('EXA', body)

    def test_export_selected_only(self):
        for fmt in ('csv', 'xlsx', 'json'):
            r = self.client.post(reverse('export_records'), {'format': fmt, 'selected_ids': [self.a.pk, self.c.pk]})
            self.assertEqual(r.status_code, 200)
            self.assertIn(f'.{fmt}"', r['Content-Disposition'])
        r = self.client.post(reverse('export_records'), {'format': 'json', 'selected_ids': [self.a.pk, self.c.pk]})
        import json
        serials = {row['serial_number'] for row in json.loads(r.content)['records']}
        self.assertEqual(serials, {'EXA', 'EXC'})

    def test_export_selected_with_none_redirects(self):
        r = self.client.post(reverse('export_records'), {'format': 'csv'})
        self.assertRedirects(r, reverse('record_list'))


class ImportLogExportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('imp', password='pw-123456789')
        self.client.force_login(self.user)
        ProductionRecord.objects.create(serial_number='OLD1', produce_dt=date(2026, 1, 1))
        upload = SimpleUploadedFile('batch.csv', full('P1,NEW1,,2026-02-01\nP1,NEW2,,2026-02-01\n'
                                                'P1,OLD1,,2026-02-01\nP1,,,2026-02-01\n').encode())
        self.client.post(reverse('import_records'), {'file': upload, 'file_format': 'csv', 'skip_errors': True})
        self.log = ImportLog.objects.get()

    def test_import_links_records_to_log(self):
        self.assertEqual(set(self.log.records.values_list('serial_number', flat=True)), {'NEW1', 'NEW2'})

    def test_export_records_of_import(self):
        r = self.client.get(reverse('export_import_log_records', args=[self.log.pk]) + '?format=csv')
        body = r.content.decode('utf-8-sig')
        self.assertIn('NEW1', body)
        self.assertIn('NEW2', body)
        self.assertNotIn('OLD1', body)

    def test_export_report_lists_errors_and_duplicates(self):
        r = self.client.get(reverse('export_import_log_report', args=[self.log.pk]) + '?format=csv')
        lines = r.content.decode('utf-8-sig').strip().splitlines()
        self.assertEqual(lines[0], 'type,row,message')
        self.assertTrue(any(l.startswith('error,5,') for l in lines))
        self.assertTrue(any(l.startswith('duplicate,4,') for l in lines))

    def test_export_log_summary(self):
        for fmt in ('csv', 'xlsx', 'json'):
            r = self.client.get(reverse('export_import_logs') + f'?format={fmt}')
            self.assertEqual(r.status_code, 200)
        body = self.client.get(reverse('export_import_logs')).content.decode('utf-8-sig')
        self.assertIn('batch.csv', body)

    def test_logs_page_shows_export_links(self):
        r = self.client.get(reverse('import_logs'))
        self.assertContains(r, reverse('export_import_log_records', args=[self.log.pk]))
        self.assertContains(r, reverse('export_import_log_report', args=[self.log.pk]))


class ImportLogFilterSortTests(TestCase):
    def setUp(self):
        from datetime import datetime, timezone as tz
        self.alice = User.objects.create_user('alice', password='pw-123456789')
        self.bob = User.objects.create_user('bob', password='pw-123456789')
        self.client.force_login(self.alice)
        mk = lambda name, user, status, total, errors, day: ImportLog.objects.create(
            file_name=name, imported_by=user, status=status, total_rows=total, error_rows=errors)
        self.l1 = mk('march_batch.csv', self.alice, 'success', 100, 0, 1)
        self.l2 = mk('april_batch.xlsx', self.bob, 'partial', 50, 5, 2)
        self.l3 = mk('may_fail.json', self.bob, 'failed', 10, 10, 3)
        for log, d in ((self.l1, 1), (self.l2, 2), (self.l3, 3)):
            ImportLog.objects.filter(pk=log.pk).update(imported_at=datetime(2026, 3, d, 12, tzinfo=tz.utc))

    def names(self, qs):
        r = self.client.get(reverse('import_logs') + qs)
        return [l.file_name for l in r.context['logs']]

    def test_default_newest_first(self):
        self.assertEqual(self.names(''), ['may_fail.json', 'april_batch.xlsx', 'march_batch.csv'])

    def test_filters(self):
        self.assertEqual(self.names('?search=batch&user=bob'), ['april_batch.xlsx'])
        self.assertEqual(self.names('?status=failed'), ['may_fail.json'])
        self.assertEqual(self.names('?date_from=2026-03-02&date_to=2026-03-02'), ['april_batch.xlsx'])

    def test_sorting(self):
        self.assertEqual(self.names('?sort=-total_rows')[0], 'march_batch.csv')
        self.assertEqual(self.names('?sort=file_name'), ['april_batch.xlsx', 'march_batch.csv', 'may_fail.json'])
        self.assertEqual(self.names('?sort=imported_by__username')[0], 'march_batch.csv')
        self.assertEqual(self.names('?sort=bogus')[0], 'may_fail.json')  # unknown sort falls back to newest

    def test_summary_export_uses_filters(self):
        r = self.client.post(reverse('export_import_logs') + '?user=bob', {'format': 'csv', 'scope': 'all'})
        body = r.content.decode('utf-8-sig')
        self.assertIn('april_batch.xlsx', body)
        self.assertNotIn('march_batch.csv', body)

    def test_pagination_keeps_filters(self):
        for i in range(25):
            ImportLog.objects.create(file_name=f'bulk_{i}.csv', imported_by=self.bob, status='success')
        r = self.client.get(reverse('import_logs') + '?user=bob&sort=file_name')
        self.assertContains(r, 'page=2&user=bob&amp;sort=file_name')



class RequiredFieldImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('req', password='pw-123456789')

    def test_blank_cell_rejects_row_and_names_fields(self):
        lines = full('P1,SN100,,2026-02-01\nP1,SN101,,2026-02-01\n').split('\n')
        cells = lines[2].split(',')
        cells[1] = ''   # palletNumber
        cells[7] = ' '  # BT_Mac (whitespace only counts as blank)
        lines[2] = ','.join(cells)
        created, errors, _ = import_csv(io.BytesIO('\n'.join(lines).encode()), self.user)
        self.assertEqual(created, 1)
        self.assertEqual(len(errors), 1)
        self.assertIn('Row 3', errors[0])
        self.assertIn('palletNumber', errors[0])
        self.assertIn('BT_Mac', errors[0])
        self.assertFalse(ProductionRecord.objects.filter(serial_number='SN101').exists())

    def test_missing_column_rejects_every_row(self):
        body = 'PO_Number,serial_number,produce_dt\nP1,SN200,2026-02-01\n'
        created, errors, _ = import_csv(io.BytesIO(body.encode()), self.user)
        self.assertEqual((created, len(errors)), (0, 1))
        self.assertIn('STB_Mac', errors[0])

    def test_blank_row_fails_whole_import_when_not_skipping(self):
        lines = full('P1,SN300,,2026-02-01\n,SN301,,2026-02-01\n')
        with self.assertRaises(ValueError):
            import_csv(io.BytesIO(lines.encode()), self.user, skip_errors=False)
        self.assertEqual(ProductionRecord.objects.count(), 0)


class ImportLogExportDialogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('dlg', password='pw-123456789')
        self.client.force_login(self.user)
        for name, rows in (('first.csv', 'P1,F1,,2026-02-01\nP1,F2,,2026-02-01\n'), ('second.csv', 'P2,S1,,2026-02-02\n')):
            self.client.post(reverse('import_records'),
                             {'file': SimpleUploadedFile(name, full(rows).encode()), 'file_format': 'csv', 'skip_errors': True})
        self.first = ImportLog.objects.get(file_name='first.csv')
        self.second = ImportLog.objects.get(file_name='second.csv')
        self.url = reverse('export_import_logs')

    def test_selected_summary_only(self):
        r = self.client.post(self.url, {'format': 'csv', 'scope': 'selected', 'selected_ids': [self.second.pk]})
        body = r.content.decode('utf-8-sig')
        self.assertIn('second.csv', body)
        self.assertNotIn('first.csv', body)
        self.assertNotIn('S1', body)  # no record data without include_data

    def test_selected_with_none_ticked_redirects(self):
        r = self.client.post(self.url, {'format': 'csv', 'scope': 'selected'})
        self.assertEqual(r.status_code, 302)

    def test_csv_with_data_is_zip_of_reimportable_files(self):
        import zipfile
        r = self.client.post(self.url, {'format': 'csv', 'scope': 'all', 'include_data': '1'})
        self.assertIn('.zip', r['Content-Disposition'])
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        self.assertIn('import_logs.csv', names)
        first_file = next(n for n in names if 'first' in n)
        data = zf.read(first_file).decode('utf-8-sig')
        self.assertIn('F1', data)
        self.assertIn('F2', data)
        self.assertNotIn('S1', data)
        # the downloaded file imports cleanly on another system (here: all duplicates, no errors)
        created, errors, skipped = import_csv(io.BytesIO(zf.read(first_file)), self.user)
        self.assertEqual((created, errors, len(skipped)), (0, [], 2))

    def test_xlsx_with_data_has_sheet_per_import(self):
        import openpyxl
        r = self.client.post(self.url, {'format': 'xlsx', 'scope': 'selected', 'include_data': '1',
                                        'selected_ids': [self.first.pk, self.second.pk]})
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        self.assertEqual(wb.sheetnames[0], 'Import Logs')
        self.assertEqual(len(wb.sheetnames), 3)
        serials = {row[5] for ws in wb.worksheets[1:] for row in ws.iter_rows(min_row=2, values_only=True)}
        self.assertEqual(serials, {'F1', 'F2', 'S1'})

    def test_json_with_data_nests_records(self):
        import json
        r = self.client.post(self.url, {'format': 'json', 'scope': 'selected', 'include_data': '1',
                                        'selected_ids': [self.first.pk]})
        imports = json.loads(r.content)['imports']
        self.assertEqual(len(imports), 1)
        self.assertEqual({x['serial_number'] for x in imports[0]['records']}, {'F1', 'F2'})

    def test_template_download_has_headers_only(self):
        r = self.client.get(reverse('export_records') + '?format=csv&template=1')
        lines = r.content.decode('utf-8-sig').strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn('serial_number', lines[0])


class RecordSortTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('srt', password='pw-123456789')
        self.client.force_login(self.user)
        for sn, pallet, mac, d in (('S1', 'P-B', 'AA:03', 1), ('S2', 'P-C', 'AA:01', 2), ('S3', 'P-A', 'AA:02', 3)):
            ProductionRecord.objects.create(serial_number=sn, pallet_number=pallet, bt_mac=mac, produce_dt=date(2026, 1, d))

    def serials(self, qs, url='record_list'):
        r = self.client.get(reverse(url) + qs)
        return [rec.serial_number for rec in r.context['records']]

    def test_every_column_sorts_both_ways(self):
        self.assertEqual(self.serials('?sort=pallet_number'), ['S3', 'S1', 'S2'])
        self.assertEqual(self.serials('?sort=-pallet_number'), ['S2', 'S1', 'S3'])
        self.assertEqual(self.serials('?sort=bt_mac'), ['S2', 'S3', 'S1'])
        self.assertEqual(self.serials('?sort=produce_dt'), ['S1', 'S2', 'S3'])

    def test_htmx_partial_sorts_and_marks_header(self):
        self.assertEqual(self.serials('?sort=-bt_mac', 'record_table_partial'), ['S1', 'S3', 'S2'])
        r = self.client.get(reverse('record_table_partial') + '?sort=-bt_mac')
        self.assertContains(r, 'data-sort="bt_mac">BT_Mac ↓')

    def test_unknown_sort_falls_back_to_newest(self):
        self.assertEqual(self.serials('?sort=password'), ['S3', 'S2', 'S1'])

    def test_custom_column_sort(self):
        from .models import ColumnDefinition
        ColumnDefinition.objects.create(name='line', label='Line', is_visible=True)
        for sn, v in (('S1', 'L2'), ('S2', 'L3'), ('S3', 'L1')):
            ProductionRecord.objects.filter(serial_number=sn).update(extra_data={'line': v})
        self.assertEqual(self.serials('?sort=x_line'), ['S3', 'S1', 'S2'])

    def test_all_headers_clickable(self):
        r = self.client.get(reverse('record_list'))
        for key in ('po_number', 'pallet_number', 'carton_number', 'pcb_label', 'chip_id', 'serial_number', 'stb_mac',
                    'bt_mac', 'wifi_ap_5g', 'wifi_ap_2g', 'wifi_client_5g', 'wifi_client_2g', 'produce_dt'):
            self.assertContains(r, f'data-sort="{key}"')
