from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class RivynUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Rivyn', {'fields': ('role',)}),
    )
    list_display = UserAdmin.list_display + ('role',)
    list_filter = UserAdmin.list_filter + ('role',)
