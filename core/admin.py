from django.contrib import admin

from core.models import AIUsage


@admin.register(AIUsage)
class AIUsageAdmin(admin.ModelAdmin):
    """AI search usage (#36): view to check spend, delete to reset a user's limits."""

    list_display = ("created_at", "kind", "user")
    list_filter = ("kind",)
    search_fields = ("user__username", "user__email")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
