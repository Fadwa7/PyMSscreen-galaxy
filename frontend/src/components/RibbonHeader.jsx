/**
 * @file RibbonHeader.jsx
 * @summary Decorative SVG ribbon header inspired by mass spectrometry peak patterns.
 *
 * @description
 * This component renders a responsive SVG header composed of stylized vertical
 * "peaks" resembling mass spectra. The header is purely decorative and does not
 * encode or display analytical data.
 *
 * The appearance adapts to light and dark themes via a background gradient.
 * Color-coded peak groups are used to evoke MS1/MS2 visual motifs.
 */

import React from "react";

/**
 * RibbonHeader component.
 *
 * @component
 * @param {Object} props
 * @param {boolean} props.isDark
 * If true, renders a dark gradient background; otherwise uses a light gradient.
 *
 * @returns {JSX.Element}
 * Responsive SVG ribbon header with stylized spectral peaks.
 *
 * @remarks
 * - This component is purely presentational (no state, no side effects).
 * - Peak positions and colors are static and chosen for visual balance.
 * - SVG scales horizontally to fill the available container width.
 */


const RibbonHeader = ({ isDark }) => {
  return (
    <svg
      width="100%"
      height="260"
      viewBox="0 0 1600 260"
      preserveAspectRatio="xMidYMid meet"
      style={{
        display: "block",
        background: isDark
          ? "linear-gradient(#0b1220, #0f172a)"
          : "linear-gradient(#e8f4ff, #dff5ff)",
      }}
    >
      <g strokeWidth="14" strokeLinecap="round">
        {/* LEFT GROUP */}
        <g className="group-left peak-glow">
          <line className="ms-peak" x1="300" y1="220" x2="300" y2="130" stroke="#ff5252" />
          <line className="ms-peak" x1="340" y1="220" x2="340" y2="75"  stroke="#d1d5db" />
          <line className="ms-peak" x1="380" y1="220" x2="380" y2="160" stroke="#ff5252" />
          <line className="ms-peak" x1="420" y1="220" x2="420" y2="100" stroke="#ff5252" />
        </g>

        {/* CENTER GROUP */}
        <g className="group-center peak-glow">
          <line className="ms-peak" x1="750" y1="220" x2="750" y2="60"  stroke="#4f8ac9" />
          <line className="ms-peak" x1="790" y1="220" x2="790" y2="150" stroke="#d1d5db" />
          <line className="ms-peak" x1="830" y1="220" x2="830" y2="95"  stroke="#d1d5db" />
          <line className="ms-peak" x1="870" y1="220" x2="870" y2="145" stroke="#4f8ac9" />
        </g>

        {/* RIGHT GROUP */}
        <g className="group-right peak-glow">
          <line className="ms-peak" x1="1200" y1="220" x2="1200" y2="110" stroke="#ff5252" />
          <line className="ms-peak" x1="1240" y1="220" x2="1240" y2="150" stroke="#d1d5db" />
          <line className="ms-peak" x1="1280" y1="220" x2="1280" y2="85"  stroke="#ff5252" />
          <line className="ms-peak" x1="1320" y1="220" x2="1320" y2="55"  stroke="#ff5252" />
        </g>
      </g>
    </svg>
  );
};

export default RibbonHeader;
