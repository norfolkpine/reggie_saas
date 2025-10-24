from django.contrib import admin
from .models import Person, Document, ActionLog

@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('first_name', 'last_name', 'email')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('person', 'document_type', 'uploaded_at', 'uploaded_by')
    list_filter = ('document_type',)
    search_fields = ('person__first_name', 'person__last_name')
    readonly_fields = ('uploaded_at',)

@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ('person', 'action', 'user', 'timestamp')
    search_fields = ('person__first_name', 'person__last_name', 'action')
    readonly_fields = ('timestamp',)
