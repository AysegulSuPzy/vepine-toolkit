# Description → Gallery Sync Rule (2026-10-23, user decision)

**Kural (TR):** Bir ürünün açıklamasında (descriptionHtml) 2'den fazla görsel varsa ve bu görsellerden herhangi biri ürün galerisinde (product media) yoksa, eksik olanlar ürün galerisine de eklenir. Açıklamadaki görseller silinmez, yeri değişmez; sadece galeriye kopyalanır.

## Trigger

- Count `<img>` tags in `descriptionHtml` **after** re-hosting (all src on our own `cdn.shopify.com` path — rehost.py).
- Rule fires only when **description image count > 2** (i.e. 3 or more). With 0–2 images, do nothing.

## What counts as "already in the gallery"

Compare each description image against the product's existing media (`product.media`, type `MediaImage`):

1. Exact CDN URL match (ignore query string / `?v=` version param), **or**
2. Same file basename after stripping Shopify size suffixes (`_1024x`, `_600x600`, `_small`, `_medium`, `_large`, `_grande`, …).

Either match → present, skip. Otherwise → missing, add.

## How to add

- `productCreateMedia` with `originalSource` = the description image's CDN URL, `mediaContentType: IMAGE`, `alt` = the description `<img alt>` (empty → product title, per image-alt-text-rule.md).
- Batch all missing images of one product into a single `productCreateMedia` call; across a batch of 10 products use aliased mutations (m0:, m1:, …) with zero bash round-trips between them.
- Append in **description order**, after all existing gallery media. Never reorder existing media, never change the featured image.
- Dedupe missing URLs within the product before the mutation — never create a duplicate.
- Poll `mediaStatus` until READY (same pattern as fileCreate in rehost.py); a FAILED upload is logged (product ID + URL) and the batch continues.
- Do NOT download the image into the container and do NOT use stagedUploadsCreate (sandbox firewall).

## Invariants

- descriptionHtml is **not** modified by this rule (count, order, src, attributes unchanged).
- Existing gallery media is never deleted or reordered.
- Runs **after** rehost.py and spread.py, **before** the final push/verify of the product.

## Verification (verify.py — check 19)

For every product with description image count > 2: every description image basename must appear in `product.media`. Report any miss as `GALLERY-MISSING: <product_id> <url>`.

## Where it applies

All backend runs that touch descriptions (Q7 = Rewrite) **and** any gallery/image task. If a run keeps descriptions (Q7 = Keep), the rule still applies when the brief explicitly asks for a gallery sync.
