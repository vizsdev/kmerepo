from django.urls import path
from . import views

urlpatterns = [
    # Dashboard / record list
    path('', views.RecordListView.as_view(), name='record_list'),

    # CRUD
    path('records/create/', views.RecordCreateView.as_view(), name='record_create'),
    path('records/<int:pk>/edit/', views.RecordUpdateView.as_view(), name='record_edit'),
    path('records/<int:pk>/delete/', views.RecordDeleteView.as_view(), name='record_delete'),
    path('records/<int:pk>/', views.RecordDetailView.as_view(), name='record_detail'),

    # Bulk actions
    path('records/bulk-delete/', views.bulk_delete, name='bulk_delete'),

    # Column management
    path('columns/toggle/<int:pk>/', views.toggle_column_visibility, name='column_toggle'),

    # Import / Export
    path('import/', views.ImportView.as_view(), name='import_records'),
    path('export/', views.export_records, name='export_records'),
    path('import/logs/', views.ImportLogListView.as_view(), name='import_logs'),
    path('import/logs/export/', views.export_import_log_list, name='export_import_logs'),
    path('import/logs/<int:pk>/records/', views.export_import_log_records, name='export_import_log_records'),
    path('import/logs/<int:pk>/report/', views.export_import_log_report, name='export_import_log_report'),

    # HTMX partials
    path('records/table/', views.RecordTablePartial.as_view(), name='record_table_partial'),
]
