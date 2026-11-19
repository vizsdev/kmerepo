import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, View
from django.urls import reverse, reverse_lazy
from django.http import JsonResponse
from django.db.models import Q
from django.contrib import messages

from .models import ProductionRecord, ColumnDefinition, ImportLog
from .forms import ProductionRecordForm, ImportForm
from django.utils import timezone
from .utils import (import_csv, import_xlsx, import_json, export_records as write_records,
                    export_import_logs, export_import_report)

EXPORT_FORMATS = ('csv', 'xlsx', 'json')


def _fmt(request):
    fmt = request.GET.get('format') or request.POST.get('format') or 'csv'
    return fmt if fmt in EXPORT_FORMATS else 'csv'


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _get_visible_columns():
    return ColumnDefinition.objects.filter(is_visible=True).order_by('order', 'id')


def _build_queryset(request):
    qs = ProductionRecord.objects.select_related('created_by', 'updated_by')
    search = request.GET.get('search', '').strip()
    if search:
        q = (
            Q(serial_number__icontains=search)
            | Q(po_number__icontains=search)
            | Q(pallet_number__icontains=search)
            | Q(carton_number__icontains=search)
            | Q(pcb_label__icontains=search)
            | Q(chip_id__icontains=search)
            | Q(stb_mac__icontains=search)
            | Q(bt_mac__icontains=search)
            | Q(wifi_ap_5g__icontains=search)
            | Q(wifi_ap_2g__icontains=search)
            | Q(wifi_client_5g__icontains=search)
            | Q(wifi_client_2g__icontains=search)
        )
        qs = qs.filter(q)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(produce_dt__gte=date_from)
    if date_to:
        qs = qs.filter(produce_dt__lte=date_to)

    sort = _record_sort(request)
    field = sort.lstrip('-')
    if field.startswith('x_'):
        # custom column stored in extra_data JSON
        field = f'extra_data__{field[2:]}'
    return qs.order_by(('-' if sort.startswith('-') else '') + field, '-pk')


RECORD_SORT_FIELDS = ['po_number', 'pallet_number', 'carton_number', 'pcb_label', 'chip_id', 'serial_number',
                      'stb_mac', 'bt_mac', 'wifi_ap_5g', 'wifi_ap_2g', 'wifi_client_5g', 'wifi_client_2g',
                      'produce_dt', 'created_at']


def _record_sort(request):
    """The requested sort if it names a known column (core or custom), else newest production date first."""
    sort = request.GET.get('sort') or '-produce_dt'
    field = sort.lstrip('-')
    if field in RECORD_SORT_FIELDS:
        return sort
    if field.startswith('x_') and ColumnDefinition.objects.filter(is_core=False, name=field[2:]).exists():
        return sort
    return '-produce_dt'


LOG_SORT_FIELDS = ['imported_at', 'file_name', 'status', 'total_rows', 'success_rows',
                   'error_rows', 'skipped_rows', 'imported_by__username']
LOG_SORTS = LOG_SORT_FIELDS + ['-' + f for f in LOG_SORT_FIELDS]


def _build_log_queryset(request):
    """Import logs filtered by file name, status, importer and date range, then sorted."""
    from django.db.models import Count
    g = request.GET
    qs = ImportLog.objects.select_related('imported_by').annotate(tracked_records=Count('records'))
    if g.get('search', '').strip():
        qs = qs.filter(file_name__icontains=g['search'].strip())
    if g.get('status') in dict(ImportLog.STATUS_CHOICES):
        qs = qs.filter(status=g['status'])
    if g.get('user'):
        qs = qs.filter(imported_by__username=g['user'])
    if g.get('date_from'):
        qs = qs.filter(imported_at__date__gte=g['date_from'])
    if g.get('date_to'):
        qs = qs.filter(imported_at__date__lte=g['date_to'])
    sort = g.get('sort')
    sort = sort if sort in LOG_SORTS else '-imported_at'
    return qs.order_by(sort, '-pk')


# ─────────────────────────────────────────────
# RECORD VIEWS
# ─────────────────────────────────────────────

class RecordListView(LoginRequiredMixin, ListView):
    model = ProductionRecord
    template_name = 'records/record_list.html'
    context_object_name = 'records'
    paginate_by = 50

    def get_queryset(self):
        return _build_queryset(self.request)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['columns'] = _get_visible_columns()
        ctx['all_columns'] = ColumnDefinition.objects.all().order_by('order', 'id')
        ctx['search'] = self.request.GET.get('search', '')
        ctx['date_from'] = self.request.GET.get('date_from', '')
        ctx['date_to'] = self.request.GET.get('date_to', '')
        ctx['sort'] = _record_sort(self.request)
        ctx['sort_presets'] = ['-produce_dt', 'produce_dt', 'serial_number', '-serial_number', '-created_at', 'created_at']
        ctx['total_count'] = ProductionRecord.objects.count()
        return ctx


class RecordTablePartial(LoginRequiredMixin, View):
    """HTMX partial — returns just the table body."""
    def get(self, request):
        qs = _build_queryset(request)
        from django.core.paginator import Paginator
        paginator = Paginator(qs, 50)
        page = paginator.get_page(request.GET.get('page', 1))
        return render(request, 'records/partials/table_rows.html', {
            'records': page,
            'columns': _get_visible_columns(),
            'page_obj': page,
            'sort': _record_sort(request),
        })


class RecordDetailView(LoginRequiredMixin, DetailView):
    model = ProductionRecord
    template_name = 'records/record_detail.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['columns'] = ColumnDefinition.objects.filter(is_core=False).order_by('order')
        return ctx


class RecordCreateView(LoginRequiredMixin, CreateView):
    model = ProductionRecord
    form_class = ProductionRecordForm
    template_name = 'records/record_form.html'
    success_url = reverse_lazy('record_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        messages.success(self.request, 'Record created successfully.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'New Production Record'
        ctx['action'] = 'Create'
        return ctx


class RecordUpdateView(LoginRequiredMixin, UpdateView):
    model = ProductionRecord
    form_class = ProductionRecordForm
    template_name = 'records/record_form.html'
    success_url = reverse_lazy('record_list')

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, 'Record updated successfully.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = f'Edit Record — {self.object.serial_number}'
        ctx['action'] = 'Update'
        return ctx


class RecordDeleteView(LoginRequiredMixin, DeleteView):
    model = ProductionRecord
    template_name = 'records/record_confirm_delete.html'
    success_url = reverse_lazy('record_list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Record deleted.')
        return super().delete(request, *args, **kwargs)


@login_required
def bulk_delete(request):
    if request.method == 'POST':
        ids = request.POST.getlist('selected_ids')
        if ids:
            ProductionRecord.objects.filter(pk__in=ids).delete()
            messages.success(request, f'{len(ids)} record(s) deleted.')
    return redirect('record_list')


# ─────────────────────────────────────────────
# COLUMN VIEWS
# ─────────────────────────────────────────────

@login_required
def toggle_column_visibility(request, pk):
    col = get_object_or_404(ColumnDefinition, pk=pk)
    if not col.is_core:
        col.is_visible = not col.is_visible
        col.save(update_fields=['is_visible'])
    return JsonResponse({'visible': col.is_visible})


# ─────────────────────────────────────────────
# IMPORT / EXPORT
# ─────────────────────────────────────────────

class ImportView(LoginRequiredMixin, View):
    template_name = 'records/import.html'

    def get(self, request):
        return render(request, self.template_name, {'form': ImportForm()})

    def post(self, request):
        form = ImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        file = request.FILES['file']
        fmt = form.cleaned_data['file_format']
        skip = form.cleaned_data['skip_errors']

        log = ImportLog.objects.create(file_name=file.name, imported_by=request.user)
        try:
            if fmt == 'csv':
                success, errors, skipped = import_csv(file, request.user, skip, log)
            elif fmt == 'xlsx':
                success, errors, skipped = import_xlsx(file, request.user, skip, log)
            else:
                success, errors, skipped = import_json(file, request.user, skip, log)

            log.success_rows = success
            log.error_rows = len(errors)
            log.skipped_rows = len(skipped)
            log.total_rows = success + len(errors) + len(skipped)
            log.errors = errors
            log.skipped = skipped
            log.status = 'success' if not errors else ('partial' if success > 0 else 'failed')
            log.save()
            messages.success(request, f'Import complete: {success} new records, {len(skipped)} duplicates skipped, {len(errors)} errors.')
        except Exception as e:
            log.status = 'failed'
            log.errors = [str(e)]
            log.save()
            messages.error(request, f'Import failed: {e}')

        return redirect('import_logs')


@login_required
def export_records(request):
    """Export records. GET: everything matching the current filters. POST with selected_ids: just those rows."""
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    if request.method == 'POST':
        ids = request.POST.getlist('selected_ids')
        if not ids:
            messages.error(request, 'No records selected to export.')
            return redirect('record_list')
        qs = ProductionRecord.objects.filter(pk__in=ids).order_by('-produce_dt', '-created_at')
        return write_records(qs, _fmt(request), f'production_records_selected_{stamp}')
    if request.GET.get('template'):
        return write_records(ProductionRecord.objects.none(), _fmt(request), 'production_records_template')
    return write_records(_build_queryset(request), _fmt(request), f'production_records_{stamp}')


@login_required
def export_import_log_list(request):
    """Export import logs.

    scope=all (default): every import matching the current filters (filters come from the query string).
    scope=selected: only the ticked imports (selected_ids, sent by POST).
    include_data=1: also include the records each import created.
    """
    params = request.POST if request.method == 'POST' else request.GET
    logs = _build_log_queryset(request)
    if params.get('scope') == 'selected':
        ids = [i for i in params.getlist('selected_ids') if i.isdigit()]
        if not ids:
            messages.error(request, 'Tick at least one import to export the selection.')
            return redirect(f"{reverse('import_logs')}?{request.GET.urlencode()}")
        logs = logs.filter(pk__in=ids)
    return export_import_logs(logs, _fmt(request), include_data=params.get('include_data') in ('1', 'on', 'true'))


@login_required
def export_import_log_records(request, pk):
    """The records that a given import created."""
    log = get_object_or_404(ImportLog, pk=pk)
    qs = log.records.order_by('pk')
    base = f'import_{log.pk}_records'
    return write_records(qs, _fmt(request), base)


@login_required
def export_import_log_report(request, pk):
    """Errors and skipped duplicates for a given import."""
    return export_import_report(get_object_or_404(ImportLog, pk=pk), _fmt(request))


class ImportLogListView(LoginRequiredMixin, ListView):
    model = ImportLog
    template_name = 'records/import_logs.html'
    context_object_name = 'logs'
    paginate_by = 20

    def get_queryset(self):
        return _build_log_queryset(self.request)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        g = self.request.GET
        ctx.update({
            'search': g.get('search', ''),
            'status': g.get('status', ''),
            'user_filter': g.get('user', ''),
            'date_from': g.get('date_from', ''),
            'date_to': g.get('date_to', ''),
            'sort': g.get('sort', '-imported_at') if g.get('sort') in LOG_SORTS else '-imported_at',
            'status_choices': ImportLog.STATUS_CHOICES,
            'importers': (ImportLog.objects.exclude(imported_by=None)
                          .values_list('imported_by__username', flat=True).distinct().order_by('imported_by__username')),
            'filtered': any(g.get(k) for k in ('search', 'status', 'user', 'date_from', 'date_to')),
            'total_logs': ImportLog.objects.count(),
        })
        params = g.copy()
        params.pop('page', None)
        ctx['query_string'] = params.urlencode()
        return ctx
