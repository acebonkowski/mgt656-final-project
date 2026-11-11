from django.contrib import admin

from accounts.models import LoginCode, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "onboarding_complete", "created_at")
    list_filter = ("onboarding_complete",)
    search_fields = ("user__username", "user__email")


@admin.register(LoginCode)
class LoginCodeAdmin(admin.ModelAdmin):
    # The code hash is never shown.
    list_display = ("email", "sent_at", "expires_at", "failed_attempts", "locked_until")
    fields = ("email", "sent_at", "expires_at", "failed_attempts", "locked_until")
    readonly_fields = fields
    search_fields = ("email",)
