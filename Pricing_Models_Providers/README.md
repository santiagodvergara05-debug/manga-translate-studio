# Provider pricing tables

This folder contains community-maintained JSON price tables that can be imported from **Usage / Prices → Prices → Import JSON**. Keep these reference files separate from the application's local `cache/pricing_tables.json`; users can download only the provider files they need and import several of them.

## File format

Each file contains a `prices` array. Rates are USD per one million tokens. Use `null` for a rate that is not published or not applicable. `cached_input_usd_per_million` may be `null` when the provider has no separate cached-input rate. Optional top-level `notes` can document source limitations or dates; the app ignores these notes during import and imports only `prices`.

```json
{
  "version": 2,
  "prices": [
    {
      "provider": "provider-id",
      "model": "model-id-or-prefix",
      "plan": "any",
      "input_usd_per_million": null,
      "cached_input_usd_per_million": null,
      "output_usd_per_million": null
    }
  ]
}
```

Supported plan values are `any`, `free`, `paid`, and `off-peak`. Model prefixes are supported by the app. Use the provider identifier expected by the app where available; files for providers not yet integrated can still be maintained here for future use.

## Contributions

- Name files clearly, for example `provider_prices.json`.
- Verify rates against the provider's official pricing page and include the source URL and verification date in the pull request description.
- Do not include API keys, account identifiers, local usage data, or personal configuration.
- Keep prices numeric or `null`; do not enter currency symbols in JSON values.
- PRs updating rates should state the affected models, plans, effective date, and source.

The JSON files in this folder are community reference snapshots. Verify current rates with each provider before relying on an estimate or submitting an update; rates, plans, cache discounts, and model availability can change.
