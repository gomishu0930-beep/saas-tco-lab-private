import { syntheticComparison } from "../lib/synthetic-data";

export function StatusStrip() {
  return (
    <div className="status-strip" role="status">
      <div className="shell status-inner">
        <span className="status-label">公開前検証</span>
        <span>合成データのみ</span>
        <span>CTA停止中</span>
        <span>生成: {syntheticComparison.generatedAt}</span>
      </div>
    </div>
  );
}
