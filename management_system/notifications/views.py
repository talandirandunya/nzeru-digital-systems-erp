from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Notification, NotificationPreference
from .forms import NotificationPreferenceForm
from governance.decorators import capability_required


@capability_required('notifications.view')
def notification_list(request):
    """List user's notifications."""
    # Get filter parameters
    status_filter = request.GET.get('status', 'unread')  # unread, read, archived, all
    type_filter = request.GET.get('type', '')  # notification type filter

    # Base queryset
    notifications = Notification.objects.filter(user=request.user)

    # Apply filters
    if status_filter == 'unread':
        notifications = notifications.filter(is_read=False, is_archived=False)
    elif status_filter == 'read':
        notifications = notifications.filter(is_read=True, is_archived=False)
    elif status_filter == 'archived':
        notifications = notifications.filter(is_archived=True)
    # 'all' shows everything

    if type_filter:
        notifications = notifications.filter(notification_type=type_filter)

    # Pagination
    paginator = Paginator(notifications, 20)
    page = request.GET.get('page')
    try:
        notifications_page = paginator.page(page)
    except:
        notifications_page = paginator.page(1)

    # Get notification counts for badges
    unread_count = Notification.objects.filter(
        user=request.user, is_read=False, is_archived=False
    ).count()

    archived_count = Notification.objects.filter(
        user=request.user, is_archived=True
    ).count()

    context = {
        'notifications': notifications_page,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'notification_types': Notification.NOTIFICATION_TYPES,
        'unread_count': unread_count,
        'archived_count': archived_count,
    }

    return render(request, 'notifications/notification_list.html', context)


@capability_required('notifications.view')
def notification_detail(request, pk):
    """View notification details and mark as read."""
    notification = get_object_or_404(
        Notification,
        pk=pk,
        user=request.user
    )

    # Mark as read if not already
    if not notification.is_read:
        notification.mark_as_read()
        messages.success(request, 'Notification marked as read.')

    context = {
        'notification': notification,
    }

    return render(request, 'notifications/notification_detail.html', context)


@capability_required('notifications.view')
@require_POST
def mark_as_read(request, pk):
    """Mark a notification as read."""
    notification = get_object_or_404(
        Notification,
        pk=pk,
        user=request.user
    )

    notification.mark_as_read()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True})

    messages.success(request, 'Notification marked as read.')
    return redirect('notifications:notification_list')


@capability_required('notifications.view')
@require_POST
def mark_as_unread(request, pk):
    """Mark a notification as unread."""
    notification = get_object_or_404(
        Notification,
        pk=pk,
        user=request.user
    )

    notification.mark_as_unread()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True})

    messages.success(request, 'Notification marked as unread.')
    return redirect('notifications:notification_list')


@capability_required('notifications.view')
@require_POST
def archive_notification(request, pk):
    """Archive a notification."""
    notification = get_object_or_404(
        Notification,
        pk=pk,
        user=request.user
    )

    notification.archive()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True})

    messages.success(request, 'Notification archived.')
    return redirect('notifications:notification_list')


@capability_required('notifications.view')
@require_POST
def unarchive_notification(request, pk):
    """Unarchive a notification."""
    notification = get_object_or_404(
        Notification,
        pk=pk,
        user=request.user
    )

    notification.unarchive()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True})

    messages.success(request, 'Notification unarchived.')
    return redirect('notifications:notification_list')


@capability_required('notifications.view')
@require_POST
def delete_notification(request, pk):
    """Delete a notification."""
    notification = get_object_or_404(
        Notification,
        pk=pk,
        user=request.user
    )

    notification.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True})

    messages.success(request, 'Notification deleted.')
    return redirect('notifications:notification_list')


@capability_required('notifications.view')
@require_POST
def mark_all_read(request):
    """Mark all unread notifications as read."""
    Notification.objects.filter(
        user=request.user,
        is_read=False,
        is_archived=False
    ).update(
        is_read=True,
        read_at=timezone.now()
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True})

    messages.success(request, 'All notifications marked as read.')
    return redirect('notifications:notification_list')


@capability_required('notifications.view')
def notification_preferences(request):
    """Manage user notification preferences."""
    prefs, created = NotificationPreference.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = NotificationPreferenceForm(request.POST, instance=prefs)
        if form.is_valid():
            form.save()
            messages.success(request, 'Notification preferences updated.')
            return redirect('notifications:notification_preferences')
    else:
        form = NotificationPreferenceForm(instance=prefs)

    context = {
        'form': form,
        'preferences': prefs,
    }

    return render(request, 'notifications/notification_preferences.html', context)


@capability_required('notifications.view')
def get_unread_count(request):
    """Get unread notification count and live feed for AJAX requests."""
    unread_qs = Notification.objects.filter(
        user=request.user,
        is_read=False,
        is_archived=False
    )
    count = unread_qs.count()
    
    recent_items = list(unread_qs.order_by('-created_at')[:5].values(
        'id', 'title', 'message', 'notification_type', 'created_at'
    ))
    
    # Format created_at for JSON serialization
    for item in recent_items:
        item['created_at'] = item['created_at'].strftime('%Y-%m-%d %H:%M')

    return JsonResponse({
        'count': count,
        'recent': recent_items
    })
