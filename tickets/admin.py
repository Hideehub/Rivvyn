from django.contrib import admin

from .models import Ticket, TicketNote


class TicketNoteInline(admin.TabularInline):
    model = TicketNote
    extra = 0


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'customer', 'status', 'category', 'urgency', 'created_at')
    list_filter = ('status', 'category', 'urgency')
    search_fields = ('subject', 'description')
    inlines = [TicketNoteInline]


@admin.register(TicketNote)
class TicketNoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'author', 'is_internal', 'created_at')
    list_filter = ('is_internal',)
