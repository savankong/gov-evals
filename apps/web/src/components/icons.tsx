/**
 * Icon set.
 *
 * Hand-drawn on a 16px grid at a single hairline weight, so the rail reads as
 * one system. No icon library: a dependency for eleven glyphs would outweigh
 * the glyphs.
 */
import type { SVGProps } from "react";

const base = {
  width: 16,
  height: 16,
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.25,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

type Props = SVGProps<SVGSVGElement>;

export const IconPortfolio = (p: Props) => (
  <svg {...base} {...p}>
    <rect x="2" y="2" width="5" height="5" />
    <rect x="9" y="2" width="5" height="5" />
    <rect x="2" y="9" width="5" height="5" />
    <rect x="9" y="9" width="5" height="5" />
  </svg>
);

export const IconBenchmark = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M2 3.5h11M2 8h7M2 12.5h9" />
  </svg>
);

export const IconReadiness = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M2 13h12" />
    <path d="M4 13V8M7.5 13V4M11 13V10M14 13V6" />
  </svg>
);

export const IconPlan = (p: Props) => (
  <svg {...base} {...p}>
    <rect x="3" y="2" width="10" height="12" />
    <path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" />
  </svg>
);

export const IconCampaign = (p: Props) => (
  <svg {...base} {...p}>
    <circle cx="8" cy="8" r="5.5" />
    <path d="M8 4.5V8l2.5 1.5" />
  </svg>
);

export const IconFinding = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M8 2.5 14 13H2L8 2.5Z" />
    <path d="M8 6.5v3" />
    <circle cx="8" cy="11.2" r="0.5" fill="currentColor" stroke="none" />
  </svg>
);

export const IconCompare = (p: Props) => (
  <svg {...base} {...p}>
    <rect x="2" y="3" width="4.5" height="10" />
    <rect x="9.5" y="3" width="4.5" height="10" />
  </svg>
);

export const IconAssurance = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M8 2 13 4v4.5c0 3-2.2 4.8-5 5.5-2.8-.7-5-2.5-5-5.5V4l5-2Z" />
    <path d="M6 8l1.5 1.5L10.5 6.5" />
  </svg>
);

export const IconFramework = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M8 2v12M2 8h12" />
    <rect x="2" y="2" width="12" height="12" />
  </svg>
);

export const IconScenario = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M2.5 4h11M2.5 8h11M2.5 12h7" />
  </svg>
);

export const IconReport = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M4 2h5l3 3v9H4V2Z" />
    <path d="M9 2v3h3" />
  </svg>
);

export const IconLibrary = (p: Props) => (
  <svg {...base} {...p}>
    <rect x="2.5" y="2.5" width="3" height="11" />
    <rect x="6.5" y="2.5" width="3" height="11" />
    <path d="M11 3.2l2.6.7-2.3 10.6-2.6-.7" />
  </svg>
);

export const IconSearch = (p: Props) => (
  <svg {...base} {...p}>
    <circle cx="7" cy="7" r="4.5" />
    <path d="M10.5 10.5 14 14" />
  </svg>
);

export const IconBell = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M4 7a4 4 0 0 1 8 0c0 3 1 4 1 4H3s1-1 1-4Z" />
    <path d="M6.5 13.5a1.6 1.6 0 0 0 3 0" />
  </svg>
);

export const IconChevron = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M6 4l4 4-4 4" />
  </svg>
);

export const IconArrow = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M3 8h10M9 4l4 4-4 4" />
  </svg>
);

export const IconClose = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </svg>
);

export const IconSun = (p: Props) => (
  <svg {...base} {...p}>
    <circle cx="8" cy="8" r="3" />
    <path d="M8 1v1.5M8 13.5V15M15 8h-1.5M2.5 8H1M12.9 3.1l-1 1M4.1 11.9l-1 1M12.9 12.9l-1-1M4.1 4.1l-1-1" />
  </svg>
);

export const IconMoon = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5Z" />
  </svg>
);

export const IconDataset = (p: Props) => (
  <svg {...base} {...p}>
    <ellipse cx="8" cy="3.75" rx="5.5" ry="2.25" />
    <path d="M2.5 3.75v8.5c0 1.24 2.46 2.25 5.5 2.25s5.5-1.01 5.5-2.25v-8.5" />
    <path d="M2.5 8c0 1.24 2.46 2.25 5.5 2.25s5.5-1.01 5.5-2.25" />
  </svg>
);

export const IconReview = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M2 3.5h12v7.5H8.5L5.5 14v-3H2z" />
    <path d="M5.5 7.25l1.75 1.75 3.25-3.25" />
  </svg>
);

export const IconExpert = (p: Props) => (
  <svg {...base} {...p}>
    <circle cx="8" cy="5" r="2.75" />
    <path d="M2.75 14a5.25 5.25 0 0 1 10.5 0" />
    <path d="M11.5 1.5l.6 1.3 1.4.2-1 1 .24 1.4-1.24-.66-1.24.66.24-1.4-1-1 1.4-.2z" />
  </svg>
);

/** Target: crosshairs on a point, for where the model is weak. */
export const IconTarget = (p: Props) => (
  <svg {...base} {...p}>
    <circle cx="8" cy="8" r="5.5" />
    <circle cx="8" cy="8" r="2" />
    <path d="M8 1v2.5M8 12.5V15M1 8h2.5M12.5 8H15" />
  </svg>
);

/** Capture: a pen drawing a line of reasoning. */
export const IconCapture = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M10.5 2.5l3 3-7.5 7.5H3v-3z" />
    <path d="M9 4l3 3" />
    <path d="M9.5 14h4.5" />
  </svg>
);

/** Deliver: a sealed box. */
export const IconPackage = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M2 5l6-3 6 3v6.5L8 14.5 2 11.5z" />
    <path d="M2 5l6 3 6-3M8 8v6.5" />
  </svg>
);

export const IconCollapse = (p: Props) => (
  <svg {...base} {...p}>
    <rect x="2" y="2.5" width="12" height="11" />
    <path d="M6.25 2.5v11" />
    <path d="M11.5 6.5L9.5 8l2 1.5" />
  </svg>
);

export const IconExpand = (p: Props) => (
  <svg {...base} {...p}>
    <rect x="2" y="2.5" width="12" height="11" />
    <path d="M6.25 2.5v11" />
    <path d="M9.5 6.5L11.5 8l-2 1.5" />
  </svg>
);

export const IconCompass = (p: Props) => (
  <svg {...base} {...p}>
    <circle cx="8" cy="8" r="6" />
    <path d="M10.5 5.5 9.2 9.2 5.5 10.5 6.8 6.8z" />
  </svg>
);

export const IconAdmin = (p: Props) => (
  <svg {...base} {...p}>
    <circle cx="6" cy="5.5" r="2.25" />
    <path d="M1.75 13a4.25 4.25 0 0 1 8.5 0" />
    <path d="M11 8.5h3.5M11 11h3.5M11 5.5h3.5" />
  </svg>
);

/* Status glyphs.
 *
 * These carry a colour where the rest of the set does not: an error is red, a
 * caution is amber, a note is quiet. The glyph says what kind of thing it is
 * and the colour says how much it matters, which is a job a rule drawn down
 * the side of a block cannot do -- a rule can only be darker or lighter. */

export const IconError = (p: Props) => (
  <svg {...base} {...p}>
    <circle cx="8" cy="8" r="6" />
    <path d="M8 5v4" />
    <path d="M8 11.25v.01" />
  </svg>
);

export const IconWarning = (p: Props) => (
  <svg {...base} {...p}>
    <path d="M8 2.25 14.5 13.5h-13L8 2.25Z" />
    <path d="M8 6.5v3" />
    <path d="M8 11.5v.01" />
  </svg>
);

export const IconNote = (p: Props) => (
  <svg {...base} {...p}>
    <circle cx="8" cy="8" r="6" />
    <path d="M8 7.5v3.5" />
    <path d="M8 4.75v.01" />
  </svg>
);
