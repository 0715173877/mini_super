# MiniSuper — Instructions & Working Guide

This is the hands-on companion to [`README.md`](README.md). It covers how to install and run the
project, how it is organised, the coding conventions to follow when extending it, and the exact fixes
for the problems that are currently in the code.

*Audience: anyone (human or AI assistant) about to change this codebase.*

**Contents** — [1 Prerequisites](#1-prerequisites) · [2 Setup](#2-first-time-setup) ·
[3 Running](#3-running-the-app) · [4 Cheat sheet](#4-command-cheat-sheet) · [5 Conventions](#5-coding-conventions) ·
[6 P0 fixes](#6-p0-fixes-apply-before-anything-else) · [7 Missing templates](#7-missing-templates) ·
[8 Hardening](#8-p1--p2-fixes-hardening) · [9 Verification](#9-verification-workflow) ·
[10 New-feature contract](#10-contract-for-any-new-feature) · [11 Troubleshooting](#11-troubleshooting) ·
[12 Definition of done](#12-definition-of-done)

---

## 1. Prerequisites

| Requirement | Notes |
| --- | --- |
| Python 3.13 | `python3 --version`. Django 5.2.7 is already installed in `../venv`. |
| Git | **It is a git repository** — `git rev-parse --show-toplevel` is the project folder itself, `HEAD` is `665857d` ("system") on `main` with a remote `origin`. Use `git diff` to review changes; `git checkout -- <file>` reverts a file, `git status --short` lists what is untracked. |
| A browser | The UI is CDN-based, so an internet connection is needed for Bootstrap/Font Awesome/Chart.js. |

Two virtual environments exist in the parent folder:

| Path | Status |
| --- | --- |
| `../venv` | **Use this one.** Python 3.13.7 with Django 5.2.7, `python-dotenv`, `Pillow`, `reportlab`, `openpyxl`, `xlsxwriter`. |
| `../.venv` | Stale — Django is *not* installed here. Ignore it. |

---

## 2. First-time setup

All commands run from the Django project root, i.e. the folder containing `manage.py`:

```bash
cd "/Users/carlmihanjo/Documents/My Projects/Mini Supermarket/minisuper"
```

```bash
# 1. Use the populated virtualenv (do not create a new one)
source "../venv/bin/activate"
python -V                 # expect: Python 3.13.7
python -c "import django; print(django.get_version())"   # expect: 5.2.7

# 2. Dependencies (already installed; only needed on a fresh machine)
pip install -r r.txt
```

`r.txt` is the real requirements file in this project (there is no `requirements.txt`). It already
lists `python-dotenv` (used to load `.env`) and `psycopg` (the PostgreSQL driver Django 5 uses).

```bash
# 3. Configuration — copy the template and fill in your database credentials
cp .env.example .env

# 4. Database (PostgreSQL)
createdb minisuper_db                   # once; use the DB_NAME you set in .env
python manage.py migrate
python manage.py createsuperuser        # optional; the admin only registers inventory models

# 5. Sanity checks before you write any code
python manage.py check                  # expect: "System check identified no issues"
python manage.py makemigrations --check --dry-run   # expect: "No changes detected"
```

The shipped `db.sqlite3` in the project root contains a small demo dataset — as measured on
2026-09-30: **3 products, 9 sales, 5 stock movements, 1 user**, and no purchase orders, categories
beyond the seeded ones, suppliers, shifts, staff or waste records. That file is used only when
`DB_NAME` is unset; a fresh PostgreSQL database starts empty after `migrate` (create a superuser to
log in). If you must reset the SQLite fallback, back it up first:

```bash
cp db.sqlite3 db.sqlite3.bak        # never delete the dev DB without a copy
```

---

## 3. Running the app

```bash
source "../venv/bin/activate"
python manage.py runserver
```

* Dashboard: <http://127.0.0.1:8000/> (redirects to `/accounts/login/` when signed out)
* POS: <http://127.0.0.1:8000/sales/pos/>
* Admin: <http://127.0.0.1:8000/admin/>
* Every page except login and the `/sales/api/...` helpers requires an authenticated user
  (`LoginRequiredMixin` / `@login_required`) — **except** the state-changing views listed in
  README §8, which are currently unprotected.

Log in with the superuser you created (a fresh PostgreSQL database has no users until you run
`createsuperuser`); the SQLite fallback `db.sqlite3` may already contain a demo account:

```bash
python manage.py shell -c "from django.contrib.auth import get_user_model; print(list(get_user_model().objects.values_list('username', flat=True)))"
```

---

## 4. Command cheat sheet

```bash
source "../venv/bin/activate"                 # always first
python manage.py check                        # system checks
python manage.py makemigrations               # create migrations after model edits
python manage.py migrate                      # apply migrations
python manage.py showmigrations               # migration state per app
python manage.py shell                        # interactive shell
python manage.py dbshell                      # psql / sqlite3 prompt, whichever engine is active
python manage.py collectstatic                # FAILS today: STATIC_ROOT is not configured
python manage.py test                         # runs the (currently empty) test suite
python manage.py runserver 0.0.0.0:8000       # expose on the LAN for a phone/tablet test
```

Useful one-liners:

```bash
# Which URLs exist?
python manage.py shell -c "from django.urls import get_resolver; [print(k) for k in sorted(get_resolver().reverse_dict.keys()) if isinstance(k, str)]"

# Row counts (useful before/after a change)
python manage.py shell -c "from inventory.models import *; from sales.models import *; from operations.models import *; print('products', Product.objects.count(), 'sales', Sale.objects.count(), 'movements', StockMovement.objects.count(), 'shifts', Shift.objects.count())"
```

### Environment variables

`settings.py` calls `load_dotenv(BASE_DIR / '.env')` (existing process variables win) and reads:

| Variable | Used for | Default in code |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Django `SECRET_KEY` | an insecure dev key |
| `DJANGO_DEBUG` | `DEBUG` (`1/true/yes/on` → `True`) | `True` |
| `DJANGO_ALLOWED_HOSTS` | `ALLOWED_HOSTS`, comma-separated | `*` |
| `DB_NAME` | PostgreSQL database; **if set, PostgreSQL is used** | — (SQLite fallback) |
| `DB_USER`, `DB_PASSWORD` | PostgreSQL credentials | — |
| `DB_HOST`, `DB_PORT` | PostgreSQL server | `localhost`, `5432` |

`.env` is git-ignored — copy `.env.example` and fill in real values. When `DB_NAME` is empty the
project falls back to the SQLite file `db.sqlite3`, so it still runs without a database server.
Never commit real credentials.

### Database notes

* Engine: **PostgreSQL** (driver `psycopg`), configured through `.env`; SQLite `db.sqlite3` next to
  `manage.py` is the fallback when `DB_NAME` is unset.
* `StockMovement`, `Sale`, `SaleItem`, `WasteRecord`, `PeakHour`, `DailySummary` and the audit FKs use
  `PROTECT` on `auth.User`, so deleting a user can be blocked by history. Use `is_active = False`
  instead of deleting staff accounts.
* Money/quantities are `Decimal`. When scripting, always use `Decimal('1.5')`, never `1.5`.

---

## 5. Project conventions

### 5.1 App layout

Each app (`inventory`, `sales`, `operations`) keeps exactly this shape:

```
<app>/
├── models.py     # one model per business object, with Meta.ordering and readable __str__
├── forms.py      # ModelForm per model; formsets for inline children (purchase order items)
├── views.py      # CBVs for CRUD (LoginRequiredMixin + ListView/DetailView/...), fbv for actions
├── urls.py       # names are hyphenated, e.g. 'purchase-order-receive'
├── admin.py      # inventory is fully customised; sales/operations are still empty stubs
└── templates/<app>/*.html
```

`minisuper/` holds the project glue: `settings.py`, root `urls.py`, cross-app dashboard/report views
(`views.py`) and the exporters (`reports.py`).

### 5.2 View conventions

* CRUD: `LoginRequiredMixin` + generic CBV, `template_name` set **explicitly** (do not rely on the
  model-name fallback — see the `daily_reports.html` trap in README §8).
* After a successful write: `messages.success(request, "...")`, then `redirect(...)` (POST-redirect-GET).
* Actions that change data must be `@login_required` + `@require_POST`, wrapped in
  `transaction.atomic()`, and must be triggered from a `<form method="post">{% csrf_token %}`.
* Anything that touches `Product.current_stock` must also create a `StockMovement` carrying
  `previous_stock`, `new_stock`, `reason` and `user`.
* Use `get_object_or_404` rather than manual `try/except Model.DoesNotExist` for URL-driven lookups.
* Prefer `select_related`/`prefetch_related` on list views (already done in the inventory list views).

### 5.3 Template conventions

Every page extends `base.html` and fills its blocks:

```django
{% extends 'base.html' %}

{% block title %}Page name - MiniSuper{% endblock %}
{% block page_title %}Page name{% endblock %}      {# shown in the top bar #}
{% block content_title %}Page name{% endblock %}
{% block content_subtitle %}One line of context{% endblock %}

{% block content %}
  ... page body ...
{% endblock %}

{% block extra_scripts %}
  ... optional page JS / Chart.js ...
{% endblock %}
```

Styling comes from the CSS variables defined in `base.html` (`--primary: #2c5aa0`, `--danger`,
`--warning`, ...) plus Bootstrap 5 utility classes. Icons are Font Awesome 6 (`<i class="fas fa-...">`).
Reuse the existing card/list/table markup — copy `templates/inventory/low_stock.html` and
`templates/inventory/purchaseorder_confirm_delete.html` as references for "confirm delete" and card
layouts.

### 5.4 The POS page

`templates/sales/point_of_sale.html` is the one JavaScript-heavy page: it keeps the cart in memory,
renders the totals, and POSTs `cart_data` (JSON) plus `customer` and `payment_method` with the CSRF
token to `point_of_sale`. If you change the cart shape, update **both** the template and
`sales/views.py::process_sale`, which validates the JSON item by item
(`Decimal(str(...))` for quantity, stock check, then atomic update).

---

## 6. P0 fixes — make the broken pages work

Apply these in order. `python manage.py check` will not catch any of them, so verify with the smoke
test in §9 after each fix.

### 6.0 Status — what is already applied

The following were applied to the working tree on **2026-09-30** and verified (see §9.1 for the
re-measured baseline):

| Item | Status | Change made |
| --- | --- | --- |
| 6.1 `timestamp` `FieldError` | **fixed** | `inventory/views.py` lines 160 and 505 now order by `created_at`. The same typo was also found in 7 template spots and fixed: `sale.timestamp` → `sale.created_at` in `templates/sales/sale_list.html` (×2), `templates/sales/sale_detail.html` (×3), `templates/dashboard.html` (×1); `record.timestamp` → `record.created_at` in `templates/operations/waste_tracking.html` (×1). Those were rendering **blank dates**, not crashing. |
| 6.2 `PurchaseOrder` `NameError` | **fixed** | `inventory/models.py` now imports `F, Sum` and `timezone`. Verified: `calculate_total_amount()` returns `100` for 4 × 25, and `is_overdue` / `is_upcoming` / `days_until_delivery` / `days_overdue` compute correctly for `status='ordered'`. |
| 6.3 `timedelta` `NameError` | **fixed** | `minisuper/reports.py` line 4 imports `timedelta`. All three `date_range=week` export routes now 200. |
| 6.4 Excel auto-width `MergedCell` | **fixed** | Both auto-width loops (sales ≈ line 222, inventory ≈ line 400) now use `get_column_letter(column[0].column)` from `openpyxl.utils` instead of `column[0].column_letter`, and the bare `except:` became `except Exception:`. |
| 6.5 `add_shift` writes `notes` | **open** | Needs a decision: drop the kwarg (loses the notes the user typed) or add a `Shift.notes` field + migration. Reproduced on a DB copy: `POST` returns 200 carrying the literal *"Error adding shift"* and creates **0** `Shift` rows. |
| §7.1-§7.5 templates | **fixed** | `inventory/product_detail.html`, `inventory/product_confirm_delete.html`, `inventory/stock_adjustment.html`, `inventory/stock_movements.html` and `operations/supplier_performance.html` now exist (see §7 for the shipped content and the two small deviations). |
| §7.6-§7.8 templates | **open** | `sales/daily_reports.html` and `operations/staff_scheduling.html` are still silently served by the model-name fallbacks; `operations/staff_productivity_report.html` is still missing. |
| §8.1-§8.3 hardening | **fixed** | The purchase-order function views are `@login_required` + `@require_POST`, the duplicate `receive_purchase_order` is deleted, the duplicate URL block is gone and `adjust_stock` is guarded. Details and the final code: §8.1-§8.3. |
| Straight purchase-order flow | **fixed / new** | Orders are created already placed (no draft step), the only action left is **Purchase**, plus *Create & Place Order* / *Create & Purchase Now* on the form. Rationale, code and the 40-check script: **§8.6** and §9.3. |
| Optional supplier (products + orders) | **fixed / new** | `Product.supplier` and `PurchaseOrder.supplier` are now `null=True, blank=True`, so a product or an order can be saved without a supplier (walk-in / cash purchase). Both forms mark it *(optional)* and five templates print *No supplier* / *walk-in / cash purchase* instead of an empty cell. Only schema change: **`inventory/migrations/0005_make_supplier_optional`**, applied 2026-09-30. Details and the 48-check script: **§8.8** and §9.3. |

Two extra fixes came out of the same review:

* `inventory/models.py::Product.stock_value` — new read-only property (`current_stock * cost_price`).
  `templates/inventory/product_form.html` already called `form.instance.stock_value`, which silently
  rendered nothing because no such attribute existed. No migration: it is a property, not a field.
* `templates/inventory/product_form.html` — the sidebar printed `form.instance.created_at` and
  `form.instance.updated_at`; `Product` has neither, so both read "Not available". Replaced with the
  current stock and stock value, which do exist.

For §6.x and §7 the database schema did not change, the seeded rows were not modified and the straight
flow (§8.6) needed no migration either. The **only** schema change in this work is
`inventory/migrations/0005_make_supplier_optional.py` (§8.8) — an `AlterField` that made
`Product.supplier` and `PurchaseOrder.supplier` nullable (`null=True, blank=True`). It was applied to
`db.sqlite3` on 2026-09-30 after copying it to `/tmp/db_backup_before_0005.sqlite3`; no row was
inserted, updated or deleted (4 products / 11 sales / 7 movements / 5 suppliers / 1 user, and every
pre-existing product still points at its supplier). `makemigrations --check` is clean.

The work is **uncommitted** on top of `665857d`, so `git diff` shows it and `git checkout -- <file>`
reverts any single file:

| File | Change |
| --- | --- |
| `inventory/views.py` | two `-timestamp` → `-created_at` orderings; the §8 P1 hardening and the straight purchase-order flow (§8.1-§8.6) |
| `inventory/urls.py` | duplicate purchase-order block removed; *place* action moved to `.../place/` (§8.3) |
| `inventory/models.py` | `F, Sum, timezone` imports; new `Product.stock_value` property; `Product.supplier` / `PurchaseOrder.supplier` made nullable (§8.8) |
| `inventory/migrations/0005_make_supplier_optional.py` *(new)* | the only schema change: `Product.supplier` and `PurchaseOrder.supplier` → `null=True, blank=True` (§8.8) |
| `minisuper/reports.py` | `timedelta` import; `get_column_letter`; two auto-width loops; bare `except` → `except Exception` |
| `templates/dashboard.html`, `templates/sales/sale_list.html`, `templates/sales/sale_detail.html` | `sale.timestamp` → `sale.created_at` |
| `templates/operations/waste_tracking.html` | `record.timestamp` → `record.created_at` |
| `templates/inventory/product_form.html` | removed the non-existent `created_at` / `updated_at` reads |
| `templates/inventory/product_detail.html` *(new)*, `product_confirm_delete.html` *(new)*, `stock_adjustment.html` *(new)*, `stock_movements.html` *(new)*, `templates/operations/supplier_performance.html` *(new)* | the §7 templates |
| `templates/inventory/purchase_order_form.html`, `purchaseorder_detail.html`, `purchaseorder_list.html` | straight-flow buttons/labels and the `placeOrder()` / `purchaseOrder()` modals (§8.6) |
| `templates/inventory/product_form.html`, `low_stock.html`, `product_detail.html`, `purchase_order_form.html`, `purchaseorder_detail.html`, `purchaseorder_list.html` | supplier marked *(optional)* and every supplier read guarded so a supplier-less row prints *No supplier* (§8.8) |
| `README.md`, `INSTRUCTIONS.md` | the documentation |



### 6.1 `FieldError: Cannot resolve keyword 'timestamp'`

`inventory/views.py` orders `StockMovement` by a field that does not exist (the model uses
`created_at`). Two places:

```python
# inventory/views.py, line ~160 (ProductDetailView.get_context_data)
context['stock_movements'] = StockMovement.objects.filter(
    product=self.object
).order_by('-created_at')[:10]          # was '-timestamp'

# inventory/views.py, line ~505 (StockMovementListView.get_queryset)
return StockMovement.objects.select_related('product', 'user').order_by('-created_at')   # was '-timestamp'
```

### 6.2 `NameError` inside `PurchaseOrder`

`inventory/models.py` starts with only:

```python
from django.db import models
from django.core.validators import MinValueValidator
```

but uses `Sum`, `F` and `timezone`. Add:

```python
from django.db import models
from django.db.models import Sum, F
from django.core.validators import MinValueValidator
from django.utils import timezone
```

This fixes `calculate_total_amount()`, `is_overdue`, `is_upcoming`, `days_until_delivery` and
`days_overdue`. `calculate_total_amount()` also saves `self.total_amount`, so call it only when the
items are already saved (the create/update views call it after saving the formset — keep that order).

### 6.3 `NameError: name 'timedelta' is not defined`

`minisuper/reports.py` line 4:

```python
from datetime import datetime, timedelta
```

`get_sales_data()` uses `timedelta` for the `week`/`month` presets, so **every** sales export other
than `?date_range=today` currently raises `NameError`.

### 6.4 Excel auto-width crash (`MergedCell`)

`minisuper/reports.py::export_excel` (sales report, around line 221) iterates `worksheet.columns`
and reads `column[0].column_letter`; the first cell of a merged range is a `MergedCell`, which has no
`column_letter`. Widths can be computed from the header row instead:

```python
        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = None
            for cell in column:
                if column_letter is None and not isinstance(cell, openpyxl.cell.cell.MergedCell):
                    column_letter = cell.column_letter
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except Exception:
                    pass
            if column_letter:
                worksheet.column_dimensions[column_letter].width = max_length + 2
```

(Simplest alternative: drop the auto-width loop entirely — the export then succeeds and columns are
default width.) The inventory `export_excel` has the same pattern; apply the fix there too.

### 6.5 `add_shift` writes a non-existent field — still open, decision needed

`operations/models.py::Shift` has `staff`, `shift_date`, `start_time`, `end_time`, `hours_worked` —
there is **no** `notes` field, but `operations/views.py` line ~295 does
`Shift.objects.create(..., notes=notes)` → `TypeError` which is swallowed by the broad
`except Exception` and reported as "Error adding shift".

Reproduced on a throwaway copy of the database on 2026-09-30 (session `add_shift` view, POST with the
same fields the scheduling form sends):

```
§6.5 add_shift POST -> 200, shifts 0 -> 0
§6.5 page contains 'Error adding shift': True
```

A `200` here is **not** success — the view re-renders the form with the error message, and no `Shift`
row is written. The `messages` list reads empty during the test because rendering the response template
consumes the queued message; look for the literal text `Error adding shift` instead. This is left open
because the two candidate fixes differ in behaviour the shop will notice, so pick one deliberately:

**Option A — no migration (loses the notes the user typed).** Collect `notes` for the flash message only
and stop passing it:

```python
            # operations/views.py — add_shift()
            Shift.objects.create(
                staff=staff,
                shift_date=shift_date,
                start_time=start_time,
                end_time=end_time,
                hours_worked=hours_worked,
            )
```

If you take this option, also remove the notes input from the scheduling form so the UI stops
collecting data that is thrown away.

**Option B — migration (keeps the notes).** Add the field and generate the migration:

```python
            # operations/models.py — Shift
            notes = models.TextField(blank=True, null=True)
```

then `../venv/bin/python manage.py makemigrations operations` + `migrate`. This one is the only option
that requires a schema change, so get it agreed first — it is also the reason §6.0 lists this item as
open rather than fixed. Until it is decided, the item stays listed under P0 in `README.md` §8.


If the UI really needs shift notes, add the field and migrate:

```python
# operations/models.py → Shift
notes = models.TextField(blank=True)
```
```bash
python manage.py makemigrations operations
python manage.py migrate
```

Also pass `Decimal` for `hours_worked`, e.g.
`hours_worked=Decimal(str(round(hours_worked, 2)))` — the field is `DecimalField(max_digits=4, decimal_places=2)`
and a float can raise a `decimal.InvalidOperation` on save.

---

## 7. Missing templates (second half of the P0 work)

These files are referenced by code but do not exist. Create them under `minisuper/templates/…`.
The four inventory ones (§7.1-§7.4) are complete — paste them and they work. §7.5-§7.8 fix the
remaining `TemplateDoesNotExist` crashes, §7.9 optionally re-brands the password-reset flow, and
§7.10 lists the views that are not routed at all.

**Shipped on 2026-09-30:** §7.1, §7.2, §7.3, §7.4 and §7.5 are now real files in the working tree.
The content below is what was written, with these small improvements over the first drafts, all of
which were re-verified against the rendered HTML:

* §7.1 `product_detail.html` — shows the real `stock_status` as a coloured badge (the property returns
  `in_stock` / `low_stock` / `out_of_stock`, never a display label), adds a **User** column to the
  movements table, lists the high-value / high-theft badges, and prints `product.stock_value` instead
  of a `{% widthratio %}` trick.
* §7.2 `product_confirm_delete.html` — adds the `page_title` block used by `base.html`.
* §7.3 `stock_adjustment.html` — renders the three fields explicitly with Bootstrap markup instead of
  `{{ form.as_p }}`; the radio group keeps `form-check-input` from the form definition.
* §7.4 `stock_movements.html` — adds the **User** column so the audit trail shows who moved the stock.
* §7.5 `supplier_performance.html` — the form posts to `evaluate-supplier` with the exact field names
  `evaluate_supplier` reads (`supplier`, `on_time_delivery_rate`, `order_accuracy`,
  `product_quality_score`, `notes`), and the page renders both `suppliers_with_performance` and the
  paginated `supplier_performances`.

The stock-adjustment page is still missing `@login_required` on `adjust_stock` — see §8.1.


### 7.1 `templates/inventory/product_detail.html`

Rendered by `ProductDetailView` with `product` (also `object`) and `stock_movements`.

```django
{% extends 'base.html' %}

{% block title %}{{ product.name }} - MiniSuper{% endblock %}
{% block page_title %}Product Details{% endblock %}

{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
    <h2 class="h4 mb-0">{{ product.name }}</h2>
    <div>
        <a href="{% url 'product-update' product.pk %}" class="btn btn-primary btn-sm">
            <i class="fas fa-edit"></i> Edit
        </a>
        <a href="{% url 'adjust-stock' product.id %}" class="btn btn-warning btn-sm">
            <i class="fas fa-boxes"></i> Adjust Stock
        </a>
        <a href="{% url 'product-list' %}" class="btn btn-secondary btn-sm">Back</a>
    </div>
</div>

<div class="row">
    <div class="col-lg-6 mb-4">
        <div class="card shadow-sm h-100">
            <div class="card-header"><strong>Details</strong></div>
            <div class="card-body">
                <p><strong>SKU:</strong> {{ product.sku }}</p>
                <p><strong>Barcode:</strong> {{ product.barcode|default:"-" }}</p>
                <p><strong>Category:</strong> {{ product.category.name }}</p>
                <p><strong>Supplier:</strong> {{ product.supplier.name }}</p>
                <p><strong>Type:</strong> {{ product.get_product_type_display }}</p>
                <p><strong>Refrigerated:</strong> {{ product.requires_refrigeration|yesno:"Yes,No" }}</p>
                <p><strong>Expiry:</strong> {{ product.expiry_date|default:"-" }}</p>
                <p><strong>Stock status:</strong> <span class="badge bg-info">{{ product.stock_status }}</span></p>
            </div>
        </div>
    </div>

    <div class="col-lg-6 mb-4">
        <div class="card shadow-sm h-100">
            <div class="card-header"><strong>Stock &amp; Pricing</strong></div>
            <div class="card-body">
                <p><strong>Current stock:</strong> {{ product.current_stock }}</p>
                <p><strong>Min / Max level:</strong> {{ product.min_stock_level }} / {{ product.max_stock_level }}</p>
                <p><strong>Cost price:</strong> TZS {{ product.cost_price }}</p>
                <p><strong>Selling price:</strong> TZS {{ product.selling_price }}</p>
                <p><strong>Profit margin:</strong> {{ product.profit_margin|floatformat:2 }}%</p>
            </div>
        </div>
    </div>
</div>

<div class="card shadow-sm">
    <div class="card-header"><strong>Recent stock movements</strong></div>
    <div class="table-responsive">
        <table class="table table-sm mb-0">
            <thead><tr><th>When</th><th>Type</th><th>Qty</th><th>Before</th><th>After</th><th>Reason</th></tr></thead>
            <tbody>
            {% for movement in stock_movements %}
                <tr>
                    <td>{{ movement.created_at|date:"Y-m-d H:i" }}</td>
                    <td>{{ movement.get_movement_type_display }}</td>
                    <td>{{ movement.quantity }}</td>
                    <td>{{ movement.previous_stock }}</td>
                    <td>{{ movement.new_stock }}</td>
                    <td>{{ movement.reason|default:"-" }}</td>
                </tr>
            {% empty %}
                <tr><td colspan="6" class="text-center text-muted py-3">No movements recorded.</td></tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
```

### 7.2 `templates/inventory/product_confirm_delete.html`

`ProductDeleteView` exposes `object` (and `product`). Copy
`templates/inventory/purchaseorder_confirm_delete.html`, changing the wording and the cancel link:

```django
{% extends 'base.html' %}

{% block title %}Delete Product - MiniSuper{% endblock %}

{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card shadow">
            <div class="card-header bg-danger text-white">
                <h5 class="card-title mb-0"><i class="fas fa-exclamation-triangle"></i> Confirm Deletion</h5>
            </div>
            <div class="card-body text-center">
                <i class="fas fa-trash-alt fa-4x text-danger mb-3"></i>
                <h4>Delete "{{ object.name }}"?</h4>
                <p class="text-muted">SKU {{ object.sku }} — existing stock movements, sale lines or
                    purchase orders referencing this product will block deletion.</p>
                <form method="post" class="mt-4">
                    {% csrf_token %}
                    <button type="submit" class="btn btn-danger me-2"><i class="fas fa-trash"></i> Yes, Delete</button>
                    <a href="{% url 'product-list' %}" class="btn btn-secondary"><i class="fas fa-times"></i> Cancel</a>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

### 7.3 `templates/inventory/stock_adjustment.html`

`adjust_stock` passes `product` and `form` (`StockAdjustmentForm` with `adjustment_type`,
`quantity`, `reason`).

```django
{% extends 'base.html' %}

{% block title %}Adjust Stock - {{ product.name }}{% endblock %}
{% block page_title %}Stock Adjustment{% endblock %}

{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card shadow-sm">
            <div class="card-header"><strong>{{ product.name }}</strong> (SKU {{ product.sku }})</div>
            <div class="card-body">
                <p class="text-muted">Current stock: <strong>{{ product.current_stock }}</strong></p>
                <form method="post">
                    {% csrf_token %}
                    {{ form.as_p }}
                    <button type="submit" class="btn btn-primary"><i class="fas fa-check"></i> Apply adjustment</button>
                    <a href="{% url 'product-detail' product.id %}" class="btn btn-secondary">Cancel</a>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

### 7.4 `templates/inventory/stock_movements.html`

`StockMovementListView` supplies `stock_movements` (paginated: `page_obj`, `is_paginated`).

```django
{% extends 'base.html' %}

{% block title %}Stock Movements - MiniSuper{% endblock %}
{% block page_title %}Stock Movements{% endblock %}

{% block content %}
<div class="card shadow-sm">
    <div class="card-header d-flex justify-content-between align-items-center">
        <strong>Audit trail</strong>
        <span class="text-muted small">Page {{ page_obj.number }} of {{ page_obj.paginator.num_pages }}</span>
    </div>
    <div class="table-responsive">
        <table class="table table-hover mb-0">
            <thead><tr><th>When</th><th>Product</th><th>Type</th><th>Qty</th><th>Before</th><th>After</th><th>User</th><th>Reason</th></tr></thead>
            <tbody>
            {% for movement in stock_movements %}
                <tr>
                    <td>{{ movement.created_at|date:"Y-m-d H:i" }}</td>
                    <td>{{ movement.product.name }}</td>
                    <td>{{ movement.get_movement_type_display }}</td>
                    <td>{{ movement.quantity }}</td>
                    <td>{{ movement.previous_stock }}</td>
                    <td>{{ movement.new_stock }}</td>
                    <td>{{ movement.user.username|default:"system" }}</td>
                    <td>{{ movement.reason|default:"-" }}</td>
                </tr>
            {% empty %}
                <tr><td colspan="8" class="text-center text-muted py-3">No stock movements recorded.</td></tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
</div>

{% if is_paginated %}
<nav class="mt-3">
    <ul class="pagination">
        {% if page_obj.has_previous %}
            <li class="page-item"><a class="page-link" href="?page={{ page_obj.previous_page_number }}">Previous</a></li>
        {% endif %}
        {% if page_obj.has_next %}
            <li class="page-item"><a class="page-link" href="?page={{ page_obj.next_page_number }}">Next</a></li>
        {% endif %}
    </ul>
</nav>
{% endif %}
{% endblock %}
```

### 7.5 `templates/operations/supplier_performance.html`

`SupplierPerformanceView` provides `supplier_performances` (paginated), `suppliers` and
`suppliers_with_performance` (dicts: `supplier`, `avg_on_time`, `avg_accuracy`, `avg_quality`,
`evaluation_count`, `overall_score`). Its model-name fallback `operations/supplierperformance_list.html`
is also missing, so this page is a hard 500 — the explicitly named file is required. The form must POST
to `{% url 'evaluate-supplier' %}` with exactly the names the view reads: `supplier`,
`on_time_delivery_rate`, `order_accuracy`, `product_quality_score`, `notes`.

```django
{% extends 'base.html' %}

{% block title %}Supplier Performance - MiniSuper{% endblock %}
{% block page_title %}Supplier Performance{% endblock %}

{% block content %}
<div class="row">
  <div class="col-lg-5 mb-4">
    <div class="card shadow-sm">
      <div class="card-header"><strong>Record an evaluation</strong></div>
      <div class="card-body">
        <form method="post" action="{% url 'evaluate-supplier' %}">
          {% csrf_token %}
          <div class="mb-2">
            <label class="form-label">Supplier</label>
            <select name="supplier" class="form-select" required>
              {% for s in suppliers %}<option value="{{ s.id }}">{{ s.name }}</option>{% endfor %}
            </select>
          </div>
          <div class="mb-2">
            <label class="form-label">On-time delivery rate (%)</label>
            <input type="number" step="0.01" min="0" max="100" name="on_time_delivery_rate" class="form-control" required>
          </div>
          <div class="mb-2">
            <label class="form-label">Order accuracy (%)</label>
            <input type="number" step="0.01" min="0" max="100" name="order_accuracy" class="form-control" required>
          </div>
          <div class="mb-2">
            <label class="form-label">Product quality (1-5)</label>
            <input type="number" step="0.1" min="1" max="5" name="product_quality_score" class="form-control" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Notes</label>
            <textarea name="notes" rows="3" class="form-control"></textarea>
          </div>
          <button class="btn btn-primary w-100"><i class="fas fa-save"></i> Save evaluation</button>
        </form>
      </div>
    </div>
  </div>

  <div class="col-lg-7">
    <div class="card shadow-sm mb-4">
      <div class="card-header"><strong>Overall scores</strong></div>
      <div class="table-responsive">
        <table class="table table-sm mb-0">
          <thead><tr><th>Supplier</th><th>On time</th><th>Accuracy</th><th>Quality</th><th>Overall</th><th>#</th></tr></thead>
          <tbody>
          {% for row in suppliers_with_performance %}
            <tr>
              <td>{{ row.supplier.name }}</td>
              <td>{{ row.avg_on_time|floatformat:1 }}%</td>
              <td>{{ row.avg_accuracy|floatformat:1 }}%</td>
              <td>{{ row.avg_quality|floatformat:1 }}</td>
              <td>{{ row.overall_score|floatformat:1 }}%</td>
              <td>{{ row.evaluation_count }}</td>
            </tr>
          {% empty %}
            <tr><td colspan="6" class="text-center text-muted py-3">No evaluations yet.</td></tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card shadow-sm">
      <div class="card-header"><strong>Recent evaluations</strong></div>
      <div class="table-responsive">
        <table class="table table-sm mb-0">
          <thead><tr><th>Date</th><th>Supplier</th><th>On time</th><th>Accuracy</th><th>Quality</th><th>Notes</th></tr></thead>
          <tbody>
          {% for evaluation in supplier_performances %}
            <tr>
              <td>{{ evaluation.evaluation_date }}</td>
              <td>{{ evaluation.supplier.name }}</td>
              <td>{{ evaluation.on_time_delivery_rate }}%</td>
              <td>{{ evaluation.order_accuracy }}%</td>
              <td>{{ evaluation.product_quality_score }}</td>
              <td>{{ evaluation.notes|default:"-" }}</td>
            </tr>
          {% empty %}
            <tr><td colspan="6" class="text-center text-muted py-3">No evaluations yet.</td></tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>
{% endblock %}
```

### 7.6 `templates/sales/daily_reports.html`

Rendered by `DailyReportView` (context: `daily_summaries`, `total_sales`, `avg_daily_sales`,
`total_customers`). Today the page only "works" because Django falls back to
`templates/sales/dailysummary_list.html`; create the explicit file (or point the view's `template_name`
at `sales/dailysummary_list.html` and drop the ambiguity).

`DailySummary` fields: `date`, `total_sales`, `total_customers`, `cash_sales`, `card_sales`,
`mobile_sales`. Note the existing `dailysummary_list.html` also prints `summary.avg_transaction`,
which is **not** a model field — it silently renders empty; use
`{{ day.total_sales|floatformat:2 }}` / `total_customers` instead, or compute it in the view.

```django
{% extends 'base.html' %}

{% block title %}Daily Reports - MiniSuper{% endblock %}
{% block page_title %}Daily Sales Summaries{% endblock %}

{% block content %}
<div class="row mb-4">
  <div class="col-md-4"><div class="card"><div class="card-body">
    <div class="text-muted small">Total (last 30 days)</div>
    <div class="h4 mb-0">TZS {{ total_sales|floatformat:2 }}</div>
  </div></div></div>
  <div class="col-md-4"><div class="card"><div class="card-body">
    <div class="text-muted small">Average per day</div>
    <div class="h4 mb-0">TZS {{ avg_daily_sales|floatformat:2 }}</div>
  </div></div></div>
  <div class="col-md-4"><div class="card"><div class="card-body">
    <div class="text-muted small">Customers</div>
    <div class="h4 mb-0">{{ total_customers }}</div>
  </div></div></div>
</div>

<div class="card shadow-sm">
  <div class="table-responsive">
    <table class="table table-hover mb-0">
      <thead><tr><th>Date</th><th>Sales</th><th>Customers</th><th>Cash</th><th>Card</th><th>Mobile</th></tr></thead>
      <tbody>
      {% for day in daily_summaries %}
        <tr>
          <td>{{ day.date }}</td>
          <td>TZS {{ day.total_sales|floatformat:2 }}</td>
          <td>{{ day.total_customers }}</td>
          <td>{{ day.cash_sales|floatformat:2 }}</td>
          <td>{{ day.card_sales|floatformat:2 }}</td>
          <td>{{ day.mobile_sales|floatformat:2 }}</td>
        </tr>
      {% empty %}
        <tr><td colspan="6" class="text-center text-muted py-3">No summaries yet.</td></tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

### 7.7 `templates/operations/staff_scheduling.html`

`StaffSchedulingView` provides `shifts`, `staff_members`, `week_start`, `week_days` (7 dates) and
`staff_hours` (a dict keyed by **staff id** → total hours). A plain week grid is enough:

```django
{% extends 'base.html' %}

{% block title %}Staff Scheduling - MiniSuper{% endblock %}
{% block page_title %}Staff Scheduling{% endblock %}

{% block content %}
<div class="card shadow-sm mb-4">
  <div class="card-header d-flex justify-content-between align-items-center">
    <strong>Week of {{ week_start }}</strong>
    <form method="get" class="d-flex gap-2">
      <input type="date" name="date" class="form-control form-control-sm" value="{{ week_start|date:'Y-m-d' }}">
      <button class="btn btn-sm btn-primary">Go</button>
    </form>
  </div>
  <div class="table-responsive">
    <table class="table table-sm table-bordered mb-0">
      <thead><tr><th>Staff</th>{% for day in week_days %}<th>{{ day|date:"D d/m" }}</th>{% endfor %}<th>Hours</th></tr></thead>
      <tbody>
      {% for member in staff_members %}
        <tr>
          <td>{{ member.user.get_full_name|default:member.user.username }}</td>
          {% for day in week_days %}
            <td>
              {% for shift in shifts %}
                {% if shift.staff.id == member.id and shift.shift_date == day %}
                  <span class="badge bg-info">{{ shift.start_time|time:"H:i" }}-{{ shift.end_time|time:"H:i" }}</span>
                {% endif %}
              {% endfor %}
            </td>
          {% endfor %}
          <td>{{ staff_hours|default_if_none:"" }}{% for key, value in staff_hours.items %}{% if key == member.id %}{{ value|floatformat:2 }}{% endif %}{% endfor %}</td>
        </tr>
      {% empty %}
        <tr><td colspan="{{ week_days|length|add:2 }}" class="text-center text-muted py-3">No staff records.</td></tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<div class="card shadow-sm">
  <div class="card-header"><strong>Add a shift</strong></div>
  <div class="card-body">
    <form method="post" action="{% url 'add-shift' %}" class="row g-2">
      {% csrf_token %}
      <div class="col-md-3">
        <select name="staff" class="form-select" required>
          <option value="">Staff…</option>
          {% for member in staff_members %}<option value="{{ member.id }}">{{ member.user.get_full_name|default:member.user.username }}</option>{% endfor %}
        </select>
      </div>
      <div class="col-md-2"><input type="date" name="shift_date" class="form-control" required></div>
      <div class="col-md-2"><input type="time" name="start_time" class="form-control" required></div>
      <div class="col-md-2"><input type="time" name="end_time" class="form-control" required></div>
      <div class="col-md-2"><input type="text" name="notes" class="form-control" placeholder="Notes (optional)"></div>
      <div class="col-md-1"><button class="btn btn-primary w-100"><i class="fas fa-plus"></i></button></div>
    </form>
  </div>
</div>
{% endblock %}
```

`delete_shift(request, shift_id)` in `operations/views.py` has no URL entry, so a template cannot
`{% url %}` it. If you want a delete button, first add to `operations/urls.py`:

```python
    path('delete-shift/<int:shift_id>/', views.delete_shift, name='delete-shift'),
```

...and wrap the button in a POST form (`@require_POST` on the view is also recommended).

### 7.8 `templates/operations/staff_productivity_report.html`

`staff_productivity_report` (not routed today) passes `staff_metrics` — a list of dicts with keys
`staff` (a `Staff` instance), `total_hours`, `shift_count`, `sales_processed`, `sales_amount`
(optional) and `sales_per_hour` — plus `start_date` and `end_date`.

```django
{% extends 'base.html' %}

{% block title %}Staff Productivity - MiniSuper{% endblock %}
{% block page_title %}Staff Productivity{% endblock %}

{% block content %}
<p class="text-muted">{{ start_date }} → {{ end_date }}</p>

<div class="card shadow-sm">
  <div class="table-responsive">
    <table class="table table-hover mb-0">
      <thead><tr><th>Staff</th><th>Shifts</th><th>Hours</th><th>Sales</th><th>Sales amount</th><th>Per hour</th></tr></thead>
      <tbody>
      {% for row in staff_metrics %}
        <tr>
          <td>{{ row.staff.user.get_full_name|default:row.staff.user.username }}</td>
          <td>{{ row.shift_count }}</td>
          <td>{{ row.total_hours|floatformat:2 }}</td>
          <td>{{ row.sales_processed|default:0 }}</td>
          <td>TZS {{ row.sales_amount|default:0|floatformat:2 }}</td>
          <td>TZS {{ row.sales_per_hour|floatformat:2 }}</td>
        </tr>
      {% empty %}
        <tr><td colspan="6" class="text-center text-muted py-3">No shifts in this period.</td></tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

To make the page reachable, add to `operations/urls.py`:

```python
    path('staff-productivity/', views.staff_productivity_report, name='staff-productivity-report'),
```

### 7.9 Password-reset templates (cosmetic, not a crash)

`minisuper/urls.py` names three templates that do not exist in this project
(`registration/password_reset_done.html`, `..._confirm.html`, `..._complete.html`), yet the flow
returns **200**: `TEMPLATES['APP_DIRS'] is True`, so Django silently loads
`django/contrib/admin/templates/registration/*` instead. The pages therefore work but are stamped
*"Django site admin"* and clash with the app's UI. `registration/password_reset_form.html` **does**
exist in the project (it extends `base.html`) — that is the only branded page in the flow.

Add the three files below to `templates/registration/` to finish the styling. They are standalone HTML
(like the existing `login.html`) rather than extending `base.html`, because `base.html` renders the
signed-in sidebar unconditionally.

```django
{# templates/registration/password_reset_done.html #}
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Reset link sent - MiniSuper</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head>
<body class="bg-light">
  <div class="container py-5" style="max-width: 480px;">
    <div class="card shadow-sm"><div class="card-body">
      <h4 class="mb-3">Check your email</h4>
      <p class="text-muted">If an account exists for that address, a password reset link has been sent.</p>
      <a class="btn btn-primary" href="{% url 'login' %}">Back to sign in</a>
    </div></div>
  </div>
</body></html>
```

```django
{# templates/registration/password_reset_confirm.html #}
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Set a new password - MiniSuper</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head>
<body class="bg-light">
  <div class="container py-5" style="max-width: 480px;">
    <div class="card shadow-sm"><div class="card-body">
      {% if validlink %}
        <h4 class="mb-3">Choose a new password</h4>
        <form method="post">
          {% csrf_token %}
          {{ form.as_p }}
          <button class="btn btn-primary w-100">Save password</button>
        </form>
      {% else %}
        <h4 class="mb-3">Link expired</h4>
        <p class="text-muted">This reset link is invalid or has already been used.</p>
        <a class="btn btn-primary" href="{% url 'password_reset' %}">Request a new link</a>
      {% endif %}
    </div></div>
  </div>
</body></html>
```

```django
{# templates/registration/password_reset_complete.html #}
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Password updated - MiniSuper</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head>
<body class="bg-light">
  <div class="container py-5" style="max-width: 480px;">
    <div class="card shadow-sm"><div class="card-body">
      <h4 class="mb-3">Password updated</h4>
      <p class="text-muted">You can now sign in with your new password.</p>
      <a class="btn btn-primary" href="{% url 'login' %}">Sign in</a>
    </div></div>
  </div>
</body></html>
```

The reset-confirm form is the one Django-rendered form in the flow; `{{ form.as_p }}` keeps it working
but unstyled. If you want Bootstrap inputs there, render the fields explicitly:

```django
{% for field in form %}
  <div class="mb-3">
    <label class="form-label" for="{{ field.id_for_label }}">{{ field.label }}</label>
    <input type="password" name="{{ field.html_name }}" id="{{ field.id_for_label }}"
           class="form-control" required>
    {% for error in field.errors %}<div class="text-danger small">{{ error }}</div>{% endfor %}
  </div>
{% endfor %}
```

Sending the reset e-mail depends on the mail configuration: with `EMAIL_BACKEND` left at its default
(SMTP to `localhost:25`) a `POST` to `/accounts/password_reset/` raises
`ConnectionRefusedError`. Add the console backend to `settings.py` for development:

```python
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
```

The reset link is then printed to the `runserver` console, which is enough to walk the whole flow:

1. `POST /accounts/password_reset/` with a real user's e-mail → redirected to
   `/accounts/password_reset/done/`, link copied from the console.
2. Open `/accounts/reset/<uidb64>/<token>/` → set the new password → `/accounts/reset/done/`.
3. Sign in again at `/accounts/login/`.

Note that `TIME_ZONE` and `USE_L10N` are still the Django defaults (`'UTC'`, `True`) — see §8.4.

### 7.10 Orphaned views

These callables exist but are not routed anywhere. Either wire them up or delete them — an unrouted
view is dead weight that confuses future readers:

| Callable | Suggested action |
| --- | --- |
| `operations.views.delete_waste_record` | add `path('waste/<int:waste_id>/delete/', …, name='delete-waste')` and a POST button on `waste_tracking.html` |
| `operations.views.delete_shift` | see §7.7 |
| `operations.views.operations_dashboard_data` | add `path('api/dashboard-data/', …, name='operations-dashboard-data')` (returns JSON) |
| `operations.views.staff_productivity_report` | see §7.8 |
| `minisuper.views.custom_login` | delete — it shadows the real login and references an unimported `messages` |

---

## 8. P1 / P2 fixes (hardening)

### 8.1 Protect the state-changing views — **applied**

`@login_required` + `@require_POST` were added to the purchase-order function views and `@login_required`
to `adjust_stock` (`from django.views.decorators.http import require_POST` was imported):

| View (`inventory/views.py`) | Now | Rejects |
| --- | --- | --- |
| `mark_as_ordered` | `@login_required` `@require_POST` | any order whose status is not `draft` ("Only draft orders can be placed.") |
| `receive_purchase_order` | `@login_required` `@require_POST` | `received` (warning, no stock change) and `cancelled` (error) |
| `cancel_purchase_order` | `@login_required` `@require_POST` | status not in `draft`/`ordered` |
| `adjust_stock` | `@login_required` **only** | quantity <= 0 (form handles it) — it must not be `@require_POST` because the same URL serves the GET form |
| `sales/views.py::process_sale` | `@login_required` (already) | non-JSON `cart_data`, unknown product ids, quantity > stock |
| `operations/views.py::record_waste` | **still missing `@login_required`** | quantity > available stock (currently capped silently) |

All three purchase-order actions `redirect()` to the order detail page, so template buttons had to
become real POST forms — done in §8.6 (`purchaseorder_detail.html`, `purchaseorder_list.html`):

```django
<form method="post" action="{% url 'purchase-order-receive' order.id %}" class="d-inline">
    {% csrf_token %}
    <button class="btn btn-sm btn-success"><i class="fas fa-check"></i> Purchase (add to stock)</button>
</form>
```

A `GET` on any of them now answers **405 Method Not Allowed** (verified in §9.3) instead of mutating
data, and a double-click posts twice but the second POST is refused by the status guard.

### 8.2 Remove the duplicated `receive_purchase_order` — **applied**

The duplicate is gone; one canonical implementation survives, split into two helpers so the create
form can reuse it (§8.6):

```python
CLOSED_ORDER_STATUSES = ('received', 'cancelled')

def add_purchase_order_to_stock(order, user):
    """Add every line of `order` to product stock, logging one movement per line.
    Must be called inside transaction.atomic()."""
    lines = list(order.items.select_related('product'))
    for item in lines:
        product = item.product
        previous_stock = product.current_stock
        product.current_stock = previous_stock + item.quantity
        product.save()
        StockMovement.objects.create(
            product=product, movement_type='in', quantity=item.quantity,
            previous_stock=previous_stock, new_stock=product.current_stock,
            reason=f'Purchase order #{order.id} purchased', user=user,
        )
    return len(lines)

def purchase_order_into_stock(order, user):
    """Purchase `order` in one atomic step: place it if still a draft, then stock it."""
    with transaction.atomic():
        if order.status == 'draft':
            order.status = 'ordered'
        lines = add_purchase_order_to_stock(order, user)
        order.status = 'received'
        order.save()
        return lines
```

`receive_purchase_order` then becomes a thin guard around it:

```python
@login_required
@require_POST
def receive_purchase_order(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk)
    if order.status == 'received':
        messages.warning(request, f'Purchase Order #{order.id} was already purchased — stock was not changed again.')
        return redirect('purchase-order-detail', pk=order.pk)
    if order.status == 'cancelled':
        messages.error(request, 'Cancelled orders cannot be purchased.')
        return redirect('purchase-order-detail', pk=order.pk)
    try:
        lines = purchase_order_into_stock(order, request.user)
    except Exception as e:
        messages.error(request, f'Error purchasing order: {e}')
    else:
        messages.success(request, f'Purchase Order #{order.id} purchased — stock updated for {lines} item(s).')
    return redirect('purchase-order-detail', pk=order.pk)
```

**Why this mattered:** the shadowing copy had no status guard, so two clicks on *Receive* added the
same quantities to stock twice (measured: `7.000 → 12.000` on the first purchase, then `12.000 →
19.000` on the second). With the guard the second purchase leaves stock at `12.000`. This is a
regression test in §9.3.

### 8.3 De-duplicate `inventory/urls.py` and `inventory/forms.py` — **applied (urls) / still open (forms)**

* `inventory/urls.py` — **fixed.** The duplicate purchase-order block is gone; the *place* action now
  lives at `/inventory/purchase-order/<pk>/place/` (URL name unchanged: `purchase-order-mark-ordered`)
  and *purchase* at `.../purchase/` (`purchase-order-receive`). The first block's
  `purchase-order/<pk>/receive/` entry used to precede `purchase-order/<pk>/`, which is why the
  GET-based copy of the view was the one being served.
* `inventory/forms.py` — **still open.** `PurchaseOrderItemFormSet` is defined twice (line 7 and
  line 349) and Python binds the **second** one, which wraps the custom `PurchaseOrderItemForm` but
  carries **no `widgets=`** — so the item rows on the create/edit page render as unstyled inputs while
  the (dead) first definition is the one with the Bootstrap classes. Both use
  `extra=1, can_delete=True`. Deleting the early stub and merging the widgets into the live definition
  is a safe, self-contained follow-up.

### 8.4 Settings (`minisuper/settings.py`)

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h]

TIME_ZONE = "Africa/Dar_es_Salaam"      # store data is priced in TZS
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]        # the empty static/ folder becomes useful
STATIC_ROOT = BASE_DIR / "staticfiles"          # enables `collectstatic`
# MEDIA_ROOT = BASE_DIR / "media"; MEDIA_URL = "/media/"   # add only when uploads are introduced
```

Drop `USE_L10N` (removed in Django 5). Keep the values in a local `.env` — `.env` is already wired up
through `python-dotenv`; remember to `pip install python-dotenv` and add it to `r.txt`.

### 8.5 Consistency pass (low risk, high readability)

* Pick one brand string (`MiniSuper` is the mildest change: `base.html` `<title>`, sidebar header,
  `dashboard.html`) and one currency. `TZS` is what the shop screens already show, so the reports and
  CSV/Excel/PDF exporters should stop hard-coding `$` — search for `f"${` in `minisuper/reports.py`
  and `minisuper/views.py`.
* Delete dead files: `templates/sales/point_of_sale copy.html`,
  `templates/sales/point_of_sale copy 2.html`, `templates/debug_templates.html`.
* Fix `AnalyticsView` revenue math (`Sum(F('unit_price') * F('quantity'))`) and document that the
  profit figure is an estimate.
* Extend `Sale.generate_transaction_id()` so it cannot collide within the same second (e.g. append
  `Sale.objects.count()` or a random suffix, or switch to a `code` field with `auto_now_add` + PK).

---

### 8.6 Straight purchase-order flow (applied 2026-09-30)

**The request:** *the shop does not use drafts — an order is written down and then, when the goods
arrive, purchased into stock; make that a straight flow and add a one-click "create and purchase".*

**What the flow is now**

| Step | UI | Result |
| --- | --- | --- |
| Create | `purchase-order-create`, button **Create & Place Order** | one order, status `ordered`, stock untouched |
| Create + stock in one click | same form, button **Create & Purchase Now** | one order, status `received`, stock increased, one `in` movement per line |
| Goods arrive later | **Purchase (add to stock)** on the detail page or the list-page modal | status `received`, stock increased, one `in` movement per line |
| Legacy `draft` row | **Place Order** (detail page) or **Purchase** directly | `draft → ordered`, or straight to `received` |
| Already received / cancelled | — | refused with a message; **stock never changes** |

**Create view** (`PurchaseOrderCreateView`):

```python
def get_initial(self):
    initial = super().get_initial()
    # Suppliers here usually deliver on the spot, so pre-fill today. The column
    # is not nullable, so the field must always end up with a real date.
    initial['expected_delivery'] = timezone.now().date()
    return initial

def form_valid(self, form):
    ...
    # Straight flow: there is no draft step — an order is created already placed.
    form.instance.order_date = timezone.now()
    form.instance.status = 'ordered'
    response = super().form_valid(form)
    formset.instance = self.object
    formset.save()
    self.object.calculate_total_amount()
    if 'purchase_now' in self.request.POST:
        self.purchase_now()          # "Create & Purchase Now"
    else:
        messages.success(self.request, f'Purchase Order #{self.object.id} created and placed. '
                                       'Use Purchase when the goods arrive to add them to stock.')
    return response
```

`PurchaseOrderUpdateView` gained the same `purchase_now` branch (`purchase_from_edit_page()`), so the
edit page keeps offering *Place Order* / *Purchase* for orders that are still open.

**Templates**

* `purchase_order_form.html` — subtitle explains the flow, the status badge and the two submit buttons
  (`name="place_order"` / `name="purchase_now"`, the second one `btn-success`). No *Save as draft*.
* `purchaseorder_detail.html` — *Place Order* (draft only), *Purchase (add to stock)* (draft/ordered),
  *Cancel* (draft/ordered); a `received` order shows *“… was added to stock”* and **no** purchase
  button, a `cancelled` order shows the cancelled alert.
* `purchaseorder_list.html` — the row actions are `placeOrder(id)` and `purchaseOrder(id)` (the old
  `markAsOrdered()` / `markAsReceived()` helpers are gone), both posting through a confirm modal to the
  `-mark-ordered` / `-receive` URLs; the stat cards and the status filter now read
  *Not placed / Placed / Purchased* (the stored values are untouched).

**No migration.** `'draft'` stays in `PurchaseOrder.STATUS_CHOICES` so pre-existing draft rows keep
working — `makemigrations --check` is still clean and `receive_purchase_order` places a draft on its
way through (`purchase_order_into_stock`). Nothing is lost by keeping the choice: it is only ever
produced by legacy rows now, and the label is *Draft (not placed)*. (The single migration in this work,
`0005_make_supplier_optional`, belongs to §8.8 — the optional supplier — not to the straight flow.)

**Regression coverage:** §9.3 (`/tmp/mu_po_straight.py`, 40 checks) covers the two create buttons, the
straight purchase, the double-purchase guard, the leftover draft, the cancelled order, `GET` → 405,
anonymous → login redirect, placing twice, purchasing from the edit page (and that a plain *Update
Order* never purchases), and the rendered wording of both pages.

### 8.7 Remaining hardening (not done)

Unchanged from §8.1: `operations/views.py::record_waste` still has no `@login_required`, `@require_POST`
is not used outside `inventory`, and `inventory/forms.py` still defines `PurchaseOrderItemFormSet`
twice (§8.3).

`manage.py check` and `makemigrations --check` both pass on the current code even though 8 routes raise
exceptions at runtime, so **never treat them as sufficient**. Use the smoke test below after every
change. Save it as `minisuper/smoke_test.py` (next to `manage.py`) and run it from that directory:

```bash
cd minisuper
source ../venv/bin/activate
python smoke_test.py
```

It exercises every GET route with a logged-in client (creating and deleting its own throwaway
`smoke_tester` user), skipping detail routes whose tables are empty:

```python
"""Smoke-test every named URL of the MiniSuper project with an authenticated client.

Run from the project root (the folder containing manage.py):

    python smoke_test.py

Any FAIL line means a broken route.
"""
import os
import sys

import django

sys.path.insert(0, os.getcwd())  # make sure manage.py's directory is importable
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "minisuper.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import reverse  # noqa: E402

from inventory.models import Product, PurchaseOrder  # noqa: E402
from sales.models import Sale  # noqa: E402

User = get_user_model()

product = Product.objects.first()
order = PurchaseOrder.objects.first()
sale = Sale.objects.first()

routes = [
    ("dashboard", reverse("dashboard")),
    ("product-list", reverse("product-list")),
    ("product-create", reverse("product-create")),
    ("category-list", reverse("category-list")),
    ("supplier-list", reverse("supplier-list")),
    ("low-stock", reverse("low-stock")),
    ("purchase-order-list", reverse("purchase-order-list")),
    ("purchase-order-create", reverse("purchase-order-create")),
    ("stock-movement-list", reverse("stock-movement-list")),
    ("point-of-sale", reverse("point-of-sale")),
    ("sale-list", reverse("sale-list")),
    ("daily-reports", reverse("daily-reports")),
    ("customer-analytics", reverse("customer-analytics")),
    ("sales-api-data", reverse("sales-api-data")),
    ("waste-tracking", reverse("waste-tracking")),
    ("staff-scheduling", reverse("staff-scheduling")),
    ("performance-metrics", reverse("performance-metrics")),
    ("supplier-performance", reverse("supplier-performance")),
    ("sales_report_new", reverse("sales_report_new")),
    ("inventory_report", reverse("inventory_report")),
    ("analytics", reverse("analytics")),
    ("export_sales_report:today:csv", reverse("export_sales_report", args=["csv"]) + "?date_range=today"),
    ("export_sales_report:week:csv", reverse("export_sales_report", args=["csv"]) + "?date_range=week"),
    ("export_sales_report:week:excel", reverse("export_sales_report", args=["excel"]) + "?date_range=week"),
    ("export_sales_report:week:pdf", reverse("export_sales_report", args=["pdf"]) + "?date_range=week"),
    ("export_inventory_report:csv", reverse("export_inventory_report", args=["csv"])),
    ("export_inventory_report:excel", reverse("export_inventory_report", args=["excel"])),
    ("export_inventory_report:pdf", reverse("export_inventory_report", args=["pdf"])),
]
if product:
    routes += [
        ("product-detail", reverse("product-detail", args=[product.pk])),
        ("product-update", reverse("product-update", args=[product.pk])),
        ("product-delete", reverse("product-delete", args=[product.pk])),
        ("adjust-stock", reverse("adjust-stock", args=[product.pk])),
    ]
if order:
    routes += [
        ("purchase-order-detail", reverse("purchase-order-detail", args=[order.pk])),
        ("purchase-order-update", reverse("purchase-order-update", args=[order.pk])),
        ("purchase-order-delete", reverse("purchase-order-delete", args=[order.pk])),
    ]
if sale:
    routes += [("sale-detail", reverse("sale-detail", args=[sale.pk]))]

client = Client()
user, _ = User.objects.get_or_create(username="smoke_tester")
user.set_password("smoke-pass-123")
user.save()
client.force_login(user)

failures = 0
for label, url in routes:
    try:
        status = client.get(url).status_code
    except Exception as exc:  # noqa: BLE001
        status = f"EXC {type(exc).__name__}: {exc}"
    ok = isinstance(status, int) and 200 <= status < 400
    if not ok:
        failures += 1
    print(f"{'PASS' if ok else 'FAIL'}  {status!s:<6} {label:<34} {url}")

print(f"\n{len(routes)} routes checked, {failures} failure(s)")

user.delete()  # housekeeping
```

### 8.8 Optional supplier on products and purchase orders (applied 2026-09-30)

**Requirement:** the supplier must be selectable but not mandatory — a small shop buys from walk-in
sellers and cash-and-carry outlets, and forcing a vendor row just to record stock is wrong. It now
applies to **both** places that used to demand one.

| Layer | Before | After |
| --- | --- | --- |
| `Product.supplier` | `ForeignKey(Supplier, on_delete=PROTECT)` — `NOT NULL` | `ForeignKey(Supplier, on_delete=PROTECT, null=True, blank=True)` |
| `PurchaseOrder.supplier` | same | same |
| `ProductForm` / `PurchaseOrderForm` | field required (Django derives `required` from `blank`) | `required=False` automatically — no `__init__` override was needed |
| Product form template | `Supplier <span class="text-danger">*</span>` | `Supplier <span class="text-muted small">(optional)</span>` + hint *Optional — leave blank if this product has no regular supplier* |
| PO form template | same red `*`, hint *Select the supplier for this purchase order* | *(optional)* + hint *Optional — leave blank for a walk-in or cash purchase* |
| Five templates that printed a supplier | `{{ product.supplier.name }}` / `{{ order.supplier.name }}` rendered an **empty cell** when the FK was `NULL` | wrapped in `{% if … %}` with a *No supplier* / *walk-in / cash purchase* fallback |

The five guarded render sites are `templates/inventory/product_detail.html` (Details),
`low_stock.html` (card), `purchaseorder_list.html` (supplier column),
`purchaseorder_detail.html` (header row **and** the *Supplier Info* card, which now explains the
walk-in purchase) — nothing else in the repository reads `.supplier` (`minisuper/reports.py`,
`sales/`, `operations/supplier_performance.html` are all built from `Supplier` rows, not from
products/orders).

**The migration is the only schema change in this work:**

```
inventory/migrations/0005_make_supplier_optional.py
    ~ Alter field supplier on product            -> ForeignKey(blank=True, null=True, PROTECT)
    ~ Alter field supplier on purchaseorder      -> ForeignKey(blank=True, null=True, PROTECT)
```

It is a pure `AlterField` (no data migration, no `default`), so it is safe on the existing data and
reversible. Applied on 2026-09-30 after backing the real database up to
`/tmp/db_backup_before_0005.sqlite3`; verified afterwards that the row counts and every existing
`supplier_id` were unchanged. `manage.py check` and `makemigrations --check --dry-run` both stay clean.

**Deliberate choices**

* `on_delete=PROTECT` was **kept** — making the column nullable must not make supplier deletion
  destructive. Deleting a supplier that any product or order still points at raises `ProtectedError`
  (asserted in the regression script).
* No `related_name` was added to either FK, so `Supplier.product_count()` (`self.product_set.count()`)
  keeps working unchanged.
* Filtering still works: the PO list `?supplier=<id>` filter only matches rows with that supplier, and
  supplier-less orders remain visible in the unfiltered list (asserted).
* The straight flow (§8.6) is unaffected *and* now composes with this: *Create & Purchase Now* with an
  empty supplier stocks the product and logs the movement, and no `NULL` leaks into any rendered page.

**Regression coverage:** §9.3 (`/tmp/mu_supplier_optional.py`, 48 checks) — nullable/`PROTECT` state,
migration applied, both forms valid without a supplier, create + *Purchase Now* and create + *Place*
with `supplier=""` (stock `0.000 → 4.000`, one movement), the *Purchase* button on a supplier-less
placed order (`→ 7.000`, and a second *Purchase* is a no-op), nine pages rendered with a supplier-less
row present and no `>None<` / empty `<strong>`, the supplier filter, the total (`4000.00`) and the
PROTECT behaviour.


### 9.1 Current status — re-measured 2026-09-30 after the §6.1-§6.4 and §7.1-§7.5 fixes

```
33 routes checked, 0 failure(s)
```

`python manage.py check` → *System check identified no issues*; `makemigrations --check --dry-run` →
*No changes detected*. On top of the route sweep, a content-level check was run (rendered HTML, plus
real `POST`s) on a **copy** of the database — 16/16 checks passed:

| Check | Result |
| --- | --- |
| `product-detail` renders name, SKU, stock value and the recent movements | pass |
| `stock-movement-list` shows a real `YYYY-MM-DD HH:MM` timestamp (not an empty cell) | pass |
| `supplier-performance` renders the evaluation form and the history table | pass |
| `POST /inventory/product/<pk>/adjust-stock/` adds 1.5 to stock and records a movement | pass (`0.000 → 1.500`) |
| `POST /operations/evaluate-supplier/` stores a `SupplierPerformance` row | pass |
| `sale-detail` renders its transaction id and a real timestamp | pass |

A third sweep rendered every page with `string_if_invalid = '@@BLANK@@'` to expose template variables
that resolve to nothing. Result: **0 blank values across 25 pages** (the two `sale.timestamp` /
`record.timestamp` families fixed in §6.1 were exactly this class of bug). The marker mechanism itself
was verified with a positive control — rendering `sale_list.html` with a deliberately incomplete
context produced 12 markers — so a zero result is meaningful, not a silent failure of the check.

Last addition (2026-09-30, see §8.6): the purchase-order straight flow was exercised end-to-end on a DB
copy — **40/40 checks passed** (`/tmp/mu_po_straight.py`, §9.3). It pins the behaviour that used to be
broken: purchasing twice leaves stock unchanged (`12.000 → 12.000`), `GET` on *place*/*purchase*
answers 405, an anonymous POST is redirected to the login page, a cancelled order is refused, a plain
*Update Order* never purchases, and the order total is still computed from its lines (`5000.00` for
10 × `500.00`).

Final addition (2026-09-30, see §8.8): the optional supplier was verified on a DB copy —
**48/48 checks passed** (`/tmp/mu_supplier_optional.py`, §9.3). It confirms migration `0005` is applied,
both FKs are nullable while `on_delete` stays `PROTECT`, both forms accept a blank supplier, a
*Create & Purchase Now* order with `supplier=""` stocks the product (`0.000 → 4.000`) and logs one
movement, the *Purchase* button purchases a supplier-less placed order (and refuses the second
attempt), nine pages render a supplier-less row as *No supplier* (no `>None<`, no empty `<strong>`),
the `?supplier=` filter is unaffected, and deleting a referenced supplier still raises `ProtectedError`.

Database state when measured — `4 products / 11 sales / 7 stock movements / 0 purchase orders /
1 user (carl)`. The row counts moved up from the earlier reading because of normal app usage on
2026-09-30 (products 4-6 and sales 9-11 were created through the UI). No test residue was left behind:
`StockMovement` rows whose reason is `post-test` = 0, `SupplierPerformance` rows = 0, `users` = 1.
The smoke test and the content check both create a throwaway user; the smoke test deletes it again,
and the content check runs against a copy, so `db.sqlite3` keeps its schema and its rows.

### 9.1a The original baseline (as first measured, before any fix)

`33 routes checked, 8 failure(s)` — these were the only things the smoke test flagged:

| Route | Error |
| --- | --- |
| `/inventory/stock-movements/` | `FieldError: Cannot resolve keyword 'timestamp'` (P0-1) |
| `/inventory/product/<pk>/` | same `timestamp` `FieldError` (P0-1) |
| `/inventory/product/<pk>/delete/` | `TemplateDoesNotExist: inventory/product_confirm_delete.html` (P0-5) |
| `/inventory/product/<pk>/adjust-stock/` | `TemplateDoesNotExist: inventory/stock_adjustment.html` (P0-4) |
| `/operations/supplier-performance/` | `TemplateDoesNotExist: operations/supplier_performance.html` + fallback (P0-6) |
| `/reports/sales/export/csv/?date_range=week` | `NameError: timedelta` (P0-3) |
| `/reports/sales/export/excel/?date_range=week` | `NameError: timedelta` (P0-3) |
| `/reports/sales/export/pdf/?date_range=week` | `NameError: timedelta` (P0-3) |

Two routes passed **for the wrong reason** and must be watched manually, because Django's
`MultipleObjectTemplateResponseMixin` silently substitutes a sibling template:

| Route | Renders | Intended |
| --- | --- | --- |
| `/sales/daily-reports/` | `sales/dailysummary_list.html` | `sales/daily_reports.html` (§7.6) |
| `/operations/staff-scheduling/` | `operations/shift_list.html` | `operations/staff_scheduling.html` (§7.7) |

Note that the sales *Excel* export only failed on the `date_range=week` branch — the `today` range
returned an empty set before the `MergedCell.column_letter` code path was reached, so the `week`/`month`
range is what caught it (and what verifies the fix).


### 9.2 Testing the POST-only routes

Once §8.1 adds `@require_POST`, the state-changing routes must be exercised with a real POST. Quick
manual check from `manage.py shell`:

```python
from django.test import Client
from django.contrib.auth import get_user_model
from inventory.models import Product

c = Client()
c.force_login(get_user_model().objects.get(username="<your-admin>"))

p = Product.objects.first()
print(c.get(f"/inventory/product/{p.pk}/adjust-stock/").status_code)                      # 200 = form
print(c.post(f"/inventory/product/{p.pk}/adjust-stock/",
             {"quantity": 1, "movement_type": "in", "reason": "smoke"}).status_code)     # 302 = redirect
print(c.get("/inventory/purchase-order/1/place/").status_code)                            # 405 (POST-only)
print(c.get("/inventory/purchase-order/1/purchase/").status_code)                         # 405 (POST-only)
```

Remember to check the matching `StockMovement` row was written (`reason="smoke"`) and delete it
afterwards so the demo data stays clean.

### 9.3 Regression scripts (run on a **copy** of the database)

The scripts below live in `/tmp` in this session; if you keep them, move them next to `manage.py`
and drop the `mu_` prefix. They all copy `db.sqlite3` to `/tmp/<name>.sqlite3` **after** importing
settings but **before** `django.setup()`, so `db.sqlite3` is never modified (verify with the row counts
in §9.1); run them from `minisuper/` with `../venv/bin/python <script>`.

| Script | What it does | Last result |
| --- | --- | --- |
| `/tmp/mu_smoke.py` | route sweep: 33 named routes, logged-in client, follows the sidebar links | `33 routes checked, 0 failure(s)` |
| `/tmp/mu_smoke_safe.py` | the same sweep, but on a DB copy — use this one, `mu_smoke.py` itself writes a throwaway user to the DB it opens | as above |
| `/tmp/mu_post_test.py` | 16 content/POST checks (product detail, movements, supplier evaluation, adjust-stock, sale detail, and that the real DB was untouched) | `16 checks run, 0 failed` |
| `/tmp/mu_audit.py` | renders 25 pages with `string_if_invalid = '@@BLANK@@'` to catch template variables that resolve to nothing | `25 pages scanned, 0 blank value(s)` |
| `/tmp/mu_po_straight.py` | the purchase-order straight flow (§8.6): 40 checks — both create buttons, straight purchase, the double-purchase guard (`12.000` stays `12.000`), leftover draft, cancelled order, `GET` → 405, anonymous → login, place-twice no-op, purchase from the edit page, plain *Update Order* leaves stock alone, order total `5000.00`, and the wording of both pages | `40/40 checks passed` |
| `/tmp/mu_supplier_optional.py` | the optional supplier (§8.8): 48 checks — migration `0005` applied, `null=True` while `on_delete` stays `PROTECT`, a blank supplier valid in both forms, create + *Purchase Now* with `supplier=""` (stock `0.000 → 4.000`, one movement), create + *Place* (stock unchanged), the *Purchase* button on a supplier-less order (idempotent), nine pages rendered with a supplier-less row and no `>None<` / empty `<strong>`, the `?supplier=` filter, the total `4000.00`, and `ProtectedError` on a referenced supplier | `48/48 checks passed` |

Example of the shape they use (copy the DB *before* `django.setup()`):

```python
import os, shutil, sys, django
sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "minisuper.settings")

from django.conf import settings                      # settings are loaded, not yet used
TEMP_DB = "/tmp/whatever.sqlite3"
shutil.copy(str(settings.DATABASES["default"]["NAME"]), TEMP_DB)
settings.DATABASES["default"]["NAME"] = TEMP_DB       # now point Django at the copy
django.setup()
...
os.remove(TEMP_DB)                                    # leave no residue
```

---

## 10. Contract for any new feature

Follow the same shape as the existing apps so the codebase stays uniform:

1. **Model** in the owning app (`inventory` = products/stock/suppliers/orders, `sales` = POS and
   summaries, `operations` = staff/waste/performance). Money and quantities are
   `DecimalField(max_digits=12, decimal_places=3)`; add `created_at = models.DateTimeField(auto_now_add=True)`
   (there is no `timestamp` field anywhere — do not reintroduce one).
2. **Migration**: `python manage.py makemigrations <app>` and commit it together with the model.
3. **Form** in `<app>/forms.py` with explicit `fields = [...]` and `widgets` carrying the Bootstrap
   classes (`form-control` / `form-select`) — never render raw `{{ form.as_p }}` inside `base.html`
   pages.
4. **View**:
   * list/detail pages: `ListView` / `DetailView` **with an explicit `template_name`** (this is exactly
     what silently fell through to the wrong template in P1);
   * write actions: function views decorated with `@login_required` and `@require_POST`, wrapping the
     writes in `transaction.atomic()`, calling `messages.success/error`, then `redirect(...)` — never
     `render` after a successful POST.
5. **Any change to `Product.current_stock` must create a `StockMovement`** in the same transaction with
   `previous_stock`, `new_stock`, `movement_type` (`in`/`out`/`adjustment`), `reason` and `user`.
6. **Template** under `templates/<app>/<name>.html`, starting with
   `{% extends 'base.html' %}` and filling `{% block title %}`, `{% block page_title %}` and
   `{% block content %}`. Use the existing card/table classes (`card shadow-sm`, `table table-hover`);
   Font Awesome icons are already loaded globally.
7. **URL** named in kebab-case in `<app>/urls.py`, then add it to the sidebar in `templates/base.html`
   **and** to `smoke_test.py`, then run the smoke test plus `python manage.py check`.

## 11. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `FieldError: Cannot resolve keyword 'timestamp'` | ordering/filter on a non-existent field | use `created_at` (§6.1) |
| `NameError: name 'Sum'/'F'/'timezone' is not defined` | missing `from django.db.models import Sum, F` / `from django.utils import timezone` | add the imports (§6.2) |
| `NameError: name 'timedelta' is not defined` | reports module | `from datetime import timedelta` (§6.3) |
| `AttributeError: 'MergedCell' object has no attribute 'column_letter'` | iterating merged cells in xlsxwriter | capture `column_letter` while adding the header (§6.4) |
| `TypeError: Shift() got unexpected keyword arguments: {'notes'}` | `Shift` has no `notes` field | drop the kwarg or add the field + migration (§6.5) |
| `TemplateDoesNotExist: X` | template genuinely missing | add the file from §7 |
| Page renders but with the wrong layout | the view's `template_name` is missing/typo'd and Django fell back to `<model>_list.html` | set `template_name` explicitly (§10.4) |
| `CSRF verification failed` on a button that used to work | a link-style mutation was converted to a POST | add `{% csrf_token %}` inside the new `<form>` |
| `no such table: ...` | migrations not applied | `python manage.py migrate` |
| Static styling missing after deploy | `DEBUG=False` without `collectstatic` | set `STATIC_ROOT` and run `python manage.py collectstatic` |
| New page 404s only in the sidebar | URL added but not named, or name typo'd | `{% url %}` names must match `urls.py` exactly |

## 12. Definition of done

Before handing a change back:

- [ ] `python manage.py check` → *System check identified no issues*.
- [ ] `python manage.py makemigrations --check --dry-run` → *No changes detected* (if you did add a
      model field, the migration is committed instead).
- [ ] `python manage.py migrate` applied locally.
- [ ] `python smoke_test.py` → `0 failure(s)`.
- [ ] Every new write path: `@login_required` + `@require_POST` + `StockMovement` when stock moves.
- [ ] No new hard-coded currency symbol; no new `timestamp` field references; no duplicated view/URL
      names.
- [ ] `r.txt` updated if a dependency was added.

**Data safety note:** the repository carries a small demo `db.sqlite3` (4 products, 11 sales,
7 stock movements, no purchase orders or shifts). Any manual testing that writes rows (POS checkouts,
purchasing orders, recording waste) must be undone or accounted for, otherwise the baseline figures in
§9.1 stop matching. Take a copy before experiments — the §9.3 scripts do exactly that and never open
the original:

```bash
cp db.sqlite3 /tmp/db.backup.sqlite3 && ../venv/bin/python smoke_test.py   # re-check after tests
```

