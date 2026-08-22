
# RouteBR scenario benchmark

The public benchmark contains 600 Chinese customer-service scenarios with five service actions, five boundary outcomes, mixed-service language, paired same-request/different-state cases, and difficult closed-list entity references. It contains no raw customer request, customer identifier, account, transaction, or confidential institutional rule.

The 600-case file is divided into DEV (120), MAIN (300), FLIP (120), and ENTITY (60). SELECT (160) and CONFIRM (320) are disjoint subsets of the 480 non-DEV cases used for backend screening and confirmatory evaluation. The runtime predicates and policy rules are synthetic and versioned. Forty ETF identifiers and display names are public exchange-listed objects with official source URLs.

The authors report joint scenario-and-label review by three engineers from the institution. The release does not claim independent labeling, adjudication, or inter-annotator agreement. The public CSV schema intentionally omits unfinished private workflow fields such as annotator identities and internal draft-status columns; their absence must not be interpreted as independent annotation evidence.

Run `validate_dataset.py` as shown in the repository root README to check split sizes, ontology closure, JSON fields, FLIP pairing, entity references, and hashes.
