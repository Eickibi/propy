"""main.py - interactive CLI (local use). Same business logic as the Vercel API."""
import getpass

import auth
import data_handler as dh
import services as svc


class InputCancelled(Exception):
    """Ctrl+C / Ctrl+D during a prompt."""


def ask(label: str, default: str = "", secret: bool = False) -> str:
    try:
        text = getpass.getpass(f"{label}: ") if secret else input(f"{label}{f' [{default}]' if default else ''}: ")
    except (EOFError, KeyboardInterrupt):
        print()
        raise InputCancelled()
    return (text if secret else text.strip()) or default


def call(func, *args):
    """Run a service call, printing friendly errors. Returns the result or None."""
    try:
        return func(*args)
    except svc.ServiceError as exc:
        print(f"  ! {exc.message}")
        for detail in exc.details:
            print(f"    - {detail}")
    except dh.StorageError as exc:
        print(f"  ! Storage problem: {exc}")
    return None


def show_products(db, user):
    q = {"search": ask("Search SKU/name"), "category": ask("Category"),
         "sort": ask("Sort by", "sku"), "order": ask("Order asc/desc", "asc"), "page": "1"}
    browsing = True
    while browsing:
        res = call(svc.list_products, db, user, q)
        if res is None:
            break
        print(f"\n{'SKU':<14}{'Name':<26}{'Qty':>6}{'Price':>10}")
        for row in res["items"]:
            flag = "  LOW" if row.get("low") else ""
            print(f"{row['sku']:<14}{row['name'][:24]:<26}{row.get('quantity_on_hand', '-'):>6}{row['selling_price']:>10.2f}{flag}")
        nav = ask(f"Page {res['page']}/{res['pages']} ({res['total']} items) [n]ext [p]rev [q]uit", "q").lower()
        if nav == "n" and res["page"] < res["pages"]:
            q["page"] = str(res["page"] + 1)
        elif nav == "p" and res["page"] > 1:
            q["page"] = str(res["page"] - 1)
        elif nav == "q":
            browsing = False


def add_product(db, user):
    payload = {"sku": ask("SKU"), "name": ask("Name"), "category": ask("Category"),
               "unit": ask("Unit (pcs/box/kg/litre/pack)", "pcs"), "cost_price": ask("Cost price"),
               "selling_price": ask("Selling price"), "reorder_point": ask("Reorder point", "0")}
    res = call(svc.create_product, db, user, payload)
    if res:
        print(f"  Saved {res['sku']}.")


def move_stock(db, user):
    payload = {"sku": ask("SKU"), "type": ask("Type (INBOUND/OUTBOUND/ADJUSTMENT)"),
               "quantity": ask("Quantity (adjustment may be negative)"), "reason": ask("Reason"),
               "reference": ask("Reference (optional)")}
    if payload["type"].upper() == "INBOUND":
        payload["unit_cost"] = ask("Unit cost (optional)")
    res = call(svc.stock_move, db, user, payload)
    if res:
        print(f"  {res['id']}: {res['type']} {res['qty_change']:+d} -> balance {res['balance_after']}")


def show_card(db, user):
    sku, page = ask("SKU"), ask("Page", "1")
    res = call(svc.stock_card, db, user, sku, {"page": page})
    if res:
        print(f"\nStock card: {res['product']['sku']} - {res['product']['name']} (page {res['page']}/{res['pages']})")
        for m in res["items"]:
            print(f" {m['timestamp'][:19]} {m['type']:<10}{m['qty_change']:>+7}{m['balance_after']:>8}  {m['user']}: {m['reason']}")


def show_low(db, user):
    res = call(svc.low_stock_report, db, user)
    if res:
        print(f"\nLow stock items: {res['total']}")
        for p in res["items"]:
            print(f" {p['sku']:<14}{p['name'][:24]:<26} on hand {p['quantity_on_hand']} / reorder {p['reorder_point']}")


def show_dashboard(db, user):
    d = call(svc.dashboard, db, user)
    if d:
        print(f"\n=== DASHBOARD ===\n Products {d['products']} | Categories {d['categories']} | Suppliers {d['suppliers']}")
        print(f" Units {d['stock_units']} | Stock value {d['stock_value']:,.2f} | Low stock {d['low_stock_count']}")
        print(f" PO: {d['po_by_status']}")


def show_valuation(db, user):
    r = call(svc.valuation_report, db, user, {"page_size": "100"})
    if r:
        for row in r["items"]:
            print(f" {row['sku']:<14}{row['quantity_on_hand']:>6} x {row['cost_price']:>9.2f} = {row['cost_value']:>12,.2f}")
        print(f" TOTAL cost {r['total_cost_value']:,.2f} | retail {r['total_retail_value']:,.2f} | margin {r['potential_margin']:,.2f}")


def show_suppliers(db, user):
    res = call(svc.list_suppliers, db, user, {"search": ask("Search")})
    if res:
        for s in res["items"]:
            print(f" {s['id']}  {s['name']:<28}{s.get('phone', '')}")
        if ask("Add a supplier? (y/n)", "n").lower() == "y":
            payload = {"name": ask("Name"), "contact": ask("Contact"), "phone": ask("Phone"), "email": ask("Email")}
            if call(svc.create_supplier, db, user, payload):
                print("  Supplier saved.")


def show_audit(db, user):
    res = call(svc.list_audit, db, user, {"user": ask("Filter by user"), "page_size": "15"})
    if res:
        for a in res["items"]:
            print(f" {a['timestamp'][:19]} {a['user']:<10}{a['action']:<14}{a['entity']} {a['entity_id']}")


MENU = [("1", "List / search products", show_products, "products.view"),
        ("2", "Add product", add_product, "products.write"),
        ("3", "Stock in / out / adjust", move_stock, "stock.move"),
        ("4", "Stock card", show_card, "stock.card"),
        ("5", "Low-stock alerts", show_low, "reports.view"),
        ("6", "Dashboard", show_dashboard, "reports.view"),
        ("7", "Valuation report", show_valuation, "reports.view"),
        ("8", "Suppliers", show_suppliers, "suppliers.view"),
        ("9", "Audit log", show_audit, "audit.view")]


def run_menu(db, user):
    allowed = {k: (label, fn) for k, label, fn, perm in MENU if auth.can(user["role"], perm)}
    running = True
    while running:
        print(f"\n== Inventory | {user['username']} ({user['role']}) ==")
        for key in sorted(allowed):
            print(f" {key}. {allowed[key][0]}")
        print(" 0. Log out")
        try:
            choice = ask("Select")
            if choice == "0":
                running = False
            elif choice in allowed:
                allowed[choice][1](db, user)
            else:
                print("  Unknown option.")
        except InputCancelled:
            print("  Cancelled.")
        except Exception as exc:                      # last-resort guard: no tracebacks
            print(f"  Unexpected error ({type(exc).__name__}); action aborted.")


def main():
    try:
        db, warnings = dh.load_all()
    except dh.StorageError as exc:
        print(f"Cannot open data storage: {exc}")
        return
    for w in warnings:
        print(f"[warning] {w}")
    if svc.bootstrap(db):
        print("First run: user 'admin' created (password from ADMIN_PASSWORD or 'Admin@123'). Change it!")
    attempts, user = 0, None
    while user is None and attempts < 3:
        try:
            result = call(svc.login, db, ask("Username"), ask("Password", secret=True))
        except InputCancelled:
            break
        user = result["user"] if result else None
        attempts += 1
    if user is None:
        print("Login failed or cancelled.")
        return
    full_user = db["users"][user["username"]]
    run_menu(db, full_user)
    print("Goodbye.")


if __name__ == "__main__":
    main()
