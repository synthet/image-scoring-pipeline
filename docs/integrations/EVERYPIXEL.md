# Everypixel Labs photo quality connector

The backend includes `modules.everypixel.EverypixelClient` for calling
Everypixel Labs' stock-photo and user-generated-photo quality models.

## Pricing (USD)

From [Everypixel Labs pricing](https://labs.everypixel.com/pricing) (pay-as-you-go):

| Connector model | Everypixel API | List price | Free trial (per API) |
|-----------------|----------------|------------|----------------------|
| `stock` | `/stock_photo_quality` → `POST /v1/quality` | **$0.60 / 1,000** requests | **500** requests |
| `ugc` | `/ugc_photo_quality` → `POST /v1/quality_ugc` | **$0.60 / 1,000** requests | **500** requests |

That is **$0.0006** per billable successful request after each API's free quota.

**Rough capacity on a $10 local cap** (connector estimate, not your Everypixel wallet):

- If both free trials are unused: **500 + 500 = 1,000** free calls, then about **16,666** more paid calls at $0.0006 each ≈ **$10** → **~17,666** total successful calls mixed across types (depending on mix).
- If free trials are already exhausted (`EVERYPIXEL_ASSUME_FREE_QUOTA_*=0`): **~16,666** successful calls ≈ **$10**.

The connector counts **successful** responses separately for `stock` and `ugc`, estimates spend from list price, and **refuses the next call** that would push the estimate over `EVERYPIXEL_SPEND_LIMIT_USD` (default **10**). Failed HTTP calls are not counted.

## Configure credentials

Add the credentials to the ignored `.env` file used by your runtime:

```dotenv
EVERYPIXEL_CLIENT_ID=your_client_id
EVERYPIXEL_SECRET_KEY=your_secret_key

# Local spend guard (USD estimate from list price + assumed free quota)
EVERYPIXEL_SPEND_LIMIT_USD=10
EVERYPIXEL_ASSUME_FREE_QUOTA_STOCK=500
EVERYPIXEL_ASSUME_FREE_QUOTA_UGC=500
# Optional: persist counters across processes (path must be writable)
# EVERYPIXEL_USAGE_STATE_PATH=.agent/scratch/everypixel_usage.json
```

Set `EVERYPIXEL_SPEND_LIMIT_USD=0` to disable the local cap (Everypixel account balance still applies).

The names can also be provided directly in the process environment. The
connector keeps them server side and authenticates each HTTPS request with
HTTP Basic Auth. Do not put these values in browser or renderer code.

## Use

```python
from modules.everypixel import EverypixelClient

client = EverypixelClient()
ugc = client.score_value("/path/to/photo.jpg", model="ugc")
stock = client.score_value("/path/to/photo.jpg", model="stock")
print(client.usage_summary())
```

`ugc` calls `https://api.everypixel.com/v1/quality_ugc`; `stock` calls
`https://api.everypixel.com/v1/quality`. Both accept JPEG/PNG uploads and
return scores from 0 to 1. Use `client.score(...)` to receive the provider's
full JSON response. API errors raise `EverypixelError`; spend cap violations
raise `EverypixelBudgetExceeded`; missing files raise `FileNotFoundError`.

The connector is an optional API client and does not run during ordinary
scoring jobs. Everypixel account trials, quotas, and paid usage apply to
successful API calls.

## Correlation study (research)

Read-only harness comparing **UGC `quality.class`** / **`quality.score`** to local
composites and `image_model_scores`: [Everypixel UGC correlation study](../planning/integrations/EVERYPIXEL_CORRELATION_STUDY.md) (GitHub [#392](https://github.com/synthet/image-scoring-backend/issues/392)).

References: [Everypixel Labs API docs](https://labs.everypixel.com/docs),
[Everypixel pricing](https://labs.everypixel.com/pricing),
[Authentication](https://labs.everypixel.com/docs#authentication),
[Stock Photo Quality](https://labs.everypixel.com/docs#stock-photo-quality),
[UGC Photo Quality](https://labs.everypixel.com/docs#ugc-photo-quality).
