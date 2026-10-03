# MiniSuper — Supermarket / Mini-Market Management System

A Django 5.2 web application for running a small supermarket or mini-market end-to-end:
point of sale, inventory, purchasing, staff scheduling, waste control and reporting.

The application is built around **fast counter operation** (a keyboard/click driven POS cart),
**auditable stock movement** (every stock change writes a `StockMovement` row) and
**perishable-goods awareness** (waste, spoilage, expiry and refrigeration flags).

> Setup, commands, coding conventions and the fix-list for known problems live in
> [`INSTRUCTIONS.md`](INSTRUCTIONS.md).

---

## 1. Snapshot

| Item | Value |
| --- | --- |
| Project folder | `minisuper/` (repo was originally named `mini_super`) |
| Framework | Django 5.2.7 |
| Python | 3.13 (working venv: `../venv`, Python 3.13.7) |
| Database | PostgreSQL (configured via `.env`, driver `psycopg`); falls back to SQLite `minisuper/db.sqlite3` when `DB_NAME` is unset |
| Front-end | Django templates + Bootstrap 5.3 + Font Awesome 6.4 + Inter + Chart.js (all via CDN) |
| Static files | `static/` exists but is empty; every asset is loaded from a CDN |
| Branding in UI | `CarlPos`, `POS.CarlKasa`, `MiniSuper` (inconsistent) |
| Currency in UI | Configurable in one place (`/settings/`) — `TZS` by default; applied to every screen, export and JS helper |
| Exports | CSV, Excel (`openpyxl`) and PDF (`reportlab`) |
| Access control | Four Django-group roles — `Owner`, `Sell`, `Stock`, `SellerStock` (`core/permissions.py`, §7) |
| Tests | 141 (`python manage.py test`), all green |

---

## 2. Feature overview

### 2.1 `inventory` — catalogue, stock and purchasing
* **Categories** — list/search, create, edit; per-category product counts.
* **Suppliers** — list/search/filter by active status, create, edit; uniqueness on name and e-mail.
  The supplier link is **optional** on both products and purchase orders (walk-in / cash sourcing);
  pages print *No supplier* instead of an empty cell.
* **Products** — SKU catalogue with barcode, category, supplier (optional), product type
  (`perishable`, `non_perishable`, `frozen`, `non_food`), cost/selling price, decimal stock levels
  (`max_digits=10, decimal_places=3`, so weighed goods work), min/max levels, refrigeration flag,
  high-value / high-theft-risk flags, computed `stock_status` and `profit_margin`. There is no
  `expiry_date` column: shelf life is recorded per delivery (see *Shelf life on deliveries* below).
* **Low stock view** — products where `current_stock <= min_stock_level`, with a stock % indicator.
* **Stock movements** — append-only audit log (`in`, `out`, `adjustment`, `waste`) recording
  `previous_stock`, `new_stock`, `reason`, `user` and `created_at`.
* **Stock adjustment** — manual add/remove with a mandatory reason (writes a `StockMovement`).
* **Purchase orders** — header plus inline item formset. The **straight flow**: an order is created
  already *placed* (status `ordered`) — there is no draft step — and the only action left is
  **Purchase**, which adds every line to stock, logs one `in` movement per line and marks the order
  `received`. The create form offers **Create & Place Order** and **Create & Purchase Now** (place and
  stock in one click); the same *Purchase* action is on the detail page and in the list page modal.
  Legacy `draft` rows can still be placed or purchased, `cancelled`/already `received` orders are
  refused (a second purchase never adds stock twice). Auto-computed `total_amount` plus
  overdue/upcoming helpers. The screens label the states *Draft (not placed) / Placed / Purchased*;
  the stored status values are unchanged (`draft`, `ordered`, `received`, `cancelled`). The list has a
  **status tab per state** (counts come from every filtered order, so switching tabs never zeroes the
  other counters) which is also how purchased orders are read apart from the ones still being chased.
* **Received purchases** (`/inventory/purchases/`) — the other half of that split: one block **per
  purchased order** (supplier, dates, line count, value, order link), each listing the products it
  actually brought in with that line's use-by date and days-left wording. Filters for supplier, date
  range, search (order id / supplier / product name and SKU) and shelf life
  (`?expiry=expired|soon|none`), plus totals for deliveries, lines, quantity and value bought in and
  counts of expired / expiring-soon lines. Nothing that was never purchased appears here.
* **Shelf life on deliveries** — each purchase-order line carries an optional use-by date
  (`PurchaseOrderItem.expiry_date`), typed into the **Expiry Date** column of the order form (a past
  date is flagged client-side as a likely typo, but still saved). This is the **only** place a shelf
  life is stored: expiry belongs to a delivery, not to a product, since the same item arrives in
  batches that run out on different days. The product row has **no** `expiry_date` column — it is
  derived on demand as a queryset annotation, `Product.objects.with_expiry()`, which reduces the
  product's received order lines to one date in the database: the **soonest use-by date that has not
  passed yet** (the delivery the shelf is about to lose), falling back to the **latest date already
  recorded** so a delivery that lapsed while still in stock keeps reporting as expired instead of the
  alert silently disappearing. Because the date is never duplicated, correcting an order line is
  enough — the list, the detail page and the bell follow immediately. The `StockMovement` reason still
  records `Purchase order #12 purchased (expires 04 Nov 2026)`. The product list gains an **Expiry**
  column with days-left wording, the product detail page shows days remaining, the order detail table
  lists the date per line, and `?expiry=expired` / `?expiry=soon` filter the product list by shelf
  life. The purchase order list has an **Expiry** column too, and — because one order can carry
  several dates — an order row is summarised by its **soonest** line (`Expired · 1 line past`,
  `6 days left`, with *earliest of N* when the delivery held more than one date; an order that is only
  placed shows the date it is expected to arrive with, and a purchased one with no dates says
  *Not recorded*). `PurchaseOrder` therefore exposes `line_expiry_dates`, `earliest_expiry`,
  `latest_expiry`, `expiry_date_count`, `days_until_earliest_expiry` and `expired_line_count`, read
  off the prefetched lines.

### 2.2 `sales` — point of sale and sales history
* **Point of Sale** (`/sales/pos/`) — searchable product grid, JavaScript cart, optional customer,
  payment method (`cash`, `card`, `mobile`, `transfer`). The cart is posted as JSON in `cart_data`;
  the server validates stock, writes `Sale` + `SaleItem`, decrements stock inside one
  `transaction.atomic()` block with `select_for_update()`, adds 8 % tax, logs stock movements and
  refreshes the day's `DailySummary`.
* **Sale list / detail** — filter by date and payment method; printable detail with line items.
* **Daily summaries** — one `DailySummary` per day (total sales, customers, cash/card/mobile split).
* **Customer analytics** — total and regular customers, top spenders, new customers.
* **JSON API** — `/sales/api/sales-data/?days=7` for chart data.

### 2.3 `operations` — store operations
* **Waste tracking** — record waste (spoilage / damage / expired / other) with quantity and cost;
  decrements stock, writes a `waste` movement, and reports monthly totals, breakdown by category and
  top wasted products.
* **Staff scheduling** — weekly shift grid over `Staff` and `Shift`, plus add/delete shift
  endpoints with overlap detection and hours calculation.
* **Performance metrics** — KPI page reading sales, waste, peak hours and staffing data.
* **Supplier performance** — `SupplierPerformance` evaluations (on-time rate, order accuracy,
  quality score, notes).
* **Peak hours** — scans the last 7 days of sales hour by hour into `PeakHour`
  (unique per `date` + `hour`).
* **JSON helpers** — `operations_dashboard_data`, `staff_productivity_report`.

### 2.4 Root project — dashboards and reports
* **Dashboard** (`/`) — last-7-days sales chart, today's sales, low-stock count, today's customers,
  month-to-date waste cost, recent sales and a low-stock list.
* **Sales report** — date-range presets (today / yesterday / week / month / custom), revenue, item
  counts, average sale, payment breakdown, daily trend and top products.
* **Inventory report** — stock valuation, low/out-of-stock counts, filters, pagination.
* **Analytics** — revenue trend plus product, category and customer performance.
* **Exports** — `/reports/sales/export/<csv|excel|pdf>/` and
  `/reports/inventory/export/<csv|excel|pdf>/`.
* **Auth** — Django `LoginView`/`LogoutView` with custom templates plus password-reset routes;
  `LOGIN_URL = 'login'`, `LOGIN_REDIRECT_URL = 'dashboard'`.

### 2.5 `core` — site settings, alerts and roles
* **Users & Roles** (`/settings/users/`) — the owner adds a login, ticks the roles it may
  hold (`Owner` / `Sell` / `Stock` / `SellerStock`) and blocks or edits one later, without
  ever opening the Django admin. The four roles, their permissions and the page-by-page
  rules live in `core/permissions.py` — see §7. Role names appear in the top bar and on the
  user list; `core.context_processors.roles` exposes `user_role`, `user_groups` and
  `user_has_role` to every template.
* **Currency & number format** (`/settings/`) — one `SiteSettings` singleton row (pk=1) holds the
  store currency (TZS, USD, EUR, GBP, KES, UGX, NGN, ZAR, INR, JPY, CNY or a custom code) plus
  symbol, decimals, position and separators. `{% load currency %}` exposes `|money`,
  `|money_code`, `|money_plain` and `|money_decimals`; Python code uses
  `core.formatting.format_money()`. `window.APP_CURRENCY` + `formatMoney()` mirror it in JavaScript.
  Money is **display-only**: changing the currency relabels stored amounts, it does not convert them.
* **Notification bell** (`/notifications/`) — every page's top bar shows a live alert count. Alerts
  are **derived from live data, never stored**, so they clear themselves the moment the problem is
  fixed:
  * *Stock* — products `out of stock` (critical) or at/below `min_stock_level` (warning).
  * *Expiry* — products holding stock whose use-by date has passed (critical) or arrives within
    7 days (warning). The date is typed per line on the purchase order and read back from those
    lines — see *Shelf life on deliveries* above.
  * *Orders* — purchase orders that are still `draft` (info), arriving within 3 days (warning) or
    `overdue` (critical); every other open `ordered` order is listed as *awaiting delivery*.
  Read state lives in the session (`core.notifications.acknowledge`), so clicking an alert marks it
  read **and** navigates to the product / purchase order; "Mark all as read" clears the badge without
  hiding the alert. The sidebar **Low Stock Alert**, **Purchase Orders** and **Expiry Alerts** badges
  use the same real counts. Adding an alert kind means appending to `product_alerts()` /
  `expiry_alerts()` / `order_alerts()` — the bell, the badge and the full page need no changes.

---

## 3. Project layout

```
Mini Supermarket/
├── venv/                     # working virtualenv (Django 5.2.7, Python 3.13)  ← use this
├── .venv/                    # older virtualenv WITHOUT Django installed (do not use)
└── minisuper/                # ← project root; every command is run from here
    ├── manage.py
    ├── .env                  # DB credentials + Django settings, loaded by python-dotenv (git-ignored)
    ├── .env.example          # documented template to copy into `.env`
    ├── db.sqlite3            # SQLite fallback, used only when DB_NAME is unset (git-ignored)
    ├── r.txt                 # the real pip freeze / requirements list
    ├── README.md             # this description
    ├── INSTRUCTIONS.md       # setup, commands, conventions, known-issue fixes
    ├── minisuper/            # settings, root urls, dashboard/report views, exporters
    │   ├── settings.py
    │   ├── urls.py
    │   ├── views.py          # SalesReportView, InventoryReportView, AnalyticsView, dashboard
    │   └── reports.py        # Export*ReportView (CSV / Excel / PDF)
    ├── core/                 # site settings, notification bell, roles
    │   ├── permissions.py    # the four role groups + PermissionRequiredMixin (§7)
    │   └── management/commands/setup_groups.py
    ├── inventory/            # models, forms, views, urls, admin
    ├── sales/
    ├── operations/
    ├── static/               # empty — all CSS/JS comes from CDNs
    └── templates/
        ├── base.html         # sidebar shell (role-gated links), global CSS, Chart.js, messages
        ├── dashboard.html    # role-gated cards / chart / recent sales
        ├── 403.html          # "this area is not part of your role"
        ├── debug_templates.html
        ├── inventory/    (19 files, incl. received_purchases.html)
        ├── sales/        (point_of_sale, sale_list, sale_detail, customer_analytics,
        │                  dailysummary_list + 2 stray "point_of_sale copy" files)
        ├── operations/   (waste_tracking, performance_metrics, shift_list)
        ├── reports/      (sales_report, inventory_report, analytics)
        ├── notifications/ (notification_list)
        ├── settings/     (site_settings + user_list, user_form)
        └── registration/ (login, logged_out, password_reset_form)
```

---

## 4. Data model at a glance

```
Category 1──n Product n──0..1 Supplier
Product  1──n StockMovement            (audit trail; user FK → auth.User)
Product  1──n PurchaseOrderItem n──1 PurchaseOrder n──0..1 Supplier
Product  1──n SaleItem          n──1 Sale n──1 Customer (nullable)
Sale     n──1 auth.User (cashier)
DailySummary                       (one row per date)
Product  1──n WasteRecord  n──1 auth.User (recorded_by)
Staff    1──1 auth.User ;  Staff 1──n Shift
PeakHour (date + hour unique) ;   SupplierPerformance n──1 Supplier
```

Modelling decisions worth preserving:

* **Stock is a decimal, not an integer** — `DecimalField(max_digits=10, decimal_places=3)` on
  `Product.current_stock`, `StockMovement.quantity`, `SaleItem.quantity`,
  `PurchaseOrderItem.quantity` and `WasteRecord.quantity`. Always parse input with
  `Decimal(str(value))`; never let a float into stock maths.
* **Every stock change is logged** — sales, waste, purchase-order receiving and manual adjustments
  all write a `StockMovement` with before/after values. Any new feature that touches stock must do the
  same. (Editing a product through the product form is the one exception today.)
* **`on_delete=PROTECT`** on `Product` → `Category`/`Supplier` and on audit-trail user FKs, so history
  cannot be orphaned by deleting a category, supplier or user. The two supplier FKs are additionally
  **optional** (`null=True, blank=True`, migration `inventory/0005_make_supplier_optional`) — a product
  or order may be saved with no supplier, but `PROTECT` still refuses to delete a supplier any row
  points at.
* **`related_name='items'`** on `PurchaseOrderItem` and `SaleItem`, accessed as `order.items` /
  `sale.items`.
* Money fields are `DecimalField(max_digits=10..12, decimal_places=2)` with `MinValueValidator(0)`
  on `Product.cost_price`, `Product.selling_price` and `Sale.total_amount`.
* **Shelf life lives on the delivery, not on the product.** `Product` has no `expiry_date` column
  (migration `inventory/0008_remove_product_expiry_date`); the date is recorded once, on
  `PurchaseOrderItem.expiry_date` (migration `inventory/0007_purchaseorderitem_expiry_date`, help text
  refreshed in `inventory/0009_purchaseorderitem_expiry_help_text`), because
  the same item can arrive in batches that expire on different days. What the pages and the bell need
  is one answer per product, so `Product.objects.with_expiry()` annotates it in the database from the
  lines of the orders that product has **received** (an `ordered` or `cancelled` order dates nothing):
  the soonest use-by date still in the future, or — when every recorded delivery has already lapsed —
  the latest one, so expired stock keeps alerting. `Product.expiry_date`, `is_expired`,
  `days_until_expiry` and `expiry_status` remain readable properties, so templates and the alert code
  are unchanged; a product fetched without the annotation (admin, shell, a bare instance) falls back to
  one narrow query and caches the result. The same reading is exposed **per order** for the list pages
  (`PurchaseOrder.earliest_expiry` and friends), computed from `order.items` so a
  `prefetch_related('items')` queryset costs no extra query.
  *Limitation:* without per-batch quantities there is no way to tell that the older of two batches has
  been sold out, so a lapsed date can be reported while newer stock is on the shelf. That is what a
  batch/lot table would fix; the fallback-to-latest rule above at least keeps the *useful* case
  (nothing fresh on the shelf) working.
* **Pagination reads `page_obj`, not the context object name.** `ListView` puts the *sliced queryset*
  under `context_object_name` and the `Page` under `page_obj`, so `{% if purchase_orders.paginator... %}`
  silently resolves to nothing and the controls never render. Both list templates page off `page_obj`
  and build their links with Django's `{% querystring %}` tag, which keeps every active filter.

---

## 5. URL map (names usable with `reverse()`)

Every row below needs a login *and* the role that owns that area — §7 has the full matrix.
Rows marked **owner** are the only ones the other roles cannot reach; `dashboard`,
`notifications`, `login` and `logout` are open to anyone signed in.

| Name | Path | View |
| --- | --- | --- |
| `dashboard` | `/` | `minisuper.views.dashboard` — everyone who is signed in |
| `login` / `logout` | `/accounts/login/`, `/accounts/logout/` | Django auth views |
| `notifications` / `notifications-open` / `notifications-mark-all-read` | `/notifications/`, `/notifications/open/`, `/notifications/mark-all-read/` | notification bell — everyone who is signed in |
| `site-settings` | `/settings/` | `SiteSettingsUpdateView` — **owner** |
| `user-list` / `user-create` / `user-update` | `/settings/users/`, `/settings/users/add/`, `/settings/users/<pk>/edit/` | Users & Roles (`UserListView`, `UserCreateView`, `UserUpdateView`) — **owner** |
| `product-list` | `/inventory/` | `ProductListView` |
| `product-detail` | `/inventory/product/<pk>/` | `ProductDetailView` |
| `product-create` / `product-update` / `product-delete` | `/inventory/product/add/`, `/<pk>/edit/`, `/<pk>/delete/` | CRUD views |
| `low-stock` | `/inventory/low-stock/` | `LowStockView` |
| `category-list` / `category-create` / `category-update` | `/inventory/categories/`, `/inventory/category/add/`, `/inventory/category/<pk>/edit/` | CRUD views |
| `supplier-list` / `supplier-create` / `supplier-update` | `/inventory/suppliers/`, `/inventory/supplier/add/`, `/inventory/supplier/<pk>/edit/` | CRUD views |
| `purchase-order-list` / `-create` / `-detail` / `-update` / `-delete` | `/inventory/purchase-orders/`, `/inventory/purchase-order/add/`, `/<pk>/`, `/<pk>/edit/`, `/<pk>/delete/` | CRUD views |
| `purchase-order-mark-ordered` / `-receive` / `-cancel` | `/inventory/purchase-order/<pk>/place\|purchase\|cancel/` | function views — **`POST`-only + `@login_required`** (`-receive` is the *Purchase* action) |
| `received-purchases` | `/inventory/purchases/` | `ReceivedPurchaseListView` — purchased orders, one block per order, with the use-by date of each line |
| `stock-movement-list` | `/inventory/stock-movements/` | `StockMovementListView` |
| `adjust-stock` | `/inventory/product/<product_id>/adjust-stock/` | `adjust_stock` |
| `point-of-sale` | `/sales/pos/` | `point_of_sale` |
| `sale-list` / `sale-detail` | `/sales/sales/`, `/sales/sales/<pk>/` | `SaleListView`, `SaleDetailView` |
| `daily-reports` | `/sales/daily-reports/` | `DailyReportView` |
| `customer-analytics` | `/sales/customer-analytics/` | `customer_analytics` |
| `sales-api-data` | `/sales/api/sales-data/` | `sales_api_data` |
| `waste-tracking` | `/operations/waste-tracking/` | `waste_tracking` |
| `staff-scheduling` / `add-shift` | `/operations/staff-scheduling/`, `/operations/add-shift/` | `StaffSchedulingView`, `add_shift` |
| `performance-metrics` | `/operations/performance-metrics/` | `PerformanceMetricsView` |
| `supplier-performance` / `evaluate-supplier` | `/operations/supplier-performance/`, `/operations/evaluate-supplier/` | `SupplierPerformanceView`, `evaluate_supplier` |
| `track-peak-hours` | `/operations/track-peak-hours/` | `track_peak_hours` |
| `sales_report_new` / `inventory_report` / `analytics` | `/reports/sales/`, `/reports/inventory/`, `/reports/analytics/` | report views |
| `export_sales_report` / `export_inventory_report` | `/reports/{sales,inventory}/export/<format_type>/` | exporter views |
| `admin` | `/admin/` | Django admin (inventory app only — see §7) |

---

## 6. How stock actually changes

| Trigger | Effect on `Product.current_stock` | `movement_type` |
| --- | --- | --- |
| POS sale (`sales.views.process_sale`) | `-= quantity` (stock-checked, atomic, row-locked) | `out` |
| Waste recorded (`operations.views.record_waste`) | `-= quantity` (capped at available) | `waste` |
| Waste record deleted (`delete_waste_record`) | `+= quantity` (restores stock) | `in` |
| Purchase order **purchased** (create form *Create & Purchase Now*, or *Purchase* on the detail/list page) | `+= item.quantity` per line — **once per order** (an already `received` or `cancelled` order is refused, a legacy `draft` is placed on the way); the line's `expiry_date` is *not* copied anywhere — it stays the single record the product's shelf life is derived from | `in` |
| Manual `adjust_stock` | `+=` or `-=` per chosen type (never below 0) | `in` / `out` |
| Editing a Product in the product form | direct field write, **no movement logged** | — |

Sales pricing: `SaleItem.unit_price` is taken from the client-submitted cart, `total_amount` is
recalculated server side, then `tax_rate = Decimal('0.08')` is applied and stored in `Sale.tax_amount`.
`DailySummary` is recalculated by `sales.views.update_daily_summary()` for the sale's date.

---

## 7. Admin, auth and roles

### The four roles
Access is decided by **Django groups**, declared in one place — `core/permissions.py` —
and created/refreshed automatically after every `migrate` (`core.apps.CoreConfig.ready`
hooks `post_migrate`) or on demand with `python manage.py setup_groups`. There is no
`role` column anywhere: a role *is* a `Group`, and everything else (views, sidebars,
dashboard cards, the bell) asks Django's own `has_perm` / `perms` questions.

| Role | Sees | Does **not** see |
| --- | --- | --- |
| `Owner` | Everything: the till, the shelf, operations, **Currency & Settings**, **Users & Roles** | the Django admin panel (`/admin/` — an owner is not `is_staff`) |
| `Sell` | Dashboard, POS, Sales History, Daily Reports, Customers, Customer Returns, Sales report, Analytics, Notifications | products/categories/suppliers, purchase orders, stock movements, supplier returns, low-stock/expiry alerts, waste, shifts, performance, inventory report, settings, users |
| `Stock` | Dashboard, products, categories, suppliers, purchase orders, received purchases, supplier returns, stock movements, low-stock + expiry alerts, waste, staff shifts, performance, supplier performance, inventory report, Notifications | POS, sales history, daily reports, customers, customer returns, sales report, analytics, settings, users |
| `SellerStock` | the union of `Sell` and `Stock` (the one person who does both) | settings, users |

* **Enforcement** — class-based views inherit `core.permissions.PermissionRequiredMixin`
  (`raise_exception = True`) and set `permission_required = 'app.codename'`; function views
  use `@permission_required(..., raise_exception=True)` **under** `@login_required`, so an
  anonymous visitor is still sent to the login form while a signed-in user who lacks the
  role gets a real **403 page** (`templates/403.html`, "This area is not part of your
  role") instead of a login loop.
* **Sidebar & dashboard** — `templates/base.html` gates every link section by permission
  (`{% if perms.inventory.view_product %}` …), the top bar shows the caller's role from
  `core.context_processors.roles` (`{{ user_role }}` → *Owner* / *Seller* / *Stock* /
  *Seller + Stock* / *No role*), the **Admin Panel** link only appears for `user.is_staff`,
  and the dashboard cards/charts/recent-sales table render per permission. A login with no
  role at all gets the dashboard plus a hint to ask the owner for one.
* **The bell is role-aware** — `core.notifications.CATEGORY_PERMISSIONS` maps each alert
  kind to the permission it needs (`stock`/`expiry` → `inventory.view_product`, `orders` →
  `inventory.view_purchaseorder`), so a seller is never nagged about shelving (and the
  sidebar counters stay at zero rather than leaking the numbers).
* **Users & Roles** (`/settings/users/`, owner only) — list, add, edit/block logins and
  hand out the four roles without touching `/admin/`. The form offers *only* the shop roles
  (`StaffUserForm` / `StaffUserUpdateForm`, 8-character minimum + Django's
  `AUTH_PASSWORD_VALIDATORS`), and an owner editing their own account cannot block
  themselves. Stepping down from `Owner` is allowed as soon as a second active Owner
  exists; otherwise (`UserUpdateView.form_valid`) the role is put back and the warning
  says why — so the shop can never lose the last person who can hand roles out. The
  role a person is given takes effect on their next page load (the sidebar, the
  dashboard and the bell are all answered from Django's own `has_perm` per request,
  nothing is cached in the session). A fresh install is bootstrapped by the Django
  superuser (who passes every permission check) or by
  `python manage.py setup_groups --owner <username>`.
* **Django admin** — untouched and still inventory-only (`inventory/admin.py`: inlines,
  status badges, bulk actions, `site_header = "MiniSuper Inventory Administration"`);
  `sales/admin.py` and `operations/admin.py` remain empty stubs, so `Sale`, `Customer`,
  `DailySummary`, `Staff`, `Shift`, `WasteRecord`, `PeakHour` and `SupplierPerformance` are
  **not** visible in `/admin/`. No role grants admin-model permissions, and only
  `is_staff` accounts can log in there.
* **All state-changing function views are decorated**: `@login_required` + `@require_POST`
  (`mark_as_ordered`, `receive_purchase_order`, `cancel_purchase_order`, `record_waste`,
  `delete_waste_record`) or `@login_required` only for the ones that render a form too
  (`adjust_stock`, `add_shift`, …) — each with the matching `@permission_required`.
  `record_waste` was the last undecorated view and is now covered (it is reached through
  `waste_tracking`'s POST branch and has no URL of its own).

Test coverage lives in `core/tests.py`: `RoleGroupTests` (the permission sets themselves,
including "every declared permission exists" and "syncing is idempotent"),
`RoleAccessTests` (a page-by-page 200/403 matrix for each role, the sidebar and the
dashboard cards), `UsersAndRolesPageTests` (including "a role change reaches the sidebar
on the next page load"), `RoleAwareNotificationTests`, `SetupGroupsCommandTests`,
`EveryPageIsGuardedTests` (walks the URLconf so a new page cannot quietly become public)
and `PageStructureTests` (renders every page for three roles and asserts the tags balance,
so a stray `</div>` in the sidebar — which used to push the whole page out of the main
column — fails the suite instead of shipping).


---

## 8. Known issues / technical debt

`python manage.py check` reports **no issues** and `makemigrations --check` reports **no pending
migrations**, yet a number of pages fail. A URL smoke test run on 2026-09-30 (33 named routes, logged-in
client, see `INSTRUCTIONS.md` §9) originally failed on **8 routes** — the P0 items below — and passed 2
more only because of the template fallback described under P1.

**Current state (re-measured 2026-09-30): `33 routes checked, 0 failure(s)`.** The P0 crashes 1-9 are
fixed; item 10 (which is also not routed) and the `add_shift` bug are still open. The purchase-order
flow was also reworked into the **straight flow** — orders are created already placed, the only action
left is *Purchase*, and the duplicate `receive_purchase_order` (which silently doubled stock) is gone;
`INSTRUCTIONS.md` §6.0 has the status table, §8.1-§8.6 the purchase-order hardening and the straight
flow (with `INSTRUCTIONS.md` §9.3 = the regression scripts, including the 40-check purchase-order one),
§6/§7 the fixes for what is left and §8 the remaining hardening. The supplier is now **optional** on
products and purchase orders (migration `inventory/0005_make_supplier_optional`, `INSTRUCTIONS.md` §8.8,
48-check script in §9.3), so a walk-in / cash purchase can be recorded without inventing a vendor.

### P0 — pages that crashed (HTTP 500)

| # | Location | Symptom | Status |
| --- | --- | --- | --- |
| 1 | `inventory/views.py` — `ProductDetailView.get_context_data`, `StockMovementListView.get_queryset` | `FieldError: Cannot resolve keyword 'timestamp'` — `StockMovement` orders on `created_at`. Broke `/inventory/stock-movements/` and product detail. | **fixed** — now `-created_at`; the same typo was rendering blank dates in `sale_list.html`, `sale_detail.html`, `dashboard.html` and `waste_tracking.html` and was fixed there too. |
| 2 | `inventory/models.py` — `PurchaseOrder` | `Sum`, `F`, `timezone` are used but never imported → `NameError` in `calculate_total_amount()` (so saving/receiving a PO blows up) and in `is_overdue` / `is_upcoming` / `days_until_delivery` / `days_overdue`. | **fixed** — imports added; totals and the four date properties verified. |
| 3 | `minisuper/reports.py` | `timedelta` is never imported → every sales export except `date_range=today` raises `NameError`. | **fixed** — imported. |
| 4 | `minisuper/reports.py` — sales `export_excel` | `AttributeError: 'MergedCell' object has no attribute 'column_letter'` while auto-sizing columns → Excel sales export fails. | **fixed** — both exporters use `get_column_letter(column[0].column)`. |
| 5 | `operations/views.py` — `add_shift` | `Shift.objects.create(..., notes=notes)` but `Shift` has no `notes` field → `TypeError`, swallowed by the broad `except Exception` and shown as *"Error adding shift"*. | **open** — decide between dropping the kwarg and adding `Shift.notes` + migration. |
| 6 | Missing template `inventory/product_detail.html` | `ProductDetailView` cannot render (the model-name fallback resolves to the same missing name). | **fixed** — template added. |
| 7 | Missing template `inventory/product_confirm_delete.html` | `ProductDeleteView` cannot render. | **fixed** — template added. |
| 8 | Missing template `inventory/stock_adjustment.html` | `adjust_stock` (GET) cannot render. | **fixed** — template added. |
| 9 | Missing templates `operations/supplier_performance.html` **and** the fallback `operations/supplierperformance_list.html` | `SupplierPerformanceView` cannot render. | **fixed** — template added and its POST target verified. |
| 10 | Missing template `operations/staff_productivity_report.html` | `staff_productivity_report` cannot render — and it is not routed either. | **open** |


### P1 — silently wrong, duplicated or fragile

* `sales/daily_reports.html` and `operations/staff_scheduling.html` are used as `template_name` but do
  not exist. They appear to work only because Django's `MultipleObjectTemplateResponseMixin` appends a
  model-based candidate (`sales/dailysummary_list.html`, `operations/shift_list.html`) and
  `select_template()` picks the first template that exists. Renaming either file silently changes the
  page — always create the explicitly named template instead.
* ~~State-changing **GET** endpoints: `mark_as_ordered`, `receive_purchase_order`,
  `cancel_purchase_order` mutate data on GET, and they — like `adjust_stock`, `record_waste`,
  `process_sale` and the second `receive_purchase_order` — carry **no `@login_required`**. Any
  anonymous visitor could hit `/inventory/purchase-order/<pk>/receive/` and change stock.~~
  **fixed** — all three purchase-order actions are `@login_required` + `@require_POST`
  (`GET` → 405, anonymous → redirect to `/accounts/login/`), `adjust_stock` got `@login_required`
  (it still *serves* the GET form, so it must not be `@require_POST`), and `process_sale` already had
  it. `record_waste` was the last state-changing view without a decorator — **fixed**:
  it now carries `@login_required` + `@require_POST` + `@permission_required`, and
  `delete_waste_record` / the other operations actions were guarded the same way. Every
  view now also asks for the **role** that owns its area (see §7), so this whole bullet is
  closed.

* ~~`receive_purchase_order` is defined **twice** in `inventory/views.py` (≈ line 418 and ≈ line 467);
  the second definition silently overrides the first, which contained the status guard and the
  `transaction.atomic()` block.~~ **fixed** — the duplicate is gone. This was the worst bug of the
  set: the live definition had **no status check**, so *purchasing the same order twice doubled the
  stock* (and the crash in README P0 #2 hid it). The surviving view refuses a `received` or
  `cancelled` order and applies the lines inside `transaction.atomic()`.
* ~~`inventory/urls.py` declares `purchase-orders/`, `purchase-order/add/` and
  `purchase-order/<pk>/receive/` twice (≈ lines 24-26 and 33-39). The first match wins.~~
  **fixed** — the duplicate block is removed; the *place* route now lives at
  `/inventory/purchase-order/<pk>/place/` (name unchanged: `purchase-order-mark-ordered`).
* `inventory/forms.py` defines `PurchaseOrderItemFormSet` twice (≈ line 7 and ≈ line 349); the second
  definition wins.
* Routed nowhere / referenced nowhere: `delete_waste_record`, `delete_shift`,
  `operations_dashboard_data`, `staff_productivity_report` (no URL entry, no template link).
* `minisuper/views.py::custom_login` calls `messages` without importing it and is not routed — dead code.
* `update_daily_summary` counts `Count('customer', distinct=True)`, which ignores anonymous
  (NULL-customer) sales; `customer_count` is therefore "distinct registered customers", not footfall.
* `AnalyticsView` "profit" is `Sum(F('unit_price') - (F('quantity') * F('product__cost_price')))` —
  a per-line estimate, not real margin — and revenue is summed from `unit_price` rather than
  `unit_price * quantity`, so multi-quantity lines are under-counted.
* `Product.profit_margin_display` duplicates the `profit_margin` property and is never used.
* Dead files: `templates/sales/point_of_sale copy.html`, `templates/sales/point_of_sale copy 2.html`
  (spaces in filenames) and `templates/debug_templates.html`.
* Branding/currency drift: `base.html` shows *CarlPos*, `dailysummary_list.html` shows *POS.CarlKasa*,
  `dashboard.html` shows *MiniSuper*; POS/product screens print `TZS` while reports and CSV/Excel
  exports hard-code `$` (`f"${product.cost_price:.2f}"`).
* `Sale.generate_transaction_id()` is timestamp based, so two sales in the same second can collide.

### P2 — configuration and production readiness

* `SECRET_KEY`, `DEBUG` and `ALLOWED_HOSTS` are read from `.env` (via `python-dotenv`), but still
  fall back to a hard-coded insecure `SECRET_KEY` and `ALLOWED_HOSTS = ['*']` when the file is absent.
* No `STATIC_ROOT` / `STATICFILES_DIRS` → `collectstatic` cannot run; `static/` is empty and every
  asset is a CDN URL, so the UI degrades without internet access.
* `TIME_ZONE = 'UTC'` for store data priced in TZS, so the local business day boundary is shifted;
  every `created_at__date=...` comparison is off by the local offset.
* `USE_L10N` is deprecated in Django 5 (harmless but should be removed).
* The database is **PostgreSQL** when `DB_NAME` is set in `.env` (driver `psycopg`, both listed in
  `r.txt`), otherwise `settings.py` falls back to the local SQLite file. `python-dotenv` loads the
  `.env` next to `manage.py`; `.env.example` documents every variable.
* No `EMAIL_BACKEND` → a `POST` to `/accounts/password_reset/` fails with
  `ConnectionRefusedError` (default SMTP on `localhost:25`).
* The password-reset pages exist only as `django.contrib.admin` templates: the three
  `registration/password_reset_*.html` files named in `minisuper/urls.py` are absent from the project,
  so Django's `APP_DIRS` loader serves the admin's versions, complete with *"Django site admin"*
  branding. `registration/password_reset_form.html` is the only project-owned file in that flow.
* Dependencies are listed in a file misnamed `r.txt`; there is no pinned `requirements.txt`.
* Test coverage is uneven: `core/tests.py` (currency, notifications, **roles**) and `inventory/tests.py`
  (purchase-order shelf life) carry the real suite, while `sales/tests.py` and `operations/tests.py`
  are still 3-line stubs — their pages are only covered indirectly, by the role matrix in
  `core.tests.RoleAccessTests`.

---

## 9. Suggested roadmap

1. **Stabilise (P0)** — *mostly done 2026-09-30*: crashes 1-4 and the five missing templates are fixed
   (`0 failure(s)` on the smoke test). Left: `add_shift`'s `notes` kwarg, `staff_productivity_report`,
   and the two model-name template fallbacks. Then put `@login_required` + `@require_POST` on every
   state-changing function view.
2. **Centralise money and date logic** — one `TAX_RATE` setting, one currency helper (TZS), one
   `get_date_range(preset, start, end)` helper shared by reports, exports and the dashboard.
3. **Unify reporting** — make `minisuper/reports.py` reuse the same querysets as the report views
   instead of duplicating them.
4. **Admin and stock depth** — register the sales/operations models in the admin, add a stock-movement
   report and a stocktake / cycle-count flow.
5. **Sales lifecycle** — void/refund, discounts, receipt printing and a collision-free `Sale.code`
   sequence.
6. **Access control** — *done 2026-10-02*: the four roles (`Owner` / `Sell` / `Stock` /
   `SellerStock`) are Django groups declared in `core/permissions.py`, enforced with
   `PermissionRequiredMixin` / `@permission_required` on every view, mirrored in the sidebar
   and on the dashboard, and handed out from the owner-only **Users & Roles** page. See §7.
   Left for later: per-object rules (a seller seeing only *their own* sales), audit logging
   of role changes, and a password-reset flow that does not rely on the admin templates.
7. **Config and deployment** — *partly done*: `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS` and the
   PostgreSQL connection are environment-driven through `.env`. Remaining: `STATIC_ROOT`,
   `Africa/Dar_es_Salaam` timezone, locally vendored assets, a real `requirements.txt` (the file is
   still named `r.txt`), and smoke tests asserting every named URL returns 200/302.

