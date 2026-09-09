"""資料模型。

大部分模型沿用既有本機 ERP（G:/ERP/models.py）的設計，維持欄位相容，
方便之後把業務邏輯（routes）也搬過來。與蝦皮工作台對接相關的部分
（ShopeeShop / ShopeeOrderRaw，以及 SalesOrder 新增的 shop 關聯欄位）
是這次新增的，其餘商業邏輯（庫存扣減、成本計算等）留待下一階段討論後再實作。
"""
from datetime import datetime

from flask_login import UserMixin

from extensions import db


# ========== 帳號與權限 ==========

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    p_products = db.Column(db.Boolean, default=True)
    p_vendors = db.Column(db.Boolean, default=True)
    p_customers = db.Column(db.Boolean, default=True)
    p_sales = db.Column(db.Boolean, default=True)
    p_purchases = db.Column(db.Boolean, default=True)
    p_employees = db.Column(db.Boolean, default=False)
    p_finance = db.Column(db.Boolean, default=False)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("role.id"))
    role_ref = db.relationship("Role", backref="users")


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    emp_no = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref=db.backref("employee", uselist=False))


# ========== 基礎資料 ==========

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class Unit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor_no = db.Column(db.String(20), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    short_name = db.Column(db.String(50))
    tax_id = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    fax = db.Column(db.String(20))
    contact_person = db.Column(db.String(50))
    bank_account = db.Column(db.String(100))
    warehouse_address = db.Column(db.String(200))
    closing_day = db.Column(db.Integer, default=20)
    payment_day = db.Column(db.Integer, default=30)
    t1_amt = db.Column(db.Float, default=0.0)
    t1_dis = db.Column(db.Float, default=100.0)
    t2_amt = db.Column(db.Float, default=0.0)
    t2_dis = db.Column(db.Float, default=100.0)
    t3_amt = db.Column(db.Float, default=0.0)
    t3_dis = db.Column(db.Float, default=100.0)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cust_no = db.Column(db.String(20), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    short_name = db.Column(db.String(50))
    tax_id = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    mobile = db.Column(db.String(20))
    fax = db.Column(db.String(20))
    contact_person = db.Column(db.String(50))
    bank_account = db.Column(db.String(100))
    shipping_address = db.Column(db.String(200))
    invoice_address = db.Column(db.String(200))
    closing_day = db.Column(db.Integer, default=20)
    payment_day = db.Column(db.Integer, default=30)
    price_discount = db.Column(db.Float, default=0.6)
    post_discount = db.Column(db.Float, default=0.0)
    has_invoice = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user_ref = db.relationship("User", backref="assigned_customers")


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(100), nullable=False)
    code1 = db.Column(db.String(50))
    code2 = db.Column(db.String(50))
    cost = db.Column(db.Float, default=0.0)
    price = db.Column(db.Float, default=0.0)
    safety_stock = db.Column(db.Integer, default=0)
    stock = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    category_ref = db.relationship("Category", backref="products")
    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"))
    unit_ref = db.relationship("Unit", backref="products")
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"))
    vendor_ref = db.relationship("Vendor", backref="products")
    # 蝦皮商品對應：用來把訂單裡的 item_id / model_id 對回自家商品
    shopee_item_id = db.Column(db.String(50), index=True)
    shopee_model_id = db.Column(db.String(50), index=True)
    created_at = db.Column(db.DateTime, default=db.func.now())


class CompanyProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, default="公司名稱")
    short_name = db.Column(db.String(50))
    tax_id = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    fax = db.Column(db.String(20))
    address = db.Column(db.String(200))
    bank_account = db.Column(db.String(200))
    contact_person = db.Column(db.String(50))
    closing_day = db.Column(db.Integer, default=31)


# ========== 銷售 ==========

class PickingSlip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slip_no = db.Column(db.String(50), unique=True)
    date = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(20), default="pending")
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    customer_ref = db.relationship("Customer")
    items = db.relationship("PickingSlipItem", backref="slip", cascade="all, delete-orphan")


class PickingSlipItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slip_id = db.Column(db.Integer, db.ForeignKey("picking_slip.id"))
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    qty = db.Column(db.Integer)
    product_ref = db.relationship("Product")


class SalesOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(50), unique=True)
    date = db.Column(db.Date)
    billing_year = db.Column(db.Integer)
    billing_month = db.Column(db.Integer)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    total_amount = db.Column(db.Float, default=0.0)
    gross_profit = db.Column(db.Float, default=0.0)
    customer_ref = db.relationship("Customer")
    items = db.relationship("SalesOrderItem", backref="order", cascade="all, delete-orphan")

    # --- 蝦皮訂單來源相關（新增）---
    source = db.Column(db.String(20), default="manual")  # manual / shopee
    status = db.Column(db.String(20), default="pending")  # pending / shipped / cancelled ...
    shop_id = db.Column(db.Integer, db.ForeignKey("shopee_shop.id"))
    shop_ref = db.relationship("ShopeeShop")
    shopee_order_sn = db.Column(db.String(50), index=True)
    shopee_package_number = db.Column(db.String(50), index=True)


class SalesOrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("sales_order.id"))
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    qty = db.Column(db.Integer)
    price = db.Column(db.Float)
    cost = db.Column(db.Float, default=0.0)
    remark = db.Column(db.String(200))
    product_ref = db.relationship("Product")


class DropShipOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(50), unique=True)
    date = db.Column(db.DateTime, default=datetime.now)
    billing_year = db.Column(db.Integer)
    billing_month = db.Column(db.Integer)
    status = db.Column(db.String(20), default="pending")
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    customer_ref = db.relationship("Customer")
    items = db.relationship("DropShipOrderItem", backref="order", cascade="all, delete-orphan")


class DropShipOrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("drop_ship_order.id"))
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    qty = db.Column(db.Integer)
    remark = db.Column(db.String(200))
    product_ref = db.relationship("Product")


class ReturnOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(50), unique=True)
    date = db.Column(db.Date)
    billing_year = db.Column(db.Integer)
    billing_month = db.Column(db.Integer)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    total_return_amount = db.Column(db.Float, default=0.0)
    total_cost_amount = db.Column(db.Float, default=0.0)
    customer_ref = db.relationship("Customer")
    items = db.relationship("ReturnOrderItem", backref="order", cascade="all, delete-orphan")


class ReturnOrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("return_order.id"))
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    qty = db.Column(db.Integer)
    price = db.Column(db.Float)
    cost = db.Column(db.Float)
    remark = db.Column(db.String(200))
    product_ref = db.relationship("Product")


# ========== 採購 ==========

class PurchaseOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(50), unique=True)
    date = db.Column(db.Date)
    billing_year = db.Column(db.Integer)
    billing_month = db.Column(db.Integer)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"))
    total_amount = db.Column(db.Float, default=0.0)
    vendor_ref = db.relationship("Vendor")
    items = db.relationship("PurchaseOrderItem", backref="order", cascade="all, delete-orphan")


class PurchaseOrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("purchase_order.id"))
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    qty = db.Column(db.Integer)
    price = db.Column(db.Float)
    product_ref = db.relationship("Product")


class PurchaseRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    req_no = db.Column(db.String(50), unique=True)
    date = db.Column(db.DateTime, default=datetime.now)
    billing_year = db.Column(db.Integer)
    billing_month = db.Column(db.Integer)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"))
    vendor_ref = db.relationship("Vendor")
    items = db.relationship("PurchaseRequestItem", backref="request", cascade="all, delete-orphan")


class PurchaseRequestItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("purchase_request.id"))
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    qty = db.Column(db.Integer)
    product_ref = db.relationship("Product")


class PurchaseReturnOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(20), unique=True, nullable=False)
    date = db.Column(db.Date, nullable=False)
    billing_year = db.Column(db.Integer, nullable=False)
    billing_month = db.Column(db.Integer, nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"), nullable=False)
    total_return_amount = db.Column(db.Float, default=0)
    vendor_ref = db.relationship("Vendor", backref="purchase_returns")
    items = db.relationship("PurchaseReturnOrderItem", backref="order", lazy=True, cascade="all, delete-orphan")


class PurchaseReturnOrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("purchase_return_order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    remark = db.Column(db.String(200))
    product_ref = db.relationship("Product")


# ========== 財務 ==========

class PaymentRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    billing_year = db.Column(db.Integer)
    billing_month = db.Column(db.Integer)
    amount = db.Column(db.Float, default=0.0)
    method = db.Column(db.String(20))
    date = db.Column(db.DateTime, default=datetime.now)
    customer_ref = db.relationship("Customer")


class VendorPaymentRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"))
    billing_year = db.Column(db.Integer)
    billing_month = db.Column(db.Integer)
    amount = db.Column(db.Float, default=0.0)
    method = db.Column(db.String(20))
    date = db.Column(db.DateTime, default=datetime.now)
    vendor_ref = db.relationship("Vendor")


class InvoiceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    billing_year = db.Column(db.Integer)
    billing_month = db.Column(db.Integer)
    invoice_date = db.Column(db.Date)
    amount = db.Column(db.Float, default=0.0)
    is_printed = db.Column(db.Boolean, default=False)
    customer_ref = db.relationship("Customer")


class FixedExpense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    remark = db.Column(db.String(200))


# ========== 其他 ==========

class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)
    image_filename = db.Column(db.String(100))


# ========== 蝦皮工作台對接（新增）==========

class ShopeeShop(db.Model):
    """一個蝦皮賣場（賣家中心的 shop_id），對應一把給擴充功能用的 API Key。"""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    platform_shop_id = db.Column(db.String(30), unique=True, nullable=False)  # 蝦皮的 shop_id
    api_key = db.Column(db.String(64), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)


class ShopeeProductMapping(db.Model):
    """蝦皮商品編號對應（多賣場）。

    一個 Product 可以同時對應到好幾個蝦皮賣場的不同 (item_id, model_id)——
    賣場A賣的「黑色」跟賣場B賣的「黑色款」很可能是同一個 A1 商品，但蝦皮
    平台編號不同。這張表取代 Product.shopee_item_id/shopee_model_id 那組
    只能存單一賣場的舊欄位（那組欄位保留只是相容舊資料，新查詢一律走這裡）。
    """

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shopee_shop.id"), nullable=False)
    shop_ref = db.relationship("ShopeeShop")
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    product_ref = db.relationship("Product", backref="shopee_mappings")
    platform_item_id = db.Column(db.String(50), nullable=False, index=True)   # 平台商品編號
    platform_model_id = db.Column(db.String(50), default="")                  # 平台規格編號（無規格商品為空字串）
    qty = db.Column(db.Integer, default=1)          # 對應數量（一個蝦皮規格對應幾個 A1 品項）
    allocation_ratio = db.Column(db.Float, default=1.0)  # 配銷比例
    created_at = db.Column(db.DateTime, default=datetime.now)

    __table_args__ = (
        db.UniqueConstraint("shop_id", "platform_item_id", "platform_model_id", name="uq_shopee_mapping_shop_item_model"),
    )


class ShopeeOrderRaw(db.Model):
    """擴充功能推送過來的原始訂單資料。先落地保存，
    轉成正式 SalesOrder（含商品比對、扣庫存等業務邏輯）留待下一階段實作。"""

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shopee_shop.id"), nullable=False)
    shop_ref = db.relationship("ShopeeShop")
    order_sn = db.Column(db.String(50), nullable=False, index=True)
    package_number = db.Column(db.String(50))
    payload = db.Column(db.JSON)
    received_at = db.Column(db.DateTime, default=datetime.now)
    processed = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.UniqueConstraint("shop_id", "order_sn", name="uq_shopee_order_raw_shop_order"),
    )
