# ============================================================
# backend/models/erp_order.py
# ERP mock table — stands in for "live data" the agent can query.
#
# In the real world this data lives in a customer's ERP system
# (WebPOS/ERP). For our learning project we mock it in PostgreSQL
# (the Data Tier we already built) so the agent can PRACTICE the
# tool-calling pattern against a real database.
#
# The tool (agent/tools.py) reads this table like a real ERP API.
# ============================================================

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ErpOrder(Base):
    __tablename__ = "erp_orders"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    order_number: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)

    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)      # pending/shipped/delivered/cancelled/failed
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    product: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ErpOrder {self.order_number} status={self.status}>"
