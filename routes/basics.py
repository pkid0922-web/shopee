from flask import Blueprint, render_template
from flask_login import login_required

from models import Product, Customer, Vendor, SalesOrder

basics_bp = Blueprint("basics", __name__)


@basics_bp.route("/")
@login_required
def dashboard():
    stats = {
        "product_count": Product.query.count(),
        "customer_count": Customer.query.count(),
        "vendor_count": Vendor.query.count(),
        "sales_order_count": SalesOrder.query.count(),
    }
    return render_template("dashboard.html", stats=stats)
