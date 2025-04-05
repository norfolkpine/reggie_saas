from django.contrib import admin
from django.contrib.admin import AdminSite


class CustomAdminSite(AdminSite):
    # This determines the order of the apps in the admin interface
    def get_app_list(self, request, app_label=None):
        """
        Return a sorted list of all the installed apps that have been
        registered in this site.
        """
        app_dict = self._build_app_dict(request, app_label)

        # Sort the apps alphabetically.
        app_list = sorted(app_dict.values(), key=lambda x: x["name"].lower())

        # Define your custom ordering here
        app_order = [
            "reggie",  # Reggie app
            "auth",  # Authentication and Authorization
            "users",  # Your custom users app
            "teams",  # Teams app
            "subscriptions",  # Subscriptions app
            "chat",  # Chat app
            "group_chat",  # Group chat app
            "ai_images",  # AI images app
            # Add other apps in your desired order
        ]

        # Sort the app list based on the custom order
        app_list.sort(key=lambda x: app_order.index(x["app_label"]) if x["app_label"] in app_order else len(app_order))

        return app_list


# Create an instance of the custom admin site
custom_admin_site = CustomAdminSite(name="custom_admin")

# Register your models with the custom admin site
# You'll need to re-register all your models here
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User

custom_admin_site.register(User, UserAdmin)
custom_admin_site.register(Group, GroupAdmin)
# Register your other models here...

# Add this after your CustomAdminSite class definition
# Copy all registered models from the default admin site
for model, model_admin in admin.site._registry.items():
    if model not in custom_admin_site._registry:
        custom_admin_site.register(model, type(model_admin))
