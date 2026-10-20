# SuperDeal image candidate patch — isolated image module

Files changed: `superdeal_phase2_full/image_enrichment.py` only, plus `test_image_candidates.py`.

Source baseline: your uploaded restored backend, with previous promotional-image guard retained.

Does not change `backend.py`, `prompt.py`, EarnKaro URLs, products, mapping, or publication stages.

Playwright gathers product JSON-LD, og/twitter metadata, rendered `<img>` sources and lazy attributes, srcsets, CSS background images; ranks by product-name tokens. This is not guaranteed to fetch every image: merchant protections and offscreen images can prevent extraction. In ambiguous multi-product messages, placeholder remains intentional.

Stop worker; back up image_enrichment.py; expand ZIP into project root; run:

`.\.venv\Scripts\python.exe -m pytest -q .\superdeal_phase2_full\test_image_candidates.py .\superdeal_phase2_full\test_image_enrichment_sync.py`

Then restart worker and check new deals. Existing deals are not reprocessed. If anything regresses, restore image_enrichment.py from your backup.
