"""
crm/views.py

Views for Contacts, Notes (activity log), Opportunities, and Pipeline Kanban.
All data is scoped to request.user.company (multi-tenant safe).
"""

from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from employees.models import Employee

from finance.models import Account, Transaction

from .forms import ContactForm, MarkPaidForm, NoteForm, OpportunityForm
from .models import Contact, Note, Opportunity

CRM_ROLES = ['admin', 'manager', 'secretary']


# ---------------------------------------------------------------------------
# Dashboard / Index
# ---------------------------------------------------------------------------

@role_required(*CRM_ROLES)
def index(request):
    company = request.user.company
    today = timezone.localdate()

    contacts_count = Contact.objects.filter(company=company).count()

    opp_qs = Opportunity.objects.filter(company=company)
    open_pipeline = opp_qs.exclude(stage__in=['won', 'lost']).aggregate(t=Sum('value'))['t'] or 0
    won_value = opp_qs.filter(stage='won').aggregate(t=Sum('value'))['t'] or 0
    overdue_followups = opp_qs.filter(
        follow_up_date__lt=today,
        stage__in=['prospect', 'qualified', 'proposal'],
    ).count()

    # Stage counts for mini pipeline bar
    stage_counts = {s: 0 for s, _ in Opportunity.STAGE_CHOICES}
    for row in opp_qs.values('stage').annotate(n=Count('id')):
        stage_counts[row['stage']] = row['n']

    # Recent follow-ups due today or overdue
    due_followups = (
        opp_qs
        .filter(follow_up_date__lte=today, stage__in=['prospect', 'qualified', 'proposal'])
        .select_related('contact', 'assigned_to__user')
        .order_by('follow_up_date')[:5]
    )

    open_opportunity_count = opp_qs.exclude(stage__in=['won', 'lost']).count()

    context = {
        'contacts_count': contacts_count,
        'total_contacts': contacts_count,
        'open_pipeline': open_pipeline,
        'won_value': won_value,
        'overdue_followups': overdue_followups,
        'overdue_opportunities': list(opp_qs.filter(
            follow_up_date__lt=today,
            stage__in=['prospect', 'qualified', 'proposal'],
        ).select_related('contact').order_by('follow_up_date')[:5]),
        'open_opportunity_count': open_opportunity_count,
        'stage_counts': stage_counts,
        'due_followups': due_followups,
    }
    return render(request, 'crm/index.html', context)


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

@role_required(*CRM_ROLES)
def contact_list(request):
    company = request.user.company
    qs = (
        Contact.objects
        .filter(company=company)
        .annotate(
            opp_count=Count('opportunities'),
            total_pipeline_value=Sum(
                'opportunities__value',
                filter=Q(opportunities__stage__in=['prospect', 'qualified', 'proposal']),
            ),
        )
        .order_by('name')
    )

    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(
            Q(name__icontains=query) |
            Q(email__icontains=query) |
            Q(organization__icontains=query) |
            Q(phone__icontains=query)
        )

    org_filter = request.GET.get('organization', '').strip()
    if org_filter:
        qs = qs.filter(organization__icontains=org_filter)

    paginator = Paginator(qs, 25)
    page = request.GET.get('page')
    try:
        contacts = paginator.page(page)
    except PageNotAnInteger:
        contacts = paginator.page(1)
    except EmptyPage:
        contacts = paginator.page(paginator.num_pages)

    # Distinct organizations for filter dropdown
    organizations = (
        Contact.objects
        .filter(company=company)
        .exclude(organization='')
        .values_list('organization', flat=True)
        .distinct()
        .order_by('organization')
    )

    return render(request, 'crm/contact_list.html', {
        'contacts': contacts,
        'query': query,
        'org_filter': org_filter,
        'organizations': organizations,
    })


@role_required(*CRM_ROLES)
def contact_detail(request, pk):
    company = request.user.company
    contact = get_object_or_404(Contact, pk=pk, company=company)
    notes = contact.notes.select_related('author').order_by('-created_at')
    opportunities = contact.opportunities.select_related('assigned_to__user').order_by('-created_at')
    note_form = NoteForm()
    return render(request, 'crm/contact_detail.html', {
        'contact': contact,
        'notes': notes,
        'opportunities': opportunities,
        'note_form': note_form,
    })


@role_required(*CRM_ROLES)
def contact_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.company = company
            contact.save()
            messages.success(request, f'Contact "{contact.name}" created.')
            return redirect('crm:contact_detail', pk=contact.pk)
    else:
        form = ContactForm()
    return render(request, 'crm/contact_form.html', {'form': form, 'title': 'New Contact'})


@role_required(*CRM_ROLES)
def contact_edit(request, pk):
    company = request.user.company
    contact = get_object_or_404(Contact, pk=pk, company=company)
    if request.method == 'POST':
        form = ContactForm(request.POST, instance=contact)
        if form.is_valid():
            form.save()
            messages.success(request, 'Contact updated.')
            return redirect('crm:contact_detail', pk=contact.pk)
    else:
        form = ContactForm(instance=contact)
    return render(request, 'crm/contact_form.html', {'form': form, 'title': 'Edit Contact'})


@role_required(*CRM_ROLES)
def contact_delete(request, pk):
    company = request.user.company
    contact = get_object_or_404(Contact, pk=pk, company=company)
    if request.method == 'POST':
        name = contact.name
        contact.delete()
        messages.success(request, f'Contact "{name}" deleted.')
        return redirect('crm:contact_list')
    return render(request, 'crm/contact_confirm_delete.html', {'contact': contact})


# ---------------------------------------------------------------------------
# Notes (activity log)
# ---------------------------------------------------------------------------

@role_required(*CRM_ROLES)
@require_POST
def note_add(request, contact_pk):
    company = request.user.company
    contact = get_object_or_404(Contact, pk=contact_pk, company=company)
    form = NoteForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.company = company
        note.contact = contact
        note.author = request.user
        note.save()
        messages.success(request, 'Note added.')
    else:
        messages.error(request, 'Could not save note. Please check the form.')
    return redirect('crm:contact_detail', pk=contact_pk)


@role_required(*CRM_ROLES)
def note_delete(request, pk):
    company = request.user.company
    note = get_object_or_404(Note, pk=pk, company=company)
    contact_pk = note.contact_id
    if request.method == 'POST':
        note.delete()
        messages.success(request, 'Note deleted.')
    return redirect('crm:contact_detail', pk=contact_pk)


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------

@role_required(*CRM_ROLES)
def opportunity_list(request):
    company = request.user.company
    qs = (
        Opportunity.objects
        .filter(company=company)
        .select_related('contact', 'assigned_to__user')
        .order_by('-created_at')
    )

    # Filters
    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(
            Q(title__icontains=query) |
            Q(contact__name__icontains=query) |
            Q(contact__organization__icontains=query)
        )

    stage_filter = request.GET.get('stage', '').strip()
    if stage_filter:
        qs = qs.filter(stage=stage_filter)

    assigned_filter = request.GET.get('assigned_to', '').strip()
    if assigned_filter:
        qs = qs.filter(assigned_to_id=assigned_filter)

    overdue_only = request.GET.get('overdue') == '1'
    today = timezone.localdate()
    if overdue_only:
        qs = qs.filter(follow_up_date__lt=today, stage__in=['prospect', 'qualified', 'proposal'])

    paginator = Paginator(qs, 25)
    page = request.GET.get('page')
    try:
        opportunities = paginator.page(page)
    except PageNotAnInteger:
        opportunities = paginator.page(1)
    except EmptyPage:
        opportunities = paginator.page(paginator.num_pages)

    employees = Employee.objects.filter(company=company, status='active').select_related('user')

    return render(request, 'crm/opportunity_list.html', {
        'opportunities': opportunities,
        'query': query,
        'stage_filter': stage_filter,
        'assigned_filter': assigned_filter,
        'overdue_only': overdue_only,
        'stage_choices': Opportunity.STAGE_CHOICES,
        'employees': employees,
        'today': today,
    })


@role_required(*CRM_ROLES)
def opportunity_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = OpportunityForm(request.POST, company=company)
        if form.is_valid():
            opp = form.save(commit=False)
            opp.company = company
            opp.created_by = request.user
            opp.save()
            messages.success(request, f'Opportunity "{opp.title}" created.')
            return redirect('crm:opportunity_list')
    else:
        form = OpportunityForm(company=company)
    return render(request, 'crm/opportunity_form.html', {'form': form, 'title': 'New Opportunity'})


@role_required(*CRM_ROLES)
def opportunity_edit(request, pk):
    company = request.user.company
    opp = get_object_or_404(Opportunity, pk=pk, company=company)
    if request.method == 'POST':
        form = OpportunityForm(request.POST, instance=opp, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, 'Opportunity updated.')
            return redirect('crm:opportunity_list')
    else:
        form = OpportunityForm(instance=opp, company=company)
    return render(request, 'crm/opportunity_form.html', {'form': form, 'title': 'Edit Opportunity'})


@role_required(*CRM_ROLES)
def opportunity_delete(request, pk):
    company = request.user.company
    opp = get_object_or_404(Opportunity, pk=pk, company=company)
    if request.method == 'POST':
        title = opp.title
        opp.delete()
        messages.success(request, f'Opportunity "{title}" deleted.')
        return redirect('crm:opportunity_list')
    return render(request, 'crm/opportunity_confirm_delete.html', {'opportunity': opp})


@role_required(*CRM_ROLES)
@require_POST
def opportunity_advance_stage(request, pk):
    """AJAX endpoint: advance an opportunity to a new stage."""
    company = request.user.company
    opp = get_object_or_404(Opportunity, pk=pk, company=company)
    old_stage = opp.stage
    new_stage = request.POST.get('stage', '')
    try:
        opp.advance_stage(new_stage)

        # Create notifications for important stage changes
        if new_stage in ['won', 'lost'] and old_stage != new_stage:
            from notifications.utils import create_notification
            from django.contrib.auth import get_user_model
            User = get_user_model()

            # Notify managers and the person who created the opportunity
            recipients = set()

            # Add managers
            managers = User.objects.filter(company=company, role='manager')
            recipients.update(managers)

            # Add the opportunity creator if different from current user
            if opp.created_by and opp.created_by != request.user:
                recipients.add(opp.created_by)

            # Add assigned employee if exists
            if opp.assigned_to and opp.assigned_to.user != request.user:
                recipients.add(opp.assigned_to.user)

            for recipient in recipients:
                create_notification(
                    user=recipient,
                    notification_type=f'opportunity_{new_stage}',
                    title=f'Opportunity {new_stage.title()}: {opp.title}',
                    message=f'Opportunity "{opp.title}" with {opp.contact.name} has been marked as {new_stage}. Value: ${opp.value}.',
                    related_object=opp
                )

        return JsonResponse({'status': 'ok', 'stage': opp.stage, 'label': opp.get_stage_display()})
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


# ---------------------------------------------------------------------------
# Payment status
# ---------------------------------------------------------------------------

@role_required(*CRM_ROLES)
@require_POST
def opportunity_mark_invoiced(request, pk):
    company = request.user.company
    opp = get_object_or_404(Opportunity, pk=pk, company=company)
    if opp.stage != 'won':
        messages.error(request, 'Only won opportunities can be marked as invoiced.')
        return redirect('crm:opportunity_list')
    if opp.payment_status == 'paid':
        messages.warning(request, 'This opportunity is already paid.')
        return redirect('crm:opportunity_list')
    opp.payment_status = 'invoiced'
    opp.save(update_fields=['payment_status', 'updated_at'])
    messages.success(request, f'"{opp.title}" marked as invoiced.')
    return redirect('crm:opportunity_list')


@role_required(*CRM_ROLES)
def opportunity_mark_paid(request, pk):
    company = request.user.company
    opp = get_object_or_404(Opportunity, pk=pk, company=company)

    if opp.stage != 'won':
        messages.error(request, 'Only won opportunities can be marked as paid.')
        return redirect('crm:opportunity_list')
    if opp.payment_status == 'paid':
        messages.warning(request, 'This opportunity is already paid.')
        return redirect('crm:opportunity_list')

    revenue_accounts = Account.objects.filter(company=company, account_type='revenue')
    if not revenue_accounts.exists():
        messages.error(request, 'No revenue accounts found. Please create one in Finance first.')
        return redirect('crm:opportunity_list')

    if request.method == 'POST':
        form = MarkPaidForm(company, request.POST)
        if form.is_valid():
            account = form.cleaned_data['account']
            date = form.cleaned_data['date']
            notes = form.cleaned_data['notes']
            description = f'CRM — {opp.title} ({opp.contact.name})'
            if notes:
                description += f': {notes}'
            txn = Transaction.objects.create(
                company=company,
                account=account,
                transaction_type='credit',
                amount=opp.value,
                description=description,
                date=date,
                entered_by=request.user,
            )
            opp.payment_status = 'paid'
            opp.revenue_transaction = txn
            opp.save(update_fields=['payment_status', 'revenue_transaction', 'updated_at'])
            messages.success(
                request,
                f'"{opp.title}" marked as paid. FCFA {opp.value:,.0f} credited to {account.name}.',
            )
            return redirect('crm:opportunity_list')
    else:
        form = MarkPaidForm(company)

    return render(request, 'crm/opportunity_mark_paid.html', {
        'form': form,
        'opportunity': opp,
    })


# ---------------------------------------------------------------------------
# Pipeline / Kanban
# ---------------------------------------------------------------------------

@role_required(*CRM_ROLES)
def pipeline(request):
    """Kanban board — opportunities grouped by stage."""
    company = request.user.company
    qs = (
        Opportunity.objects
        .filter(company=company)
        .select_related('contact', 'assigned_to__user')
        .order_by('-value')
    )

    # Optional filter by assignee
    assigned_filter = request.GET.get('assigned_to', '').strip()
    if assigned_filter:
        qs = qs.filter(assigned_to_id=assigned_filter)

    stages = Opportunity.STAGE_CHOICES
    columns = []
    for stage_key, stage_label in stages:
        items = [o for o in qs if o.stage == stage_key]
        total = sum(o.value for o in items)
        columns.append({
            'key': stage_key,
            'label': stage_label,
            'items': items,
            'count': len(items),
            'total': total,
        })

    employees = Employee.objects.filter(company=company, status='active').select_related('user')

    return render(request, 'crm/pipeline.html', {
        'columns': columns,
        'employees': employees,
        'assigned_filter': assigned_filter,
        'stage_choices': stages,
    })