# Hermes Browser Use Overview

## Executive summary

This conversation thread focused on two things:

1. Tuning Hermes itself so it behaves better in long sessions.
2. Understanding how Hermes browser use actually works today — locally, through the browser tool stack, and in the broader browser-agent ecosystem.

The main conclusions were:

- Hermes was compacting too early at the default `compression.threshold` of `0.50`, so it was raised to `0.80`.
- The user’s timezone preference is EST/ET.
- Hermes browser use is not a single mode. It is a routed system that can use CDP attachment, Browser Use direct API mode, Browserbase integration, or local handling for private URLs.
- On this machine, the current config points to a hybrid setup: browser engine `auto`, no explicit CDP URL, private URLs blocked by default but eligible for automatic local routing, and no explicit Browserbase project configured.
- The current browser automation landscape is moving toward DOM-first control, selective vision fallback, Playwright/MCP integration, live browser attachment, hosted infra, self-healing flows, and mobile/device control.
- The biggest remaining browser-agent problems are login/session handling, CAPTCHAs and anti-bot defenses, screenshot latency, and safety/sandboxing.
- Hermes appears ahead on orchestration and integration, while the Nous Portal subscription appears to bundle hosted browser/tool access rather than unlocking a wholly separate browser intelligence layer.

## What we worked on across sessions

### 1) Context compression and session behavior

We started by asking why Hermes sessions compact at 50%.

What we found:
- The default compression trigger is `compression.threshold = 0.50`.
- That value is a trigger point, not a hard cap.
- For long, tool-heavy sessions, `0.50` can feel too aggressive.
- The threshold was raised to `0.80` in `/Users/watson/.hermes/config.yaml`.

This improved the “keep more context before compacting” behavior.

### 2) Timezone and config hygiene

The user clarified that the timezone is EST.

That was captured as a durable preference so future responses and scheduling can respect it.

### 3) Hermes browser settings audit

We then looked at the browser-related config and the unset settings around Hermes.

Important confirmed config values in `/Users/watson/.hermes/config.yaml`:
- `browser.engine: auto`
- `browser.cdp_url: ''`
- `browser.allow_private_urls: false`
- `browser.auto_local_for_private_urls: true`
- `browser.record_sessions: false`
- `browser.inactivity_timeout: 120`
- `browser.command_timeout: 30`
- `browser.dialog_policy: must_respond`
- `browser.dialog_timeout_s: 300`
- `browser.camofox.managed_persistence: false`
- `browser.cloud_provider` is not set

Environment clues from the machine:
- `BROWSER_USE_API_KEY` is present
- `BROWSERBASE_PROJECT_ID` is not set

Interpretation:
- Hermes is set up for an adaptive browser path.
- It does not have a pinned CDP override.
- It can route private URLs locally.
- Browser Use is the most likely active cloud path on this machine.
- Browserbase is incomplete here.

### 4) Browser behavior explanation

We clarified the distinction between web search/extraction and browser automation:

- Web backends fetch and extract text.
- Browser tools interact with a live page.

Hermes browser tools include:
- `browser_navigate`
- `browser_snapshot`
- `browser_click`
- `browser_type`
- `browser_press`
- `browser_scroll`
- `browser_console`
- `browser_vision`

So Hermes can do the full loop:
- inspect
- act
- re-inspect
- fall back to vision when the DOM is not enough

### 5) Browser architecture investigation

We inspected the local Hermes code and confirmed the browser stack is layered.

Key takeaways:
- CDP override has the highest priority when explicitly configured.
- Browser Use direct API mode is supported.
- Browserbase integration exists.
- Private URLs can be routed locally.
- The browser engine defaults to auto-selection when not pinned.

Practical interpretation for this device:
- Public browsing likely goes through Browser Use cloud/direct API behavior.
- Local/private URLs can be handled locally.
- CDP attachment is available if explicitly configured later.
- The system is hybrid by design.

### 6) Browser automation research sweep

We also did a broader research pass on browser automation trends in the agent space, including a last30days-style sweep and subagent research.

The current market direction is clearly toward:
- DOM-first automation
- selective vision fallback
- Playwright-first toolchains
- MCP integration
- live browser attachment via CDP
- hosted browser infrastructure
- self-healing workflows
- mobile/browser-on-device control
- vision + DOM hybrids

High-signal projects and themes that came up:
- Browser Use
- Stagehand
- Skyvern
- browser-harness
- Steel browser infra
- Playwright MCP
- Chrome DevTools MCP
- OmniParser-style vision parsing
- mobile device/browser automation projects

### 7) The current limitations of browser automation

The main pain points are still very real:

- Login and session handling remain brittle.
- CAPTCHAs and anti-bot defenses still block many workflows.
- Screenshot-heavy loops are slow.
- Safety and sandboxing are not optional.
- Reliability is still the hardest part of production browser automation.

The most robust pattern today is:
- DOM first
- vision only when needed
- strong session/auth handling
- live browser/CDP attachment when helpful
- careful routing and safety controls

## What Hermes seems ahead on

Hermes appears ahead on the platform/orchestration layer rather than just the browser itself.

What stands out:
- Browser tools are first-class in the agent runtime.
- Hermes also integrates memory, skills, delegation, tool gateway, and browser support in one system.
- Private URLs can be handled locally while public browsing stays cloud-backed.
- The browser stack is designed to work as part of an agent OS, not as a bolt-on browser robot.

In other words:
- Hermes is ahead on integration and control-plane design.
- The broader browser-agent ecosystem is ahead on raw browser experimentation and rapid infra innovation.

## Subscription-gated value

Hermes release notes confirmed that paid Nous Portal subscribers get:
- web search
- image generation
- TTS
- browser automation through the Tool Gateway
- no extra API keys required

That reads like bundled hosted access and convenience, not a totally separate browser model.

## Current local interpretation

For this machine, the most likely browser path is:

- Browser Use cloud/direct API mode for public sites
- local routing for private URLs
- no explicit CDP override
- no Browserbase project configured
- Browser Use API key present

That is why Hermes feels flexible rather than brittle: it can choose the right execution path for the URL and the task.

## Session identifiers we found

- Hermes session ID: `20260511_011446_1edb90`
- Discord chat ID: `1502096019087687880`

## Recommended next steps

If you want to keep tightening this stack, the most useful next moves are:

1. Decide whether you want a pinned browser backend or want to stay on auto.
2. Decide whether private URL handling should remain local-first.
3. Check whether you want Browser Use, Browserbase, or CDP attachment as your default.
4. If you care about reliability, test login/session-heavy browser flows explicitly.
5. If you want stronger operational safety, review browser allow/block behavior and SSRF protection.
6. If you want to compare tools, benchmark Hermes browser use against Browser Use, Stagehand, and Playwright MCP on the same task set.

## Bottom line

Hermes browser use is already more than a browser wrapper. It is a routed, agent-native browsing system with local/private handling, cloud integration options, and safety controls. The browser-agent field is moving fast, but Hermes is already positioned more like an agent OS than a standalone browser automation library.
