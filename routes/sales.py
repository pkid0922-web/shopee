from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Product, Customer, SalesOrder, SalesOrderItem, PickingSlip, PickingSlipItem, ReturnOrder, ReturnOrderItem, DropShipOrder, DropShipOrderItem, PurchaseOrder, PurchaseOrderItem, Vendor
from datetime import datetime

# 💡 接收主程式傳來的工具 (app, 權限檢查, 防撞鎖, 帳單期計算)
def register_sales_routes(app, permission_required, order_lock, get_current_billing_period, calc_billing_year):

    @app.route('/add_picking_page')
    @login_required
    @permission_required('sales')
    def add_picking_page():
        return render_template('add_picking.html', customers=Customer.query.all())

    @app.route('/save_picking', methods=['POST'])
    @login_required
    @permission_required('sales')
    def save_picking():
        data = request.json
        slip = PickingSlip(slip_no=f"PK{datetime.now().strftime('%Y%m%d%H%M%S')}", customer_id=data.get('customer_id'))
        with order_lock:
            for i in data.get('items'):
                item_remark = i.get('remark', '')
                db.session.add(PickingSlipItem(slip=slip, product_id=i['id'], qty=i['qty']))
            db.session.add(slip)
            db.session.commit()
        return jsonify({'success':True})

    @app.route('/add_sales_page')
    @login_required
    @permission_required('sales')
    def add_sales_page():
        _, b_month = get_current_billing_period()
        return render_template('add_sales.html', customers=Customer.query.all(), today=datetime.now().strftime('%Y-%m-%d'), month=b_month)

    @app.route('/add_sales', methods=['POST'])
    @login_required
    def add_sales():
        if current_user.username != 'admin' and not getattr(current_user.role_ref, 'p_sales', False): return redirect(url_for('index'))
        cust_id = request.form.get('customer_id'); month = int(request.form.get('billing_month') or datetime.now().month); today = datetime.now()
        b_year = today.year
        if month > today.month + 6: b_year -= 1
        elif month < today.month - 6: b_year += 1
        customer = db.session.get(Customer, cust_id)
        with order_lock:
            prefix = f"S{today.strftime('%y%m%d')}"; last_order = SalesOrder.query.filter(SalesOrder.order_no.like(f"{prefix}%")).order_by(SalesOrder.order_no.desc()).first(); seq = int(last_order.order_no[-3:]) + 1 if last_order else 1; order_no = f"{prefix}{seq:03d}"
            so = SalesOrder(order_no=order_no, date=today.date(), billing_year=b_year, billing_month=month, customer_id=cust_id)
            p_ids = request.form.getlist('product_id[]'); qtys = request.form.getlist('qty[]'); prices = request.form.getlist('price[]'); rems = request.form.getlist('remark[]')
            total = 0; std_raw_profit = 0; cash_raw_profit = 0; added = False
            for i in range(len(p_ids)):
                q = int(qtys[i] or 0)
                if q > 0:
                    p = db.session.get(Product, p_ids[i]); pr = float(prices[i] or 0.0); cost = p.cost or 0.0; rem = rems[i]; is_cash = '現金價' in (rem or '')
                    db.session.add(SalesOrderItem(order=so, product_id=p.id, qty=q, price=pr, cost=cost, remark=rem)); p.stock -= q; total += (q * pr); item_profit = (pr - cost) * q
                    if is_cash: cash_raw_profit += item_profit
                    else: std_raw_profit += item_profit
                    added = True
            if not added: flash("請至少輸入一項商品！"); return redirect(url_for('add_sales_page'))
            so.total_amount = total; so.gross_profit = (std_raw_profit * (1 - ((customer.post_discount or 0.0) / 100))) + cash_raw_profit
            db.session.add(so); db.session.commit()
        # 💡 修復點：跳轉回 list_sales_orders
        flash(f"銷貨單 {order_no} 已成功開立！庫存已同步扣除。"); return redirect(url_for('list_sales_orders'))

    @app.route('/finalize_sales', methods=['POST'])
    @login_required
    @permission_required('sales')
    def finalize_sales():
        cust_id = request.form.get('customer_id'); month = int(request.form.get('billing_month') or 1); slip_id = request.form.get('slip_id'); today = datetime.now(); prefix = today.strftime('%y%m%d'); last_order = SalesOrder.query.filter(SalesOrder.order_no.like(f"{prefix}%")).order_by(SalesOrder.order_no.desc()).first(); seq = int(last_order.order_no[-3:]) + 1 if last_order else 1; order_no = f"{prefix}{seq:03d}"; b_year = calc_billing_year(today.date(), month)
        p_ids = request.form.getlist('product_id[]'); qtys = request.form.getlist('qty[]'); prices = request.form.getlist('price[]'); rems = request.form.getlist('remark[]'); order = SalesOrder(order_no=order_no, date=today.date(), billing_year=b_year, billing_month=month, customer_id=cust_id)
        total = 0; std_raw_profit = 0; cash_raw_profit = 0
        for i in range(len(p_ids)):
            p = db.session.get(Product, p_ids[i]); q = int(qtys[i]); pr = float(prices[i]); p_cost = p.cost or 0.0; rem = rems[i]; is_cash = '現金價' in (rem or ''); p.stock -= q; total += (q * pr); item_profit = (pr - p_cost) * q
            if is_cash: cash_raw_profit += item_profit
            else: std_raw_profit += item_profit
            db.session.add(SalesOrderItem(order=order, product_id=p.id, qty=q, price=pr, cost=p_cost, remark=rem))
        order.total_amount = total; cust = db.session.get(Customer, cust_id); order.gross_profit = (std_raw_profit * (1 - ((cust.post_discount or 0.0) / 100))) + cash_raw_profit
        if slip_id: 
            s = db.session.get(PickingSlip, slip_id)
            if s: s.status = 'converted'
        db.session.add(order); db.session.commit(); flash(f"單據 {order_no} 已正式入帳，毛利已計算儲存"); return redirect(url_for('list_sales_orders'))

    @app.route('/sales_orders')
    @login_required
    @permission_required('sales')
    def list_sales_orders():
        q = request.args.get('q', '').strip(); month_filter = request.args.get('month', ''); year_filter = request.args.get('year', str(datetime.now().year))
        query = SalesOrder.query.join(Customer)
        if q: query = query.filter((SalesOrder.order_no.like(f"%{q}%")) | (Customer.short_name.like(f"%{q}%")) | (Customer.full_name.like(f"%{q}%")))
        if year_filter: query = query.filter(SalesOrder.billing_year == int(year_filter))
        if month_filter: query = query.filter(SalesOrder.billing_month == int(month_filter))
        return render_template('sales_orders.html', orders=query.order_by(SalesOrder.order_no.desc()).all(), q=q, month_filter=month_filter, year_filter=year_filter)

    @app.route('/edit_sales_order/<int:id>', methods=['GET', 'POST'])
    @login_required
    @permission_required('sales')
    def edit_sales_order(id):
        order = db.session.get(SalesOrder, id)
        if request.method == 'POST':
            order.customer_id = request.form.get('customer_id'); date_str = request.form.get('date')
            if date_str: order.date = datetime.strptime(date_str, '%Y-%m-%d').date()
            order.billing_month = int(request.form.get('billing_month') or order.date.month); order.billing_year = calc_billing_year(order.date, order.billing_month)
            for item in list(order.items):
                if item.product_ref: item.product_ref.stock += item.qty
                db.session.delete(item)
            p_ids = request.form.getlist('product_id[]'); qtys = request.form.getlist('qty[]'); prices = request.form.getlist('price[]'); rems = request.form.getlist('remark[]'); total = 0; std_raw_profit = 0; cash_raw_profit = 0
            for i in range(len(p_ids)):
                p = db.session.get(Product, p_ids[i]); q = int(qtys[i]); pr = float(prices[i]); p_cost = p.cost or 0.0; rem = rems[i]; is_cash = '現金價' in (rem or '')
                p.stock -= q; total += (q * pr); item_profit = (pr - p_cost) * q
                if is_cash: cash_raw_profit += item_profit
                else: std_raw_profit += item_profit
                db.session.add(SalesOrderItem(order=order, product_id=p.id, qty=q, price=pr, cost=p_cost, remark=rem))
            order.total_amount = total; cust = db.session.get(Customer, order.customer_id)
            order.gross_profit = (std_raw_profit * (1 - ((cust.post_discount or 0.0) / 100))) + cash_raw_profit
            db.session.commit(); flash(f"銷貨單 {order.order_no} 內容與庫存已成功更新"); return redirect(url_for('list_sales_orders'))
        return render_template('edit_sales_order.html', order=order, customers=Customer.query.all())

    @app.route('/delete_sales_order/<int:id>', methods=['POST'])
    @login_required
    @permission_required('sales')
    def delete_sales_order(id):
        order = db.get_or_404(SalesOrder, id)
        for item in order.items:
            if item.product_ref: item.product_ref.stock += item.qty
        db.session.delete(order); db.session.commit(); flash(f"銷貨單 {order.order_no} 已作廢，庫存已歸還"); return redirect(url_for('list_sales_orders'))

    @app.route('/convert_to_sales/<int:slip_id>')
    @login_required
    @permission_required('sales')
    def convert_to_sales(slip_id): 
        slip = db.get_or_404(PickingSlip, slip_id); _, b_month = get_current_billing_period(); return render_template('sales_from_picking.html', slip=slip, customers=Customer.query.all(), current_month=b_month)

    @app.route('/add_return_page')
    @login_required
    @permission_required('sales')
    def add_return_page(): 
        _, b_month = get_current_billing_period(); return render_template('add_return.html', customers=Customer.query.all(), today=datetime.now().strftime('%Y-%m-%d'), month=b_month)

    @app.route('/save_return', methods=['POST'])
    @login_required
    @permission_required('sales')
    def save_return():
        cust_id = request.form.get('customer_id'); month = int(request.form.get('billing_month') or 1); date_str = request.form.get('date'); today = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.now(); b_year = calc_billing_year(today.date(), month)
        with order_lock:
            prefix = f"R{today.strftime('%y%m%d')}"; last_order = ReturnOrder.query.filter(ReturnOrder.order_no.like(f"{prefix}%")).order_by(ReturnOrder.order_no.desc()).first(); seq = int(last_order.order_no[-3:]) + 1 if last_order else 1; order_no = f"{prefix}{seq:03d}"
            p_ids = request.form.getlist('product_id[]'); qtys = request.form.getlist('qty[]'); prices = request.form.getlist('price[]'); rems = request.form.getlist('remark[]')
            ro = ReturnOrder(order_no=order_no, date=today.date(), billing_year=b_year, billing_month=month, customer_id=cust_id)
            total_return = 0; total_cost = 0
            for i in range(len(p_ids)):
                p = db.session.get(Product, p_ids[i]); q = int(qtys[i]); pr = float(prices[i]); c = p.cost or 0.0; total_return += (q * pr); total_cost += (q * c)
                db.session.add(ReturnOrderItem(order=ro, product_id=p.id, qty=q, price=pr, cost=c, remark=rems[i]))
            ro.total_return_amount = total_return; ro.total_cost_amount = total_cost
            db.session.add(ro); db.session.commit()
        flash(f"退貨單 {order_no} 已建立！本期應收與應付帳款已自動抵扣，庫存維持不變。"); return redirect(url_for('return_orders'))

    @app.route('/return_orders')
    @login_required
    @permission_required('sales')
    def return_orders():
        q = request.args.get('q', '').strip(); year_filter = request.args.get('year', str(datetime.now().year)); month_filter = request.args.get('month', '')
        query = ReturnOrder.query
        if year_filter and year_filter.isdigit(): query = query.filter(ReturnOrder.billing_year == int(year_filter))
        if month_filter and month_filter.isdigit(): query = query.filter(ReturnOrder.billing_month == int(month_filter))
        if q:
            query = query.join(Customer).filter(db.or_(ReturnOrder.order_no.ilike(f'%{q}%'), Customer.short_name.ilike(f'%{q}%'), Customer.full_name.ilike(f'%{q}%')))
        orders = query.order_by(ReturnOrder.date.desc(), ReturnOrder.id.desc()).all()
        return render_template('return_orders.html', orders=orders, q=q, year_filter=year_filter, month_filter=month_filter)

    @app.route('/delete_return_order/<int:id>', methods=['POST'])
    @login_required
    @permission_required('sales')
    def delete_return_order(id):
        ro = db.get_or_404(ReturnOrder, id); db.session.delete(ro); db.session.commit()
        flash("退貨單已作廢！該筆扣除的應收帳款與應付帳款已恢復原狀。"); return redirect(url_for('return_orders'))

    @app.route('/add_dropship_page')
    @login_required
    @permission_required('sales')
    def add_dropship_page(): 
        _, b_month = get_current_billing_period(); return render_template('add_dropship.html', customers=Customer.query.all(), month=b_month)

    @app.route('/save_dropship', methods=['POST'])
    @login_required
    @permission_required('sales')
    def save_dropship():
        cust_id = request.form.get('customer_id'); month = int(request.form.get('billing_month') or 1); today = datetime.now(); b_year = calc_billing_year(today.date(), month)
        prefix = f"DS{today.strftime('%y%m%d')}"; last_order = DropShipOrder.query.filter(DropShipOrder.order_no.like(f"{prefix}%")).order_by(DropShipOrder.order_no.desc()).first(); seq = int(last_order.order_no[-3:]) + 1 if last_order else 1; order_no = f"{prefix}{seq:03d}"
        ds = DropShipOrder(order_no=order_no, date=today, billing_year=b_year, billing_month=month, customer_id=cust_id, status='pending')
        p_ids = request.form.getlist('product_id[]'); qtys = request.form.getlist('qty[]'); rems = request.form.getlist('remark[]'); added = False
        for i in range(len(p_ids)):
            q = int(qtys[i] or 0)
            if q > 0: db.session.add(DropShipOrderItem(order=ds, product_id=p_ids[i], qty=q, remark=rems[i])); added = True
        if not added: flash("請至少輸入一項商品！"); return redirect(url_for('add_dropship_page'))
        db.session.add(ds); db.session.commit(); flash(f"指配單 {order_no} 已建立，請等待廠商出貨後至首頁進行轉單！"); return redirect(url_for('index'))

    @app.route('/delete_dropship/<int:id>', methods=['POST'])
    @login_required
    @permission_required('sales')
    def delete_dropship(id): 
        ds = db.get_or_404(DropShipOrder, id); db.session.delete(ds); db.session.commit(); flash(f"指配單 {ds.order_no} 已作廢！"); return redirect(url_for('index'))

    @app.route('/print_dropship/<int:id>')
    @login_required
    @permission_required('sales')
    def print_dropship(id): ds = db.get_or_404(DropShipOrder, id); return f"指配單 {ds.order_no} 列印功能開發中..."

    @app.route('/convert_dropship/<int:id>')
    @login_required
    @permission_required('sales')
    def convert_dropship(id):
        ds = db.get_or_404(DropShipOrder, id); po_summary = {}
        for item in ds.items:
            v = item.product_ref.vendor_ref if item.product_ref else None; v_name = v.short_name if v else "未指定廠商"
            if v_name not in po_summary: po_summary[v_name] = []
            po_summary[v_name].append(item)
        return render_template('convert_dropship.html', ds=ds, po_summary=po_summary)

    @app.route('/execute_convert_dropship/<int:id>', methods=['POST'])
    @login_required
    @permission_required('sales')
    def execute_convert_dropship(id):
        ds = db.get_or_404(DropShipOrder, id)
        if ds.status == 'converted': flash("此單據已轉換過！"); return redirect(url_for('index'))
        today = datetime.now()
        prefix_s = today.strftime('%y%m%d'); last_so = SalesOrder.query.filter(SalesOrder.order_no.like(f"{prefix_s}%")).order_by(SalesOrder.order_no.desc()).first(); seq_s = int(last_so.order_no[-3:]) + 1 if last_so else 1; so_no = f"{prefix_s}{seq_s:03d}"
        so = SalesOrder(order_no=so_no, date=today.date(), billing_year=ds.billing_year, billing_month=ds.billing_month, customer_id=ds.customer_id); total_s = 0; std_raw_profit = 0; cash_raw_profit = 0; vendor_items = {}
        for item in ds.items:
            p = item.product_ref
            if not p: continue
            q = item.qty; pr = p.price * ((ds.customer_ref.price_discount or 100) / 100) if ds.customer_ref.price_discount > 1 else p.price * (ds.customer_ref.price_discount or 1.0); cost = p.cost or 0.0; rem = "[直寄] " + (item.remark or ''); is_cash = '現金價' in rem
            db.session.add(SalesOrderItem(order=so, product_id=p.id, qty=q, price=pr, cost=cost, remark=rem)); total_s += (q * pr); item_profit = (pr - cost) * q
            if is_cash: cash_raw_profit += item_profit
            else: std_raw_profit += item_profit
            vid = p.vendor_id
            if vid not in vendor_items: vendor_items[vid] = []
            vendor_items[vid].append({'p': p, 'q': q, 'cost': cost})
        so.total_amount = total_s; so.gross_profit = (std_raw_profit * (1 - ((ds.customer_ref.post_discount or 0.0) / 100))) + cash_raw_profit; db.session.add(so)
        prefix_p = f"P{today.strftime('%y%m%d')}"; last_po = PurchaseOrder.query.filter(PurchaseOrder.order_no.like(f"{prefix_p}%")).order_by(PurchaseOrder.order_no.desc()).first(); seq_p = int(last_po.order_no[-3:]) + 1 if last_po else 1
        for vid, items in vendor_items.items():
            if not vid: continue 
            po_no = f"{prefix_p}{seq_p:03d}"; seq_p += 1; po = PurchaseOrder(order_no=po_no, date=today.date(), billing_year=ds.billing_year, billing_month=ds.billing_month, vendor_id=vid); total_p = 0
            for vi in items:
                p = vi['p']; q = vi['q']; c = vi['cost']; db.session.add(PurchaseOrderItem(order=po, product_id=p.id, qty=q, price=c)); total_p += (q * c)
            po.total_amount = total_p; db.session.add(po)
        ds.status = 'converted'; db.session.commit(); flash(f"轉單成功！已自動生成銷貨與進貨單。系統庫存完美抵銷無變動。"); return redirect(url_for('index'))

    @app.route('/print_picking/<int:id>')
    @login_required
    @permission_required('sales')
    def print_picking(id): 
        slip = db.get_or_404(PickingSlip, id); return render_template('print_picking.html', slip=slip)

    @app.route('/print_sales/<int:id>')
    @login_required
    @permission_required('sales')
    def print_sales(id): 
        order = db.get_or_404(SalesOrder, id); return render_template('print_sales.html', order=order)