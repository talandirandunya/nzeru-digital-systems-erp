from django.contrib import admin
from .models import (
    Position, LeaveRequest, SalaryComponent, PayrollPeriod,
    PayrollEntry, PayrollEntryComponent, Payslip,
    PerformanceGoal, PerformanceReview, PerformanceReviewComment,
    TrainingCourse, TrainingSession, EmployeeTraining, Skill, EmployeeSkill,
)

# Register your models here.


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'salary_grade')
    list_filter = ('company',)
    search_fields = ('title',)


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'start_date', 'end_date', 'status')
    list_filter = ('company', 'leave_type', 'status')
    date_hierarchy = 'start_date'
    actions = ['approve_requests', 'deny_requests']

    def approve_requests(self, request, queryset):
        queryset.update(status='approved')
        self.message_user(request, f"{queryset.count()} leave(s) approved.")
    approve_requests.short_description = "Approve selected leave requests"

    def deny_requests(self, request, queryset):
        queryset.update(status='denied')
        self.message_user(request, f"{queryset.count()} leave(s) denied.")
    deny_requests.short_description = "Deny selected leave requests"


# Payroll Admin
# ---------------------------------------------------------------------------

class PayrollEntryComponentInline(admin.TabularInline):
    model = PayrollEntryComponent
    extra = 0
    fields = ('component', 'amount', 'notes')
    readonly_fields = ('component', 'amount')


@admin.register(SalaryComponent)
class SalaryComponentAdmin(admin.ModelAdmin):
    list_display = ('name', 'component_type', 'company', 'is_active')
    list_filter = ('company', 'component_type', 'is_active')
    search_fields = ('name', 'description')


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ('period_type', 'start_date', 'end_date', 'company', 'status', 'total_net_pay')
    list_filter = ('company', 'period_type', 'status', 'start_date')
    search_fields = ('company__name',)
    readonly_fields = ('total_earnings', 'total_deductions', 'total_net_pay', 'processed_at')
    date_hierarchy = 'end_date'

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj and obj.status != 'draft':
            readonly.extend(['period_type', 'start_date', 'end_date'])
        return readonly


@admin.register(PayrollEntry)
class PayrollEntryAdmin(admin.ModelAdmin):
    list_display = ('employee', 'payroll_period', 'base_salary', 'gross_earnings', 'net_pay')
    list_filter = ('payroll_period__company', 'payroll_period__status')
    search_fields = ('employee__user__last_name', 'employee__user__first_name')
    inlines = [PayrollEntryComponentInline]
    readonly_fields = ('gross_earnings', 'total_deductions', 'tax_amount', 'net_pay')


@admin.register(PayrollEntryComponent)
class PayrollEntryComponentAdmin(admin.ModelAdmin):
    list_display = ('payroll_entry', 'component', 'amount')
    list_filter = ('component__component_type', 'component__company')
    search_fields = ('payroll_entry__employee__user__last_name', 'component__name')


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ('payslip_number', 'payroll_entry', 'issued_date', 'email_sent')
    list_filter = ('issued_date', 'email_sent', 'payroll_entry__payroll_period__company')
    search_fields = ('payslip_number', 'payroll_entry__employee__user__last_name')
    date_hierarchy = 'issued_date'
    readonly_fields = ('payslip_number', 'issued_date')


@admin.register(PerformanceGoal)
class PerformanceGoalAdmin(admin.ModelAdmin):
    list_display = ('title', 'employee', 'company', 'status', 'progress', 'end_date')
    list_filter = ('company', 'status')
    search_fields = ('title', 'description', 'employee__user__last_name', 'employee__user__first_name')
    date_hierarchy = 'end_date'


@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ('employee', 'reviewer', 'review_date', 'status', 'rating')
    list_filter = ('company', 'status', 'rating')
    search_fields = (
        'employee__user__last_name', 'reviewer__user__last_name',
        'strengths', 'improvements', 'summary'
    )
    date_hierarchy = 'review_date'


@admin.register(PerformanceReviewComment)
class PerformanceReviewCommentAdmin(admin.ModelAdmin):
    list_display = ('review', 'author', 'created_at')
    list_filter = ('review__status', 'author')
    search_fields = ('comment',)
    date_hierarchy = 'created_at'


class TrainingSessionInline(admin.TabularInline):
    model = TrainingSession
    extra = 0
    fields = ('start_date', 'end_date', 'status', 'location')
    readonly_fields = ('start_date', 'end_date')


class EmployeeTrainingInline(admin.TabularInline):
    model = EmployeeTraining
    extra = 0
    fields = ('employee', 'status', 'enrollment_date')
    readonly_fields = ('enrollment_date',)


@admin.register(TrainingCourse)
class TrainingCourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'course_type', 'provider', 'duration_hours', 'cost', 'company', 'is_active')
    list_filter = ('company', 'course_type', 'is_active')
    search_fields = ('title', 'description', 'provider')
    inlines = [TrainingSessionInline]


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ('course', 'start_date', 'end_date', 'status', 'location', 'instructor')
    list_filter = ('course__company', 'status', 'start_date')
    search_fields = ('course__title', 'instructor', 'location')
    date_hierarchy = 'start_date'
    inlines = [EmployeeTrainingInline]


@admin.register(EmployeeTraining)
class EmployeeTrainingAdmin(admin.ModelAdmin):
    list_display = ('employee', 'session', 'status', 'enrollment_date', 'completion_date', 'score')
    list_filter = ('session__course__company', 'status', 'enrollment_date')
    search_fields = ('employee__user__last_name', 'employee__user__first_name', 'session__course__title')
    date_hierarchy = 'enrollment_date'


class EmployeeSkillInline(admin.TabularInline):
    model = EmployeeSkill
    extra = 0
    fields = ('skill', 'proficiency_level', 'assessment_date')
    readonly_fields = ('assessment_date',)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'company', 'is_active')
    list_filter = ('company', 'category', 'is_active')
    search_fields = ('name', 'description')
    inlines = [EmployeeSkillInline]


@admin.register(EmployeeSkill)
class EmployeeSkillAdmin(admin.ModelAdmin):
    list_display = ('employee', 'skill', 'proficiency_level', 'assessment_date', 'assessed_by')
    list_filter = ('skill__company', 'proficiency_level', 'assessment_date')
    search_fields = ('employee__user__last_name', 'employee__user__first_name', 'skill__name')
    date_hierarchy = 'assessment_date'
