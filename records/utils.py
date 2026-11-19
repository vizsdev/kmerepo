import csv
import json
import io
import re
from datetime import date, datetime
from decimal import Decimal

from django.db import models, transaction
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from django.http import HttpResponse

from .models import ProductionRecord, ColumnDefinition, ImportLog


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

CORE_FIELDS = [
    'po_number', 'pallet_number', 'carton_number', 'pcb_label', 'chip_id',
    'serial_number',
    'stb_mac', 'bt_mac', 'wifi_ap_5g', 'wifi_ap_2g', 'wifi_client_5g', 'wifi_client_2g',
    'produce_dt'
]


# Every core column must be filled on import; blank cells make the row an error.
REQUIRED_TEXT_FIELDS = [f for f in CORE_FIELDS if f not in ('serial_number', 'produce_dt')]
FIELD_LABELS = {f.name: f.verbose_name for f in ProductionRecord._meta.fields}


def _clean(value):
    return '' if value is None else str(value).strip()


def _normalize_field_name(name):
    if name is None:
        return ''
    value = str(name).strip().lower()
    # unify variants like "wifi client 5g", "wifi-client-5g", "WIFI_CLIENT_5G" to "wifi_client_5g"
    normalized = re.sub(r'[^a-z0-9]+', '_', value)
    normalized = normalized.strip('_')
    return normalized


def _normalize_rows(rows):
    normalized = []
    for row in rows:
        norm_row = {}
        for key, value in row.items():
            if key is None:
                continue
            normalized_key = _normalize_field_name(key)
            norm_row[normalized_key] = value
            # keep original key for compatibility with edge cases
            norm_row[key] = value
        normalized.append(norm_row)
    return normalized


def _find_field_value(row, field_name, label=None):
    if row is None:
        return None

    # Alias support for known header variants
    FIELD_ALIASES = {
        'wifi_client_5g': ['wifi_client_2g1', 'wifi_client_5g', 'wifi-client-5g', 'wifi client 5g', 'wificlient5g'],
        'wifi_client_2g': ['wifi_client_2g', 'wifi-client-2g', 'wifi client 2g', 'wificlient2g'],
    }

    candidates = [field_name] if field_name else []
    if field_name:
        candidates.extend([field_name.replace('_', ''), field_name.replace('_', ' ')])

    if label:
        candidates.extend([label, label.replace(' ', '_')])

    normalized_field = _normalize_field_name(field_name)
    alias_candidates = FIELD_ALIASES.get(normalized_field, [])
    candidates.extend(alias_candidates)

    for cand in candidates:
        if cand in row and row[cand] is not None:
            return row[cand]
        cand_norm = _normalize_field_name(cand)
        if cand_norm in row and row[cand_norm] is not None:
            return row[cand_norm]

    # final fallback: match normalized form against any row key
    norm_field = normalized_field
    norm_label = _normalize_field_name(label) if label else None
    for key, value in row.items():
        if key is None or value is None:
            continue
        key_norm = _normalize_field_name(key)
        if key_norm == norm_field or (norm_label and key_norm == norm_label):
            return value

    return None

    # final fallback: match normalized form against any row key
    norm_field = _normalize_field_name(field_name)
    norm_label = _normalize_field_name(label) if label else None
    for key, value in row.items():
        if key is None or value is None:
            continue
        if _normalize_field_name(key) == norm_field or (norm_label and _normalize_field_name(key) == norm_label):
            return value

    return None


def _get_all_headers():
    custom = list(ColumnDefinition.objects.filter(is_core=False).values_list('name', flat=True))
    return CORE_FIELDS + custom


def _record_to_row(record):
    row = {
        'po_number': record.po_number,
        'pallet_number': record.pallet_number,
        'carton_number': record.carton_number,
        'pcb_label': record.pcb_label,
        'chip_id': record.chip_id,
        'serial_number': record.serial_number,
        'stb_mac': record.stb_mac,
        'bt_mac': record.bt_mac,
        'wifi_ap_5g': record.wifi_ap_5g,
        'wifi_ap_2g': record.wifi_ap_2g,
        'wifi_client_5g': record.wifi_client_5g,
        'wifi_client_2g': record.wifi_client_2g,
        'produce_dt': str(record.produce_dt) if record.produce_dt else '',
    }
    row.update(record.extra_data)
    return row


def _parse_date(val):
    if not val:
        return None
    if isinstance(val, (date, datetime)):
        return val.date() if isinstance(val, datetime) else val
    for fmt in (
        '%Y-%m-%d',
        '%d/%m/%Y',
        '%m/%d/%Y',
        '%d-%m-%Y',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d %H:%M:%S',
        '%d/%m/%Y %H:%M',
        '%d/%m/%Y %H:%M:%S',
        '%m/%d/%Y %H:%M',
        '%m/%d/%Y %H:%M:%S',
        '%d-%m-%Y %H:%M',
        '%d-%m-%Y %H:%M:%S',
    ):
        try:
            parsed = datetime.strptime(str(val).strip(), fmt)
            return parsed.date()
        except ValueError:
            continue
    raise ValueError(f'Cannot parse date: {val}')


def serial_key(value):
    """Duplicate-check key for a serial number: trimmed, case-insensitive."""
    return str(value or '').strip().upper()


def existing_serial_keys(keys, chunk=2000):
    """Return the subset of serial keys that already exist in the database (case-insensitive)."""
    from django.db.models.functions import Upper, Trim
    keys = list(keys)
    found = set()
    for i in range(0, len(keys), chunk):
        part = keys[i:i + chunk]
        found.update(
            ProductionRecord.objects.annotate(_k=Upper(Trim('serial_number')))
            .filter(_k__in=part).values_list('_k', flat=True)
        )
    return found


def _import_rows(rows, user, skip_errors=True, log=None):
    """Validate every row, then insert only records whose serial_number is not already stored.

    Existing records are never overwritten. Rows whose serial already exists in the database,
    or appears earlier in the same file, are skipped and reported. Returns (created, errors, skipped).
    If skip_errors is False and any row is invalid, nothing is imported.
    """
    log_errors = []
    custom_cols = {c.name: c for c in ColumnDefinition.objects.filter(is_core=False)}
    parsed = []  # (row_number, serial, fields)

    for i, row in enumerate(rows, start=2):
        # Normalize keys on every import path for consistent field matching
        normalized_row = {}
        for key, value in row.items():
            if key is None:
                continue
            normalized_row[_normalize_field_name(key)] = value
            normalized_row[key] = value
        row = normalized_row

        try:
            raw_serial = _find_field_value(row, 'serial_number')
            serial = _clean(raw_serial)
            prod_date = _parse_date(_find_field_value(row, 'produce_dt'))

            extra = {}
            for col_name, col_obj in custom_cols.items():
                cell_val = None
                normalized_label = _normalize_field_name(col_obj.label)
                if col_name in row:
                    cell_val = row[col_name]
                elif normalized_label in row:
                    cell_val = row[normalized_label]
                elif col_obj.label in row:
                    cell_val = row[col_obj.label]
                else:
                    for row_key in row:
                        norm_key = _normalize_field_name(row_key)
                        if norm_key == col_name or norm_key == normalized_label:
                            cell_val = row[row_key]
                            break
                if cell_val is not None:
                    extra[col_name] = str(cell_val)

            fields = {f: _clean(_find_field_value(row, f)) for f in REQUIRED_TEXT_FIELDS}
            missing = [FIELD_LABELS[f] for f in CORE_FIELDS
                       if not (serial if f == 'serial_number' else prod_date if f == 'produce_dt' else fields[f])]
            missing += [c.label for n, c in custom_cols.items() if c.is_required and not _clean(extra.get(n))]
            if missing:
                raise ValueError(f'blank required field(s): {", ".join(missing)}')
            fields['produce_dt'] = prod_date
            fields['extra_data'] = extra
            parsed.append((i, serial, fields))
        except Exception as e:
            log_errors.append(f'Row {i}: {e}')

    if log_errors and not skip_errors:
        raise ValueError(f'{len(log_errors)} invalid row(s), nothing imported. First: {log_errors[0]}')

    in_db = existing_serial_keys({serial_key(s) for _, s, _ in parsed})
    seen = {}
    skipped = []
    new_records = []
    for i, serial, fields in parsed:
        key = serial_key(serial)
        if key in in_db:
            skipped.append(f'Row {i}: serial {serial} already exists, skipped')
        elif key in seen:
            skipped.append(f'Row {i}: serial {serial} repeats row {seen[key]} in this file, skipped')
        else:
            seen[key] = i
            new_records.append(ProductionRecord(serial_number=serial, created_by=user, updated_by=user, import_log=log, **fields))

    with transaction.atomic():
        # ignore_conflicts guards against a record added by someone else between the check and the insert
        ProductionRecord.objects.bulk_create(new_records, batch_size=1000, ignore_conflicts=True)
    return len(new_records), log_errors, skipped


# ─────────────────────────────────────────────
# IMPORT
# ─────────────────────────────────────────────

def import_csv(file_obj, user, skip_errors=True, log=None):
    decoded = file_obj.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(decoded))
    rows = _normalize_rows(list(reader))
    return _import_rows(rows, user, skip_errors, log)


def import_xlsx(file_obj, user, skip_errors=True, log=None):
    wb = openpyxl.load_workbook(file_obj, data_only=True)
    ws = wb.active
    headers = [str(cell.value).strip() if cell.value else '' for cell in ws[1]]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        row_dict = {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}
        if any(v for v in row_dict.values()):
            rows.append(row_dict)
    rows = _normalize_rows(rows)
    return _import_rows(rows, user, skip_errors, log)


def import_json(file_obj, user, skip_errors=True, log=None):
    data = json.loads(file_obj.read().decode('utf-8'))
    if isinstance(data, dict):
        data = data.get('records', [data])
    return _import_rows(data, user, skip_errors, log)


# ─────────────────────────────────────────────
# EXPORT
# ─────────────────────────────────────────────

def _attachment(response, filename):
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def write_table(fmt, headers, rows, filename, sheet_title='Export'):
    """Return a download response for a list of row dicts in csv, xlsx or json."""
    if fmt == 'json':
        body = json.dumps({'records': rows}, indent=2, default=str)
        return _attachment(HttpResponse(body, content_type='application/json'), f'{filename}.json')

    if fmt == 'xlsx':
        wb = openpyxl.Workbook()
        _fill_sheet(wb.active, sheet_title[:31], headers, rows)
        output = io.BytesIO()
        wb.save(output)
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        return _attachment(response, f'{filename}.xlsx')

    response = HttpResponse(_csv_text(headers, rows), content_type='text/csv')
    return _attachment(response, f'{filename}.csv')


def export_records(queryset, fmt='csv', filename='production_records'):
    rows = (_record_to_row(r) for r in queryset.iterator(chunk_size=2000))
    return write_table(fmt, _get_all_headers(), list(rows), filename, 'Production Records')


def export_csv(queryset):
    return export_records(queryset, 'csv')


def export_xlsx(queryset):
    return export_records(queryset, 'xlsx')


def export_json(queryset):
    return export_records(queryset, 'json')


LOG_HEADERS = ['id', 'file_name', 'status', 'total_rows', 'success_rows', 'error_rows',
               'skipped_rows', 'records_available', 'imported_by', 'imported_at']


def _log_to_row(log):
    return {
        'id': log.pk,
        'file_name': log.file_name,
        'status': log.status,
        'total_rows': log.total_rows,
        'success_rows': log.success_rows,
        'error_rows': log.error_rows,
        'skipped_rows': log.skipped_rows,
        # records linked to this import (0 for imports made before tracking was added)
        'records_available': log.tracked_records if hasattr(log, 'tracked_records') else log.records.count(),
        'imported_by': log.imported_by.username if log.imported_by else '',
        'imported_at': log.imported_at.strftime('%Y-%m-%d %H:%M:%S') if log.imported_at else '',
    }


def _log_record_rows(log):
    return [_record_to_row(r) for r in log.records.order_by('pk').iterator(chunk_size=2000)]


def _data_file_name(log, ext):
    stem = re.sub(r'[^A-Za-z0-9._-]+', '_', log.file_name.rsplit('.', 1)[0]).strip('_') or 'import'
    return f'import_{log.pk}_{stem}.{ext}'


def export_import_logs(logs, fmt='csv', include_data=False):
    """Summary of the given imports, one row per import.

    With include_data, also the records each import created, in the same columns as an import
    file, so another user can download exactly what was imported (and re-import it elsewhere):
      csv  -> .zip with import_logs.csv plus one CSV of records per import
      xlsx -> one workbook: 'Import Logs' sheet plus one records sheet per import
      json -> {"imports": [{...summary, "records": [...]}]}
    """
    logs = list(logs)
    summary = [_log_to_row(l) for l in logs]
    if not include_data:
        return write_table(fmt, LOG_HEADERS, summary, 'import_logs', 'Import Logs')

    headers = _get_all_headers()
    if fmt == 'json':
        data = {'imports': [dict(row, records=_log_record_rows(log)) for row, log in zip(summary, logs)]}
        return _attachment(HttpResponse(json.dumps(data, indent=2, default=str), content_type='application/json'),
                           'import_logs_with_data.json')

    if fmt == 'xlsx':
        wb = openpyxl.Workbook()
        _fill_sheet(wb.active, 'Import Logs', LOG_HEADERS, summary)
        used = set()
        for log in logs:
            title = re.sub(r'[\[\]:*?/\\]', '_', f'{log.pk} {log.file_name}')[:31]
            while title in used:
                title = title[:28] + f'_{len(used)}'
            used.add(title)
            _fill_sheet(wb.create_sheet(), title, headers, _log_record_rows(log))
        output = io.BytesIO()
        wb.save(output)
        response = HttpResponse(output.getvalue(),
                                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        return _attachment(response, 'import_logs_with_data.xlsx')

    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('import_logs.csv', _csv_text(LOG_HEADERS, summary))
        for log in logs:
            zf.writestr(_data_file_name(log, 'csv'), _csv_text(headers, _log_record_rows(log)))
    return _attachment(HttpResponse(buf.getvalue(), content_type='application/zip'), 'import_logs_with_data.zip')


def _csv_text(headers, rows):
    out = io.StringIO()
    out.write('\ufeff')
    writer = csv.DictWriter(out, fieldnames=headers, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def _fill_sheet(ws, title, headers, rows):
    ws.title = title
    header_fill = PatternFill(start_color='1a1a2e', end_color='1a1a2e', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True, size=11)
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = max(15, len(header) + 4)
    for row in rows:
        ws.append([row.get(h, '') for h in headers])


_ROW_RE = re.compile(r'^Row (\d+):\s*(.*)$')


def export_import_report(log, fmt='csv'):
    """Every error and skipped duplicate of one import, one line each."""
    rows = []
    for kind, items in (('error', log.errors or []), ('duplicate', log.skipped or [])):
        for msg in items:
            m = _ROW_RE.match(str(msg))
            rows.append({'type': kind, 'row': m.group(1) if m else '', 'message': m.group(2) if m else str(msg)})
    return write_table(fmt, ['type', 'row', 'message'], rows,
                       f'import_{log.pk}_report', 'Import Report')


# ─────────────────────────────────────────────
# MAC-to-serial lookup import
# ─────────────────────────────────────────────

def _find_record_by_mac(mac):
    if not mac:
        return None
    mac_norm = str(mac).strip()
    if not mac_norm:
        return None
    return ProductionRecord.objects.filter(
        models.Q(stb_mac__iexact=mac_norm) |
        models.Q(bt_mac__iexact=mac_norm) |
        models.Q(wifi_ap_5g__iexact=mac_norm) |
        models.Q(wifi_ap_2g__iexact=mac_norm) |
        models.Q(wifi_client_5g__iexact=mac_norm) |
        models.Q(wifi_client_2g__iexact=mac_norm)
    ).first()


def _normalize_mac_header(headers):
    normalized = [h.strip().lower() for h in headers]
    for k in ('stb_mac', 'bt_mac', 'wifi_ap_5g', 'wifi_ap_2g', 'wifi_client_5g', 'wifi_client_2g', 'mac'):
        if k in normalized:
            return k
    return None


def map_macs_to_serial(rows):
    """rows: list of dicts containing at least one MAC value. Returns mapping list."""
    output = []
    for i, row in enumerate(rows, start=2):
        # try to find a mac field in row
        mac_value = ''
        for key in row:
            if key.strip().lower() in ('stb_mac', 'bt_mac', 'wifi_ap_5g', 'wifi_ap_2g', 'wifi_client_5g', 'wifi_client_2g', 'mac'):
                mac_value = str(row.get(key, '') or '').strip()
                if mac_value:
                    break
        if not mac_value:
            output.append({'row': i, 'mac': None, 'serial_number': None, 'error': 'No MAC value found'})
            continue

        rec = _find_record_by_mac(mac_value)
        if rec:
            output.append({'row': i, 'mac': mac_value, 'serial_number': rec.serial_number, 'status': 'found'})
        else:
            output.append({'row': i, 'mac': mac_value, 'serial_number': None, 'error': 'No matching record'})
    return output


def import_mac_list_csv(file_obj, skip_errors=False):
    decoded = file_obj.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(decoded))
    rows = list(reader)
    return map_macs_to_serial(rows)


def import_mac_list_xlsx(file_obj, skip_errors=False):
    wb = openpyxl.load_workbook(file_obj, data_only=True)
    ws = wb.active
    headers = [str(cell.value).strip() if cell.value else '' for cell in ws[1]]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        # skip empty rows
        if not any(row):
            continue
        row_dict = {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}
        rows.append(row_dict)
    return map_macs_to_serial(rows)
