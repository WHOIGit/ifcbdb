from django.contrib import admin

from .models import ApiKey


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("prefix", "user", "name", "scopes_display", "created_at", "revoked")
    list_filter = ("revoked",)
    search_fields = ("prefix", "user__username", "name")
    readonly_fields = ("prefix", "hashed_key", "description", "created_at", "last_used_at")
    @admin.display(description="Scopes")
    def scopes_display(self, obj):
        return ", ".join(obj.scopes)
