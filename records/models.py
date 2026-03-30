from django.db import models
from django.contrib.auth.models import User
import json


FIELD_TYPES = [
    ('text', 'Text'),
    ('number', 'Number'),
    ('date', 'Date'),
    ('dropdown', 'Dropdown'),
    ('checkbox', 'Checkbox'),
    ('mac', 'MAC Address'),
]


class ColumnDefinition(models.Model):
    """Defines a custom column for the production record table."""
    name = models.CharField(max_length=100)
    label = models.CharField(max_length=100)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default='text')
    is_core = models.BooleanField(default=False)       # built-in, non-deletable
    is_visible = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    options = models.TextField(blank=True, help_text='Comma-separated options for dropdown')
    is_required = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.label} ({self.field_type})"

    def get_options_list(self):
        if self.options:
            return [o.strip() for o in self.options.split(',') if o.strip()]
        return []


class ProductionRecord(models.Model):
    """Core production record with fixed and dynamic fields."""
    # --- Fixed core fields ---
    po_number = models.CharField(max_length=100, blank=True, db_index=True, verbose_name='PO_Number')
    pallet_number = models.CharField(max_length=100, blank=True, verbose_name='palletNumber')
    carton_number = models.CharField(max_length=100, blank=True, verbose_name='cartonNumber')
    pcb_label = models.CharField(max_length=100, blank=True, verbose_name='pcb_label')
    chip_id = models.CharField(max_length=100, blank=True, verbose_name='chip_id')
    serial_number = models.CharField(max_length=100, unique=True, null=True, blank=True, db_index=True, verbose_name='serial_number')
    stb_mac = models.CharField(max_length=17, blank=True, verbose_name='STB_Mac')
    bt_mac = models.CharField(max_length=17, blank=True, verbose_name='BT_Mac')
    wifi_ap_5g = models.CharField(max_length=17, blank=True, verbose_name='Wifi_AP_5G')
    wifi_ap_2g = models.CharField(max_length=17, blank=True, verbose_name='Wifi_AP_2G')
    wifi_client_5g = models.CharField(max_length=17, blank=True, verbose_name='Wifi_Client_5G')
    wifi_client_2g = models.CharField(max_length=17, blank=True, verbose_name='Wifi_Client_2G')
    produce_dt = models.DateField(null=True, blank=True, verbose_name='produce_dt')

    # --- Dynamic extra fields stored as JSON ---
    extra_data = models.JSONField(default=dict, blank=True)

    # --- Metadata ---
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_records')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='updated_records')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-produce_dt', '-created_at']

    def __str__(self):
        return f"Record {self.serial_number}"

    def get_extra_value(self, field_name):
        return self.extra_data.get(field_name, '')

    def set_extra_value(self, field_name, value):
        self.extra_data[field_name] = value

    @property
    def mac_addresses(self):
        return [m for m in [self.stb_mac, self.bt_mac, self.wifi_ap_5g, self.wifi_ap_2g, self.wifi_client_5g, self.wifi_client_2g] if m]


class ImportLog(models.Model):
    STATUS_CHOICES = [('pending', 'Pending'), ('success', 'Success'), ('partial', 'Partial'), ('failed', 'Failed')]
    file_name = models.CharField(max_length=255)
    imported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    imported_at = models.DateTimeField(auto_now_add=True)
    total_rows = models.PositiveIntegerField(default=0)
    success_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    errors = models.JSONField(default=list)

    class Meta:
        ordering = ['-imported_at']

    def __str__(self):
        return f"Import {self.file_name} ({self.status})"
