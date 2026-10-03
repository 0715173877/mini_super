"""Create/refresh the four shop roles (Owner, Sell, Stock, SellerStock).

The same synchronisation happens automatically after every ``migrate``; this
command is for when you want to *see* it, or to hand the Owner role to the first
person on a fresh install:

    python manage.py setup_groups --owner carl
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.permissions import (
    GROUP_DESCRIPTIONS, GROUP_ORDER, GROUP_OWNER, assign_role, sync_groups,
)


class Command(BaseCommand):
    help = 'Create or refresh the Owner, Sell, Stock and SellerStock role groups.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--owner',
            action='append',
            default=[],
            metavar='USERNAME',
            help='Also give this existing user the Owner role (repeatable).',
        )

    def handle(self, *args, **options):
        summary = sync_groups(verbosity=options['verbosity'], stdout=self.stdout)

        if options['verbosity'] >= 2:
            for name in GROUP_ORDER:
                self.stdout.write(
                    f'  {name}: {summary[name]} permissions — {GROUP_DESCRIPTIONS[name]}'
                )

        users = get_user_model().objects
        for username in options['owner']:
            try:
                user = users.get(username=username)
            except users.model.DoesNotExist:
                raise CommandError(f'No user called {username!r}.')
            assign_role(user, GROUP_OWNER)
            self.stdout.write(self.style.SUCCESS(
                f'{username} is now an Owner.'
            ))
