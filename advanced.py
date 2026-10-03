"""Advanced inventory extension using Python standard library only."""
import csv
import io
from datetime import datetime, timezone
import data_handler as dh
from services import ServiceError, _need
import validators as V

def _wh(db, wid):
    wid=str(wid or "MAIN").upper()
    row=db["warehouses"].get(wid)
    if not row or not row.get("active", True):
        raise ServiceError("Warehouse not found",404)
    return row

def bootstrap(db):
    if not db["warehouses"]:
        db["warehouses"]["MAIN"]={"id":"MAIN","name":"Main Warehouse","location":"Default","active":True,"created_at":dh.now_iso()}
        return True
    return False

def list_warehouses(db,user,q):
    rows=[x for x in db["warehouses"].values() if x.get("active",True)]
    rows.sort(key=lambda x:x["name"].lower())
    return {"items":rows,"total":len(rows)}

def create_warehouse(db,user,payload):
    errors=[]; wid=str(payload.get("id") or "").strip().upper()
    name=V.to_str(payload.get("name"),"name",errors,2,80)
    location=V.to_str(payload.get("location"),"location",errors,1,120)
    if not wid or len(wid)>20 or not wid.replace("-","").isalnum(): errors.append("id is invalid")
    _need(errors)
    if wid in db["warehouses"]: raise ServiceError("Warehouse already exists",409)
    row={"id":wid,"name":name,"location":location,"active":True,"created_at":dh.now_iso()}
    db["warehouses"][wid]=row; dh.append_audit(db,user["username"],"CREATE","warehouse",wid,None,row)
    if not dh.persist(db,"warehouses","audit_log","meta"): raise ServiceError("Could not save data",503)
    return row

def stock_by_warehouse(db,user,sku):
    return {"sku":sku,"items":[{"warehouse":w["id"],"quantity":int(db["warehouse_stock"].get(w["id"],{}).get(sku,0))} for w in db["warehouses"].values() if w.get("active",True)]}

def transfer(db,user,payload):
    errors=[]; sku=V.to_sku(payload.get("sku"),errors)
    src=str(payload.get("from_warehouse") or "MAIN").upper(); dst=str(payload.get("to_warehouse") or "MAIN").upper()
    qty=V.to_int(payload.get("quantity"),"quantity",errors,1,1000000)
    reason=V.to_str(payload.get("reason"),"reason",errors,3,200); _need(errors)
    _wh(db,src); _wh(db,dst)
    if src==dst: raise ServiceError("Warehouses must be different",409)
    if sku not in db["products"]: raise ServiceError("Product not found",404)
    srcq=int(db["warehouse_stock"].get(src,{}).get(sku,0))
    if srcq<qty: raise ServiceError("Insufficient stock in source warehouse",409)
    db["warehouse_stock"].setdefault(src,{})[sku]=srcq-qty
    db["warehouse_stock"].setdefault(dst,{})[sku]=int(db["warehouse_stock"].get(dst,{}).get(sku,0))+qty
    tid=dh.next_id(db,"TRF"); row={"id":tid,"sku":sku,"from_warehouse":src,"to_warehouse":dst,"quantity":qty,"reason":reason,"user":user["username"],"timestamp":dh.now_iso()}
    db["transfers"][tid]=row; dh.append_audit(db,user["username"],"TRANSFER","warehouse",tid,None,row)
    if not dh.persist(db,"warehouse_stock","transfers","audit_log","meta"): raise ServiceError("Could not save data",503)
    return row

def stock_count(db,user,payload):
    errors=[]; wid=str(payload.get("warehouse") or "MAIN").upper(); _wh(db,wid)
    items=payload.get("items")
    if not isinstance(items,list) or not items: errors.append("items must be a non-empty list")
    _need(errors); result=[]
    for item in items:
        sku=str(item.get("sku") or "").upper()
        try: counted=int(item.get("counted"))
        except (TypeError,ValueError): raise ServiceError("counted must be integer",422)
        system=int(db["warehouse_stock"].get(wid,{}).get(sku,0)); diff=counted-system
        db["warehouse_stock"].setdefault(wid,{})[sku]=counted
        if sku in db["products"]: db["products"][sku]["quantity_on_hand"]+=diff
        result.append({"sku":sku,"system":system,"counted":counted,"difference":diff})
    cid=dh.next_id(db,"CNT"); row={"id":cid,"warehouse":wid,"items":result,"user":user["username"],"timestamp":dh.now_iso()}
    db["stock_counts"][cid]=row; dh.append_audit(db,user["username"],"STOCK_COUNT","stock_count",cid,None,row)
    if not dh.persist(db,"stock_counts","warehouse_stock","products","audit_log","meta"): raise ServiceError("Could not save data",503)
    return row

def forecast(db,user,sku,days=30):
    try: days=max(1,min(int(days),365))
    except (TypeError,ValueError): days=30
    moves=[m for m in db["stock_movements"] if m["sku"]==sku and m["qty_change"]<0]
    if not moves: return {"sku":sku,"daily_average":0,"forecast":0,"days":days}
    dates=[datetime.fromisoformat(m["timestamp"][:10]).date() for m in moves]
    span=max(1,(datetime.now(timezone.utc).date()-min(dates)).days+1)
    daily=round(sum(-m["qty_change"] for m in moves)/span,2)
    return {"sku":sku,"daily_average":daily,"forecast":round(daily*days,2),"days":days}

def csv_products(db):
    out=io.StringIO(); fields=["sku","name","category","unit","cost_price","selling_price","reorder_point","quantity_on_hand"]
    w=csv.DictWriter(out,fieldnames=fields); w.writeheader()
    for p in db["products"].values():
        if p.get("active"): w.writerow({k:p.get(k,"") for k in fields})
    return out.getvalue()

def import_products_csv(db,user,text):
    rows=list(csv.DictReader(io.StringIO(text)))
    if len(rows)>5000: raise ServiceError("Maximum 5000 rows",422)
    created=updated=0
    for row in rows:
        clean,errors=V.validate_product(row,creating=True); _need(errors)
        sku=clean["sku"]
        if sku in db["products"]:
            p=db["products"][sku]; before=dict(p); p.update(clean); dh.append_audit(db,user["username"],"IMPORT_UPDATE","product",sku,before,p); updated+=1
        else:
            from services import _new_product
            db["products"][sku]=_new_product(clean,user); dh.append_audit(db,user["username"],"IMPORT_CREATE","product",sku,None,db["products"][sku]); created+=1
    if not dh.persist(db,"products","audit_log","meta"): raise ServiceError("Could not save data",503)
    return {"created":created,"updated":updated,"rows":len(rows)}

def create_lot(db,user,payload):
    errors=[]; sku=V.to_sku(payload.get("sku"),errors); wid=str(payload.get("warehouse") or "MAIN").upper()
    lot=V.to_str(payload.get("lot"),"lot",errors,1,50); qty=V.to_int(payload.get("quantity"),"quantity",errors,1,1000000)
    cost=V.to_float(payload.get("unit_cost"),"unit_cost",errors); expiry=V.to_str(payload.get("expiry"),"expiry",errors,10,10); _need(errors)
    _wh(db,wid)
    try: datetime.strptime(expiry,"%Y-%m-%d")
    except ValueError: raise ServiceError("expiry must be YYYY-MM-DD",422)
    if sku not in db["products"]: raise ServiceError("Product not found",404)
    lid=dh.next_id(db,"LOT"); row={"id":lid,"sku":sku,"warehouse":wid,"lot":lot,"quantity":qty,"unit_cost":cost,"expiry":expiry,"active":True,"created_at":dh.now_iso()}
    db["lots"][lid]=row; db["warehouse_stock"].setdefault(wid,{})[sku]=int(db["warehouse_stock"].get(wid,{}).get(sku,0))+qty
    db["products"][sku]["quantity_on_hand"]+=qty
    dh.append_audit(db,user["username"],"CREATE","lot",lid,None,row)
    if not dh.persist(db,"lots","warehouse_stock","products","audit_log","meta"): raise ServiceError("Could not save data",503)
    return row

def allocate_lots(db, sku, warehouse, quantity, method="FEFO"):
    rows=[x for x in db["lots"].values() if x.get("active",True) and x["sku"]==sku and x["warehouse"]==warehouse and x["quantity"]>0]
    method=str(method).upper()
    rows.sort(key=(lambda x:(x["expiry"],x["created_at"])) if method=="FEFO" else (lambda x:(x["created_at"],x["expiry"])))
    remaining=int(quantity); used=[]
    for row in rows:
        take=min(remaining,row["quantity"])
        if take: row["quantity"]-=take; used.append({"lot_id":row["id"],"quantity":take,"unit_cost":row["unit_cost"]}); remaining-=take
        if remaining==0: break
    if remaining: raise ServiceError("Not enough lot stock",409)
    return used

def list_lots(db,user,q):
    rows=[x for x in db["lots"].values() if x.get("active",True)]
    if q.get("sku"): rows=[x for x in rows if x["sku"]==q["sku"].upper()]
    if q.get("warehouse"): rows=[x for x in rows if x["warehouse"]==q["warehouse"].upper()]
    method=q.get("method","FEFO").upper()
    rows.sort(key=(lambda x:(x["expiry"],x["created_at"])) if method=="FEFO" else (lambda x:(x["created_at"],x["expiry"])))
    return {"items":rows,"total":len(rows),"method":method}

def excel_products(db):
    """Export products as Excel-compatible SpreadsheetML without third-party packages."""
    from xml.sax.saxutils import escape, quoteattr
    fields=["sku","name","category","unit","cost_price","selling_price","reorder_point","quantity_on_hand"]
    rows=['<?xml version="1.0"?>','<?mso-application progid="Excel.Sheet"?>',
          '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">',
          '<Worksheet ss:Name="Products"><Table>']
    rows.append('<Row>'+''.join('<Cell><Data ss:Type="String">'+escape(x)+'</Data></Cell>' for x in fields)+'</Row>')
    for p in db["products"].values():
        if not p.get("active"): continue
        cells=[]
        for k in fields:
            v=p.get(k,"")
            typ="Number" if isinstance(v,(int,float)) and not isinstance(v,bool) else "String"
            cells.append('<Cell><Data ss:Type="%s">%s</Data></Cell>'%(typ,escape(str(v))))
        rows.append('<Row>'+''.join(cells)+'</Row>')
    rows += ['</Table></Worksheet></Workbook>']
    return ''.join(rows)


def import_products_excel(db,user,text):
    """Accept simple Excel SpreadsheetML or HTML-table exports using stdlib only."""
    import re
    if "<Workbook" in text or "<ss:Workbook" in text:
        cells=re.findall(r'<Data[^>]*>(.*?)</Data>',text,re.S|re.I)
        clean=[re.sub(r'<[^>]+>','',x).replace('&amp;','&').replace('&lt;','<').replace('&gt;','>') for x in cells]
        width=8
        rows=[clean[i:i+width] for i in range(0,len(clean),width)]
        if rows and rows[0] and rows[0][0].lower()=="sku": rows=rows[1:]
        csv_text=io.StringIO(); w=csv.writer(csv_text); w.writerows(rows)
        header="sku,name,category,unit,cost_price,selling_price,reorder_point,quantity_on_hand\n"
        return import_products_csv(db,user,header+csv_text.getvalue())
    raise ServiceError("Unsupported Excel format. Export using this system's Excel button or upload CSV.",422)
