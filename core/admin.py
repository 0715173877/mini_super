from django.contrib import admin

from .models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'currency', 'symbol_override', 'symbol_position',
                    'decimal_places', 'updated_at')
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        # Only one settings row is allowed.
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def response_change(self, request, obj):
        SiteSettings.reset_cache()
        return super().response_change(request, obj)
