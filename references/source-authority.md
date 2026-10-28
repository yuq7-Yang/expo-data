# Source authority and identity rules

## Define authority by field

Authority belongs to a source-field pair, not to whichever source has more text.
A practical default for expo systems is:

| Fact | Typical authority | Secondary sources may do |
| --- | --- | --- |
| Participation, hall, booth | Organizer exhibitor list | Flag conflicts only |
| Event time and venue | Organizer schedule or signed correction | Add public description |
| Stable event identity | Versioned internal registry backed by organizer keys | Supply aliases as candidates |
| Registered-company profile | Verified registry export | Enrich a confirmed exhibitor |
| Products, brands, narrative | Organizer material or attributed public content | Add evidence-bearing text |

Document a different hierarchy when the project has stronger evidence. Do not
infer authority from recency, row count, or textual richness.

## Field policy

Classify every input field before ingestion:

- **Public:** approved facts that may reach canonical tables and retrieval.
- **Restricted:** retained only in access-controlled quarantine when authorized.
- **Discarded:** unnecessary fields that should not persist downstream.

For a public attendee assistant, phone numbers, legal representatives, personal
addresses, and similar identifiers stay outside retrieval even if publicly
visible elsewhere. A separately authorized contact directory is a different data
product with its own purpose, access controls, and review.

## Stable identity

Maintain an append-only registry containing stable ID, durable upstream keys,
canonical name, aliases, first-seen release, status, and merge history.

- Never derive IDs from current sort order.
- Never recycle retired IDs.
- Treat normalized names and fuzzy similarity as candidate generation only.
- Require durable corroboration before merging identities.
- Do not allocate provisional stable IDs to unresolved rows.
- Represent booth moves and repeated participation as versioned relationships,
  not new exhibitor identities.

Every source row receives one explicit disposition: canonicalized, attached as
enrichment, quarantined for review, or intentionally excluded with a reason.
