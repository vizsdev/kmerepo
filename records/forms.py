from django import forms
from .models import ProductionRecord, ColumnDefinition
import re


MAC_PATTERN = re.compile(r'^([0-9A-Fa-f]{2}[:\-]){5}([0-9A-Fa-f]{2})$')


def validate_mac(value):
    if value and not MAC_PATTERN.match(value):
        raise forms.ValidationError(f'"{value}" is not a valid MAC address (e.g. AA:BB:CC:DD:EE:FF)')


class ProductionRecordForm(forms.ModelForm):
    stb_mac = forms.CharField(required=False, validators=[validate_mac],
                              widget=forms.TextInput(attrs={'class': 'form-input mac-input', 'placeholder': 'AA:BB:CC:DD:EE:FF'}))
    bt_mac = forms.CharField(required=False, validators=[validate_mac],
                             widget=forms.TextInput(attrs={'class': 'form-input mac-input', 'placeholder': 'AA:BB:CC:DD:EE:FF'}))
    wifi_ap_5g = forms.CharField(required=False, validators=[validate_mac],
                                 widget=forms.TextInput(attrs={'class': 'form-input mac-input', 'placeholder': 'AA:BB:CC:DD:EE:FF'}))
    wifi_ap_2g = forms.CharField(required=False, validators=[validate_mac],
                                 widget=forms.TextInput(attrs={'class': 'form-input mac-input', 'placeholder': 'AA:BB:CC:DD:EE:FF'}))
    wifi_client_5g = forms.CharField(required=False, validators=[validate_mac],
                                     widget=forms.TextInput(attrs={'class': 'form-input mac-input', 'placeholder': 'AA:BB:CC:DD:EE:FF'}))
    wifi_client_2g = forms.CharField(required=False, validators=[validate_mac],
                                     widget=forms.TextInput(attrs={'class': 'form-input mac-input', 'placeholder': 'AA:BB:CC:DD:EE:FF'}))

    class Meta:
        model = ProductionRecord
        fields = [
            'po_number', 'pallet_number', 'carton_number', 'pcb_label', 'chip_id',
            'serial_number',
            'stb_mac', 'bt_mac', 'wifi_ap_5g', 'wifi_ap_2g', 'wifi_client_5g', 'wifi_client_2g',
            'produce_dt'
        ]
        widgets = {
            'po_number': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'PO_Number'}),
            'pallet_number': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'palletNumber'}),
            'carton_number': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'cartonNumber'}),
            'pcb_label': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'pcb_label'}),
            'chip_id': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'chip_id'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'serial_number'}),
            'produce_dt': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add dynamic fields
        custom_columns = ColumnDefinition.objects.filter(is_core=False, is_visible=True).order_by('order')
        instance = kwargs.get('instance')

        for col in custom_columns:
            field_name = f'extra_{col.name}'
            value = instance.get_extra_value(col.name) if instance else ''

            if col.field_type == 'text':
                self.fields[field_name] = forms.CharField(
                    required=col.is_required, label=col.label,
                    initial=value,
                    widget=forms.TextInput(attrs={'class': 'form-input'})
                )
            elif col.field_type == 'number':
                self.fields[field_name] = forms.DecimalField(
                    required=col.is_required, label=col.label,
                    initial=value or None,
                    widget=forms.NumberInput(attrs={'class': 'form-input'})
                )
            elif col.field_type == 'date':
                self.fields[field_name] = forms.DateField(
                    required=col.is_required, label=col.label,
                    initial=value or None,
                    widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'})
                )
            elif col.field_type == 'dropdown':
                opts = [(o, o) for o in col.get_options_list()]
                opts.insert(0, ('', '--- Select ---'))
                self.fields[field_name] = forms.ChoiceField(
                    required=col.is_required, label=col.label,
                    initial=value, choices=opts,
                    widget=forms.Select(attrs={'class': 'form-select'})
                )
            elif col.field_type == 'checkbox':
                self.fields[field_name] = forms.BooleanField(
                    required=False, label=col.label,
                    initial=bool(value),
                    widget=forms.CheckboxInput(attrs={'class': 'form-checkbox'})
                )
            elif col.field_type == 'mac':
                self.fields[field_name] = forms.CharField(
                    required=col.is_required, label=col.label,
                    initial=value,
                    validators=[validate_mac],
                    widget=forms.TextInput(attrs={'class': 'form-input mac-input', 'placeholder': 'AA:BB:CC:DD:EE:FF'})
                )

    def clean_serial_number(self):
        serial = (self.cleaned_data.get('serial_number') or '').strip()
        if not serial:
            raise forms.ValidationError('Serial number is required.')
        dup = ProductionRecord.objects.filter(serial_number__iexact=serial)
        if self.instance.pk:
            dup = dup.exclude(pk=self.instance.pk)
        if dup.exists():
            raise forms.ValidationError(f'A record with serial number "{serial}" already exists.')
        return serial

    def save(self, commit=True):
        instance = super().save(commit=False)
        custom_columns = ColumnDefinition.objects.filter(is_core=False)
        for col in custom_columns:
            field_name = f'extra_{col.name}'
            if field_name in self.cleaned_data:
                val = self.cleaned_data[field_name]
                instance.set_extra_value(col.name, str(val) if val is not None else '')
        if commit:
            instance.save()
        return instance


class ImportForm(forms.Form):
    FILE_FORMAT_CHOICES = [('csv', 'CSV'), ('xlsx', 'Excel (.xlsx)'), ('json', 'JSON')]
    file = forms.FileField(widget=forms.FileInput(attrs={'class': 'form-input', 'accept': '.csv,.xlsx,.json'}))
    file_format = forms.ChoiceField(choices=FILE_FORMAT_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    skip_errors = forms.BooleanField(required=False, initial=True, label='Skip rows with errors and continue import',
                                     widget=forms.CheckboxInput(attrs={'class': 'form-checkbox'}))
