"""把「蝦皮商品對照表」匯入進 Product.shopee_item_id / shopee_model_id。

來源是鼎新A1「商品編號對應」頁面側錄出來的 CSV（見
scripts/import_a1_products.py 的姊妹腳本，資料來源不同但比對邏輯類似）。
比對主鍵用「A1商品明細編號」（沒有就退回「A1商品編號」）對應 Product.code1，
找到就把該筆商品的蝦皮平台商品編號/規格編號寫進去，這樣蝦皮工作台之後
用 item_id+model_id 查詢就能拿到成本、庫存、售價來算毛利。

用法：
    python scripts/import_shopee_mapping.py <對照表csv路徑> [--dry-run]
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from extensions import db
from models import Product


def load_rows(csv_path):
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        rows = load_rows(args.csv_path)
        print(f"讀到 {len(rows)} 筆對照資料")

        matched, unmatched, no_a1_code, dup_code1 = 0, 0, 0, 0
        seen_code1 = {}

        for row in rows:
            a1_code = (row.get("A1商品明細編號") or "").strip() or (row.get("A1商品編號") or "").strip()
            if not a1_code:
                no_a1_code += 1
                continue

            item_id = (row.get("平台商品編號") or "").strip()
            model_id = (row.get("平台規格編號") or "").strip()

            product = Product.query.filter_by(code1=a1_code).first()
            if not product:
                unmatched += 1
                continue

            if a1_code in seen_code1:
                dup_code1 += 1
            seen_code1[a1_code] = True

            if not args.dry_run:
                product.shopee_item_id = item_id or None
                product.shopee_model_id = model_id or None
            matched += 1

        if args.dry_run:
            print(f"[dry-run] 會更新 {matched} 筆商品（其中 {dup_code1} 筆 A1 品號在對照表出現一次以上，只會留最後一筆）")
        else:
            db.session.commit()
            print(f"完成：更新 {matched} 筆商品的蝦皮編號")

        print(f"對照表裡沒有填 A1 編號（尚未比對過）：{no_a1_code} 筆")
        print(f"對照表裡的 A1 編號在商品資料庫找不到對應商品：{unmatched} 筆")


if __name__ == "__main__":
    main()
