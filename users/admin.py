from django.contrib import admin

from users.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "role", "status", "email_verified", "is_staff")
    search_fields = ("email", "full_name", "phone")
    list_filter = ("role", "status", "email_verified", "is_staff")
