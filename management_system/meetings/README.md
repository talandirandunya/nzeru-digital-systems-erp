# Meeting Reports Module Documentation

## Overview

The **Meetings** module is a comprehensive system for managing meeting reports, action items, and team collaboration. It provides a complete workflow for scheduling meetings, recording detailed notes, tracking action items, and managing meeting attachments.

## Features

### 1. **Meeting Management**
- **Create & Schedule Meetings**: Schedule meetings with multiple attendees
- **Meeting Types**: Support for various meeting types:
  - Team Meetings
  - 1-on-1 Meetings
  - Stakeholder Meetings
  - Board Meetings
  - Client Meetings
  - Training Sessions
  - Brainstorming Sessions
  - Reviews
  - Planning Sessions
  - Other

- **Meeting Status Tracking**: scheduled, in_progress, completed, cancelled, rescheduled
- **Priority Levels**: Low, Medium, High
- **Attendee Management**: Add multiple employees as meeting participants
- **Location Tracking**: Physical location or video conference link

### 2. **Meeting Notes & Documentation**
- **Comprehensive Note Taking**:
  - Agenda documentation
  - Discussion summaries
  - Key decisions and resolutions
  - Risk identification
  - Next steps planning
  
- **Document Upload**: Upload Word, Excel, PDF, and other formats as meeting reports
- **Version Control**: Track when notes were created and last edited

### 3. **Action Item Management**
- **Create Action Items**: Define tasks that need to be completed from meeting discussions
- **Assignment**: Assign action items to specific team members
- **Due Date Tracking**: Set deadlines for each action item
- **Status Management**: Track progress (Pending, In Progress, Completed, On Hold, Cancelled, Overdue)
- **Priority Levels**: Categorize importance of action items
- **Completion Tracking**: Monitor progress percentage and actual completion dates
- **Overdue Detection**: Automatically identify overdue items

### 4. **File Attachments**
- **Multiple File Support**: Upload documents, presentations, spreadsheets, images
- **File Types**:
  - Documents: PDF, Word (.doc, .docx), Text
  - Spreadsheets: Excel (.xls, .xlsx), CSV
  - Presentations: PowerPoint (.ppt, .pptx)
  - Images: PNG, JPG, GIF
  - Archives: ZIP files
  
- **File Organization**: Categorize attachments (Agenda, Handout, Presentation, Minutes, Report, Spreadsheet, Other)
- **Download Capability**: Easy access to all meeting documents
- **Upload Tracking**: Know who uploaded each file and when

### 5. **Reporting & Analytics**
- **Meeting Dashboard**: Overview of all meetings and statistics
- **Analytics Reports**:
  - Total meetings count
  - Meetings by type breakdown
  - Meetings by status summary
  - Action item completion rate
  - Overdue items tracking
  
- **Charts & Visualizations**: Interactive charts for data analysis
- **Detailed Statistics**: Comprehensive metrics and KPIs

## Database Models

### Meeting Model
```python
Meeting
├── company (ForeignKey)
├── title
├── description
├── meeting_type
├── scheduled_date
├── actual_start / actual_end
├── location
├── organizer (ForeignKey → Employee)
├── attendees (ManyToMany → Employee)
├── status (choices)
├── priority
├── created_by (ForeignKey → User)
└── timestamps (created_at, updated_at)
```

### MeetingNote Model
```python
MeetingNote
├── meeting (OneToOne)
├── agenda
├── discussion_summary
├── decisions_made
├── risks_identified
├── next_steps
├── report_document (FileField)
├── last_edited_by (ForeignKey → User)
└── timestamps
```

### ActionItem Model
```python
ActionItem
├── meeting (ForeignKey)
├── title
├── description
├── assigned_to (ForeignKey → Employee)
├── due_date
├── status (choices)
├── priority
├── actual_completion_date
├── completion_percentage (0-100)
├── notes
└── timestamps
```

### MeetingAttachment Model
```python
MeetingAttachment
├── meeting (ForeignKey)
├── title
├── file_type (choices)
├── file (FileField)
├── uploaded_by (ForeignKey → User)
├── uploaded_at
└── description
```

## Views & URL Routes

### Dashboard
- Route: `/meetings/`
- Displays: Statistics, upcoming meetings, recent meetings, personal action items

### Meeting Management
- List: `/meetings/list/` - View all meetings
- Create: `/meetings/create/` - Create a new meeting
- Detail: `/meetings/<id>/` - View meeting details
- Edit: `/meetings/<id>/edit/` - Edit meeting information
- Delete: `/meetings/<id>/delete/` - Delete a meeting

### Meeting Notes
- Create: `/meetings/<id>/notes/create/` - Add notes to meeting
- Edit: `/meetings/notes/<id>/edit/` - Edit existing notes

### Action Items
- Create: `/meetings/<id>/action/create/` - Create new action item
- Edit: `/meetings/action/<id>/edit/` - Edit action item
- Delete: `/meetings/action/<id>/delete/` - Delete action item
- Toggle: `/meetings/action/<id>/toggle/` - Mark complete/pending

### Attachments
- Upload: `/meetings/<id>/attachment/upload/` - Upload file
- Download: `/meetings/attachment/<id>/download/` - Download file
- Delete: `/meetings/attachment/<id>/delete/` - Delete attachment

### Reports
- Analytics: `/meetings/report/` - View analytics and reports

## Permission Levels

### View Permission (`MEETINGS_VIEW_ROLES`)
- admin
- hr_manager
- manager
- secretary
- accountant
- employee

### Write Permission (`MEETINGS_WRITE_ROLES`)
- admin
- hr_manager
- manager
- secretary

### Delete Permission (`MEETINGS_DELETE_ROLES`)
- admin
- manager

### Report Permission (`MEETINGS_REPORT_ROLES`)
- admin
- manager
- accountant

## Forms

### MeetingForm
Creates/edits meeting details with multiple attendee selection

### MeetingNoteForm
Used for recording comprehensive meeting notes and uploading documents

### ActionItemForm
For creating and editing action items with full tracking capabilities

### MeetingAttachmentForm
Simple form for uploading meeting-related files

### QuickMeetingForm
Simplified form for quick meeting creation

### MeetingFilterForm
Advanced filtering for meeting list view

## Usage Examples

### Create a Meeting
1. Click "New Meeting" button
2. Fill in title, type, date/time
3. Select organizer and attendees
4. Set priority level
5. Add location or video link
6. Save

### Record Meeting Notes
1. View meeting details
2. Click "Add Notes" button
3. Enter agenda, discussion summary, decisions
4. Upload report document (Word, PDF, etc.)
5. Save notes

### Create Action Items
1. From meeting detail page, click "Create Action Item"
2. Enter task title and description
3. Assign to team member
4. Set due date and priority
5. Save

### Track Progress
1. Dashboard shows overview of all action items
2. Click on meeting to see action items
3. Edit action items to update progress
4. Mark as completed when done

### Generate Reports
1. Go to Meeting Reports section
2. View analytics charts and statistics
3. Download or share reports

## File Upload Configuration

The application supports uploading the following file types:
- **Documents**: PDF, MS Word (DOC, DOCX), TXT
- **Spreadsheets**: Excel (XLS, XLSX)
- **Presentations**: PowerPoint (PPT, PPTX)
- **Images**: PNG, JPG, JPEG, GIF
- **Other**: ZIP, CSV

Maximum file size and storage location are configured in Django settings.

## Integration with Other Modules

### Employees
- Uses Employee model for attendees and assignees
- Links to Department and User models

### Accounts
- Company scoping for multi-tenant functionality
- Role-based permission system
- User tracking for audit purposes

### Dashboard
- Displays meeting statistics
- Shows upcoming meetings
- Lists personal action items

## Best Practices

1. **Consistent Naming**: Use clear, descriptive titles for meetings and action items
2. **Timely Updates**: Record notes immediately after meetings
3. **Clear Assignments**: Always assign action items to specific people
4. **Priority Management**: Use priority levels appropriately
5. **Regular Follow-up**: Check on overdue action items
6. **Document Upload**: Keep meeting documents organized with descriptive titles
7. **Completion Tracking**: Mark action items complete when finished

## Admin Interface

The meetings app includes comprehensive Django admin interface for:
- Meeting management
- Filtering by type, status, priority, date
- Bulk operations on action items
- Attachment management
- Audit trail viewing

## Performance Considerations

- Meetings are indexed by company, status, and date
- Action items are indexed for efficient querying
- Querysets use `select_related` and `prefetch_related` for optimization
- Pagination prevents loading large datasets

## Future Enhancement Ideas

1. **Recurring Meetings**: Support for recurring meeting schedules
2. **Email Notifications**: Send reminders for upcoming meetings and overdue actions
3. **Calendar Integration**: Sync with calendar systems
4. **Minutes Search**: Full-text search across meeting notes
5. **Meeting Templates**: Pre-defined meeting formats
6. **Attendance Reports**: Track attendance patterns
7. **Video Recording**: Support for meeting recordings
8. **Real-time Collaboration**: Live note editing during meetings
9. **Slack Integration**: Post meeting summaries to Slack
10. **Export Formats**: Export meetings to PDF or Word documents

## Troubleshooting

### Missing Meetings
- Check filters are not hiding meetings
- Verify company context is set correctly
- Ensure you have view permissions

### Action Items Not Updating
- Check that you have edit permissions
- Verify the assigned employee exists
- Check due date is in the future

### File Upload Issues
- Verify file type is supported
- Check file size limits
- Ensure media directory has proper permissions

## Support

For issues, feature requests, or documentation updates, contact the development team.

---

**Version**: 1.0
**Last Updated**: March 2026
**Module Status**: Production Ready
