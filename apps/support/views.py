from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .forms import HijackUserForm

CustomUser = get_user_model()

@user_passes_test(lambda u: u.is_superuser, login_url="/404")
@staff_member_required
def hijack_user(request):
    form = HijackUserForm()
    return render(
        request,
        "support/hijack_user.html",
        {
            "active_tab": "support",
            "form": form,
            "redirect_url": settings.LOGIN_REDIRECT_URL,
        },
    )
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_hijack_user(request):
    """
    API endpoint for user impersonation from React.
    Only superusers can impersonate other users.
    """
    if not request.user.is_superuser:
        return Response(
            {"error": "Only superusers can impersonate users"}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    user_id = request.data.get('user_id')
    if not user_id:
        return Response(
            {"error": "user_id is required"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        target_user = CustomUser.objects.get(id=user_id, is_active=True)
    except CustomUser.DoesNotExist:
        return Response(
            {"error": "User not found"}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Store the original user in session for later restoration
    request.session['hijack_original_user_id'] = request.user.id
    
    # Log in as the target user
    login(request, target_user)
    
    return Response({
        "success": True,
        "message": f"Now impersonating {target_user.email}",
        "impersonated_user": {
            "id": target_user.id,
            "email": target_user.email,
            "full_name": target_user.get_full_name()
        }
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_stop_hijack(request):
    """
    API endpoint to stop impersonating and return to original user.
    """
    original_user_id = request.session.get('hijack_original_user_id')
    if not original_user_id:
        return Response(
            {"error": "Not currently impersonating any user"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        original_user = CustomUser.objects.get(id=original_user_id, is_active=True)
    except CustomUser.DoesNotExist:
        return Response(
            {"error": "Original user not found"}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Log back in as the original user
    login(request, original_user)
    
    # Clean up session
    if 'hijack_original_user_id' in request.session:
        del request.session['hijack_original_user_id']
    
    return Response({
        "success": True,
        "message": f"Stopped impersonating, back to {original_user.email}",
        "original_user": {
            "id": original_user.id,
            "email": original_user.email,
            "full_name": original_user.get_full_name()
        }
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_impersonation_status(request):
    """
    API endpoint to check current impersonation status.
    """
    original_user_id = request.session.get('hijack_original_user_id')
    
    if original_user_id:
        try:
            original_user = CustomUser.objects.get(id=original_user_id, is_active=True)
            return Response({
                "is_impersonating": True,
                "impersonated_user": {
                    "id": request.user.id,
                    "email": request.user.email,
                    "full_name": request.user.get_full_name()
                },
                "original_user": {
                    "id": original_user.id,
                    "email": original_user.email,
                    "full_name": original_user.get_full_name()
                }
            })
        except CustomUser.DoesNotExist:
            # Clean up invalid session data
            if 'hijack_original_user_id' in request.session:
                del request.session['hijack_original_user_id']
    
    return Response({
        "is_impersonating": False,
        "impersonated_user": None,
        "original_user": None
    })

