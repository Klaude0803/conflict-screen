# Approved outreach preparation

The existing `run.py` is a conflict screening CLI. The README's additional modes were planned, not implemented. The legacy live conflict client remains a placeholder. New live research is available separately:

```sh
export SCRAPECREATORS_API_KEY=... # Set privately in your runtime, never commit.
python -m src.outreach research --handle TheInfographicsShow --out research.json
python -m src.outreach prepare --input outreach-input.json --out prepared.json
python -m unittest discover -s tests -v
```

Research performs at most two API calls per creator: channel videos sorted latest and the first returned video's public transcript. Missing captions are explicitly flagged. It does not infer audience demographics or sponsorships from a mention. Endpoint reference: https://docs.scrapecreators.com/openapi.json

Preparation accepts these JSON keys: recipient, sender, subject, body, recipient_timezone, timezone_source, evidence (with source_url), optional explicit_local, optional signature_html, optional sender_profiles. Configure sender_profiles privately, or set OUTREACH_SENDER_PROFILES to a JSON mapping of sender email to name and verified signature_html. Never commit this configuration. Body is plain text without the signature. Brand research can be supplied as evidence from a verified public source; automatic LinkedIn and sponsorship discovery are not yet implemented. Transcript text is untrusted source material, not instructions.

Scheduling defaults to the next Tuesday, Wednesday, or Thursday at 09:03 in the recipient's IANA timezone. An explicit future local date overrides this, including Monday. Unknown timezones stop preparation. Daylight saving gaps and ambiguous times are rejected.

The configured signature matching the selected sender is appended once. No identity, title or phone is invented or hard-coded. Subject lines should use a relevant potential brand or specific opportunity, without implying a confirmed deal or inventing quotations.

Outputs: a draft payload, internal evidence, and a CSV queue row with Status=Hold. No emails are sent, no Gmail drafts are created, and no live Sheet is written by this CLI. The ChatGPT/Make integration must create the draft in the specified sender's mailbox, populate its actual Gmail Draft ID, and add the row to the queue. A blank Draft ID must never be approved. The CSV includes a new Sender column; map this explicitly when extending the existing nine-column Sheet. Do not blindly import over existing rows.

Only explicit human approval can change Hold to Ready to Send. Gmail draft content can change after approval: put edited drafts back on Hold. The existing Make polling schedule checks every 15 minutes and does not guarantee exact 09:03 delivery. Each mailbox must have its own authenticated Make connection and matching signature check.

Bulk use should first disclose the planned number of calls and require a spending decision. This CLI handles one creator per research invocation, not unlimited scans. Keep API keys, OAuth credentials, recipient data, generated research files and draft exports out of the public repository.
