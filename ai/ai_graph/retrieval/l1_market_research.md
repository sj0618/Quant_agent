# L1 Market Research Evidence

L1 evidence is deterministic market and research context used before any strategy signal is produced. For the MVP it is fixture based and never calls securities APIs.

Supported Korean equity research signals include analyst report coverage, target price revision, net foreign buying or selling, sector momentum, consensus earnings revision, and liquidity guardrails.

Evidence timing rule: reports collected after market close are available from the next trading session open. Candidate filtering should preserve a reason trace for each ticker so the user can see why Samsung Electronics, SK hynix, or another KRX equity was included.
