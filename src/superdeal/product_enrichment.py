"""Asynchronous additive product enrichment for converted deals."""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from .browser_enrichment import fetch_product_metadata
LOGGER = logging.getLogger("superdeal.product_enrichment")

def enrich_pending_deals(connection, *, limit: int = 10, fetcher=fetch_product_metadata) -> int:
    """Enrich deals without changing EarnKaro canonical text or affiliate URL."""
    rows = connection.execute(
        """SELECT id, affiliate_url FROM deals
           WHERE affiliate_url IS NOT NULL AND affiliate_url != ''
             AND COALESCE(enrichment_status, 'pending') IN ('pending', 'error')
           ORDER BY id LIMIT ?""", (limit,)
    ).fetchall()
    processed = 0
    for row in rows:
        try:
            metadata = fetcher(row["affiliate_url"])
            now = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """UPDATE deals SET
                   page_title=COALESCE(?,page_title), canonical_url=COALESCE(?,canonical_url),
                   image_url=COALESCE(?,image_url), verified_price=COALESCE(?,verified_price),
                   last_verified_at=?, description=COALESCE(?,description),
                   brand=COALESCE(?,brand), mrp=COALESCE(?,mrp),
                   enriched_merchant=COALESCE(?,enriched_merchant),
                   page_discount_pct=COALESCE(?,page_discount_pct),
                   enrichment_status='enriched', enrichment_error=NULL WHERE id=?""",
                (metadata.title, metadata.canonical_url, metadata.image_url, metadata.price,
                 now, metadata.description, metadata.brand, metadata.mrp,
                 metadata.merchant, metadata.discount_pct, row["id"])
            )
            connection.commit()
        except Exception as exc:
            connection.execute(
                "UPDATE deals SET enrichment_status='error', enrichment_error=? WHERE id=?",
                (str(exc)[:1000], row["id"])
            )
            connection.commit()
            LOGGER.warning("Product enrichment failed: deal_id=%s error=%s", row["id"], exc)
        processed += 1
    return processed
