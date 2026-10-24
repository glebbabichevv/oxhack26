"""Polymarket access for the trader: the integrations/ code, paper or live by POLYMARKET_LIVE."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations"))
import mcp_polymarket as pm  # noqa: E402
import polymarket_trading as trading  # noqa: E402


class Broker:
    mode = trading.mode()
    ceiling = trading.MAX_BET_USD

    def market(self, market_id):
        return pm.get_market(market_id)

    def quote(self, m, side, usd):
        return trading.quote(m, side, usd)

    def buy(self, m, side, usd, worst_price, note):
        r = trading.place_bet(m, side, usd, limit_price=worst_price, confirm=True, note=note)
        order_id = status = None
        if r["status"] == "paper_filled":
            shares, cost = r["shares"], r["cost_usd"]
        else:  # live FAK order: makingAmount = USDC paid, takingAmount = shares received
            order = r.get("order") or {}
            order_id, status = order.get("orderID"), order.get("status")
            raw = str(order)[:300]
            if not order.get("success", False):
                raise RuntimeError(f"order rejected: {order.get('errorMsg') or 'no message'} (reply: {raw})")
            try:
                shares, cost = float(order.get("takingAmount") or 0), float(order.get("makingAmount") or 0)
            except (TypeError, ValueError):
                raise RuntimeError(f"unreadable order reply: {raw}")
            if shares <= 0 or cost <= 0:
                raise RuntimeError(f"order not filled (status {status}): {raw}")
        if shares <= 0:
            raise RuntimeError("order filled nothing")
        return {"shares": shares, "cost": round(cost, 4), "avg_price": round(cost / shares, 4),
                "order_id": order_id, "status": status}

    def mark(self, m, side):
        return trading.exit_mark(m, side), trading.resolution(m, side)
