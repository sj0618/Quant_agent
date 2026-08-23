import { PUBLIC_CLAIM_LEDGER, type PublicClaimKey } from "../../content/publicClaimLedger";

interface PublicClaimDisclosureProps {
  claimKey: PublicClaimKey;
  asOf?: string;
}

/** A compact, visible link between public copy and its UI-contract claim. */
export function PublicClaimDisclosure({ claimKey, asOf }: PublicClaimDisclosureProps) {
  const claim = PUBLIC_CLAIM_LEDGER[claimKey];

  return (
    <dl className="public-claim-disclosure">
      <div><dt>공개 문구 ID</dt><dd>{claim.id}</dd></div>
      <div><dt>근거 범위</dt><dd>{claim.source}</dd></div>
      <div><dt>기준 시점</dt><dd>{asOf || claim.asOfPolicy}</dd></div>
      <div><dt>수치 표기</dt><dd>{claim.valuePolicy}</dd></div>
    </dl>
  );
}
