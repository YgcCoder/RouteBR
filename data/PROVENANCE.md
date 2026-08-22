
# Data provenance and release boundary

## What the released rows are

The rows are synthetic reconstructions designed from recurring task, ambiguity, and boundary patterns observed in confidential customer-service requests at one real financial institution. Scenario drafting used local template-based and AI-assisted tooling. The authors report that three engineers from the institution jointly reviewed the scenarios and labels for practice relevance.

## What the released rows are not

- They are not copied customer utterances or raw institutional traffic.
- They are not a frequency estimate of production requests.
- They are not independently annotated or adjudicated, and no inter-annotator agreement is claimed.
- Their runtime predicates and policy rules are experimental software records, not institutional policy, regulation, or legal advice.
- Public ETF identifiers make the closed object registry auditable; they do not make the conversations observational records.

## Excluded material

The release excludes source requests, customer and account identifiers, transaction data, institution-specific rules, practitioner identities, private review workbooks, credentials, local paths, workbench notes, and exploratory outputs. The public case files retain only the task inputs and gold fields needed to reproduce the reported evaluation.

## Author and institutional checks required before publication

Before a public release, the authors should retain written institutional authorization for the reconstruction and publication procedure, confirm that no confidential source request was sent to a hosted model, and verify that the venue permits the documented AI-assisted data-construction process. This repository does not itself establish those approvals.
