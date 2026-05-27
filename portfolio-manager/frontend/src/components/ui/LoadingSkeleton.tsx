export function LoadingSkeleton() {
  return (
    <main className="signal-loading signal-skeleton" data-testid="loading-skeleton">
      <div className="skeleton-rail" />
      <div className="skeleton-workspace">
        <div className="skeleton-telemetry" />
        <div className="skeleton-hero" />
        <div className="skeleton-grid">
          <div className="skeleton-card tall" />
          <div className="skeleton-card tall" />
        </div>
        <div className="skeleton-strip" />
      </div>
    </main>
  );
}
