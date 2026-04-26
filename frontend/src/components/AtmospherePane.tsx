/**
 * Right-pane visual for the login screen — six layered fills:
 * base gradient, three radial glows, chart silhouette, grid texture.
 * Hidden below 768px viewport width.
 */
export default function AtmospherePane() {
  return (
    <div
      className="hidden md:block relative overflow-hidden border-l border-surface-border"
      aria-hidden="true"
    >
      {/* Layer 1: base gradient corner-to-corner */}
      <div
        className="absolute inset-0"
        style={{ background: 'linear-gradient(135deg, #1a1823 0%, #0f0e14 100%)' }}
      />

      {/* Layer 2: central kraken glow with breathe pulse */}
      <div
        className="absolute inset-0 animate-glow-pulse"
        style={{
          background:
            'radial-gradient(circle at 60% 50%, rgba(123, 97, 255, 0.35) 0%, rgba(123, 97, 255, 0.15) 40%, transparent 80%)',
        }}
      />

      {/* Layer 3: bottom-left accent glow */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse at 30% 90%, rgba(98, 72, 229, 0.4) 0%, transparent 60%)',
        }}
      />

      {/* Layer 4: top-right accent glow */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse at 100% 0%, rgba(155, 133, 255, 0.25) 0%, transparent 50%)',
        }}
      />

      {/* Layer 5: chart silhouette */}
      <svg
        className="absolute inset-0 w-full h-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="atmosphereChartFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#7B61FF" stopOpacity="0.45" />
            <stop offset="1" stopColor="#7B61FF" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path
          d="M0,75 C15,72 28,58 42,52 S68,38 82,22 L100,12 L100,100 L0,100 Z"
          fill="url(#atmosphereChartFill)"
        />
        <path
          d="M0,75 C15,72 28,58 42,52 S68,38 82,22 L100,12"
          stroke="#7B61FF"
          strokeWidth="0.9"
          fill="none"
          opacity="0.85"
          strokeLinecap="round"
        />
      </svg>

      {/* Layer 6: subtle grid texture */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            'linear-gradient(rgba(240, 238, 245, 0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(240, 238, 245, 0.025) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
        }}
      />
    </div>
  )
}
