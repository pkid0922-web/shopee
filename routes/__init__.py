from routes.auth import auth_bp
from routes.basics import basics_bp
from routes.sales import sales_bp
from routes.purchases import purchases_bp
from routes.finance import finance_bp
from routes.api_shopee import api_shopee_bp


def register_routes(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(basics_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(api_shopee_bp)
