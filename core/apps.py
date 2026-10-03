from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'System Settings'

    def ready(self):
        """Keep the Owner / Sell / Stock / SellerStock roles in sync.

        ``post_migrate`` is sent once per installed app, in ``INSTALLED_APPS``
        order, so we wait for the *last* app that has models: by then every
        permission of every app exists (including our own ``inventory``,
        ``sales`` and ``operations``), and the four roles can be filled in one
        go. That also covers the throw-away database the test runner builds.
        """
        from django.apps import apps as django_apps
        from django.db.models.signals import post_migrate

        from .permissions import sync_groups

        def _last_app_with_models():
            with_models = [
                config for config in django_apps.get_app_configs()
                if config.models_module is not None
            ]
            return with_models[-1] if with_models else None

        def _sync_groups(sender, **kwargs):
            if sender is not _last_app_with_models():
                return
            sync_groups(
                verbosity=kwargs.get('verbosity', 1),
                stdout=kwargs.get('stdout'),
            )

        post_migrate.connect(_sync_groups, dispatch_uid='core.sync_groups')


