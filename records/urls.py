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
    path('columns/', views.ColumnListView.as_view(), name='column_list'),
    path('columns/create/', views.ColumnCreateView.as_view(), name='column_create'),
    path('columns/<int:pk>/edit/', views.ColumnUpdateView.as_view(), name='column_edit'),
    path('columns/<int:pk>/delete/', views.ColumnDeleteView.as_view(), name='column_delete'),
    path('columns/reorder/', views.reorder_columns, name='column_reorder'),
    path('columns/toggle/<int:pk>/', views.toggle_column_visibility, name='column_toggle'),

    # Import / Export
    path('import/', views.ImportView.as_view(), name='import_records'),
    path('export/', views.export_records, name='export_records'),
    path('import/logs/', views.ImportLogListView.as_view(), name='import_logs'),

    # HTMX partials
    path('records/table/', views.RecordTablePartial.as_view(), name='record_table_partial'),
]
