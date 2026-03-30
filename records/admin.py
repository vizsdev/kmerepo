from django.contrib import admin
from .models import ProductionRecord, ColumnDefinition, ImportLog


@admin.register(ColumnDefinition)
class ColumnDefinitionAdmin(admin.ModelAdmin):
    list_display = ['label', 'name', 'field_type', 'is_core', 'is_visible', 'order']
    list_editable = ['is_visible', 'order']
    list_filter = ['field_type', 'is_core', 'is_visible']


@admin.register(ProductionRecord)
class ProductionRecordAdmin(admin.ModelAdmin):
    list_display = [
        'po_number', 'pallet_number', 'carton_number', 'pcb_label', 'chip_id', 'serial_number',
        'stb_mac', 'bt_mac', 'wifi_ap_5g', 'wifi_ap_2g', 'wifi_client_5g', 'wifi_client_2g', 'produce_dt',
        'created_by', 'created_at'
    ]
    search_fields = [
        'serial_number', 'po_number', 'pallet_number', 'carton_number', 'pcb_label', 'chip_id',
        'stb_mac', 'bt_mac', 'wifi_ap_5g', 'wifi_ap_2g', 'wifi_client_5g', 'wifi_client_2g'
    ]
    list_filter = ['produce_dt']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']


@admin.register(ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    list_display = ['file_name', 'status', 'success_rows', 'error_rows', 'imported_by', 'imported_at']
    readonly_fields = ['file_name', 'imported_by', 'imported_at', 'errors']
