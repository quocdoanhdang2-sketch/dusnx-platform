# Post-Week 4 evidence

All accounts and databases are synthetic scratch data. JSON and screenshots contain no token,
password, cookie, personal DB or model artifact. `browser.json` is real Chromium/Gateway/Ollama;
`demo.json` is the repeatable PowerShell scenario; `i18n-inspector.json` is real HTTP with filtered
Inspector; `performance-security.json` is a bounded local health test and security probes.

Two earlier Chromium runs remain only under ignored `runtime/`: the first exposed CSP blocking
legacy inline handlers; after allowing current handlers, the second showed the verifier's string
`eval` was rejected by CSP. The verifier now polls geometry without eval and the final run passed.
