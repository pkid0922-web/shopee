from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Product, Vendor, PurchaseOrder, PurchaseOrderItem, PurchaseReturnOrder, PurchaseReturnOrderItem, PurchaseRequest, PurchaseRequestItem
from datetime import datetime

def register_purchases_routes(app, permission_required, order_lock, get_current_billing_period, calc_billing_year):

    @app.route('/add_purchase_page')
    @login_required
    @permission_required('purchases')
    def add_purchase_page():
        _, b_month = get_current_billing_period()
        return render_template('add_purchase.html', vendors=Vendor.query.all(), today=datetime.now().strftime('%Y-%m-%d'), month=b_month)

    @app.route('/finalize_purchase', methods=['POST'])
    @login_required
    @permission_required('purchases')
    def finalize_purchase():
        v_id = request.form.get('vendor_id'); month = int(request.form.get('billing_month') or 1); today = datetime.now(); b_year = calc_billing_year(today.date(), month)
        with order_lock:
            prefix = f"P{today.strftime('%y%m%d')}"; last_order = PurchaseOrder.query.filter(PurchaseOrder.order_no.like(f"{prefix}%")).order_by(PurchaseOrder.order_no.desc()).first(); seq = int(last_order.order_no[-3:]) + 1 if last_order else 1; order_no = f"{prefix}{seq:03d}"
            p_ids = request.form.getlist('product_id[]'); qtys = request.form.getlist('qty[]'); prices = request.form.getlist('price[]'); order = PurchaseOrder(order_no=order_no, date=today.date(), billing_year=b_year, billing_month=month, vendor_id=v_id); total = 0
            for i in range(len(p_ids)):
                p = db.session.get(Product, p_ids[i]); q = int(qtys[i]); pr = float(prices[i]); p.stock += q; p.cost = pr; total += (q * pr)
                db.session.add(PurchaseOrderItem(order=order, product_id=p.id, qty=q, price=pr))
            order.total_amount = total; db.session.add(order); db.session.commit()
        flash(f"進貨單 {order_no} 成功入庫，存貨已增加"); return redirect(url_for('list_purchase_orders'))

    @app.route('/purchase_orders')
    @login_required
    @permission_required('purchases')
    def list_purchase_orders():
        q = request.args.get('q', '').strip(); month_filter = request.args.get('month', ''); year_filter = request.args.get('year', str(datetime.now().year))
        query = PurchaseOrder.query.join(Vendor)
        if q: query = query.filter((PurchaseOrder.order_no.ilike(f"%{q}%")) | (Vendor.short_name.ilike(f"%{q}%")) | (Vendor.full_name.ilike(f"%{q}%")))
        if year_filter and year_filter.isdigit(): query = query.filter(PurchaseOrder.billing_year == int(year_filter))
        if month_filter and month_filter.isdigit(): query = query.filter(PurchaseOrder.billing_month == int(month_filter))
        return render_template('purchase_orders.html', orders=query.order_by(PurchaseOrder.order_no.desc()).all(), q=q, month_filter=month_filter, year_filter=year_filter)

    @app.route('/edit_purchase_order/<int:id>', methods=['GET', 'POST'])
    @login_required
    @permission_required('purchases')
    def edit_purchase_order(id):
        order = db.session.get(PurchaseOrder, id)
        if request.method == 'POST':
            order.vendor_id = request.form.get('vendor_id'); date_str = request.form.get('date')
            if date_str: order.date = datetime.strptime(date_str, '%Y-%m-%d').date()
            order.billing_month = int(request.form.get('billing_month') or order.date.month); order.billing_year = calc_billing_year(order.date, order.billing_month)
            for item in list(order.items):
                if item.product_ref: item.product_ref.stock -= item.qty
                db.session.delete(item)
            p_ids = request.form.getlist('product_id[]'); qtys = request.form.getlist('qty[]'); prices = request.form.getlist('price[]'); total = 0
            for i in range(len(p_ids)):
                p = db.session.get(Product, p_ids[i]); q = int(qtys[i]); pr = float(prices[i]); p.stock += q; p.cost = pr; total += (q * pr); db.session.add(PurchaseOrderItem(order=order, product_id=p.id, qty=q, price=pr))
            order.total_amount = total; db.session.commit(); flash(f"進貨單 {order.order_no} 內容與庫存已成功更新"); return redirect(url_for('list_purchase_orders'))
        return render_template('edit_purchase_order.html', order=order, vendors=Vendor.query.all())

    @app.route('/delete_purchase_order/<int:id>', methods=['POST'])
    @login_required
    @permission_required('purchases')
    def delete_purchase_order(id):
        order = db.get_or_404(PurchaseOrder, id)
        for item in order.items:
            if item.product_ref: item.product_ref.stock -= item.qty
        db.session.delete(order); db.session.commit(); flash(f"進貨單 {order.order_no} 已作廢，入庫商品已扣回"); return redirect(url_for('list_purchase_orders'))

    @app.route('/add_purchase_return_page')
    @login_required
    @permission_required('purchases')
    def add_purchase_return_page():
        _, b_month = get_current_billing_period(); return render_template('add_purchase_return.html', vendors=Vendor.query.all(), today=datetime.now().strftime('%Y-%m-%d'), month=b_month)

    @app.route('/save_purchase_return', methods=['POST'])
    @login_required
    @permission_required('purchases')
    def save_purchase_return():
        v_id = request.form.get('vendor_id'); month = int(request.form.get('billing_month') or 1); date_str = request.form.get('date'); today = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.now(); b_year = calc_billing_year(today.date(), month)
        with order_lock:
            prefix = f"PRT{today.strftime('%y%m%d')}"; last_order = PurchaseReturnOrder.query.filter(PurchaseReturnOrder.order_no.like(f"{prefix}%")).order_by(PurchaseReturnOrder.order_no.desc()).first(); seq = int(last_order.order_no[-3:]) + 1 if last_order else 1; order_no = f"{prefix}{seq:03d}"
            pro = PurchaseReturnOrder(order_no=order_no, date=today.date(), billing_year=b_year, billing_month=month, vendor_id=v_id); p_ids = request.form.getlist('product_id[]'); qtys = request.form.getlist('qty[]'); prices = request.form.getlist('price[]'); rems = request.form.getlist('remark[]'); total_return = 0; added = False
            for i in range(len(p_ids)):
                q = int(qtys[i] or 0)
                if q > 0:
                    p = db.session.get(Product, p_ids[i]); pr = float(prices[i] or 0.0); p.stock -= q; total_return += (q * pr); db.session.add(PurchaseReturnOrderItem(order=pro, product_id=p.id, qty=q, price=pr, remark=rems[i])); added = True
            if not added: flash("請至少輸入一項退貨商品！"); return redirect(url_for('add_purchase_return_page'))
            pro.total_return_amount = total_return; db.session.add(pro); db.session.commit()
        flash(f"進貨退回單 {order_no} 已建立！商品已退庫，本期應付帳款已自動抵扣。"); return redirect(url_for('purchase_returns'))

    # 💡 核心修復點：進貨退回查詢路由
    @app.route('/purchase_returns')
    @login_required
    @permission_required('purchases')
    def purchase_returns():
        q = request.args.get('q', '').strip()
        year_filter = request.args.get('year', str(datetime.now().year))
        month_filter = request.args.get('month', '')
        
        query = PurchaseReturnOrder.query
        if year_filter and year_filter.isdigit(): 
            query = query.filter(PurchaseReturnOrder.billing_year == int(year_filter))
        if month_filter and month_filter.isdigit(): 
            query = query.filter(PurchaseReturnOrder.billing_month == int(month_filter))
        if q: 
            query = query.join(Vendor).filter((PurchaseReturnOrder.order_no.ilike(f'%{q}%')) | (Vendor.short_name.ilike(f'%{q}%')) | (Vendor.full_name.ilike(f'%{q}%')))
            
        orders = query.order_by(PurchaseReturnOrder.date.desc(), PurchaseReturnOrder.id.desc()).all()
        return render_template('purchase_returns.html', orders=orders, q=q, year_filter=year_filter, month_filter=month_filter)

    @app.route('/delete_purchase_return/<int:id>', methods=['POST'])
    @login_required
    @permission_required('purchases')
    def delete_purchase_return(id):
        pro = db.get_or_404(PurchaseReturnOrder, id)
        with order_lock:
            for item in pro.items:
                if item.product_ref: item.product_ref.stock += item.qty
            db.session.delete(pro); db.session.commit()
        flash("進貨退回單已作廢！商品庫存與廠商應付帳款已恢復原狀。"); return redirect(url_for('purchase_returns'))

    @app.route('/add_pr_page')
    @login_required
    @permission_required('purchases')
    def add_pr_page(): 
        _, b_month = get_current_billing_period(); return render_template('add_pr.html', vendors=Vendor.query.all(), month=b_month)

    @app.route('/save_pr', methods=['POST'])
    @login_required
    @permission_required('purchases')
    def save_pr():
        v_id = request.form.get('vendor_id'); today = datetime.now(); month = int(request.form.get('billing_month') or today.month); b_year = calc_billing_year(today.date(), month)
        p_ids = request.form.getlist('product_id[]'); qtys = request.form.getlist('qty[]'); prefix = f"PR{today.strftime('%y%m%d')}"; last_req = PurchaseRequest.query.filter(PurchaseRequest.req_no.like(f"{prefix}%")).order_by(PurchaseRequest.req_no.desc()).first(); seq = int(last_req.req_no[-3:]) + 1 if last_req else 1; req_no = f"{prefix}{seq:03d}"
        pr = PurchaseRequest(req_no=req_no, date=today, billing_year=b_year, billing_month=month, vendor_id=v_id); added_any = False
        for i in range(len(p_ids)):
            q = int(qtys[i] or 0)
            if q > 0: db.session.add(PurchaseRequestItem(request=pr, product_id=p_ids[i], qty=q)); added_any = True
        if not added_any: flash("請至少輸入一項商品的叫貨數量！"); return redirect(url_for('add_pr_page'))
        db.session.add(pr); db.session.commit(); return redirect(url_for('print_pr', id=pr.id))

    @app.route('/print_pr/<int:id>')
    @login_required
    @permission_required('purchases')
    def print_pr(id): 
        pr = db.get_or_404(PurchaseRequest, id); return render_template('print_pr.html', pr=pr)