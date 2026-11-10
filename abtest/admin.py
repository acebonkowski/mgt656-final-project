from django.contrib import admin

from abtest.models import Click, Impression


class ReadOnlyAdmin(admin.ModelAdmin):
    """View and delete only: counts must come from real visits."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Impression)
class ImpressionAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "variant", "visitor_id")
    list_filter = ("variant",)


@admin.register(Click)
class ClickAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "impression")
