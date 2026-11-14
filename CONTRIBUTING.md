# Contributing to Manga Translate Studio

Thank you for contributing. This guide covers code, manga translation languages, AI providers, and community price references. For **application interface translations**, follow [TRANSLATION.md](TRANSLATION.md), which is the source of truth for catalog workflow, credits, human audits, and localization policy.

## Code of conduct

Be respectful and constructive. Discuss code and technical choices without attacking people. Harassment, personal attacks, and sharing private information without permission are not acceptable. Maintainers may take action when behavior harms the community.

## Project-wide requirements

- **Licensing:** The project is distributed under Apache License 2.0. By submitting a contribution, you confirm you have the right to contribute it under the repository's license. Do not submit proprietary code or material whose license is incompatible with the project.
- **Architecture:** Keep UI, provider requests, prompt construction, persistence, and usage handling in their established layers. Follow the existing manager/provider interfaces instead of adding parallel request paths.
- **Provider results:** Normalize provider outcomes through `TranslationResult` and `ProviderStatus`. Keep temporary overload/rate limits distinct from daily quota exhaustion and permanent errors.
- **Source language:** Write code comments, docstrings, identifiers, logs, and developer-facing errors in technical English. User-visible UI text must use the localization system.
- **Privacy:** Never commit API keys, tokens, personal account identifiers, user rules, local usage history, or private price settings. Runtime state belongs in the git-ignored `cache/` directory.
- **AI assistance:** AI tools and coding agents are allowed. The contributor must understand and fully review every submitted change, check its license and behavior, and remain responsible for it. Never provide an agent with credentials or private user data.

## Add a manga translation language

This section is for languages recognized from manga pages or used as translation output. It does not add an application UI language; see [TRANSLATION.md](TRANSLATION.md) for that separate workflow.

Language lists and target-language SFX rules are in `src/backend/languages.py`.

1. Add the language to `SUPPORTED_SOURCE_LANGUAGES` if the model may read it from an image, to `SUPPORTED_TARGET_LANGUAGES` if it may be selected as output, or to both. Use a stable language code, English name, and native name. Follow the existing code convention; translation language codes are distinct from UI catalog filenames (for example, target Portuguese uses `pt-br`, while the UI catalog is `pt-BR.json`).
2. If the source script needs CJK/vertical-layout handling, update `ASIAN_LANG_CODES` with its source-language code. Do not add a language there solely because it is geographically in Asia.
3. Add target-specific comic SFX examples or conventions to `get_sfx_rule_for_target()` when they materially improve the prompt. Keep examples natural for the target language and avoid changing unrelated language rules.
4. Review source/target continuity, punctuation, and prompt behavior with representative examples. Describe what was checked in the PR.

## Add an AI provider

Gemini and Ollama are the implemented providers. OpenAI, xAI, Anthropic, OpenRouter, and DeepSeek are currently unavailable scaffolds: they must remain fail-closed until a complete integration is implemented and verified. Do not treat a visible settings entry as a working provider.

1. Implement a provider in `src/backend/providers/<provider_name>_provider.py` as a subclass of `BaseAIProvider` in `base_provider.py`.
2. Implement `test_and_fetch_models()` for the provider's actual connection/model behavior and `execute_translation()` for its vision request. Match their existing signatures and return a normalized `TranslationResult`; do not return simulated success or placeholder usage data.
3. Declare the provider UI attributes used by API Settings, such as `display_name`, `requires_endpoint`, `has_lan_mode`, `is_primary_secret`, placeholders, endpoint, and default models. Inspect Gemini and Ollama for the relevant patterns; omit capabilities the provider does not support.
4. Map outcomes accurately: successful extraction, empty page, moderation block, temporary overload, quota exhaustion, and unrecoverable error. Use `DailyQuotaExceeded` only for a confirmed daily quota limit; map retryable overload/rate-limit conditions to the appropriate busy result.
5. Report token, cache, request, and thinking usage only when the provider actually returns those values. Do not infer cached tokens or silently turn missing usage into confirmed measurements.
6. Register the provider in `PROVIDERS` in `src/backend/ai_client.py` and add the provider's default credential shape to `CredentialManager.default_config` when needed. Preserve saved connection-profile behavior and make sure unavailable integrations cannot be saved or called as active providers.
7. Keep network work in the existing worker/request path. Use bounded timeouts and provider-appropriate retry behavior; preserve the system/user prompt separation and shared per-provider pacing. Do not add provider-specific requests directly to UI widgets.
8. Test connection discovery, local/cloud modes if supported, a real vision response, empty output, transient failures, quota errors, usage parsing, and credential/profile save-and-reload behavior. Document setup requirements and any provider-specific limitations in the PR.

Do not copy a provider example that returns a fixed successful connection or invented token counts. The scaffold files are intentionally unavailable examples, not complete implementations.

## Update community price references

Reference price files are in `Pricing_Models_Providers/` and are imported by users; they are separate from the private runtime table in `cache/pricing_tables.json`.

- Follow the schema and import behavior documented in [`Pricing_Models_Providers/PRICING_TABLES.md`](Pricing_Models_Providers/PRICING_TABLES.md).
- Use numeric USD-per-million-token rates or `null` when a rate is not published or does not apply. Do not put currency symbols in numeric fields.
- Verify changed rates against the provider's official pricing source. Include the source URL, date checked, affected models/plans, effective date, and any limitations in the PR.
- Do not add account information, API credentials, usage records, or personal settings.

## Pull request checklist

Complete the checks that apply to your changes and report any that could not be run. Do not claim a check passed unless it was actually performed.

### Every pull request

- [ ] The diff is focused, understood, and follows the project structure; no unrelated or dead code was added.
- [ ] No secrets, private user data, cache files, logs, temporary images, or build artifacts are included.
- [ ] New and changed source comments/docstrings follow the technical-English convention.
- [ ] User-visible strings use `tr()` or `tr_label()` and have non-empty English source entries. For localization changes, follow [TRANSLATION.md](TRANSLATION.md) and report structural validation and human review separately.
- [ ] Run relevant syntax checks. For a source-level review, the full command is:

  ```powershell
  python -m compileall -q main.py src tools build_exe.py generate_icons.py
  ```

- [ ] Launch with `python main.py` and perform relevant manual checks when the change affects runtime behavior. State the checks performed and remaining limitations in the PR.

### AI-assisted code contributions

- [ ] Identify the areas where an AI agent or other AI tool assisted, where relevant, and personally review the full diff.
- [ ] Trace affected imports, call paths, signals, data flow, persistence, and error handling. Confirm the code is connected and no unintended/dead implementation remains.
- [ ] Confirm the code is understood, compatible with the project's license, and does not reproduce unauthorized proprietary material.
- [ ] Do not give AI tools credentials, API keys, private logs, user rules, or other sensitive data.
- [ ] Report accurately which checks were run and which remain unverified. AI output is not a substitute for testing or contributor responsibility.

### Manga translation language changes

- [ ] Register the language in the correct source and/or target list with a consistent code and native label.
- [ ] Update `ASIAN_LANG_CODES` only when the source-script handling requires it.
- [ ] Review relevant SFX conventions, continuity, punctuation, and target-language behavior.

### UI localization changes

- [ ] Follow the catalog creation, LLM-assisted workflow, key verification, human audit, credits, and integrity policy in [TRANSLATION.md](TRANSLATION.md). Do not duplicate its detailed procedure here.

### Provider changes

- [ ] Confirm the provider implements `BaseAIProvider` and is registered in `AIClientManager.PROVIDERS` with correct settings metadata and credential/profile handling.
- [ ] Confirm only real provider results and usage metadata are reported; classify busy, safety, daily quota, and permanent errors correctly.
- [ ] Confirm unavailable guards are removed only after the integration works and has been tested.

### Price-reference changes

- [ ] JSON parses and follows the `prices` schema in [`PRICING_TABLES.md`](Pricing_Models_Providers/PRICING_TABLES.md).
- [ ] Changed rates include authoritative sources and verification dates.
- [ ] No local usage or account data is included.

### UI, worker, prompt, canvas, or script changes

- [ ] Keep network requests and long-running work off the Qt GUI thread. Review signal/slot ownership and shutdown behavior for affected workers.
- [ ] Preserve the Manga Cleaner script contract: `<translation>...</translation>` and `Image X [filename]` records. Preserve Unicode NFC normalization where script matching/writing uses `_nfc()`.
- [ ] Resolve runtime files through `Paths` helpers; check that packaged resources stay in `MangaTranslate_Data` and persistent user data stays outside it.
- [ ] For image/canvas changes, check long vertical pages, scrolling, zoom, pan, and page-switch behavior as applicable.
- [ ] For reset or page lifecycle changes, check that session state and image references are cleared as intended without deleting persistent user settings or on-disk projects.
- [ ] If changing `DEFAULT_CORE_RULES`, preserve the silent-page output shape (`{"bubbles": []}`) and the documented JSON contract.
