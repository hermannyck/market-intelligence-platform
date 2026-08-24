import { NOT_LIVE_TRADING_DISCLAIMER } from "../services/navConfig";

export default function DisclaimerBanner() {
  return (
    <div role="note" className="disclaimer-banner">
      {NOT_LIVE_TRADING_DISCLAIMER}
    </div>
  );
}
