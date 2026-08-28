# CLAUDE.md

給 Claude Code 在這個專案裡工作的指引。完整功能與架構說明見 [README.md](README.md)。

## 專案是什麼

雲端進銷存系統（Flask + SQLAlchemy + PostgreSQL/Railway），從本機 ERP 搬遷而來，並與蝦皮出貨工作台（Chrome 擴充功能）串接。核心進銷存業務邏輯（銷售/採購/財務）已完整實作；蝦皮串接目前只做到訂單原始資料落地保存，尚未轉正式銷貨單。

## 開發指令

```bash
./.venv/Scripts/python -m pip install -r requirements.txt
./.venv/Scripts/python scripts/seed.py   # 建表 + 建立管理員帳號 admin/admin123
./.venv/Scripts/python app.py            # 開發伺服器 http://localhost:5000
```

- Migration：`flask db migrate -m "..."` → `flask db upgrade`（Railway 部署時 `release` 階段會自動跑 `flask db upgrade`）
- 沒有測試套件、沒有 lint 設定——目前這個專案沒有自動化檢查

## 架構慣例（新增程式碼時要遵守）

- **App factory 模式**：所有初始化在 `app.py` 的 `create_app()` 裡完成，不要在 import 階段建立全域狀態
- **`extensions.py` 的 `db`/`migrate`/`login_manager` 要先建立、後 `init_app()` 綁定**，這是刻意設計來避免 `models.py` / `routes/*.py` / `app.py` 之間 circular import，不要改成在 `models.py` 裡直接 `from app import db`
- **業務路由模組（`routes/basics.py`/`sales.py`/`purchases.py`/`finance.py`）不是 Blueprint**，而是匯出 `register_*_routes(app, ...)` 函式，用 `@app.route`直接註冊、靠參數做依賴注入（`permission_required`、`order_lock`、`get_current_billing_period`、`calc_billing_year`）。新增這類路由要放進對應模組並沿用同一種寫法
- **只有 `routes/api_shopee.py` 用標準 Blueprint**（給外部擴充功能呼叫的獨立 API 命名空間）。新增其他對外 API 時比照這個模式，不要塞進既有 ERP 頁面路由裡
- **權限檢查**：頁面路由用 `@permission_required('sales')` 等 decorator（檢查 `Role.p_*` 布林欄位，`admin` 帳號略過）；新模組要加權限就先在 `Role` model 加對應的 `p_xxx` 欄位 + migration

## 業務規則（容易出錯、AI 常常猜錯的部分）

- **單號規則**：銷貨單 `S`、進貨單 `P`、退貨單 `R`、進貨退出 `PRT`、請購單 `PR`、代出貨單 `DS` + `YYMMDD` + 3 碼流水號。產生新單號一定要在 `order_lock` 鎖內查詢「當天最大單號 + 1」，不要用資料庫自增 id 或省略鎖
- **現金價 vs 一般價**：靠 `remark` 欄位字串是否包含「現金價」文字判斷，不是額外欄位。一般價毛利要套用客戶 `post_discount`（月結折扣），現金價毛利不打折
- **毛利公式**：`gross_profit = 一般價毛利 * (1 - post_discount%) + 現金價毛利`
- **結帳月（billing period）**：不是自然月，是依 `CompanyProfile.closing_day` 判斷；`calc_billing_year(date_obj, billing_month)` 處理跨年容錯（差距 ≥6 個月要調整年份），修改結帳月相關邏輯要連這個函式一起看
- **庫存連動是雙向且會被「復原」**：銷貨/退出扣庫存，進貨/退回加庫存；編輯或作廢單據時，程式碼會先把舊明細的庫存**復原**，再套用新內容重新扣/加。改這類路由時務必保留「先復原再套用」的順序，否則庫存會算錯
- **代出貨轉單**（`execute_convert_dropship`）：一張代出貨單依商品供應商拆分，同時產生一張銷貨單 + 多張進貨單，庫存互相抵銷、帳面存貨不變動——這是這個系統最複雜的單一路由，改動前建議先重讀 `routes/sales.py` 的完整邏輯

## 蝦皮串接現況（未完成的部分，避免誤以為已經做完）

- `POST /api/shopee/orders/sync` 目前**只把訂單原始資料存進 `ShopeeOrderRaw`**，不會建立 `SalesOrder`、不會扣庫存
- `SalesOrder.source`/`shop_id`/`shopee_order_sn` 和 `Product.shopee_item_id`/`shopee_model_id` 欄位已經預留好，但轉換邏輯（商品比對、扣庫存、成本/毛利計算）還沒寫，不要假設它已經運作
- API 認證用 `X-API-Key` header 對應 `ShopeeShop.api_key`，每個蝦皮賣場一把

## 待確認事項（改動前最好先跟使用者確認）

- 蝦皮 API Key 的發放/儲存機制還在規劃中
- `ShopeeOrderRaw` → 正式 `SalesOrder` 的業務規則還沒定案
- 多店鋪情境下商品/庫存是否要分店鋪，還沒決定
