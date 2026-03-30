import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, View
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.db.models import Q
from django.contrib import messages

from .models import ProductionRecord, ColumnDefinition, ImportLog
from .forms import ProductionRecordForm, ColumnDefinitionForm, ImportForm
from .utils import import_csv, import_xlsx, import_json, export_csv, export_xlsx, export_json


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

    sort = request.GET.get('sort', '-produce_dt')
    allowed_sorts = ['serial_number', '-serial_number', 'produce_dt', '-produce_dt',
                     'created_at', '-created_at']
    if sort in allowed_sorts:
        qs = qs.order_by(sort)
    return qs


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
        ctx['sort'] = self.request.GET.get('sort', '-production_date')
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

class ColumnListView(LoginRequiredMixin, ListView):
    model = ColumnDefinition
    template_name = 'records/column_list.html'
    context_object_name = 'columns'
    queryset = ColumnDefinition.objects.all().order_by('order', 'id')


class ColumnCreateView(LoginRequiredMixin, CreateView):
    model = ColumnDefinition
    form_class = ColumnDefinitionForm
    template_name = 'records/column_form.html'
    success_url = reverse_lazy('column_list')

    def form_valid(self, form):
        # Set order to last position
        last = ColumnDefinition.objects.order_by('-order').first()
        form.instance.order = (last.order + 1) if last else 0
        messages.success(self.request, f'Column "{form.instance.label}" created.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'New Column'
        ctx['action'] = 'Create'
        return ctx


class ColumnUpdateView(LoginRequiredMixin, UpdateView):
    model = ColumnDefinition
    form_class = ColumnDefinitionForm
    template_name = 'records/column_form.html'
    success_url = reverse_lazy('column_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.object.is_core:
            for field in form.fields:
                form.fields[field].disabled = True
        return form

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = f'Edit Column — {self.object.label}'
        ctx['action'] = 'Update'
        return ctx


class ColumnDeleteView(LoginRequiredMixin, DeleteView):
    model = ColumnDefinition
    template_name = 'records/column_confirm_delete.html'
    success_url = reverse_lazy('column_list')

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.is_core:
            messages.error(request, 'Core columns cannot be deleted.')
            return redirect('column_list')
        return super().dispatch(request, *args, **kwargs)


@login_required
def reorder_columns(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            for item in data.get('order', []):
                ColumnDefinition.objects.filter(pk=item['id']).update(order=item['order'])
            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error'}, status=405)


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
                success, errors = import_csv(file, request.user, skip)
            elif fmt == 'xlsx':
                success, errors = import_xlsx(file, request.user, skip)
            else:
                success, errors = import_json(file, request.user, skip)

            log.success_rows = success
            log.error_rows = len(errors)
            log.total_rows = success + len(errors)
            log.errors = errors
            log.status = 'success' if not errors else ('partial' if success > 0 else 'failed')
            log.save()
            messages.success(request, f'Import complete: {success} rows imported, {len(errors)} errors.')
        except Exception as e:
            log.status = 'failed'
            log.errors = [str(e)]
            log.save()
            messages.error(request, f'Import failed: {e}')

        return redirect('import_logs')


@login_required
def export_records(request):
    fmt = request.GET.get('format', 'csv')
    qs = _build_queryset(request)
    if fmt == 'xlsx':
        return export_xlsx(qs)
    elif fmt == 'json':
        return export_json(qs)
    return export_csv(qs)


class ImportLogListView(LoginRequiredMixin, ListView):
    model = ImportLog
    template_name = 'records/import_logs.html'
    context_object_name = 'logs'
    paginate_by = 20
