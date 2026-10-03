from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from . import notifications
from .currencies import CURRENCIES
from .forms import SiteSettingsForm, StaffUserForm, StaffUserUpdateForm
from .models import SiteSettings
from .permissions import (
    GROUP_DESCRIPTIONS, GROUP_OWNER, PermissionRequiredMixin, role_groups, role_help,
    role_label,
)


class SiteSettingsUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Currency / number format settings for the whole system (owner only)."""

    permission_required = 'core.change_sitesettings'
    model = SiteSettings
    form_class = SiteSettingsForm
    template_name = 'settings/site_settings.html'
    success_url = reverse_lazy('site-settings')

    def get_object(self, queryset=None):
        return SiteSettings.load()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Currency presets so the live preview can react to the selected currency.
        context['currency_presets'] = CURRENCIES
        context['preview_amounts'] = [1234.5, 98765.43, 0.99]
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        settings = self.object
        messages.success(
            self.request,
            'Settings saved. Money is now shown as %s (%s).' % (
                settings.format_money(1234.5), settings.currency_name(),
            ),
        )
        return response


class NotificationListView(LoginRequiredMixin, TemplateView):
    """All current alerts (low stock, orders), grouped by urgency.

    Only the alerts this user's role covers — see ``core.notifications``.
    """

    template_name = 'notifications/notification_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        alerts = notifications.attach_read_state(
            self.request,
            notifications.visible_to(
                notifications.build_notifications(), self.request.user
            ),
        )
        context['notifications'] = alerts
        context['notification_groups'] = notifications.group_by_severity(alerts)
        context['notification_summary'] = notifications.summarise(alerts)
        context['unread_count'] = len(notifications.unread(alerts))
        context['notification_total'] = len(alerts)
        return context


def _safe_redirect(request, fallback='notifications'):
    """Redirect back to `next` when it points at this site, else to `fallback`."""
    target = request.POST.get('next') or ''
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(target)
    return redirect(fallback)


@login_required
@require_POST
def open_notification(request):
    """Mark one alert as read, then continue to the page it points at."""
    key = request.POST.get('key', '').strip()
    if key:
        notifications.acknowledge(request, [key])
    return _safe_redirect(request)


@login_required
@require_POST
def mark_all_notifications_read(request):
    notifications.acknowledge_all(request)
    messages.success(request, 'All notifications marked as read.')
    return _safe_redirect(request)


# ----------------------------------------------------------------------
# Users & Roles — the owner's replacement for the Django admin
# ----------------------------------------------------------------------
class RoleFormMixin:
    """Shared context for the two screens that hand out roles."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['role_help'] = role_help()
        return context


class UserListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Who can sign in, and with which role. Owner only — there is no admin panel."""

    permission_required = 'auth.view_user'
    template_name = 'settings/user_list.html'
    context_object_name = 'staff_users'

    def get_queryset(self):
        return get_user_model().objects.prefetch_related('groups').order_by('username')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # The legend shows how many logins hold each role, so the owner can see at a
        # glance whether the shop is covered.
        context['role_summary'] = [
            {
                'group': group,
                'members': group.user_set.count(),
                'description': GROUP_DESCRIPTIONS.get(group.name, ''),
            }
            for group in role_groups()
        ]
        return context


class UserCreateView(LoginRequiredMixin, RoleFormMixin, PermissionRequiredMixin, CreateView):
    """Add a staff login."""

    permission_required = 'auth.add_user'
    model = get_user_model()
    form_class = StaffUserForm
    template_name = 'settings/user_form.html'
    success_url = reverse_lazy('user-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['heading'] = 'Add a staff login'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'{self.object.username} can now sign in as {role_label(self.object)}.',
        )
        return response


class UserUpdateView(LoginRequiredMixin, RoleFormMixin, PermissionRequiredMixin, UpdateView):
    """Change someone's name, password, roles or access — including your own."""

    permission_required = 'auth.change_user'
    model = get_user_model()
    form_class = StaffUserUpdateForm
    template_name = 'settings/user_form.html'
    success_url = reverse_lazy('user-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['heading'] = f'Edit {self.object.username}'
        context['editing_self'] = self.object.pk == self.request.user.pk
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['editor'] = self.request.user
        return kwargs

    def _another_active_owner(self):
        """True when someone else still holds Owner, so stepping down is safe."""
        return (
            get_user_model().objects
            .filter(is_active=True, groups__name=GROUP_OWNER)
            .exclude(pk=self.object.pk)
            .exists()
        )

    def form_valid(self, form):
        editing_self = form.instance.pk == self.request.user.pk
        response = super().form_valid(form)

        if not editing_self:
            messages.success(
                self.request,
                f'{self.object.username} is now {role_label(self.object)}.',
            )
            return response

        # Editing your own login: the role you ticked applies straight away — the
        # sidebar re-filters on the next page load. We only step in to stop the shop
        # ending up with no way back in (your own account switched off, or the last
        # remaining Owner demoted out of the Users & Roles page).
        undone = []
        if not self.object.is_active:
            self.object.is_active = True
            undone.append('switched your own account back on')
        owner = Group.objects.filter(name=GROUP_OWNER).first()
        if (
            owner
            and not self._another_active_owner()
            and not self.object.groups.filter(pk=owner.pk).exists()
        ):
            self.object.groups.add(owner)
            undone.append('kept your own Owner role')
        if undone:
            self.object.save()
            messages.warning(
                self.request,
                'You are the last Owner, so to keep you from locking yourself out we '
                + ' and '.join(undone) + '.',
            )
        else:
            messages.success(
                self.request, f'Your account was saved. You are now {role_label(self.object)}.'
            )
        if not self.object.has_perm('auth.view_user'):
            # They just handed their own Owner role over — land on a page they can
            # still open instead of bouncing them straight into a 403.
            return redirect('dashboard')
        return response


