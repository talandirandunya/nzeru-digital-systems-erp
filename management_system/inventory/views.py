from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, F, Case, When, IntegerField
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from django.utils import timezone
import pandas as pd
import io
import json
import math
from datetime import datetime, timedelta

from .models import Stock, StockTransaction, StockCategory
from .forms import StockForm, StockTransactionForm, StockCategoryForm
from governance.models import AuditEvent
from accounts.permissions import (
    INVENTORY_VIEW_ROLES,
    INVENTORY_WRITE_ROLES,
    INVENTORY_MANAGE_ROLES,
    INVENTORY_REPORT_ROLES,
    role_required,
)

@role_required(*INVENTORY_VIEW_ROLES)
def stock_list(request):
    """Display list of stock items with filters"""
    company = request.user.company
    
    # Get all stock items for the company
    stocks = Stock.objects.filter(company=company).select_related(
        'category', 'created_by'
    ).order_by('-created_at')
    
    # Apply search filter
    query = request.GET.get('q', '').strip()
    if query:
        stocks = stocks.filter(
            Q(item_code__icontains=query) |
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(supplier_name__icontains=query)
        )
    
    # Apply category filter
    category_id = request.GET.get('category', '')
    if category_id:
        stocks = stocks.filter(category_id=category_id)
    
    # Apply status filter
    status = request.GET.get('status', '')
    if status == 'low':
        stocks = stocks.filter(quantity__lte=F('reorder_level'))
    elif status == 'out':
        stocks = stocks.filter(quantity=0)
    elif status == 'in_stock':
        stocks = stocks.filter(quantity__gt=F('reorder_level'))
    
    # Get categories for filter dropdown
    categories = StockCategory.objects.filter(company=company).order_by('name')
    
    # Calculate statistics
    total_items = stocks.count()
    total_value = sum(stock.total_value for stock in stocks)
    low_stock_items = stocks.filter(quantity__lte=F('reorder_level')).count()
    out_of_stock_items = stocks.filter(quantity=0).count()
    
    context = {
        'stocks': stocks,
        'categories': categories,
        'query': query,
        'selected_category': category_id,
        'selected_status': status,
        'total_items': total_items,
        'total_value': total_value,
        'low_stock_items': low_stock_items,
        'out_of_stock_items': out_of_stock_items,
    }
    
    return render(request, 'inventory/stock_list.html', context)

@role_required(*INVENTORY_VIEW_ROLES)
def stock_detail(request, pk):
    """Display stock item details"""
    company = request.user.company
    stock = get_object_or_404(
        Stock.objects.select_related('category', 'created_by'), 
        pk=pk, 
        company=company
    )
    
    # Get recent transactions
    recent_transactions = stock.transactions.all().order_by('-transaction_date')[:10]
    
    # Calculate transaction statistics
    total_in = stock.transactions.filter(transaction_type='in').aggregate(Sum('quantity'))['quantity__sum'] or 0
    total_out = stock.transactions.filter(transaction_type='out').aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    context = {
        'stock': stock,
        'recent_transactions': recent_transactions,
        'total_in': total_in,
        'total_out': total_out,
    }
    
    return render(request, 'inventory/stock_detail.html', context)

@role_required(*INVENTORY_WRITE_ROLES)
def stock_create(request):
    """Create new stock item"""
    company = request.user.company
    
    if request.method == 'POST':
        form = StockForm(request.POST, request.FILES, company=company)
        if form.is_valid():
            stock = form.save(commit=False)
            stock.company = company
            stock.created_by = request.user
            
            # Create initial transaction if quantity > 0
            if stock.quantity > 0:
                with transaction.atomic():
                    stock.save()
                    
                    # Create initial stock in transaction
                    StockTransaction.objects.create(
                        company=company,
                        stock=stock,
                        transaction_type='in',
                        quantity=stock.quantity,
                        remarks=f'Initial stock - {stock.quantity} units',
                        user=request.user
                    )
            else:
                stock.save()
            
            messages.success(request, f'Stock item "{stock.name}" created successfully!')
            return redirect('inventory:stock_list')
    else:
        form = StockForm(company=company)
    
    return render(request, 'inventory/stock_form.html', {
        'form': form,
        'title': 'Add New Stock Item'
    })

@role_required(*INVENTORY_WRITE_ROLES)
def stock_edit(request, pk):
    """Edit existing stock item"""
    company = request.user.company
    stock = get_object_or_404(Stock, pk=pk, company=company)
    
    if request.method == 'POST':
        form = StockForm(request.POST, request.FILES, instance=stock, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, f'Stock item "{stock.name}" updated successfully!')
            return redirect('inventory:stock_detail', pk=stock.pk)
    else:
        form = StockForm(instance=stock, company=company)
    
    return render(request, 'inventory/stock_form.html', {
        'form': form,
        'stock': stock,
        'title': 'Edit Stock Item'
    })

@role_required(*INVENTORY_MANAGE_ROLES)
def stock_delete(request, pk):
    """Delete stock item"""
    company = request.user.company
    stock = get_object_or_404(Stock, pk=pk, company=company)
    
    if request.method == 'POST':
        stock_name = stock.name
        stock.delete()
        messages.success(request, f'Stock item "{stock_name}" deleted successfully!')
        return redirect('inventory:stock_list')
    
    return render(request, 'inventory/stock_confirm_delete.html', {'stock': stock})

@role_required(*INVENTORY_MANAGE_ROLES)
def stock_transaction(request, pk):
    """Handle stock transactions (in/out/adjustment)"""
    company = request.user.company
    stock = get_object_or_404(Stock, pk=pk, company=company)
    
    if request.method == 'POST':
        form = StockTransactionForm(request.POST)
        if form.is_valid():
            transaction_obj = form.save(commit=False)
            transaction_obj.company = company
            transaction_obj.stock = stock
            transaction_obj.user = request.user
            
            try:
                with transaction.atomic():
                    # Update stock quantity
                    if transaction_obj.transaction_type == 'in':
                        stock.quantity = F('quantity') + transaction_obj.quantity
                        message = f'Added {transaction_obj.quantity} units to stock.'
                    elif transaction_obj.transaction_type == 'out':
                        if stock.quantity >= transaction_obj.quantity:
                            stock.quantity = F('quantity') - transaction_obj.quantity
                            message = f'Removed {transaction_obj.quantity} units from stock.'
                        else:
                            messages.error(request, 'Insufficient stock for this transaction!')
                            return render(request, 'inventory/stock_transaction.html', {
                                'form': form,
                                'stock': stock
                            })
                    else:  # adjustment
                        stock.quantity = transaction_obj.quantity
                        message = f'Stock quantity adjusted to {transaction_obj.quantity} units.'
                    
                    # Save stock and transaction
                    stock.save()
                    stock.refresh_from_db()
                    transaction_obj.save()
                    AuditEvent.record(actor=request.user, company=company, module='inventory', action='stock_movement_created', obj=transaction_obj, after={'type': transaction_obj.transaction_type, 'quantity': transaction_obj.quantity}, request=request)
                    
                    # Update last_restocked date for stock in transactions
                    if transaction_obj.transaction_type == 'in':
                        stock.last_restocked = timezone.now().date()
                        stock.save()
                    
                    # Check for low stock and create notification
                    if stock.quantity <= stock.reorder_level:
                        from notifications.utils import create_notification
                        from django.contrib.auth import get_user_model
                        User = get_user_model()

                        # Notify stock managers about low stock
                        stock_managers = User.objects.filter(
                            company=company,
                            role='stock_manager'
                        )

                        for manager in stock_managers:
                            # Check if notification already exists for this stock item today
                            from notifications.models import Notification
                            existing_notification = Notification.objects.filter(
                                user=manager,
                                notification_type='low_stock',
                                related_object=stock,
                                created_at__date=timezone.now().date()
                            ).exists()

                            if not existing_notification:
                                create_notification(
                                    user=manager,
                                    notification_type='low_stock',
                                    title=f'Low Stock Alert: {stock.name}',
                                    message=f'Stock item "{stock.name}" (Code: {stock.item_code}) is running low. Current quantity: {stock.quantity}, Reorder level: {stock.reorder_level}.',
                                    related_object=stock
                                )
                    
                    messages.success(request, f'Transaction recorded successfully! {message}')
                    return redirect('inventory:stock_detail', pk=stock.pk)
                    
            except Exception as e:
                messages.error(request, f'Error processing transaction: {str(e)}')
    else:
        form = StockTransactionForm()
    
    return render(request, 'inventory/stock_transaction.html', {
        'form': form,
        'stock': stock
    })

@role_required(*INVENTORY_MANAGE_ROLES)
def stock_transaction_journal(request):
    """Display stock transaction journal"""
    company = request.user.company
    
    # Get all transactions for the company
    transactions = StockTransaction.objects.filter(company=company).select_related(
        'stock', 'user', 'stock__category'
    ).order_by('-transaction_date')
    
    # Apply filters
    stock_id = request.GET.get('stock', '')
    transaction_type = request.GET.get('type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    if stock_id:
        transactions = transactions.filter(stock_id=stock_id)
    
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    if date_from:
        transactions = transactions.filter(transaction_date__date__gte=date_from)
    
    if date_to:
        transactions = transactions.filter(transaction_date__date__lte=date_to)
    
    # Get stocks for filter dropdown
    stocks = Stock.objects.filter(company=company).order_by('name')
    
    context = {
        'transactions': transactions,
        'stocks': stocks,
        'selected_stock': stock_id,
        'selected_type': transaction_type,
        'date_from': date_from,
        'date_to': date_to,
        'TRANSACTION_TYPES': StockTransaction.TRANSACTION_TYPES,
    }
    
    return render(request, 'inventory/stock_transaction_journal.html', context)

@role_required(*INVENTORY_MANAGE_ROLES)
def stock_transaction_export(request):
    """Export stock transactions to Excel"""
    company = request.user.company
    
    # Apply filters
    stock_id = request.GET.get('stock', '')
    transaction_type = request.GET.get('type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    transactions = StockTransaction.objects.filter(company=company).select_related(
        'stock', 'user', 'stock__category'
    ).order_by('-transaction_date')
    
    if stock_id:
        transactions = transactions.filter(stock_id=stock_id)
    
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    if date_from:
        transactions = transactions.filter(transaction_date__date__gte=date_from)
    
    if date_to:
        transactions = transactions.filter(transaction_date__date__lte=date_to)
    
    # Prepare data
    data = []
    for t in transactions:
        data.append({
            'Date': t.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
            'Item Code': t.stock.item_code,
            'Item Name': t.stock.name,
            'Category': t.stock.category.name if t.stock.category else 'N/A',
            'Transaction Type': t.get_transaction_type_display(),
            'Quantity': t.quantity,
            'Unit': t.stock.get_unit_display(),
            'Remarks': t.remarks or '',
            'User': t.user.get_full_name() if t.user else 'System',
            'Location': t.stock.location or '',
            'Unit Price': float(t.stock.cost_price),
            'Total Value': float(t.quantity * t.stock.cost_price),
        })
    
    if not data:
        messages.warning(request, 'No data available for export with current filters.')
        return redirect('inventory:stock_transaction_journal')
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Create Excel file in memory
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Stock Transactions', index=False)
        
        # Auto-adjust column widths
        worksheet = writer.sheets['Stock Transactions']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    buffer.seek(0)
    
    # Create response
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="stock_transactions.xlsx"'
    return response

def _safe_int(val, default=0):
    """Convert a value from an Excel/pandas cell to int, treating NaN/None as default."""
    if val is None:
        return default
    if isinstance(val, float) and math.isnan(val):
        return default
    if isinstance(val, str) and not val.strip():
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_float(val, default=0.0):
    """Convert a value from an Excel/pandas cell to float, treating NaN/None as default."""
    if val is None:
        return default
    if isinstance(val, float) and math.isnan(val):
        return default
    if isinstance(val, str) and not val.strip():
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_str(val, default=''):
    """Convert a value from an Excel/pandas cell to a stripped string, treating NaN/None as default."""
    if val is None:
        return default
    if isinstance(val, float) and math.isnan(val):
        return default
    return str(val).strip()


@role_required(*INVENTORY_WRITE_ROLES)
def stock_import(request):
    """Import stock items from Excel"""
    company = request.user.company
    
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        
        if not excel_file.name.endswith(('.xlsx', '.xls')):
            messages.error(request, 'Please upload a valid Excel file (.xlsx or .xls)')
            return redirect('inventory:stock_import')
        
        try:
            df = pd.read_excel(excel_file)
            required_columns = ['item_code', 'name']
            
            # Check required columns
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                messages.error(request, f'Missing required columns: {", ".join(missing_columns)}')
                return redirect('inventory:stock_import')
            
            success_count = 0
            updated_count = 0
            error_count = 0
            errors = []
            
            # Cache categories
            category_cache = {c.name: c for c in StockCategory.objects.filter(company=company)}
            
            with transaction.atomic():
                for index, row in df.iterrows():
                    row_num = index + 2
                    
                    try:
                        item_code = _safe_str(row.get('item_code'))
                        name = _safe_str(row.get('name'))
                        
                        if not item_code or not name:
                            errors.append(f'Row {row_num}: Missing required fields')
                            error_count += 1
                            continue
                        
                        # Get or create category
                        category = None
                        if 'category' in df.columns and pd.notna(row.get('category')):
                            category_name = _safe_str(row.get('category'))
                            if category_name:
                                category = category_cache.get(category_name)
                                if not category:
                                    category, _ = StockCategory.objects.get_or_create(
                                        name=category_name,
                                        company=company,
                                        defaults={'description': f'Category for {category_name}'}
                                    )
                                    category_cache[category_name] = category
                        
                        # Check if stock item exists
                        stock = Stock.objects.filter(company=company, item_code=item_code).first()
                        
                        if stock:
                            # Update existing item
                            stock.name = name
                            stock.category = category
                            stock.description = _safe_str(row.get('description'))
                            stock.quantity = _safe_int(row.get('quantity'), 0)
                            stock.unit = _safe_str(row.get('unit'), 'pcs')
                            stock.cost_price = _safe_float(row.get('cost_price'), 0)
                            stock.selling_price = _safe_float(row.get('selling_price'), 0)
                            stock.reorder_level = _safe_int(row.get('reorder_level'), 0)
                            stock.supplier_name = _safe_str(row.get('supplier_name'))
                            stock.supplier_contact = _safe_str(row.get('supplier_contact'))
                            stock.location = _safe_str(row.get('location'))
                            
                            # Update is_marketplace_visible if provided
                            if 'is_marketplace_visible' in df.columns and pd.notna(row.get('is_marketplace_visible')):
                                value = str(row.get('is_marketplace_visible')).strip().lower()
                                stock.is_marketplace_visible = value in ('true', 'yes', '1', 'y')
                            
                            # Update last_restocked if quantity increased
                            if 'quantity' in df.columns and pd.notna(row.get('quantity')):
                                new_quantity = _safe_int(row.get('quantity'), 0)
                                if new_quantity > stock.quantity:
                                    stock.last_restocked = timezone.now().date()
                            
                            stock.save()
                            updated_count += 1
                        else:
                            # Create new item
                            is_visible = True
                            if 'is_marketplace_visible' in df.columns and pd.notna(row.get('is_marketplace_visible')):
                                value = str(row.get('is_marketplace_visible')).strip().lower()
                                is_visible = value in ('true', 'yes', '1', 'y')
                            
                            stock = Stock(
                                company=company,
                                item_code=item_code,
                                name=name,
                                category=category,
                                description=_safe_str(row.get('description')),
                                quantity=_safe_int(row.get('quantity'), 0),
                                unit=_safe_str(row.get('unit'), 'pcs'),
                                cost_price=_safe_float(row.get('cost_price'), 0),
                                selling_price=_safe_float(row.get('selling_price'), 0),
                                reorder_level=_safe_int(row.get('reorder_level'), 0),
                                supplier_name=_safe_str(row.get('supplier_name')),
                                supplier_contact=_safe_str(row.get('supplier_contact')),
                                location=_safe_str(row.get('location')),
                                is_marketplace_visible=is_visible,
                                created_by=request.user,
                            )
                            
                            if stock.quantity > 0:
                                stock.last_restocked = timezone.now().date()
                            
                            stock.save()
                            success_count += 1
                        
                    except Exception as e:
                        errors.append(f'Row {row_num}: {str(e)}')
                        error_count += 1
            
            # Show results
            if success_count > 0 or updated_count > 0:
                messages.success(request, f'Processed: {success_count} created, {updated_count} updated.')
            
            if error_count > 0:
                error_message = f'{error_count} errors occurred during import.'
                if errors:
                    error_message += ' First few errors: ' + '; '.join(errors[:5])
                    if len(errors) > 5:
                        error_message += f' ... and {len(errors) - 5} more'
                messages.warning(request, error_message)
            
            return redirect('inventory:stock_list')
            
        except Exception as e:
            messages.error(request, f'Error reading Excel file: {str(e)}')
    
    return render(request, 'inventory/stock_import.html')

@role_required(*INVENTORY_REPORT_ROLES)
def stock_export(request):
    """Export stock items to Excel"""
    company = request.user.company
    stocks = Stock.objects.filter(company=company).select_related('category', 'created_by')
    
    # Prepare data
    data = []
    for stock in stocks:
        data.append({
            'Item Code': stock.item_code,
            'Name': stock.name,
            'Category': stock.category.name if stock.category else '',
            'Description': stock.description,
            'Quantity': stock.quantity,
            'Unit': stock.get_unit_display(),
            'Unit Price': float(stock.cost_price),
            'Total Value': float(stock.total_value),
            'Reorder Level': stock.reorder_level,
            'Supplier Name': stock.supplier_name,
            'Supplier Contact': stock.supplier_contact,
            'Location': stock.location,
            'Last Restocked': stock.last_restocked.strftime('%Y-%m-%d') if stock.last_restocked else '',
            'Needs Reorder': 'Yes' if stock.needs_reorder else 'No',
            'Created By': stock.created_by.get_full_name() if stock.created_by else '',
            'Created At': stock.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Create Excel file in memory
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Stock Data', index=False)
        
        # Auto-adjust column widths
        worksheet = writer.sheets['Stock Data']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    buffer.seek(0)
    
    # Create response
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="stock_export.xlsx"'
    return response

@role_required(*INVENTORY_WRITE_ROLES)
def stock_download_template(request):
    """Download Excel template for stock import"""
    sample_data = {
        'item_code': 'ITEM-001',
        'name': 'Sample Item Name',
        'category': 'Electronics',
        'description': 'Sample description',
        'quantity': 100,
        'unit': 'pcs',
        'cost_price': 10.50,
        'selling_price': 15.99,
        'reorder_level': 20,
        'supplier_name': 'Sample Supplier Inc.',
        'supplier_contact': 'contact@supplier.com',
        'location': 'Warehouse A, Shelf B2',
        'is_marketplace_visible': True,
    }
    
    df = pd.DataFrame([sample_data])
    
    # Create instructions
    instructions = pd.DataFrame({
        'Column': list(sample_data.keys()),
        'Required': [
            'Yes',
            'Yes',
            'No',
            'No',
            'No',
            'No',
            'No',
            'No',
            'No',
            'No',
            'No',
            'No',
            'No',
        ],
        'Description': [
            'Unique item code',
            'Item name',
            'Category name (will be created if not exists)',
            'Item description',
            'Initial quantity',
            'Unit: pcs, kg, ltr, box, set',
            'Cost price per unit (for inventory valuation)',
            'Selling price per unit (for marketplace)',
            'Reorder level',
            'Supplier name',
            'Supplier contact info',
            'Storage location',
            'Show on marketplace (true/false)',
        ],
        'Example': [
            sample_data['item_code'],
            sample_data['name'],
            sample_data['category'],
            sample_data['description'],
            str(sample_data['quantity']),
            sample_data['unit'],
            f"{sample_data['cost_price']:.2f}",
            f"{sample_data['selling_price']:.2f}",
            str(sample_data['reorder_level']),
            sample_data['supplier_name'],
            sample_data['supplier_contact'],
            sample_data['location'],
            'true',
        ]
    })
    
    # Create Excel file
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Template', index=False)
        instructions.to_excel(writer, sheet_name='Instructions', index=False)
    
    buffer.seek(0)
    
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="stock_import_template.xlsx"'
    return response

@role_required(*INVENTORY_MANAGE_ROLES)
def stock_bulk_remove(request):
    """Handle bulk stock removal"""
    company = request.user.company
    
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        
        if not excel_file.name.endswith(('.xlsx', '.xls')):
            messages.error(request, 'Please upload a valid Excel file (.xlsx or .xls)')
            return redirect('inventory:stock_bulk_remove')
        
        try:
            df = pd.read_excel(excel_file)
            required_columns = ['item_code', 'quantity']
            
            # Check required columns
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                messages.error(request, f'Missing required columns: {", ".join(missing_columns)}')
                return redirect('inventory:stock_bulk_remove')
            
            success_count = 0
            error_count = 0
            errors = []
            insufficient_stock_items = []
            
            with transaction.atomic():
                for index, row in df.iterrows():
                    row_num = index + 2
                    
                    try:
                        item_code = str(row.get('item_code', '')).strip()
                        quantity = int(float(row.get('quantity', 0)))
                        remarks = str(row.get('remarks', '')).strip()
                        
                        if not item_code or quantity <= 0:
                            errors.append(f'Row {row_num}: Invalid item code or quantity')
                            error_count += 1
                            continue
                        
                        # Get stock item
                        stock = Stock.objects.select_for_update().filter(
                            company=company, 
                            item_code=item_code
                        ).first()
                        
                        if not stock:
                            errors.append(f'Row {row_num}: Item "{item_code}" not found')
                            error_count += 1
                            continue
                        
                        # Check stock availability
                        if stock.quantity >= quantity:
                            # Update stock quantity
                            stock.quantity = F('quantity') - quantity
                            stock.save()
                            stock.refresh_from_db()
                            
                            # Create transaction
                            StockTransaction.objects.create(
                                company=company,
                                stock=stock,
                                transaction_type='out',
                                quantity=quantity,
                                remarks=remarks or f'Bulk removal - {quantity} units',
                                user=request.user
                            )
                            
                            success_count += 1
                        else:
                            insufficient_stock_items.append({
                                'item_code': item_code,
                                'name': stock.name,
                                'requested': quantity,
                                'available': stock.quantity
                            })
                            errors.append(f'Row {row_num}: Insufficient stock for {item_code}. Available: {stock.quantity}, Requested: {quantity}')
                            error_count += 1
                            
                    except Exception as e:
                        errors.append(f'Row {row_num}: {str(e)}')
                        error_count += 1
            
            # Show results
            if success_count > 0:
                messages.success(request, f'Successfully removed stock for {success_count} items.')
            
            if insufficient_stock_items:
                insufficient_msg = f'Insufficient stock for {len(insufficient_stock_items)} items: '
                for item in insufficient_stock_items[:3]:
                    insufficient_msg += f"{item['item_code']} (Available: {item['available']}, Requested: {item['requested']}); "
                if len(insufficient_stock_items) > 3:
                    insufficient_msg += f"... and {len(insufficient_stock_items) - 3} more"
                messages.warning(request, insufficient_msg)
            
            if error_count > 0:
                error_message = f'{error_count} errors occurred during bulk removal.'
                if errors:
                    error_message += ' First few errors: ' + '; '.join(errors[:5])
                    if len(errors) > 5:
                        error_message += f' ... and {len(errors) - 5} more'
                messages.error(request, error_message)
            
            return redirect('inventory:stock_list')
            
        except Exception as e:
            messages.error(request, f'Error reading Excel file: {str(e)}')
    
    return render(request, 'inventory/stock_bulk_remove.html')

@role_required(*INVENTORY_MANAGE_ROLES)
def stock_download_removal_template(request):
    """Download Excel template for bulk stock removal"""
    sample_data = {
        'item_code': 'ITEM-001',
        'quantity': 10,
        'remarks': 'Removed for project XYZ',
    }
    
    df = pd.DataFrame([sample_data])
    
    # Create instructions
    instructions = pd.DataFrame({
        'Column': ['item_code', 'quantity', 'remarks'],
        'Required': ['Yes', 'Yes', 'No'],
        'Description': [
            'Item code (must exist in system)',
            'Quantity to remove (must be positive number)',
            'Optional remarks for the transaction'
        ],
        'Example': [
            'ITEM-001',
            '10',
            'Removed for maintenance'
        ]
    })
    
    # Create Excel file
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Template', index=False)
        instructions.to_excel(writer, sheet_name='Instructions', index=False)
    
    buffer.seek(0)
    
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="stock_removal_template.xlsx"'
    return response

@role_required(*INVENTORY_VIEW_ROLES)
def category_list(request):
    """Display list of categories"""
    company = request.user.company
    categories = StockCategory.objects.filter(company=company).annotate(
        item_count=Count('items')
    ).order_by('name')
    
    return render(request, 'inventory/category_list.html', {
        'categories': categories
    })

@role_required(*INVENTORY_WRITE_ROLES)
def category_create(request):
    """Create new category"""
    company = request.user.company
    
    if request.method == 'POST':
        form = StockCategoryForm(request.POST, company=company)
        if form.is_valid():
            category = form.save(commit=False)
            category.company = company
            category.save()
            messages.success(request, f'Category "{category.name}" created successfully!')
            return redirect('inventory:category_list')
    else:
        form = StockCategoryForm(company=company)
    
    return render(request, 'inventory/category_form.html', {
        'form': form,
        'title': 'Add New Category'
    })

@role_required(*INVENTORY_WRITE_ROLES)
def category_edit(request, pk):
    """Edit existing category"""
    company = request.user.company
    category = get_object_or_404(StockCategory, pk=pk, company=company)
    
    if request.method == 'POST':
        form = StockCategoryForm(request.POST, instance=category, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, f'Category "{category.name}" updated successfully!')
            return redirect('inventory:category_list')
    else:
        form = StockCategoryForm(instance=category, company=company)
    
    return render(request, 'inventory/category_form.html', {
        'form': form,
        'category': category,
        'title': 'Edit Category'
    })

@role_required(*INVENTORY_MANAGE_ROLES)
def category_delete(request, pk):
    """Delete category"""
    company = request.user.company
    category = get_object_or_404(StockCategory, pk=pk, company=company)
    
    # Check if category has items
    if category.items.exists():
        messages.error(request, f'Cannot delete category "{category.name}" because it has items assigned to it.')
        return redirect('inventory:category_list')
    
    if request.method == 'POST':
        category_name = category.name
        category.delete()
        messages.success(request, f'Category "{category_name}" deleted successfully!')
        return redirect('inventory:category_list')
    
    return render(request, 'inventory/category_confirm_delete.html', {'category': category})

@role_required(*INVENTORY_REPORT_ROLES)
def low_stock_report(request):
    """Generate low stock report"""
    company = request.user.company
    
    # Get low stock items (quantity <= reorder_level)
    low_stock_items = Stock.objects.filter(
        company=company,
        quantity__lte=F('reorder_level')
    ).select_related('category').order_by('quantity')
    
    # Calculate statistics
    total_low_stock = low_stock_items.count()
    total_value = sum(item.total_value for item in low_stock_items)
    
    # Group by category
    category_summary = low_stock_items.values('category__name').annotate(
        count=Count('id'),
        total_items=Sum('quantity'),
        total_value=Sum(F('quantity') * F('cost_price'))
    ).order_by('-count')
    
    context = {
        'low_stock_items': low_stock_items,
        'total_low_stock': total_low_stock,
        'total_value': total_value,
        'category_summary': category_summary,
        'report_date': timezone.now().date(),
    }
    
    return render(request, 'inventory/low_stock_report.html', context)

@role_required(*INVENTORY_REPORT_ROLES)
def stock_valuation_report(request):
    """Generate stock valuation report"""
    company = request.user.company
    
    # Get all stock items with calculated total value
    stocks = Stock.objects.filter(company=company).select_related('category').annotate(
        calculated_total_value=F('quantity') * F('cost_price')
    ).order_by('-calculated_total_value')
    
    # Calculate statistics
    total_items = stocks.count()
    total_quantity = stocks.aggregate(total=Sum('quantity'))['total'] or 0
    total_value = stocks.aggregate(total=Sum(F('quantity') * F('cost_price')))['total'] or 0
    avg_cost_price = stocks.aggregate(avg=Avg('cost_price'))['avg'] or 0
    
    # Group by category
    category_summary = Stock.objects.filter(company=company).values('category__name').annotate(
        count=Count('id'),
        total_quantity=Sum('quantity'),
        total_value=Sum(F('quantity') * F('cost_price'))
    ).order_by('-total_value')
    
    # Top 10 most valuable items
    top_items = stocks.order_by('-calculated_total_value')[:10]
    
    # Top 10 least valuable items (excluding zero value)
    bottom_items = stocks.filter(calculated_total_value__gt=0).order_by('calculated_total_value')[:10]
    
    context = {
        'stocks': stocks,
        'total_items': total_items,
        'total_quantity': total_quantity,
        'total_value': total_value,
        'avg_cost_price': avg_cost_price,
        'category_summary': list(category_summary),
        'top_items': top_items,
        'bottom_items': bottom_items,
        'report_date': timezone.now().date(),
    }
    
    return render(request, 'inventory/stock_valuation_report.html', context)

@role_required(*INVENTORY_REPORT_ROLES)
def stock_movement_report(request):
    """Generate stock movement report"""
    company = request.user.company
    
    # Get date range
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)  # Last 30 days
    
    # Get transactions for the period
    transactions = StockTransaction.objects.filter(
        company=company,
        transaction_date__date__range=[start_date, end_date]
    ).select_related('stock', 'stock__category')
    
    # Calculate movement by item
    movement_data = transactions.values(
        'stock__item_code',
        'stock__name',
        'stock__category__name'
    ).annotate(
        total_in=Sum('quantity', filter=Q(transaction_type='in')),
        total_out=Sum('quantity', filter=Q(transaction_type='out')),
        net_movement=Sum(
            Case(
                When(transaction_type='in', then=F('quantity')),
                When(transaction_type='out', then=-F('quantity')),
                default=0,
                output_field=IntegerField()
            )
        )
    ).order_by('-net_movement')
    
    # Calculate statistics
    total_transactions = transactions.count()
    total_in = transactions.filter(transaction_type='in').aggregate(Sum('quantity'))['quantity__sum'] or 0
    total_out = transactions.filter(transaction_type='out').aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    # Daily movement trend
    daily_trend = transactions.extra(
        select={'day': "date(transaction_date)"}
    ).values('day', 'transaction_type').annotate(
        total_quantity=Sum('quantity')
    ).order_by('day')
    
    context = {
        'movement_data': movement_data,
        'total_transactions': total_transactions,
        'total_in': total_in,
        'total_out': total_out,
        'daily_trend': list(daily_trend),
        'start_date': start_date,
        'end_date': end_date,
        'report_date': timezone.now().date(),
    }
    
    return render(request, 'inventory/stock_movement_report.html', context)

@role_required(*INVENTORY_VIEW_ROLES)
def inventory_dashboard(request):
    """Inventory dashboard with overview"""
    company = request.user.company
    
    # Basic statistics
    total_items = Stock.objects.filter(company=company).count()
    total_value = Stock.objects.filter(company=company).aggregate(
        total=Sum(F('quantity') * F('cost_price'))
    )['total'] or 0
    
    low_stock_items = Stock.objects.filter(
        company=company,
        quantity__lte=F('reorder_level')
    ).count()
    
    out_of_stock_items = Stock.objects.filter(company=company, quantity=0).count()
    
    # Recent transactions
    recent_transactions = StockTransaction.objects.filter(
        company=company
    ).select_related('stock', 'user').order_by('-transaction_date')[:10]
    
    # Top categories by value
    top_categories = Stock.objects.filter(company=company).values(
        'category__name'
    ).annotate(
        total_value=Sum(F('quantity') * F('cost_price')),
        item_count=Count('id')
    ).order_by('-total_value')[:5]
    
    # Low stock alerts
    low_stock_alerts = Stock.objects.filter(
        company=company,
        quantity__lte=F('reorder_level')
    ).select_related('category').order_by('quantity')[:10]
    
    # Monthly movement
    thirty_days_ago = timezone.now() - timedelta(days=30)
    monthly_in = StockTransaction.objects.filter(
        company=company,
        transaction_type='in',
        transaction_date__gte=thirty_days_ago
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    monthly_out = StockTransaction.objects.filter(
        company=company,
        transaction_type='out',
        transaction_date__gte=thirty_days_ago
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    context = {
        'total_items': total_items,
        'total_value': total_value,
        'low_stock_items': low_stock_items,
        'out_of_stock_items': out_of_stock_items,
        'recent_transactions': recent_transactions,
        'top_categories': top_categories,
        'low_stock_alerts': low_stock_alerts,
        'monthly_in': monthly_in,
        'monthly_out': monthly_out,
    }
    
    return render(request, 'inventory/inventory_dashboard.html', context)