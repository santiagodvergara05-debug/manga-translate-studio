# Community provider price tables

This folder contains reference JSON files for **Usage / Prices → Prices → Import JSON**. They are optional snapshots for users to review and import. They are separate from the user's private, editable `cache/pricing_tables.json`; importing a reference file does not make it authoritative or keep it current automatically.

## Import behavior

- The importer reads the top-level `prices` array and ignores other fields, including `version` and `notes`.
- Import is additive: a row with the same provider, model, and plan replaces that matching local row; unrelated rows are retained.
- `model` may be an exact model name or a prefix used to match model variants. Use the narrowest reliable identifier.
- Provider IDs should match IDs used by the application. Reference rows for providers not yet integrated can be kept for future use, but cannot produce estimates until the provider is supported.
- These values estimate costs from reported token usage. They are not invoices, and estimates may differ from provider billing because of plan, modality, discounts, taxes, or pricing changes.

## JSON format

Each file must be a JSON object with a `prices` array. Rates are USD per one million tokens. Use JSON numbers for known rates and `null` when a rate is unknown or not applicable; do not guess or use formatted strings. A top-level `version` or `notes` field is allowed for maintainers, but the application ignores it during import.

```json
{
  "version": 2,
  "notes": ["Source URL and date checked: https://provider.example/pricing — YYYY-MM-DD"],
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

Supported `plan` values are `any`, `free`, `paid`, and `off-peak`. Use `any` when one price applies across plans or the source does not distinguish a plan. Use `null` for a rate that the provider does not publish or that does not apply. Do not enter zero unless the provider explicitly offers that usage at no charge.

## Updating a reference table

- Check rates against the provider's official pricing documentation, not a third-party estimate.
- In the PR description, include the source URL, date checked, affected models and plans, effective date if known, and any limitations or interpretation required by the app's schema.
- Keep provider tables separate. Do not include API keys, account identifiers, personal usage, local settings, or the contents of a user's runtime cache.
- Review the resulting JSON and explain any rate the app schema cannot represent exactly (for example, modality-specific input prices when the app has one input-rate field).

Prices, plans, cache discounts, and model availability change. Verify a snapshot with the provider before relying on it or importing it for cost decisions.
