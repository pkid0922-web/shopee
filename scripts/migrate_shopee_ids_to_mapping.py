"""一次性搬遷：把 Product.shopee_item_id/shopee_model_id 舊欄位的資料
搬進新的 ShopeeProductMapping 表（標記為指定賣場）。

用法：
    python scripts/migrate_shopee_ids_to_mapping.py <賣場名稱> <平台shop_id>
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from extensions import db
from models import Product, ShopeeShop, ShopeeProductMapping
import secrets


def main():
    if len(sys.argv) < 3:
        print("用法：python scripts/migrate_shopee_ids_to_mapping.py <賣場名稱> <平台shop_id>")
        sys.exit(1)
    shop_name, platform_shop_id = sys.argv[1], sys.argv[2]

    app = create_app()
    with app.app_context():
        shop = ShopeeShop.query.filter_by(platform_shop_id=platform_shop_id).first()
        if not shop:
            shop = ShopeeShop(name=shop_name, platform_shop_id=platform_shop_id, api_key=secrets.token_hex(24))
            db.session.add(shop)
            db.session.flush()
            print(f"建立賣場：{shop_name} ({platform_shop_id})")
        else:
            print(f"賣場已存在：{shop.name} ({shop.platform_shop_id})")

        products = Product.query.filter(Product.shopee_item_id.isnot(None)).all()
        created, skipped = 0, 0
        for p in products:
            exists = ShopeeProductMapping.query.filter_by(
                shop_id=shop.id, platform_item_id=p.shopee_item_id, platform_model_id=p.shopee_model_id or ""
            ).first()
            if exists:
                skipped += 1
                continue
            db.session.add(ShopeeProductMapping(
                shop_id=shop.id,
                product_id=p.id,
                platform_item_id=p.shopee_item_id,
                platform_model_id=p.shopee_model_id or "",
            ))
            created += 1

        db.session.commit()
        print(f"完成：新增 {created} 筆對照、略過 {skipped} 筆（已存在）")


if __name__ == "__main__":
    main()
