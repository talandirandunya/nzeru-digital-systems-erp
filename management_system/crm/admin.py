from django.contrib import admin
from .models import Contact, Opportunity

# Register your models here.


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'email', 'phone')
    search_fields = ('name', 'email', 'organization')
    list_filter = ('company',)


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ('title', 'contact', 'stage', 'value', 'company')
    list_filter = ('company', 'stage')
    search_fields = ('title',)
    actions = ['mark_won', 'mark_lost']

    def mark_won(self, request, queryset):
        queryset.update(stage='won')
        self.message_user(request, f"{queryset.count()} opportunity(ies) marked as won.")
    mark_won.short_description = "Mark selected opportunities as won"

    def mark_lost(self, request, queryset):
        queryset.update(stage='lost')
        self.message_user(request, f"{queryset.count()} opportunity(ies) marked as lost.")
    mark_lost.short_description = "Mark selected opportunities as lost"
