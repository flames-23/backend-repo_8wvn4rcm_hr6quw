"""
Database Schemas for Personal Finance Assistant

Each Pydantic model represents a collection in your MongoDB database.
The collection name is the lowercase of the class name.

- User -> "user"
- Transaction -> "transaction"
- Budget -> "budget"
- ChatMessage -> "chatmessage"
"""

from pydantic import BaseModel, Field
from typing import Optional


class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    is_active: bool = Field(True, description="Whether user is active")


class Transaction(BaseModel):
    """Personal finance transaction schema"""
    amount: float = Field(..., gt=0, description="Transaction amount (absolute value)")
    type: str = Field(..., pattern=r"^(expense|income)$", description="Transaction type")
    category: str = Field(..., description="Category such as groceries, rent, salary")
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Transaction date (YYYY-MM-DD)")
    notes: Optional[str] = Field(None, description="Optional description or note")


class Budget(BaseModel):
    """Monthly budget per category"""
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="Budget month, e.g., 2025-01")
    category: str = Field(..., description="Budget category")
    limit: float = Field(..., ge=0, description="Spending limit for the category in this month")


class ChatMessage(BaseModel):
    """Stored chat messages (optional persistence for conversations)"""
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(...)
    session_id: Optional[str] = Field(None, description="Conversation session identifier")
