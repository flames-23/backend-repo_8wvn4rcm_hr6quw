import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime

from database import db, create_document, get_documents
from schemas import Transaction, Budget, ChatMessage

app = FastAPI(title="Personal Finance Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Personal Finance Assistant API is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# ---------- Finance Endpoints ----------

class TransactionCreate(Transaction):
    pass


@app.post("/api/transactions")
def add_transaction(txn: TransactionCreate):
    try:
        txn_dict = txn.model_dump()
        # Convert date string to datetime for storage
        try:
            txn_dict["date"] = datetime.strptime(txn_dict["date"], "%Y-%m-%d")
        except Exception:
            pass
        inserted_id = create_document("transaction", txn_dict)
        return {"id": inserted_id, "status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/transactions")
def list_transactions(limit: Optional[int] = 100):
    try:
        docs = get_documents("transaction", {}, limit)
        for d in docs:
            if isinstance(d.get("date"), datetime):
                d["date"] = d["date"].date().isoformat()
            if "_id" in d:
                d["id"] = str(d.pop("_id"))
        return {"items": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/summary")
def summary(month: Optional[str] = None):
    """Return simple income/expense totals and category breakdown.
    month format: YYYY-MM (filters by that month).
    """
    try:
        flt = {}
        if month:
            # filter date range for month
            year, m = map(int, month.split("-"))
            start = datetime(year, m, 1)
            if m == 12:
                end = datetime(year + 1, 1, 1)
            else:
                end = datetime(year, m + 1, 1)
            flt["date"] = {"$gte": start, "$lt": end}
        docs = get_documents("transaction", flt, None)
        income = sum(d.get("amount", 0) for d in docs if d.get("type") == "income")
        expense = sum(d.get("amount", 0) for d in docs if d.get("type") == "expense")
        by_cat = {}
        for d in docs:
            if d.get("type") == "expense":
                cat = d.get("category", "Other")
                by_cat[cat] = by_cat.get(cat, 0) + d.get("amount", 0)
        # Budgets for that month
        budget_docs = get_documents("budget", {"month": month} if month else {}, None)
        budgets = {}
        for b in budget_docs:
            budgets[b["category"]] = b["limit"]
        return {
            "income": income,
            "expense": expense,
            "net": income - expense,
            "categories": by_cat,
            "budgets": budgets,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BudgetCreate(Budget):
    pass


@app.post("/api/budgets")
def set_budget(b: BudgetCreate):
    try:
        inserted_id = create_document("budget", b)
        return {"id": inserted_id, "status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/budgets")
def list_budgets(month: Optional[str] = None):
    try:
        flt = {"month": month} if month else {}
        docs = get_documents("budget", flt, None)
        for d in docs:
            if "_id" in d:
                d["id"] = str(d.pop("_id"))
        return {"items": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Simple AI Chat (rule-based for demo) ----------
# Note: If an external LLM is needed, integrate here later. For now,
# we provide a helpful assistant that summarizes finance data using our DB.

class ChatRequest(BaseModel):
    message: str
    month: Optional[str] = None


@app.post("/api/chat")
def chat(req: ChatRequest):
    try:
        user_msg = req.message.lower()
        month = req.month
        # Use summary to ground responses
        s = summary(month)
        if "spend" in user_msg or "expense" in user_msg:
            top_cat = None
            if s["categories"]:
                top_cat = max(s["categories"], key=lambda k: s["categories"][k])
            reply = (
                f"For {month or 'all time'}, you spent ${s['expense']:.2f}. "
                + (f"Your top spending category is {top_cat} at ${s['categories'][top_cat]:.2f}. " if top_cat else "")
            )
        elif "income" in user_msg:
            reply = f"For {month or 'all time'}, your income totals ${s['income']:.2f}. Net is ${s['net']:.2f}."
        elif "budget" in user_msg:
            lines = ["Budgets:"]
            for cat, lim in s["budgets"].items():
                spent = s["categories"].get(cat, 0)
                lines.append(f"- {cat}: ${spent:.2f} / ${lim:.2f} ({'over' if spent>lim else 'under'})")
            reply = "\n".join(lines) if len(lines) > 1 else "No budgets set yet."
        else:
            reply = (
                "I can help with your personal finance. Ask things like 'show expenses this month', "
                "'what's my income', or 'how am I doing against my budget?'."
            )
        # Optionally store message
        try:
            create_document("chatmessage", ChatMessage(role="user", content=req.message))
            create_document("chatmessage", ChatMessage(role="assistant", content=reply))
        except Exception:
            pass
        return {"reply": reply, "summary": s}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
