"""蝦皮出貨工作台（Chrome 擴充功能）對接 API。

擴充功能側錄到待出貨訂單後，用每個蝦皮賣場專屬的 API Key 呼叫這裡，
把訂單原始資料推送進來。這裡先只做「落地保存 + 依 order_sn 去重」，
轉成正式 SalesOrder（商品比對、扣庫存、金額計算等業務邏輯）留待下一
階段討論後再實作 —— 目的是先把「擴充功能 -> 雲端」的路打通。
"""
from flask import Blueprint, request, jsonify

from extensions import db
from models import ShopeeShop, ShopeeOrderRaw

api_shopee_bp = Blueprint("api_shopee", __name__, url_prefix="/api/shopee")


def _authenticate():
    """用 X-API-Key header 找出對應的蝦皮賣場，找不到回傳 None。"""
    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        return None
    return ShopeeShop.query.filter_by(api_key=api_key, is_active=True).first()


@api_shopee_bp.route("/ping", methods=["GET"])
def ping():
    """給擴充功能測試連線 + API Key 是否有效用。"""
    shop = _authenticate()
    if not shop:
        return jsonify({"ok": False, "error": "invalid or missing X-API-Key"}), 401
    return jsonify({"ok": True, "shop": shop.name})


@api_shopee_bp.route("/orders/sync", methods=["POST"])
def sync_orders():
    shop = _authenticate()
    if not shop:
        return jsonify({"ok": False, "error": "invalid or missing X-API-Key"}), 401

    body = request.get_json(silent=True) or {}
    orders = body.get("orders", [])
    if not isinstance(orders, list):
        return jsonify({"ok": False, "error": "orders must be a list"}), 400

    created, updated, skipped = 0, 0, 0
    for raw in orders:
        order_sn = (raw or {}).get("order_sn")
        if not order_sn:
            skipped += 1
            continue

        existing = ShopeeOrderRaw.query.filter_by(shop_id=shop.id, order_sn=order_sn).first()
        if existing:
            existing.payload = raw
            existing.package_number = raw.get("package_number")
            updated += 1
        else:
            db.session.add(ShopeeOrderRaw(
                shop_id=shop.id,
                order_sn=order_sn,
                package_number=raw.get("package_number"),
                payload=raw,
            ))
            created += 1

    db.session.commit()
    return jsonify({
        "ok": True,
        "shop": shop.name,
        "created": created,
        "updated": updated,
        "skipped": skipped,
    })
