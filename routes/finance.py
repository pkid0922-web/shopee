from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, SalesOrder, ReturnOrder, ReturnOrderItem, PaymentRecord, VendorPaymentRecord, PurchaseOrder, Product, InvoiceRecord, FixedExpense, CompanyProfile, Customer, Vendor
from datetime import datetime, timedelta
import calendar

# 💡 接收主程式傳來的工具
def register_finance_routes(app, permission_required):

    @app.route('/receivables')
    @login_required
    @permission_required('sales')
    def receivables():
        target_year = int(request.args.get('year', datetime.now().year))
        target_month = int(request.args.get('month', datetime.now().month))
        orders = SalesOrder.query.filter_by(billing_year=target_year, billing_month=target_month).all()
        payments = PaymentRecord.query.filter_by(billing_year=target_year, billing_month=target_month).all()
        returns = ReturnOrder.query.filter_by(billing_year=target_year, billing_month=target_month).all()
        
        cust_totals = {}
        for o in orders:
            if o.customer_id not in cust_totals: cust_totals[o.customer_id] = {'std_ar': 0.0, 'cash_ar': 0.0, 'std_ret': 0.0, 'cash_ret': 0.0, 'received': 0.0, 'customer': o.customer_ref}
            for item in o.items:
                if '現金價' in (item.remark or ''): cust_totals[o.customer_id]['cash_ar'] += (item.qty * item.price)
                else: cust_totals[o.customer_id]['std_ar'] += (item.qty * item.price)
        for r in returns:
            if r.customer_id not in cust_totals: cust_totals[r.customer_id] = {'std_ar': 0.0, 'cash_ar': 0.0, 'std_ret': 0.0, 'cash_ret': 0.0, 'received': 0.0, 'customer': r.customer_ref}
            for item in r.items:
                if '現金價' in (item.remark or ''): cust_totals[r.customer_id]['cash_ret'] += (item.qty * item.price)
                else: cust_totals[r.customer_id]['std_ret'] += (item.qty * item.price)
        for p in payments:
            if p.customer_id not in cust_totals: cust_totals[p.customer_id] = {'std_ar': 0.0, 'cash_ar': 0.0, 'std_ret': 0.0, 'cash_ret': 0.0, 'received': 0.0, 'customer': p.customer_ref}
            cust_totals[p.customer_id]['received'] += p.amount
            
        reps_summary = {}
        for cid, data in cust_totals.items():
            c = data['customer']
            rep_name = c.user_ref.employee.name if c.user_ref and c.user_ref.employee else (c.user_ref.username if c.user_ref else '未指定業務')
            if rep_name not in reps_summary: reps_summary[rep_name] = {'total_ar': 0, 'total_returns': 0, 'total_received': 0, 'total_unpaid': 0, 'customers': []}
            
            disc = (100 - (c.post_discount or 0.0)) / 100
            net_std = data['std_ar'] - data['std_ret']
            net_cash = data['cash_ar'] - data['cash_ret']
            current_receivable = (net_std * disc) + net_cash
            unpaid = current_receivable - data['received']
            ar_total = data['std_ar'] + data['cash_ar']
            ret_total = data['std_ret'] + data['cash_ret']
            
            reps_summary[rep_name]['total_ar'] += ar_total
            reps_summary[rep_name]['total_returns'] += ret_total
            reps_summary[rep_name]['total_received'] += data['received']
            reps_summary[rep_name]['total_unpaid'] += unpaid
            reps_summary[rep_name]['customers'].append({'customer': c, 'ar': ar_total, 'returns': ret_total, 'received': data['received'], 'unpaid': unpaid, 'std_ar': data['std_ar'], 'cash_ar': data['cash_ar']})
            
        return render_template('receivables.html', target_year=target_year, target_month=target_month, reps_summary=reps_summary)

    @app.route('/add_payment', methods=['POST'])
    @login_required
    @permission_required('sales')
    def add_payment():
        cid = request.form.get('customer_id')
        year = int(request.form.get('year'))
        month = int(request.form.get('month'))
        amount = float(request.form.get('amount') or 0)
        method = request.form.get('method')
        if amount > 0: 
            p = PaymentRecord(customer_id=cid, billing_year=year, billing_month=month, amount=amount, method=method)
            db.session.add(p)
            db.session.commit()
            flash(f"已成功登錄收款：$ {amount:,.0f} ({method})")
        return redirect(url_for('receivables', year=year, month=month))

    @app.route('/payables')
    @login_required
    @permission_required('purchases')
    def payables():
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        today = datetime.today()
        if not start_date_str or not end_date_str: 
            start_date = today.replace(day=1).date()
            last_day = calendar.monthrange(today.year, today.month)[1]
            end_date = today.replace(day=last_day).date()
        else: 
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            
        pos = PurchaseOrder.query.all()
        payments = VendorPaymentRecord.query.all()
        returns = ReturnOrder.query.all()
        
        ap_data = {}
        for po in pos:
            vid = po.vendor_id
            ym = (po.billing_year, po.billing_month)
            if vid not in ap_data: ap_data[vid] = {}
            if ym not in ap_data[vid]: ap_data[vid][ym] = {'ap': 0, 'paid': 0, 'return_amt': 0, 'vendor': po.vendor_ref, 'po_count': 0}
            ap_data[vid][ym]['ap'] += po.total_amount
            ap_data[vid][ym]['po_count'] += 1
            
        for ro in returns:
            ym = (ro.billing_year, ro.billing_month)
            for item in ro.items:
                vid = item.product_ref.vendor_id if item.product_ref else None
                if vid:
                    if vid not in ap_data: ap_data[vid] = {}
                    if ym not in ap_data[vid]: ap_data[vid][ym] = {'ap': 0, 'paid': 0, 'return_amt': 0, 'vendor': item.product_ref.vendor_ref, 'po_count': 0}
                    if 'return_amt' not in ap_data[vid][ym]: ap_data[vid][ym]['return_amt'] = 0
                    ap_data[vid][ym]['return_amt'] += (item.qty * item.cost)
                    
        for py in payments:
            vid = py.vendor_id
            ym = (py.billing_year, py.billing_month)
            if vid in ap_data and ym in ap_data[vid]: 
                ap_data[vid][ym]['paid'] += py.amount
                
        results = []
        for vid, ym_dict in ap_data.items():
            for (y, m), data in ym_dict.items():
                v = data['vendor']
                if not v: continue
                last_d = calendar.monthrange(y, m)[1]
                c_day = min(v.closing_day or 31, last_d)
                closing_date = datetime(y, m, c_day).date()
                pay_date = closing_date + timedelta(days=(v.payment_day or 0))
                if start_date <= pay_date <= end_date: 
                    unpaid = data['ap'] - data.get('return_amt', 0) - data['paid']
                    results.append({'vendor': v, 'billing_year': y, 'billing_month': m, 'pay_date': pay_date, 'ap': data['ap'], 'return_amt': data.get('return_amt', 0), 'paid': data['paid'], 'unpaid': unpaid, 'po_count': data['po_count']})
        results.sort(key=lambda x: x['pay_date'])
        return render_template('payables.html', results=results, start_date=start_date.strftime('%Y-%m-%d'), end_date=end_date.strftime('%Y-%m-%d'))

    @app.route('/add_vendor_payment', methods=['POST'])
    @login_required
    @permission_required('purchases')
    def add_vendor_payment():
        vid = request.form.get('vendor_id')
        year = int(request.form.get('year'))
        month = int(request.form.get('month'))
        amount = float(request.form.get('amount') or 0)
        method = request.form.get('method')
        if amount > 0: 
            p = VendorPaymentRecord(vendor_id=vid, billing_year=year, billing_month=month, amount=amount, method=method)
            db.session.add(p)
            db.session.commit()
            flash(f"已成功登錄廠商付款：$ {amount:,.0f} ({method})")
        return redirect(request.referrer or url_for('payables'))

    @app.route('/statement_page')
    @login_required
    @permission_required('sales')
    def statement_page(): 
        return render_template('statement_page.html', customers=Customer.query.all(), current_year=datetime.now().year, current_month=datetime.now().month)

    @app.route('/print_statement', methods=['POST'])
    @login_required
    @permission_required('sales')
    def print_statement():
        cid = request.form.get('customer_id')
        year = int(request.form.get('year'))
        month = int(request.form.get('month'))
        cust = db.get_or_404(Customer, cid)
        profile = CompanyProfile.query.first()
        company_name = profile.name if profile else "公司"
        
        orders = SalesOrder.query.filter_by(customer_id=cid, billing_year=year, billing_month=month).order_by(SalesOrder.date).all()
        payments = PaymentRecord.query.filter_by(customer_id=cid, billing_year=year, billing_month=month).order_by(PaymentRecord.date).all()
        returns = ReturnOrder.query.filter_by(customer_id=cid, billing_year=year, billing_month=month).all()
        
        # 💡 修正：移除強制進位的 +0.5，改用系統標準的 round()，確保與銷貨單完全一致
        current_sales_total = sum(round(o.total_amount) for o in orders)
        current_payments_total = sum(round(p.amount) for p in payments)
        returns_total = sum(round(r.total_return_amount) for r in returns)

        all_past_orders = SalesOrder.query.filter_by(customer_id=cid).all()
        all_past_payments = PaymentRecord.query.filter_by(customer_id=cid).all()
        all_past_returns = ReturnOrder.query.filter_by(customer_id=cid).all()

        past_std_sales = 0; past_cash_sales = 0
        for o in all_past_orders:
            if o.billing_year < year or (o.billing_year == year and o.billing_month < month):
                for i in o.items:
                    if '現金價' in (i.remark or ''): past_cash_sales += (i.qty * i.price)
                    else: past_std_sales += (i.qty * i.price)
                    
        past_std_ret = 0; past_cash_ret = 0
        for r in all_past_returns:
            if r.billing_year < year or (r.billing_year == year and r.billing_month < month):
                for i in r.items:
                    if '現金價' in (i.remark or ''): past_cash_ret += (i.qty * i.price)
                    else: past_std_ret += (i.qty * i.price)
                    
        past_payments = sum(p.amount for p in all_past_payments if p.billing_year < year or (p.billing_year == year and p.billing_month < month))
        
        disc_past = (100 - (cust.post_discount or 0.0)) / 100
        previous_balance = round(((past_std_sales - past_std_ret) * disc_past) + (past_cash_sales - past_cash_ret) - past_payments)
        
        curr_std_sales = round(sum(i.qty * i.price for o in orders for i in o.items if '現金價' not in (i.remark or '')))
        curr_cash_sales = round(sum(i.qty * i.price for o in orders for i in o.items if '現金價' in (i.remark or '')))
        curr_std_ret = round(sum(i.qty * i.price for r in returns for i in r.items if '現金價' not in (i.remark or '')))
        curr_cash_ret = round(sum(i.qty * i.price for r in returns for i in r.items if '現金價' in (i.remark or '')))
        
        discount_percent = cust.post_discount or 0.0
        discount_multiplier = (100 - discount_percent) / 100
        
        current_receivable = round(((curr_std_sales - curr_std_ret) * discount_multiplier) + (curr_cash_sales - curr_cash_ret))
        total_due = previous_balance + current_receivable - current_payments_total
        
        today_date = datetime.now().strftime('%Y/%m/%d')
        
        return render_template('print_statement.html', customer=cust, year=year, month=month, 
                               orders=orders, payments=payments, returns=returns,
                               current_sales_total=current_sales_total, returns_total=returns_total, 
                               discount_percent=discount_percent, current_receivable=current_receivable, 
                               current_payments_total=current_payments_total, previous_balance=previous_balance, 
                               total_due=total_due, company_name=company_name, profile=profile,
                               curr_std_sales=curr_std_sales, curr_cash_sales=curr_cash_sales,
                               curr_std_ret=curr_std_ret, curr_cash_ret=curr_cash_ret, today_date=today_date)

    @app.route('/vendor_statement_page')
    @login_required
    @permission_required('purchases')
    def vendor_statement_page(): 
        return render_template('vendor_statement_page.html', vendors=Vendor.query.all(), current_year=datetime.now().year, current_month=datetime.now().month)

    @app.route('/print_vendor_statement', methods=['POST'])
    @login_required
    @permission_required('purchases')
    def print_vendor_statement():
        vid = request.form.get('vendor_id')
        year = int(request.form.get('year'))
        month = int(request.form.get('month'))
        vendor = db.get_or_404(Vendor, vid)
        profile = CompanyProfile.query.first()
        company_name = profile.name if profile else "公司"
        
        pos = PurchaseOrder.query.filter_by(vendor_id=vid, billing_year=year, billing_month=month).order_by(PurchaseOrder.date).all()
        payments = VendorPaymentRecord.query.filter_by(vendor_id=vid, billing_year=year, billing_month=month).order_by(VendorPaymentRecord.date).all()
        current_returns = db.session.query(ReturnOrderItem).join(ReturnOrder).join(Product).filter(Product.vendor_id == vid, ReturnOrder.billing_year == year, ReturnOrder.billing_month == month).all()
        
        current_po_total = sum(po.total_amount for po in pos)
        current_payment_total = sum(p.amount for p in payments)
        current_return_total = sum(r.qty * r.cost for r in current_returns)
        
        all_past_pos = PurchaseOrder.query.filter_by(vendor_id=vid).all()
        all_past_payments = VendorPaymentRecord.query.filter_by(vendor_id=vid).all()
        all_past_returns = db.session.query(ReturnOrderItem).join(ReturnOrder).join(Product).filter(Product.vendor_id == vid).all()
        
        past_po_total = sum(po.total_amount for po in all_past_pos if po.billing_year < year or (po.billing_year == year and po.billing_month < month))
        past_payment_total = sum(p.amount for p in all_past_payments if p.billing_year < year or (p.billing_year == year and p.billing_month < month))
        past_return_total = sum(r.qty * r.cost for r in all_past_returns if r.order.billing_year < year or (r.order.billing_year == year and r.order.billing_month < month))
        
        previous_balance = past_po_total - past_return_total - past_payment_total
        total_due = previous_balance + current_po_total - current_return_total - current_payment_total
        return render_template('print_vendor_statement.html', vendor=vendor, year=year, month=month, pos=pos, payments=payments, current_returns=current_returns, current_po_total=current_po_total, current_payment_total=current_payment_total, current_return_total=current_return_total, previous_balance=previous_balance, total_due=total_due, company_name=company_name)

    @app.route('/invoices')
    @login_required
    def invoices():
        if current_user.username != 'admin' and not getattr(current_user.role_ref, 'p_sales', False): 
            flash("權限不足！"); return redirect(url_for('index'))
            
        target_year = request.args.get('year', default=datetime.now().year, type=int)
        target_month = request.args.get('month', default=datetime.now().month, type=int)
        
        orders = SalesOrder.query.filter_by(billing_year=target_year, billing_month=target_month).all()
        returns = ReturnOrder.query.filter_by(billing_year=target_year, billing_month=target_month).all()
        inv_dict = {}
        
        for o in orders:
            c = o.customer_ref
            if c and c.has_invoice:
                if c.id not in inv_dict: inv_dict[c.id] = {'customer': c, 'std_amount': 0}
                std_sum = sum(item.qty * item.price for item in o.items if '現金價' not in (item.remark or ''))
                inv_dict[c.id]['std_amount'] += std_sum
                
        for r in returns:
            c = r.customer_ref
            if c and c.has_invoice and c.id in inv_dict:
                std_ret = sum(item.qty * item.price for item in r.items if '現金價' not in (item.remark or ''))
                inv_dict[c.id]['std_amount'] -= std_ret
                
        results = []
        for cid, data in inv_dict.items():
            if data['std_amount'] > 0:
                existing_inv = InvoiceRecord.query.filter_by(customer_id=cid, billing_year=target_year, billing_month=target_month).first()
                if not existing_inv:
                    c = data['customer']
                    net_amount = data['std_amount'] * (1 - ((c.post_discount or 0.0) / 100))
                    final_amount = int(net_amount + 0.5)
                    results.append({'customer': c, 'default_amount': final_amount})
                    
        history = InvoiceRecord.query.filter_by(billing_year=target_year, billing_month=target_month).all()
        return render_template('invoices.html', target_year=target_year, target_month=target_month, results=results, history=history)

    @app.route('/api/save_invoice', methods=['POST'])
    @login_required
    @permission_required('sales')
    def api_save_invoice():
        data = request.json
        cid = data.get('customer_id'); y = data.get('year'); m = data.get('month'); amt = float(data.get('amount', 0))
        date_str = data.get('invoice_date')
        inv_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
        
        rec = InvoiceRecord.query.filter_by(customer_id=cid, billing_year=y, billing_month=m).first()
        if not rec: 
            rec = InvoiceRecord(customer_id=cid, billing_year=y, billing_month=m)
            db.session.add(rec)
        rec.amount = amt
        rec.invoice_date = inv_date
        db.session.commit()
        return jsonify({'success': True})

    @app.route('/print_invoice/<int:customer_id>/<int:year>/<int:month>')
    @login_required
    @permission_required('sales')
    def print_invoice(customer_id, year, month):
        c = db.get_or_404(Customer, customer_id)
        rec = InvoiceRecord.query.filter_by(customer_id=customer_id, billing_year=year, billing_month=month).first()
        if not rec or rec.amount == 0: 
            flash("請先確認並儲存發票金額後再列印！"); return redirect(url_for('invoices', year=year, month=month))
            
        rec.is_printed = True
        db.session.commit()
        profile = CompanyProfile.query.first()
        return render_template('print_invoice.html', customer=c, record=rec, profile=profile)

    @app.route('/delete_invoice_record/<int:id>', methods=['POST'])
    @login_required
    def delete_invoice_record(id):
        if current_user.username != 'admin' and not getattr(current_user.role_ref, 'p_sales', False): return redirect(url_for('index'))
        inv = db.get_or_404(InvoiceRecord, id)
        y = inv.billing_year; m = inv.billing_month
        db.session.delete(inv)
        db.session.commit()
        flash("發票紀錄已作廢！該客戶已重新退回待開立清單。")
        return redirect(url_for('invoices', year=y, month=m))

    @app.route('/fixed_expenses', methods=['GET', 'POST'])
    @login_required
    def fixed_expenses():
        if current_user.username != 'admin' and not getattr(current_user.role_ref, 'p_finance', False): 
            flash("權限不足，無法進入財務管理！"); return redirect(url_for('index'))
            
        if request.method == 'POST':
            day = request.form.get('day', type=int)
            name = request.form.get('name')
            amount = request.form.get('amount', type=float)
            remark = request.form.get('remark', '')
            if day and name and amount is not None: 
                db.session.add(FixedExpense(day=day, name=name, amount=amount, remark=remark))
                db.session.commit()
                flash(f"已成功新增每月 {day} 號的固定支出：{name}")
            return redirect(url_for('fixed_expenses'))
            
        return render_template('fixed_expenses.html', expenses=FixedExpense.query.order_by(FixedExpense.day).all())

    @app.route('/delete_fixed_expense/<int:id>', methods=['POST'])
    @login_required
    def delete_fixed_expense(id):
        if current_user.username != 'admin' and not getattr(current_user.role_ref, 'p_finance', False): return redirect(url_for('index'))
        exp = db.get_or_404(FixedExpense, id)
        db.session.delete(exp)
        db.session.commit()
        flash("已作廢該筆固定支出！")
        return redirect(url_for('fixed_expenses'))

    @app.route('/monthly_finance')
    @login_required
    def monthly_finance():
        if current_user.username != 'admin' and not getattr(current_user.role_ref, 'p_finance', False): 
            flash("權限不足，無法進入財務管理！"); return redirect(url_for('index'))
            
        target_year = int(request.args.get('year', datetime.now().year))
        target_month = int(request.args.get('month', datetime.now().month))
        last_day = calendar.monthrange(target_year, target_month)[1]
        
        daily_data = {i: {'income': 0.0, 'expense': 0.0, 'income_details': [], 'expense_details': []} for i in range(1, last_day + 1)}
        
        for exp in FixedExpense.query.all():
            day = min(exp.day, last_day)
            daily_data[day]['expense'] += exp.amount
            daily_data[day]['expense_details'].append({'name': f"[固定] {exp.name}", 'amount': exp.amount})
            
        orders = SalesOrder.query.filter_by(billing_year=target_year, billing_month=target_month).all()
        returns = ReturnOrder.query.filter_by(billing_year=target_year, billing_month=target_month).all()
        
        ar_dict = {}
        for o in orders:
            if o.customer_id not in ar_dict: ar_dict[o.customer_id] = {'std_amt': 0, 'cash_amt': 0, 'customer': o.customer_ref}
            for item in o.items:
                if '現金價' in (item.remark or ''): ar_dict[o.customer_id]['cash_amt'] += (item.qty * item.price)
                else: ar_dict[o.customer_id]['std_amt'] += (item.qty * item.price)
                
        for r in returns:
            if r.customer_id not in ar_dict: ar_dict[r.customer_id] = {'std_amt': 0, 'cash_amt': 0, 'customer': r.customer_ref}
            for item in r.items:
                if '現金價' in (item.remark or ''): ar_dict[r.customer_id]['cash_amt'] -= (item.qty * item.price)
                else: ar_dict[r.customer_id]['std_amt'] -= (item.qty * item.price)
                
        for cid, data in ar_dict.items():
            c = data['customer']
            net_ar = (data['std_amt'] * ((100 - (c.post_discount or 0.0)) / 100)) + data['cash_amt']
            if net_ar > 0: 
                day = min(c.payment_day or 10, last_day)
                daily_data[day]['income'] += net_ar
                daily_data[day]['income_details'].append({'name': f"[應收] {c.short_name}", 'amount': net_ar})
                
        pos = PurchaseOrder.query.filter_by(billing_year=target_year, billing_month=target_month).all()
        vendor_returns = db.session.query(ReturnOrderItem, ReturnOrder).join(ReturnOrder).filter(ReturnOrder.billing_year == target_year, ReturnOrder.billing_month == target_month).all()
        
        ap_dict = {}
        for po in pos:
            vid = po.vendor_id
            if vid not in ap_dict: ap_dict[vid] = {'amount': 0, 'vendor': po.vendor_ref}
            ap_dict[vid]['amount'] += po.total_amount
            
        for item, ro in vendor_returns:
            vid = item.product_ref.vendor_id if item.product_ref else None
            if vid:
                if vid not in ap_dict: ap_dict[vid] = {'amount': 0, 'vendor': item.product_ref.vendor_ref}
                ap_dict[vid]['amount'] -= (item.qty * item.cost)
                
        for vid, data in ap_dict.items():
            v = data['vendor']
            net_ap = data['amount']
            if net_ap > 0: 
                day = min(v.payment_day or 10, last_day)
                daily_data[day]['expense'] += net_ap
                daily_data[day]['expense_details'].append({'name': f"[應付] {v.short_name}", 'amount': net_ap})
                
        results = []
        cumulative = 0; total_in = 0; total_out = 0
        for i in range(1, last_day + 1):
            d = daily_data[i]
            daily_net = d['income'] - d['expense']
            cumulative += daily_net
            total_in += d['income']
            total_out += d['expense']
            results.append({'day': i, 'income': d['income'], 'expense': d['expense'], 'net': daily_net, 'cumulative': cumulative, 'income_details': d['income_details'], 'expense_details': d['expense_details'], 'has_data': (d['income'] > 0 or d['expense'] > 0)})
            
        return render_template('monthly_finance.html', target_year=target_year, target_month=target_month, results=results, total_in=total_in, total_out=total_out, final_net=cumulative)