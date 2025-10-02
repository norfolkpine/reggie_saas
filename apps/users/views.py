#from allauth.account.utils import send_email_confirmation
from allauth.account.internal.flows.email_verification import (
    send_verification_email_to_address,
)
from allauth.socialaccount.models import SocialAccount
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.models import UserAPIKey

from .adapter import user_has_valid_totp_device
from .forms import CustomUserChangeForm, UploadAvatarForm
from .helpers import require_email_confirmation, user_has_confirmed_email_address
from .models import CustomUser


@login_required
def profile(request):
    if request.method == "POST":
        form = CustomUserChangeForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            user_before_update = CustomUser.objects.get(pk=user.pk)
            need_to_confirm_email = (
                user_before_update.email != user.email
                and require_email_confirmation()
                and not user_has_confirmed_email_address(user, user.email)
            )
            if need_to_confirm_email:
                # don't change it but instead send a confirmation email
                # email will be changed by signal when confirmed
                new_email = user.email
                # Create an EmailAddress object for the new email
                from allauth.account.models import EmailAddress
                email_address = EmailAddress.objects.create(
                    user=user,
                    email=new_email,
                    verified=False
                )
                send_verification_email_to_address(request, email_address, signup=False)
                user.email = user_before_update.email
                # recreate the form to avoid populating the previous email in the returned page
                form = CustomUserChangeForm(instance=user)
            user.save()

            user_language = user.language
            if user_language and user_language != translation.get_language():
                translation.activate(user_language)
            if user.timezone != timezone.get_current_timezone():
                if user.timezone:
                    timezone.activate(user.timezone)
                else:
                    timezone.deactivate()
            messages.success(request, _("Profile successfully saved."))
    else:
        form = CustomUserChangeForm(instance=request.user)
    return render(
        request,
        "account/profile.html",
        {
            "form": form,
            "active_tab": "profile",
            "page_title": _("Profile"),
            "api_keys": request.user.api_keys.filter(revoked=False),
            "social_accounts": SocialAccount.objects.filter(user=request.user),
            "user_has_valid_totp_device": user_has_valid_totp_device(request.user),
            "now": timezone.now(),
            "current_tz": timezone.get_current_timezone(),
        },
    )


@login_required
@require_POST
def upload_profile_image(request):
    user = request.user
    form = UploadAvatarForm(request.POST, request.FILES)
    if form.is_valid():
        user.avatar = request.FILES["avatar"]
        user.save()
        return HttpResponse(_("Success!"))
    else:
        readable_errors = ", ".join(str(error) for key, errors in form.errors.items() for error in errors)
        return JsonResponse(status=403, data={"errors": readable_errors})


@login_required
@require_POST
def create_api_key(request):
    """Create API key - handles django form submissions"""
    name = request.POST.get("name", "")
    if not name:
        name = f"{request.user.get_display_name()[:40]} API Key"

    _, key = UserAPIKey.objects.create_key(name=name, user=request.user)

    messages.success(
        request,
        _("API Key created. Your key is: {key}. Save this somewhere safe - you will only see it once!").format(
            key=key,
        ),
    )
    return HttpResponseRedirect(reverse("users:user_profile"))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_api_key_json(request):
    """Create API key - handles JSON API requests."""
    name = request.data.get("name", "")
    if not name:
        name = f"{request.user.get_display_name()[:40]} API Key"

    api_key, key = UserAPIKey.objects.create_key(name=name, user=request.user)

    return Response(
        {
            "success": True,
            "message": _("API Key created successfully. Save this somewhere safe - you will only see it once!"),
            "api_key": {
                "name": api_key.name,
                "api_key": key,
                "prefix": api_key.prefix,
                "created": api_key.created,
            },
        }
    )


@login_required
def list_api_keys(request):
    """List API keys - handles both Django template rendering and JSON API requests."""
    api_keys = request.user.api_keys.filter(revoked=False).order_by("-created")

    # Django template response (for profile page)
    return render(
        request,
        "account/profile.html",
        {
            "form": CustomUserChangeForm(instance=request.user),
            "active_tab": "profile",
            "page_title": _("Profile"),
            "api_keys": api_keys,
            "social_accounts": SocialAccount.objects.filter(user=request.user),
            "user_has_valid_totp_device": user_has_valid_totp_device(request.user),
            "now": timezone.now(),
            "current_tz": timezone.get_current_timezone(),
        },
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_api_keys_json(request):
    """List API keys - handles JSON API requests."""
    api_keys = request.user.api_keys.filter(revoked=False).order_by("-created")
    api_keys_data = []
    for api_key in api_keys:
        api_keys_data.append(
            {
                "id": api_key.id,
                "name": api_key.name,
                "prefix": api_key.prefix,
                "created": api_key.created,
            }
        )

    return Response({"success": True, "api_keys": api_keys_data, "count": len(api_keys_data)})


@login_required
@require_POST
def revoke_api_key(request):
    """Revoke API key - handles django form submissions"""
    key_id = request.POST.get("key_id")
    if not key_id:
        messages.error(request, _("Invalid request."))
        return HttpResponseRedirect(reverse("users:user_profile"))

    try:
        api_key = request.user.api_keys.get(id=key_id)
        api_key.revoked = True
        api_key.save()

        messages.success(
            request,
            _("API Key {key} has been revoked. It can no longer be used to access the site.").format(
                key=api_key.prefix,
            ),
        )
        return HttpResponseRedirect(reverse("users:user_profile"))

    except UserAPIKey.DoesNotExist:
        messages.error(request, _("API key not found."))
        return HttpResponseRedirect(reverse("users:user_profile"))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def revoke_api_key_json(request):
    """Revoke API key - handles JSON API requests."""
    key_id = request.data.get("key_id")
    if not key_id:
        return Response({"error": "key_id is required"}, status=400)

    try:
        api_key = request.user.api_keys.get(id=key_id)
        api_key.revoked = True
        api_key.save()

        return Response(
            {
                "success": True,
                "message": _("API Key {key} has been revoked. It can no longer be used to access the site.").format(
                    key=api_key.prefix,
                ),
            }
        )

    except UserAPIKey.DoesNotExist:
        return Response({"error": "API key not found"}, status=404)
