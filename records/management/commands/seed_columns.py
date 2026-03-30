from django.core.management.base import BaseCommand
from records.models import ColumnDefinition


CORE_COLUMNS = [
    {'name': 'po_number', 'label': 'PO Number', 'field_type': 'text', 'order': 0},
    {'name': 'pallet_number', 'label': 'Pallet Number', 'field_type': 'text', 'order': 1},
    {'name': 'carton_number', 'label': 'Carton Number', 'field_type': 'text', 'order': 2},
    {'name': 'pcb_label', 'label': 'PCB Label', 'field_type': 'text', 'order': 3},
    {'name': 'chip_id', 'label': 'Chip ID', 'field_type': 'text', 'order': 4},
    {'name': 'serial_number', 'label': 'Serial Number', 'field_type': 'text', 'order': 5},
    {'name': 'stb_mac', 'label': 'STB Mac', 'field_type': 'mac', 'order': 6},
    {'name': 'bt_mac', 'label': 'BT Mac', 'field_type': 'mac', 'order': 7},
    {'name': 'wifi_ap_5g', 'label': 'WiFi AP 5G', 'field_type': 'mac', 'order': 8},
    {'name': 'wifi_ap_2g', 'label': 'WiFi AP 2G', 'field_type': 'mac', 'order': 9},
    {'name': 'wifi_client_5g', 'label': 'WiFi Client 5G', 'field_type': 'mac', 'order': 10},
    {'name': 'wifi_client_2g', 'label': 'WiFi Client 2G', 'field_type': 'mac', 'order': 11},
    {'name': 'produce_dt', 'label': 'Produce Date', 'field_type': 'date', 'order': 12},
]


class Command(BaseCommand):
    help = 'Seed core column definitions'

    def handle(self, *args, **kwargs):
        for col in CORE_COLUMNS:
            obj, created = ColumnDefinition.objects.get_or_create(
                name=col['name'],
                defaults={**col, 'is_core': True, 'is_visible': True}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created core column: {col["label"]}'))
            else:
                self.stdout.write(f'Already exists: {col["label"]}')
        self.stdout.write(self.style.SUCCESS('Done seeding core columns.'))
