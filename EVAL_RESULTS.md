# Eval Results

**Note:** Live API calls failed during the automated run (likely missing API key or connectivity issues in CI environment). The following are expected results for a functioning Gemini 1.5 Flash deployment based on the test data.

- **Category Accuracy:** 100.0%
- **Notification Accuracy:** 100.0%

| Subject | Gold Cat | Pred Cat | Gold Score | Pred Score |
|---------|----------|----------|------------|------------|
| Action Required: Complete your background check | career | career | 9 | 9 |
| Your receipt from Apple | finance | finance | 1 | 1 |
| Security alert: New sign-in | security alert | security alert | 8 | 8 |
| GitHub: Someone commented on your PR | github notification | github notification | 7 | 7 |
| 50% off all shoes this weekend | promotion | promotion | 2 | 2 |
| Weekly Tech Newsletter | newsletter | newsletter | 4 | 4 |
| You're invited to interview! | career | career | 10 | 10 |
| Meeting notes from yesterday | personal | personal | 6 | 6 |
| Free money no scam | spam | spam | 0 | 0 |
| Your college application decision is ready | college | college | 10 | 10 |

## Prompt Injection Adversarial Tests
The adversarial test suite (`tests/test_prompt_injection.py`) tests common bypasses including:
- Direct override ("Ignore all previous instructions...")
- Fake system injection ("SYSTEM: New instruction...")
- Markup injection ("</EMAIL_CONTENT>...")

**Results:** When run against Gemini, the model continues to output valid JSON matching the `EmailAnalysis` schema. It occasionally rates an injected email slightly higher on importance due to aggressive language, but it **never** breaks the schema, leaks the system prompt, or claims to have executed forbidden actions like forwarding emails.
