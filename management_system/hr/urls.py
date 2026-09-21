from django.urls import path
from . import views

app_name = 'hr'

urlpatterns = [
    # Dashboard
    path('', views.index, name='index'),

    # Positions
    path('positions/', views.position_list, name='position_list'),
    path('positions/new/', views.position_create, name='position_create'),
    path('positions/<int:pk>/edit/', views.position_edit, name='position_edit'),
    path('positions/<int:pk>/delete/', views.position_delete, name='position_delete'),

    # Leave requests — HR management
    path('leaves/', views.leave_list, name='leave_list'),
    path('leaves/new/', views.leave_create, name='leave_create'),
    path('leaves/<int:pk>/edit/', views.leave_edit, name='leave_edit'),
    path('leaves/<int:pk>/delete/', views.leave_delete, name='leave_delete'),
    path('leaves/<int:pk>/approve/', views.leave_approve, name='leave_approve'),
    path('leaves/<int:pk>/deny/', views.leave_deny, name='leave_deny'),

    # Employee self-service
    path('my-leaves/', views.my_leave_list, name='my_leave_list'),
    path('my-leaves/new/', views.my_leave_create, name='my_leave_create'),

    # Attendance
    path('attendance/', views.attendance_list, name='attendance_list'),
    path('attendance/new/', views.attendance_create, name='attendance_create'),
    path('attendance/me/', views.my_attendance, name='my_attendance'),
    path('attendance/clock-in/', views.attendance_clock_in, name='attendance_clock_in'),
    path('attendance/clock-out/', views.attendance_clock_out, name='attendance_clock_out'),

    # Salary components
    path('components/', views.salary_component_list, name='salary_component_list'),
    path('components/new/', views.salary_component_create, name='salary_component_create'),
    path('components/<int:pk>/edit/', views.salary_component_edit, name='salary_component_edit'),
    path('components/<int:pk>/delete/', views.salary_component_delete, name='salary_component_delete'),

    # Payroll periods
    path('payroll/', views.payroll_period_list, name='payroll_period_list'),
    path('payroll/new/', views.payroll_period_create, name='payroll_period_create'),
    path('payroll/<int:pk>/', views.payroll_period_detail, name='payroll_period_detail'),
    path('payroll/<int:pk>/add-entries/', views.payroll_period_add_entries, name='payroll_period_add_entries'),
    path('payroll/<int:pk>/lock/', views.payroll_period_lock, name='payroll_period_lock'),
    path('payroll/<int:pk>/process/', views.payroll_period_process, name='payroll_period_process'),

    # Payroll entries
    path('entries/<int:pk>/edit/', views.payroll_entry_edit, name='payroll_entry_edit'),
    path('entries/<int:pk>/delete/', views.payroll_entry_delete, name='payroll_entry_delete'),

    # Performance management (Phase 2)
    path('performance/goals/', views.performance_goal_list, name='performance_goal_list'),
    path('performance/goals/new/', views.performance_goal_create, name='performance_goal_create'),
    path('performance/goals/<int:pk>/edit/', views.performance_goal_edit, name='performance_goal_edit'),
    path('performance/goals/<int:pk>/delete/', views.performance_goal_delete, name='performance_goal_delete'),

    path('performance/reviews/', views.performance_review_list, name='performance_review_list'),
    path('performance/reviews/new/', views.performance_review_create, name='performance_review_create'),
    path('performance/reviews/<int:pk>/', views.performance_review_detail, name='performance_review_detail'),
    path('performance/reviews/<int:pk>/edit/', views.performance_review_edit, name='performance_review_edit'),
    path('performance/reviews/<int:pk>/delete/', views.performance_review_delete, name='performance_review_delete'),
    path('performance/reviews/<int:pk>/submit/', views.performance_review_submit, name='performance_review_submit'),
    path('performance/reviews/<int:pk>/complete/', views.performance_review_complete, name='performance_review_complete'),

    path('performance/reviews/<int:pk>/comments/new/', views.performance_review_comment_create, name='performance_review_comment_create'),

    # Training & Development (Phase 3)
    path('training/courses/', views.training_course_list, name='training_course_list'),
    path('training/courses/new/', views.training_course_create, name='training_course_create'),
    path('training/courses/<int:pk>/edit/', views.training_course_edit, name='training_course_edit'),
    path('training/courses/<int:pk>/delete/', views.training_course_delete, name='training_course_delete'),

    path('training/sessions/', views.training_session_list, name='training_session_list'),
    path('training/sessions/new/', views.training_session_create, name='training_session_create'),
    path('training/sessions/<int:pk>/edit/', views.training_session_edit, name='training_session_edit'),
    path('training/sessions/<int:pk>/delete/', views.training_session_delete, name='training_session_delete'),
    path('training/sessions/<int:pk>/enroll/', views.training_session_enroll, name='training_session_enroll'),

    path('training/enrollments/', views.employee_training_list, name='employee_training_list'),
    path('training/enrollments/new/', views.employee_training_enroll, name='employee_training_enroll'),
    path('training/enrollments/<int:pk>/edit/', views.employee_training_edit, name='employee_training_edit'),
    path('training/enrollments/<int:pk>/delete/', views.employee_training_delete, name='employee_training_delete'),
    path('training/enrollments/<int:pk>/complete/', views.employee_training_complete, name='employee_training_complete'),
    path('training/enrollments/<int:pk>/cancel/', views.employee_training_cancel, name='employee_training_cancel'),

    path('training/skills/', views.skill_list, name='skill_list'),
    path('training/skills/new/', views.skill_create, name='skill_create'),
    path('training/skills/<int:pk>/edit/', views.skill_edit, name='skill_edit'),
    path('training/skills/<int:pk>/delete/', views.skill_delete, name='skill_delete'),

    path('training/employee-skills/', views.employee_skill_list, name='employee_skill_list'),
    path('training/employee-skills/new/', views.employee_skill_create, name='employee_skill_create'),
    path('training/employee-skills/<int:pk>/edit/', views.employee_skill_edit, name='employee_skill_edit'),
    path('training/employee-skills/<int:pk>/delete/', views.employee_skill_delete, name='employee_skill_delete'),

    # Payslips
    path('payslips/', views.payslip_list, name='payslip_list'),
    path('payslips/<int:pk>/', views.payslip_detail, name='payslip_detail'),
]