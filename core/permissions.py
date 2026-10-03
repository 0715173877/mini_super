"""The roles of the shop — built on Django groups.

There is no ``role`` column anywhere: a role *is* a
``django.contrib.auth.Group``, and the permissions each one carries are declared
once, in this module. Four roles cover the shop:

===============  =================================================================
Role             What it can reach
===============  =================================================================
``Owner``        Everything: selling, stock, operations, the currency settings and
                 the Users & Roles page — but **not** the Django admin (an owner
                 is not ``is_staff``, so ``/admin/`` stays out of reach).
``Sell``         The selling process: the till (POS), sales history, daily
                 reports, customers, customer returns and the sales report.
``Stock``        The shelf: products, categories, suppliers, purchase orders,
                 received purchases, supplier returns, stock movements, low-stock
                 and expiry alerts, waste, staff shifts and performance.
``SellerStock``  The union of ``Sell`` and ``Stock``, for the one person who does
                 both jobs.
===============  =================================================================

The groups are created and kept up to date automatically after every ``migrate``
(:meth:`core.apps.CoreConfig.ready`) and on demand with
``python manage.py setup_groups`` — so a fresh database, including the throw-away
one the test runner builds, always has them.

Views protect themselves with Django's own machinery
(``PermissionRequiredMixin`` / ``permission_required``) and the templates ask the
same question through ``perms``, so there is only one source of truth: the group
permissions built here.
"""

from django.contrib.auth.mixins import PermissionRequiredMixin as DjangoPermissionRequiredMixin
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

GROUP_OWNER = 'Owner'
GROUP_SELL = 'Sell'
GROUP_STOCK = 'Stock'
GROUP_SELLER_STOCK = 'SellerStock'

#: The four roles, in the order they are shown to the owner.
GROUP_ORDER = (GROUP_OWNER, GROUP_SELL, GROUP_STOCK, GROUP_SELLER_STOCK)

#: How a role is named on screen (the top bar, the user list, ...).
GROUP_LABELS = {
    GROUP_OWNER: 'Owner',
    GROUP_SELL: 'Seller',
    GROUP_STOCK: 'Stock',
    GROUP_SELLER_STOCK: 'Seller + Stock',
}

#: One line per role, for the Users & Roles page and the setup command.
GROUP_DESCRIPTIONS = {
    GROUP_OWNER: (
        'Everything, including the currency settings and this user list — '
        'but not the Django admin panel.'
    ),
    GROUP_SELL: (
        'Selling only: the till, sales history, daily reports, customers and '
        'customer returns.'
    ),
    GROUP_STOCK: (
        'Stock only: products, categories, suppliers, purchase orders, received '
        'purchases, supplier returns, stock movements, expiry alerts, waste, '
        'shifts and performance.'
    ),
    GROUP_SELLER_STOCK: 'Both jobs: everything the Seller and the Stock role can reach.',
}

# Model permissions, written as a compact "vacd" string:
#     v = view, a = add, c = change, d = delete
VERBS = {'v': 'view', 'a': 'add', 'c': 'change', 'd': 'delete'}



def merge_permissions(*specs):
    """Combine several ``{app: {model: 'vacd'}}`` specs into one.

    The flags of a model that appears in more than one spec are unioned, which is
    how ``SellerStock`` (and the owner) are built out of the two job specs.
    """
    merged = {}
    for spec in specs:
        for app_label, models in spec.items():
            for model, flags in models.items():
                known = merged.setdefault(app_label, {}).get(model, '')
                merged[app_label][model] = ''.join(sorted(set(known) | set(flags)))
    return merged


#: What the till needs: sales, their lines, the day's takings, customers and
#: customer returns. Products are *read* through the POS page, which is a sales
#: page, so selling does not depend on the inventory permissions.
SELL_PERMISSIONS = {
    'sales': {
        'customer': 'vacd',
        'customerreturn': 'vac',
        'customerreturnitem': 'vac',
        'sale': 'vacd',
        'saleitem': 'va',
        'dailysummary': 'v',
    },
}

#: What the shelf needs: the whole catalogue, purchasing, stock takes, returns to
#: suppliers, and the store operations that belong with stock (waste, shifts,
#: performance).
STOCK_PERMISSIONS = {
    'inventory': {
        'category': 'vacd',
        'supplier': 'vacd',
        'product': 'vacd',
        'stockmovement': 'va',
        'purchaseorder': 'vacd',
        'purchaseorderitem': 'vacd',
        'supplierreturn': 'vacd',
        'supplierreturnitem': 'vacd',
    },
    'operations': {
        'staff': 'vacd',
        'shift': 'vacd',
        'wasterecord': 'vacd',
        'peakhour': 'vacd',
        'supplierperformance': 'vacd',
    },
}

#: The owner runs the shop: both jobs, the currency settings, and the user list
#: that hands the roles out. Deliberately *not* the Django admin.
OWNER_PERMISSIONS = merge_permissions(
    SELL_PERMISSIONS,
    STOCK_PERMISSIONS,
    {
        'core': {'sitesettings': 'vc'},
        'auth': {'user': 'vac', 'group': 'v'},
    },
)

#: Spec per role — the single place a role's reach is decided.
GROUP_SPECS = {
    GROUP_OWNER: OWNER_PERMISSIONS,
    GROUP_SELL: SELL_PERMISSIONS,
    GROUP_STOCK: STOCK_PERMISSIONS,
    GROUP_SELLER_STOCK: merge_permissions(SELL_PERMISSIONS, STOCK_PERMISSIONS),
}


def permission_codenames(spec):
    """Flatten a spec into the ``{'app.codename', ...}`` strings Django uses."""
    codenames = set()
    for app_label, models in spec.items():
        for model, flags in models.items():
            for flag in flags:
                codenames.add(f'{app_label}.{VERBS[flag]}_{model}')
    return codenames


def declared_permissions():
    """Every ``app.codename`` any role asks for (used by the tests)."""
    codenames = set()
    for spec in GROUP_SPECS.values():
        codenames |= permission_codenames(spec)
    return codenames


def sync_groups(verbosity=1, stdout=None):
    """Create the four roles and make their permissions match :data:`GROUP_SPECS`.

    Idempotent — safe to run after every ``migrate``: a role that already holds
    the right permissions is left alone, a permission that is no longer meant to
    be there is taken away. Returns ``{group_name: permission_count}``.
    """
    available = {
        f'{permission.content_type.app_label}.{permission.codename}': permission
        for permission in Permission.objects.select_related('content_type')
    }

    summary = {}
    missing = set()
    for name in GROUP_ORDER:
        wanted = permission_codenames(GROUP_SPECS[name])
        missing |= wanted - set(available)
        present = sorted(wanted & set(available))
        group, _created = Group.objects.get_or_create(name=name)
        group.permissions.set([available[codename] for codename in present])
        summary[name] = len(present)

    if stdout is not None and verbosity:
        counts = ', '.join(f'{name} ({summary[name]})' for name in GROUP_ORDER)
        stdout.write(f'Roles ready: {counts}')
        if missing:
            stdout.write(
                'Warning: skipped permissions that do not exist in this install: '
                + ', '.join(sorted(missing))
            )
    return summary


def role_groups():
    """The role groups that exist right now, in :data:`GROUP_ORDER` order."""
    by_name = {group.name: group for group in Group.objects.filter(name__in=GROUP_ORDER)}
    return [by_name[name] for name in GROUP_ORDER if name in by_name]


def role_help():
    """``[(name, description), ...]`` for the role legend on screen."""
    return [(name, GROUP_DESCRIPTIONS[name]) for name in GROUP_ORDER]


def group_names(user):
    """The roles this user has, in a stable order (unknown groups come last)."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return []
    names = set(user.groups.values_list('name', flat=True))
    return [name for name in GROUP_ORDER if name in names] + sorted(
        names - set(GROUP_ORDER)
    )


def role_label(user):
    """How to describe this user's access in one line ("Seller + Stock")."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return ''
    if user.is_superuser:
        return 'Administrator'
    names = group_names(user)
    if not names:
        return 'No role'
    return ' + '.join(GROUP_LABELS.get(name, name) for name in names)


def has_role(user, *names):
    """True when the user holds one of these roles (or any role, if none given).

    Superusers — the technical Django administrator — always pass, which is also
    what bootstraps a brand new install: the first account can hand out roles.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    held = set(group_names(user))
    if not names:
        return bool(held)
    return bool(held & set(names))


def assign_role(user, *names):
    """Give ``user`` these roles by name (and return them), for tests and setup."""
    user.groups.add(*[Group.objects.get(name=name) for name in names])
    return user


class PermissionRequiredMixin(DjangoPermissionRequiredMixin):
    """Denied users get a proper 403 page instead of a bounce to the login form.

    Anonymous visitors are still sent to the login form first (that is the only
    way they could ever get in), but someone who *is* signed in and simply does
    not hold the role gets an explanation instead of a login loop.
    """

    raise_exception = True

    def get_permission_denied_message(self):
        return 'Your role does not include this page.'

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        raise PermissionDenied(self.get_permission_denied_message())
