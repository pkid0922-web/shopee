from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from models import db, Product, Vendor, Customer, User, Role, Employee, Category, Unit, CompanyProfile, SalesOrderItem, PurchaseOrderItem
from werkzeug.security import generate_password_hash
from sqlalchemy import func
from datetime import datetime
import pandas as pd
import io

def register_basics_routes(app, permission_required):

    @app.route('/api/search_products')
    @login_required
    def api_search_products():
        q = request.args.get('q', '').strip()
        if not q: return jsonify([])
        matches = Product.query.filter((Product.barcode.like(f"%{q}%")) | (Product.code1.like(f"%{q}%")) | (Product.code2.like(f"%{q}%")) | (Product.name.like(f"%{q}%"))).filter(Product.is_active == True).limit(20).all()
        return jsonify([{'id':p.id, 'barcode':p.barcode, 'name':p.name, 'unit':p.unit_ref.name if p.unit_ref else '個', 'price':p.price, 'cost':p.cost, 'stock':p.stock, 'code1':p.code1} for p in matches])

    @app.route('/api/get_product/<barcode>')
    @login_required
    def api_get_product(barcode):
        p = Product.query.filter((Product.barcode == barcode) | (Product.code1 == barcode) | (Product.code2 == barcode)).first()
        if p: return jsonify({'id':p.id, 'barcode':p.barcode, 'name':p.name, 'unit':p.unit_ref.name if p.unit_ref else '個', 'price':p.price, 'stock':p.stock, 'cost':p.cost})
        return jsonify({'error': '找不到'}), 404

    @app.route('/api/get_vendor_products/<int:vendor_id>')
    @login_required
    def api_get_vendor_products(vendor_id):
        products = Product.query.filter_by(vendor_id=vendor_id, is_active=True).all()
        return jsonify([{'id': p.id, 'barcode': p.barcode or '---', 'name': p.name, 'unit': p.unit_ref.name if p.unit_ref else '個'} for p in products])

    @app.route('/products')
    @login_required
    @permission_required('products')
    def list_products():
        q = request.args.get('q', '')
        status = request.args.get('status', 'all')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        per_page = per_page if per_page in (20, 50, 100, 200) else 50

        query = Product.query
        if status == 'on': query = query.filter(Product.is_active == True)
        elif status == 'off': query = query.filter(Product.is_active == False)

        if q: query = query.filter((Product.name.like(f"%{q}%")) | (Product.barcode.like(f"%{q}%")) | (Product.code1.like(f"%{q}%")))

        # 💡 分頁：只從資料庫撈當頁那 N 筆，不要把符合條件的商品全部讀出來
        # （商品資料已經上萬筆，撈全部 + 逐筆再查統計會非常慢）
        pagination = query.order_by(Product.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
        products = pagination.items

        # 💡 統計改成「當頁商品」一次 GROUP BY 撈出來，取代原本每筆商品各查兩次的迴圈
        # （原本 6,921 筆商品 = 13,842 次查詢；現在固定只要 2 次，不管有幾頁）
        product_ids = [p.id for p in products]
        stats = {pid: {'sales': 0, 'purchases': 0} for pid in product_ids}
        if product_ids:
            sales_rows = db.session.query(SalesOrderItem.product_id, func.sum(SalesOrderItem.qty)) \
                .filter(SalesOrderItem.product_id.in_(product_ids)).group_by(SalesOrderItem.product_id).all()
            purchase_rows = db.session.query(PurchaseOrderItem.product_id, func.sum(PurchaseOrderItem.qty)) \
                .filter(PurchaseOrderItem.product_id.in_(product_ids)).group_by(PurchaseOrderItem.product_id).all()
            for pid, total in sales_rows:
                stats[pid]['sales'] = total or 0
            for pid, total in purchase_rows:
                stats[pid]['purchases'] = total or 0

        return render_template('products.html', products=products, q=q, status=status, stats=stats,
                                pagination=pagination, per_page=per_page)

    # 💡 核心新增：商品匯出 Excel 的神級路由
    @app.route('/export_products')
    @login_required
    @permission_required('products')
    def export_products():
        export_type = request.args.get('export_type', 'all')
        q = request.args.get('q', '')
        status = request.args.get('status', 'all')
        
        query = Product.query
        
        # 如果是「匯出搜尋結果」，就套用跟畫面上完全一樣的過濾條件
        if export_type == 'filtered':
            if status == 'on': query = query.filter(Product.is_active == True)
            elif status == 'off': query = query.filter(Product.is_active == False)
            if q: query = query.filter((Product.name.like(f"%{q}%")) | (Product.barcode.like(f"%{q}%")) | (Product.code1.like(f"%{q}%")))
            
        products = query.order_by(Product.id.desc()).all()
        
        data = []
        for p in products:
            total_sales = db.session.query(func.sum(SalesOrderItem.qty)).filter(SalesOrderItem.product_id == p.id).scalar() or 0
            total_purchases = db.session.query(func.sum(PurchaseOrderItem.qty)).filter(PurchaseOrderItem.product_id == p.id).scalar() or 0
            
            data.append({
                '商品名稱': p.name or '',
                '國際條碼(Barcode)': p.barcode or '',
                '自編碼1': p.code1 or '',
                '自編碼2': p.code2 or '',
                '供應商': p.vendor_ref.short_name if p.vendor_ref else '',
                '分類': p.category_ref.name if p.category_ref else '未分類',
                '單位': p.unit_ref.name if p.unit_ref else '個',
                '採購成本': p.cost or 0,
                '商品定價': p.price or 0,
                '目前庫存': p.stock or 0,
                '安全庫存線': p.safety_stock or 0,
                '總進貨量': total_purchases,
                '總銷售量': total_sales,
                '狀態': '上架中' if p.is_active else '已停用'
            })
            
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='商品資料匯出')
        output.seek(0)
        
        filename = f"商品匯出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(output, download_name=filename, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.route('/add_product_page')
    @login_required
    @permission_required('products')
    def add_product_page(): 
        return render_template('add_product.html', categories=Category.query.all(), units=Unit.query.all(), vendors=Vendor.query.all())

    @app.route('/add_product', methods=['POST'])
    @login_required
    @permission_required('products')
    def add_product():
        v_id = request.form.get('vendor_id')
        p = Product(barcode=request.form.get('barcode'), name=request.form.get('name'), code1=request.form.get('code1'), code2=request.form.get('code2'), category_id=request.form.get('category_id'), unit_id=request.form.get('unit_id'), vendor_id=int(v_id) if v_id else None, cost=float(request.form.get('cost') or 0), price=float(request.form.get('price') or 0), safety_stock=int(request.form.get('safety_stock') or 0), stock=int(request.form.get('stock') or 0))
        db.session.add(p); db.session.commit(); return redirect(url_for('list_products'))

    @app.route('/edit_product/<int:id>', methods=['GET', 'POST'])
    @login_required
    @permission_required('products')
    def edit_product(id):
        p = db.session.get(Product, id)
        if request.method == 'POST':
            v_id = request.form.get('vendor_id')
            p.barcode = request.form.get('barcode'); p.name = request.form.get('name'); p.code1 = request.form.get('code1'); p.code2 = request.form.get('code2'); p.category_id = request.form.get('category_id'); p.unit_id = request.form.get('unit_id'); p.vendor_id = int(v_id) if v_id else None; p.cost = float(request.form.get('cost') or 0); p.price = float(request.form.get('price') or 0); p.safety_stock = int(request.form.get('safety_stock') or 0); p.stock = int(request.form.get('stock') or 0); p.is_active = True if request.form.get('is_active') else False
            db.session.commit(); return redirect(url_for('list_products'))
        return render_template('edit_product.html', product=p, categories=Category.query.all(), units=Unit.query.all(), vendors=Vendor.query.all())

    @app.route('/toggle_product_status/<int:id>')
    @login_required
    @permission_required('products')
    def toggle_product_status(id):
        p = db.session.get(Product, id); p.is_active = not p.is_active; db.session.commit(); return redirect(request.referrer)

    @app.route('/quick_add_cat', methods=['POST'])
    @login_required
    def quick_add_cat():
        name = request.form.get('name')
        if name and not Category.query.filter_by(name=name).first(): db.session.add(Category(name=name)); db.session.commit()
        return redirect(request.referrer)

    @app.route('/quick_add_unit', methods=['POST'])
    @login_required
    def quick_add_unit():
        name = request.form.get('name')
        if name and not Unit.query.filter_by(name=name).first(): db.session.add(Unit(name=name)); db.session.commit()
        return redirect(request.referrer)

    @app.route('/vendors')
    @login_required
    @permission_required('vendors')
    def list_vendors(): 
        return render_template('vendors.html', vendors=Vendor.query.all())

    @app.route('/add_vendor', methods=['POST'])
    @login_required
    @permission_required('vendors')
    def add_vendor():
        v = Vendor(vendor_no=request.form.get('vendor_no'), full_name=request.form.get('full_name'), short_name=request.form.get('short_name'), tax_id=request.form.get('tax_id'), phone=request.form.get('phone'), fax=request.form.get('fax'), contact_person=request.form.get('contact_person'), bank_account=request.form.get('bank_account'), warehouse_address=request.form.get('warehouse_address'), closing_day=int(request.form.get('closing_day') or 20), payment_day=int(request.form.get('payment_day') or 30), t1_amt=float(request.form.get('t1_amt') or 0), t1_dis=float(request.form.get('t1_dis') or 100), t2_amt=float(request.form.get('t2_amt') or 0), t2_dis=float(request.form.get('t2_dis') or 100), t3_amt=float(request.form.get('t3_amt') or 0), t3_dis=float(request.form.get('t3_dis') or 100))
        db.session.add(v); db.session.commit(); return redirect(url_for('list_vendors'))

    @app.route('/edit_vendor/<int:id>', methods=['GET', 'POST'])
    @login_required
    @permission_required('vendors')
    def edit_vendor(id):
        v = db.session.get(Vendor, id)
        if request.method == 'POST':
            v.vendor_no = request.form.get('vendor_no'); v.full_name = request.form.get('full_name'); v.short_name = request.form.get('short_name'); v.tax_id = request.form.get('tax_id'); v.phone = request.form.get('phone'); v.fax = request.form.get('fax'); v.contact_person = request.form.get('contact_person'); v.bank_account = request.form.get('bank_account'); v.warehouse_address = request.form.get('warehouse_address'); v.closing_day = int(request.form.get('closing_day') or 20); v.payment_day = int(request.form.get('payment_day') or 30); v.t1_amt = float(request.form.get('t1_amt') or 0); v.t1_dis = float(request.form.get('t1_dis') or 100); v.t2_amt = float(request.form.get('t2_amt') or 0); v.t2_dis = float(request.form.get('t2_dis') or 100); v.t3_amt = float(request.form.get('t3_amt') or 0); v.t3_dis = float(request.form.get('t3_dis') or 100)
            db.session.commit(); return redirect(url_for('list_vendors'))
        return render_template('edit_vendor.html', vendor=v)

    @app.route('/customers')
    @login_required
    @permission_required('customers')
    def list_customers(): 
        return render_template('customers.html', customers=Customer.query.all(), users=User.query.all())

    @app.route('/add_customer', methods=['POST'])
    @login_required
    @permission_required('customers')
    def add_customer():
        u_id = request.form.get('user_id')
        c = Customer(cust_no=request.form.get('cust_no'), full_name=request.form.get('full_name'), short_name=request.form.get('short_name'), tax_id=request.form.get('tax_id'), contact_person=request.form.get('contact_person'), phone=request.form.get('phone'), mobile=request.form.get('mobile'), fax=request.form.get('fax'), bank_account=request.form.get('bank_account'), price_discount=float(request.form.get('price_discount') or 60)/100, post_discount=float(request.form.get('post_discount') or 0), closing_day=int(request.form.get('closing_day') or 20), payment_day=int(request.form.get('payment_day') or 30), shipping_address=request.form.get('shipping_address'), invoice_address=request.form.get('invoice_address'), has_invoice=True if request.form.get('has_invoice') else False, user_id=int(u_id) if u_id else None)
        db.session.add(c); db.session.commit(); return redirect(url_for('list_customers'))

    @app.route('/edit_customer/<int:id>', methods=['GET', 'POST'])
    @login_required
    @permission_required('customers')
    def edit_customer(id):
        c = db.session.get(Customer, id)
        if request.method == 'POST':
            u_id = request.form.get('user_id')
            c.cust_no = request.form.get('cust_no'); c.full_name = request.form.get('full_name'); c.short_name = request.form.get('short_name'); c.tax_id = request.form.get('tax_id'); c.contact_person = request.form.get('contact_person'); c.phone = request.form.get('phone'); c.mobile = request.form.get('mobile'); c.fax = request.form.get('fax'); c.bank_account = request.form.get('bank_account'); c.price_discount = float(request.form.get('price_discount') or 60)/100; c.post_discount = float(request.form.get('post_discount') or 0); c.closing_day = int(request.form.get('closing_day') or 20); c.payment_day = int(request.form.get('payment_day') or 30); c.shipping_address = request.form.get('shipping_address'); c.invoice_address = request.form.get('invoice_address'); c.has_invoice = True if request.form.get('has_invoice') else False; c.user_id = int(u_id) if u_id else None
            db.session.commit(); return redirect(url_for('list_customers'))
        return render_template('edit_customer.html', customer=c, users=User.query.all())

    @app.route('/employees')
    @login_required
    @permission_required('employees')
    def list_employees(): 
        return render_template('employees.html', roles=Role.query.all(), users=User.query.all())

    @app.route('/add_role', methods=['POST'])
    @login_required
    @permission_required('employees')
    def add_role():
        r = Role(name=request.form.get('role_name'), p_products=True if request.form.get('p_products') else False, p_vendors=True if request.form.get('p_vendors') else False, p_customers=True if request.form.get('p_customers') else False, p_sales=True if request.form.get('p_sales') else False, p_purchases=True if request.form.get('p_purchases') else False, p_employees=True if request.form.get('p_employees') else False, p_finance=True if request.form.get('p_finance') else False)
        db.session.add(r); db.session.commit(); return redirect(url_for('list_employees'))

    @app.route('/add_user', methods=['POST'])
    @login_required
    @permission_required('employees')
    def add_user():
        u = User(username=request.form.get('username'), password=generate_password_hash(request.form.get('password')), role_id=request.form.get('role_id'))
        db.session.add(u); db.session.flush(); db.session.add(Employee(name=request.form.get('emp_name'), user_id=u.id)); db.session.commit(); return redirect(url_for('list_employees'))

    @app.route('/company_settings', methods=['GET', 'POST'])
    @login_required
    def company_settings():
        if current_user.username != 'admin' and not getattr(current_user.role_ref, 'p_employees', False): flash("權限不足，無法進入公司設定。"); return redirect(url_for('index'))
        profile = CompanyProfile.query.first()
        if not profile: profile = CompanyProfile(name="衣橙企業", short_name="e-Orange", closing_day=31); db.session.add(profile); db.session.commit()
        if request.method == 'POST':
            profile.name = request.form.get('name'); profile.short_name = request.form.get('short_name'); profile.tax_id = request.form.get('tax_id'); profile.phone = request.form.get('phone'); profile.fax = request.form.get('fax'); profile.address = request.form.get('address'); profile.bank_account = request.form.get('bank_account'); profile.contact_person = request.form.get('contact_person'); profile.closing_day = int(request.form.get('closing_day') or 31); db.session.commit(); flash("公司基本設定已成功更新！")
            return redirect(url_for('company_settings'))
        return render_template('company_settings.html', profile=profile)

    @app.route('/download_product_template')
    @login_required
    @permission_required('products')
    def download_product_template():
        df = pd.DataFrame(columns=['國際條碼(Barcode)', '商品名稱(Name)*必填', '自編碼1', '自編碼2', '供應商簡稱(留空不綁定)', '分類名稱(不存在將自動建立)', '單位(預設:個)', '採購成本', '商品定價', '安全庫存線', '首批庫存量']); df.loc[0] = ['4711234567890', '雄獅奇異筆 黑', 'P001', '', '雄獅', '文具用品', '支', 10, 20, 15, 50]; df.loc[1] = ['', '無條碼測試商品', '', '', '', '生活用品', '個', 50, 100, 5, 10]; output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False, sheet_name='商品批次匯入範本')
        output.seek(0)
        return send_file(output, download_name="商品批次匯入範本.xlsx", as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.route('/bulk_upload_products', methods=['POST'])
    @login_required
    @permission_required('products')
    def bulk_upload_products():
        if 'file' not in request.files: flash("請選擇檔案！"); return redirect(url_for('list_products'))
        file = request.files['file']
        if file.filename == '': flash("請選擇檔案！"); return redirect(url_for('list_products'))
        if not file.filename.endswith(('.xlsx', '.xls')): flash("僅支援 Excel (.xlsx, .xls) 檔案格式！"); return redirect(url_for('list_products'))
        try:
            df = pd.read_excel(file); success_count = skip_count = 0
            for index, row in df.iterrows():
                def safe_val(col, default=''): val = row.get(col); return default if pd.isna(val) else val
                name = str(safe_val('商品名稱(Name)*必填')).strip()
                if not name or name == 'nan': skip_count += 1; continue
                barcode = str(safe_val('國際條碼(Barcode)')).strip()
                if barcode.endswith('.0'): barcode = barcode[:-2]
                if not barcode or barcode == 'nan': barcode = None
                if barcode and Product.query.filter_by(barcode=barcode).first(): skip_count += 1; continue
                code1 = str(safe_val('自編碼1')).strip()
                if code1.endswith('.0'): code1 = code1[:-2]
                if not code1 or code1 == 'nan': code1 = None
                code2 = str(safe_val('自編碼2')).strip()
                if code2.endswith('.0'): code2 = code2[:-2]
                if not code2 or code2 == 'nan': code2 = None
                vendor_name = str(safe_val('供應商簡稱(留空不綁定)')).strip(); vendor_id = None
                if vendor_name and vendor_name != 'nan':
                    v = Vendor.query.filter((Vendor.short_name == vendor_name) | (Vendor.full_name == vendor_name)).first()
                    if v: vendor_id = v.id
                cat_name = str(safe_val('分類名稱(不存在將自動建立)')).strip(); cat_id = None
                if cat_name and cat_name != 'nan':
                    c = Category.query.filter_by(name=cat_name).first()
                    if not c: c = Category(name=cat_name); db.session.add(c); db.session.commit()
                    cat_id = c.id
                unit_name = str(safe_val('單位(預設:個)', '個')).strip()
                if not unit_name or unit_name == 'nan': unit_name = '個'
                u = Unit.query.filter_by(name=unit_name).first()
                if not u: u = Unit(name=unit_name); db.session.add(u); db.session.commit()
                unit_id = u.id
                try: cost = float(safe_val('採購成本', 0.0))
                except: cost = 0.0
                try: price = float(safe_val('商品定價', 0.0))
                except: price = 0.0
                try: safety_stock = int(safe_val('安全庫存線', 10))
                except: safety_stock = 10
                try: stock = int(safe_val('首批庫存量', 0))
                except: stock = 0
                p = Product(barcode=barcode, name=name, code1=code1, code2=code2, category_id=cat_id, unit_id=unit_id, vendor_id=vendor_id, cost=cost, price=price, safety_stock=safety_stock, stock=stock); db.session.add(p); success_count += 1
            db.session.commit(); msg = f"成功匯入 {success_count} 筆商品資料！"
            if skip_count > 0: msg += f" (已略過 {skip_count} 筆名稱空白或條碼重複的資料)"
            flash(msg)
        except Exception as e: db.session.rollback(); flash(f"匯入失敗，請確認檔案格式是否與範本相符！錯誤細節：{str(e)}")
        return redirect(url_for('list_products'))
    
    # ==========================================
    # 💡 全新模組：新品報價單引擎
    # ==========================================
    @app.route('/quotation')
    @login_required
    def quotation_page():
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        cust_id = request.args.get('customer_id', '')
        
        products = []
        # 只有在業務有選擇日期時才去撈資料
        if start_date and end_date:
            # 確保時間範圍涵蓋到 end_date 當天的 23:59:59
            products = Product.query.filter(
                Product.is_active == True,
                Product.created_at >= f"{start_date} 00:00:00",
                Product.created_at <= f"{end_date} 23:59:59"
            ).order_by(Product.created_at.desc()).all()
            
        customers = Customer.query.all()
        selected_cust = db.session.get(Customer, cust_id) if cust_id else None
        
        return render_template('quotation.html', products=products, start_date=start_date, end_date=end_date, customers=customers, selected_cust=selected_cust)