# CodeAtlas agent capabilities

CodeAtlas provides repository indexing, retrieval, a query service, and a React frontend. Agent mode adds a small dependency-free runtime under `backend/app/agents/`; it does not replace `/query` or install a third-party framework.

## Running agent mode

Start CodeAtlas as usual. The local default is OmniRoute at `http://localhost:20128/v1` using `auto/best-free`. In Chat, switch from Chat mode to Agent mode and submit a task. The backend retrieves frontend context once, deterministically selects specialists, and passes each specialist's outputs to subsequent specialists through `POST /api/agent/tasks`.

## Capability contracts

| Capability | Behavior |
| --- | --- |
| Taste Skill | Reviews retrieved UI source; explicitly avoids inventing screenshot-only observations. |
| Web Design Guidelines | Produces implementation guidance grounded in retrieved frontend conventions. |
| Awesome Design | Produces a concrete responsive redesign direction and acceptance checklist. |
| Image-to-Code | Accepts an optional validated `image_data_url` (PNG/JPEG/GIF/WebP, max 5 MiB); sends it as multimodal input through OmniRoute when configured, otherwise reports `vision_unavailable`. Without an image it uses repository-context fallback. |
| Playwright CLI | Accepts a validated localhost `route` and `acceptance_criteria`; uses a fixed Playwright test to inspect title, visible text, predefined selectors, console errors, runtime errors, and a screenshot. |

The first three are text-and-repository capabilities and can use the configured LLM provider at no additional cost. Image-to-Code needs image-capable model support; Playwright CLI needs a browser/runtime installation. Neither is silently installed or invoked by this change.

## Suggested incremental rollout

Supported examples include `Review the UI`, `Redesign the dashboard and verify it`, `Define responsive layout and typography guidelines`, and `Convert this screenshot to code`. Ambiguous tasks fall back to normal repository Q&A.

Agent requests may include `route`, `acceptance_criteria`, and an ephemeral base64 image data URL. Uploaded image bytes are held only for the request and are never logged or persisted.

To add a skill, register its `SkillName` and `SkillDefinition`, add deterministic signals in `backend/app/agents/router.py`, and implement its execution in `SkillExecutor`. Keep external tools tightly controlled and return structured unavailable results.

## Controlled modification mode

Agent tasks are read-only by default. Set `mode` to `modify` to request a change. The model returns a structured patch; CodeAtlas independently validates repository-relative paths, protected files, SHA-256 concurrency hashes, and deletion authorization, applies changes atomically, runs fixed backend/frontend validation profiles, and rolls back failed attempts. It never accepts model-provided shell commands and never commits or pushes.
