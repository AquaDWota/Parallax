export default function ParkingGuide({ baselineMethod }: { baselineMethod: "mean" | "median" }) {
  return (
    <details className="parking-guide">
      <summary>What does relative parking activity mean?</summary>
      <dl className="parking-scale">
        <div><dt>0.5x</dt><dd>Half as active</dd></div>
        <div><dt>1x</dt><dd>At its reference level</dd></div>
        <div><dt>1.5x</dt><dd>50% more active</dd></div>
      </dl>
      <p><strong>1x is this building&apos;s pre-COVID reference.</strong> A value of 1.5x means one and a half times that activity. It does not mean 150% of parking spaces are filled.</p>
      <p>The map compares detected cars per estimated space with the building&apos;s own reference. Study charts also adjust for nearby properties.</p>
      <details><summary>Reference calculation</summary><p>The reference uses the {baselineMethod} of usable observations from January 2016 to February 2020 in real-data mode (2018-2019 in synthetic mode). Higher and lower are activity descriptions, not good/bad ratings.</p></details>
    </details>
  );
}
