import os
import threading
from functools import wraps
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func
from PIL import Image

from config import Config
from extensions import db, migrate, login_manager


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    import models  # noqa: F401  確保 models 在 migrate 之前被載入
    from models import (
        User, Product, Announcement, CompanyProfile,
        SalesOrder, SalesOrderItem, PurchaseOrder, PurchaseOrderItem,
    )

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # === 系統初始化與防撞鎖（沿用既有 ERP 的設計）===
    order_lock = threading.Lock()

    UPLOAD_FOLDER_ANN = os.path.join('static', 'uploads', 'announcements')
    app.config['UPLOAD_FOLDER_ANN'] = UPLOAD_FOLDER_ANN
    os.makedirs(UPLOAD_FOLDER_ANN, exist_ok=True)
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

    # === 核心輔助函式區（沿用既有 ERP） ===
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    def process_and_save_image(file):
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER_ANN'], filename)
            img = Image.open(file)
            if img.width > 800:
                w_percent = (800 / float(img.width))
                h_size = int((float(img.height) * float(w_percent)))
                img = img.resize((800, h_size), Image.Resampling.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(os.path.splitext(filepath)[0] + ".jpg", "JPEG", quality=85, optimize=True)
            return os.path.splitext(filename)[0] + ".jpg"
        return None

    def permission_required(perm):
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                if current_user.username == 'admin':
                    return f(*args, **kwargs)
                role = current_user.role_ref
                if not role or not getattr(role, f'p_{perm}', False):
                    flash("系統提示：您的帳號沒有該功能的使用權限！")
                    return redirect(url_for('index'))
                return f(*args, **kwargs)
            return decorated_function
        return decorator

    def get_current_billing_period():
        today = datetime.now().date()
        profile = CompanyProfile.query.first()
        closing_day = profile.closing_day if profile and profile.closing_day else 31
        if today.day > closing_day:
            if today.month == 12:
                return today.year + 1, 1
            return today.year, today.month + 1
        return today.year, today.month

    def calc_billing_year(date_obj, billing_month):
        diff = billing_month - date_obj.month
        if diff <= -6:
            return date_obj.year + 1
        if diff >= 6:
            return date_obj.year - 1
        return date_obj.year

    # ==========================================
    # === 模組路由註冊（沿用既有 ERP 的四大模組）===
    # ==========================================
    from routes.basics import register_basics_routes
    from routes.sales import register_sales_routes
    from routes.purchases import register_purchases_routes
    from routes.finance import register_finance_routes

    register_basics_routes(app, permission_required)
    register_sales_routes(app, permission_required, order_lock, get_current_billing_period, calc_billing_year)
    register_purchases_routes(app, permission_required, order_lock, get_current_billing_period, calc_billing_year)
    register_finance_routes(app, permission_required)

    # ==========================================
    # === 共用 API 與首頁儀表板（沿用既有 ERP）===
    # ==========================================
    @app.route('/api/get_return_price')
    @login_required
    def get_return_price():
        cid, pid = request.args.get('customer_id', type=int), request.args.get('product_id', type=int)
        if not cid or not pid:
            return jsonify({'price': None})
        last_sale = db.session.query(SalesOrderItem).join(SalesOrder).filter(
            SalesOrder.customer_id == cid, SalesOrderItem.product_id == pid
        ).order_by(SalesOrder.date.desc(), SalesOrder.id.desc()).first()
        return jsonify({'price': last_sale.price if last_sale else None})

    @app.route('/api/get_latest_purchase_price')
    @login_required
    def get_latest_purchase_price():
        vid, pid = request.args.get('vendor_id', type=int), request.args.get('product_id', type=int)
        if not vid or not pid:
            return jsonify({'price': None})
        last_purchase = db.session.query(PurchaseOrderItem).join(PurchaseOrder).filter(
            PurchaseOrder.vendor_id == vid, PurchaseOrderItem.product_id == pid
        ).order_by(PurchaseOrder.date.desc(), PurchaseOrder.id.desc()).first()
        return jsonify({'price': last_purchase.price if last_purchase else None})

    @app.route('/api/historical_prices')
    @login_required
    def api_historical_prices():
        cid, pid = request.args.get('customer_id', type=int), request.args.get('product_id', type=int)
        if not cid or not pid:
            return jsonify([])
        history = db.session.query(SalesOrderItem.price, SalesOrder.date).join(SalesOrder).filter(
            SalesOrder.customer_id == cid, SalesOrderItem.product_id == pid
        ).order_by(SalesOrder.id.desc()).limit(3).all()
        return jsonify([{'date': h.date.strftime('%Y-%m-%d'), 'price': h.price} for h in history])

    @app.route('/api/historical_purchase_prices')
    @login_required
    def api_historical_purchase_prices():
        vid, pid = request.args.get('vendor_id', type=int), request.args.get('product_id', type=int)
        if not vid or not pid:
            return jsonify([])
        history = db.session.query(PurchaseOrderItem.price, PurchaseOrder.date).join(PurchaseOrder).filter(
            PurchaseOrder.vendor_id == vid, PurchaseOrderItem.product_id == pid
        ).order_by(PurchaseOrder.id.desc()).limit(3).all()
        return jsonify([{'date': h.date.strftime('%Y-%m-%d'), 'price': h.price} for h in history])

    @app.route('/')
    @login_required
    def index():
        from models import PickingSlip, DropShipOrder

        if current_user.username != 'admin' and current_user.role_ref and '業務' in current_user.role_ref.name:
            return render_template('index_pda.html', announcements=Announcement.query.order_by(Announcement.date.desc()).all())

        today = datetime.now().date()
        today_orders = SalesOrder.query.filter_by(date=today).all()
        today_revenue = sum(order.total_amount for order in today_orders)
        today_profit = sum(order.gross_profit for order in today_orders) if current_user.username == 'admin' else 0

        last_7_days = []
        revenue_7_days = []
        top_product_names = []
        top_product_qtys = []
        current_b_month = None
        current_month_revenue = 0
        current_month_purchase_total = 0

        if current_user.username == 'admin':
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                last_7_days.append(d.strftime('%m/%d'))
                revenue_7_days.append(sum(o.total_amount for o in SalesOrder.query.filter_by(date=d).all()))

            top_products = db.session.query(
                Product.name, func.sum(SalesOrderItem.qty).label('total_qty')
            ).join(SalesOrderItem).join(SalesOrder).filter(
                SalesOrder.billing_year == today.year, SalesOrder.billing_month == today.month
            ).group_by(Product.id).order_by(func.sum(SalesOrderItem.qty).desc()).limit(5).all()
            top_product_names, top_product_qtys = [p.name for p in top_products], [p.total_qty for p in top_products]

            current_b_year, current_b_month = get_current_billing_period()
            current_month_revenue = sum(o.total_amount for o in SalesOrder.query.filter_by(billing_year=current_b_year, billing_month=current_b_month).all())
            current_month_purchase_total = sum(o.total_amount for o in PurchaseOrder.query.filter_by(billing_year=current_b_year, billing_month=current_b_month).all())

        return render_template(
            'index.html',
            pending_slips=PickingSlip.query.filter_by(status='pending').all(),
            pending_dropships=DropShipOrder.query.filter_by(status='pending').all(),
            low_stock=Product.query.filter(Product.stock <= Product.safety_stock, Product.is_active == True).all(),
            today_revenue=today_revenue, today_profit=today_profit,
            announcements=Announcement.query.order_by(Announcement.date.desc()).all(),
            last_7_days=last_7_days, revenue_7_days=revenue_7_days,
            top_product_names=top_product_names, top_product_qtys=top_product_qtys,
            current_b_month=current_b_month, current_month_revenue=current_month_revenue,
            current_month_purchase_total=current_month_purchase_total,
        )

    @app.route('/add_announcement', methods=['POST'])
    @login_required
    def add_announcement():
        if current_user.username != 'admin':
            return redirect(url_for('index'))
        title = request.form.get('title')
        content = request.form.get('content')
        image_file = request.files.get('image')
        filename = process_and_save_image(image_file)
        if title and content:
            db.session.add(Announcement(title=title, content=content, image_filename=filename))
            db.session.commit()
            flash("公告已發布！")
        return redirect(url_for('index'))

    @app.route('/edit_announcement/<int:id>', methods=['POST'])
    @login_required
    def edit_announcement(id):
        if current_user.username != 'admin':
            return redirect(url_for('index'))
        ann = db.session.get(Announcement, id)
        if ann:
            ann.title = request.form.get('title')
            ann.content = request.form.get('content')
            new_image = request.files.get('image')
            if new_image and new_image.filename != '':
                old_path = os.path.join(app.config['UPLOAD_FOLDER_ANN'], ann.image_filename or '')
                if ann.image_filename and os.path.exists(old_path):
                    os.remove(old_path)
                ann.image_filename = process_and_save_image(new_image)
            db.session.commit()
            flash("公告已更新！")
        return redirect(url_for('index'))

    @app.route('/delete_announcement/<int:id>', methods=['POST'])
    @login_required
    def delete_announcement(id):
        if current_user.username != 'admin':
            return redirect(url_for('index'))
        ann = db.session.get(Announcement, id)
        if ann:
            old_path = os.path.join(app.config['UPLOAD_FOLDER_ANN'], ann.image_filename or '')
            if ann.image_filename and os.path.exists(old_path):
                os.remove(old_path)
            db.session.delete(ann)
            db.session.commit()
            flash("公告已刪除！")
        return redirect(url_for('index'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            user = User.query.filter_by(username=request.form.get('username')).first()
            if user and check_password_hash(user.password, request.form.get('password')):
                login_user(user)
                return redirect(url_for('index'))
            flash("帳號或密碼錯誤")
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.route('/pda')
    @login_required
    def pda_mode():
        return render_template('pda_mode.html')

    # ==========================================
    # === 蝦皮工作台對接（新增）===
    # ==========================================
    from routes.api_shopee import api_shopee_bp
    app.register_blueprint(api_shopee_bp)

    @app.route('/health')
    def health():
        return {'ok': True}

    return app


app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
