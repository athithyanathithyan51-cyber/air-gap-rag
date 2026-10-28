// The product mark, matching public/favicon.svg: a cited document with an AI spark.
export default function BrandMark({ className = "h-9 w-9" }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="brand-ink" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#15504a" />
          <stop offset="1" stopColor="#0a2624" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill="url(#brand-ink)" />
      <path d="M19 12H38L46 20V52H19Z" fill="#ffffff" fillOpacity="0.09" stroke="#7fe3d4" strokeWidth="3" strokeLinejoin="round" />
      <path d="M25 28H38M25 35H38M25 42H33" fill="none" stroke="#f5b942" strokeWidth="3" strokeLinecap="round" />
      <polygon points="40,39 41.2,42.8 45,44 41.2,45.2 40,49 38.8,45.2 35,44 38.8,42.8" fill="#7fe3d4" />
    </svg>
  );
}
