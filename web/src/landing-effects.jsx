import { useEffect, useRef } from 'react';

// A small DOM grid keeps the cursor interaction lightweight and easy to restyle.
const gridTiles = Array.from({ length: 112 }, (_, index) => ({
  row: Math.floor(index / 14),
  column: index % 14,
}));

export function GridRise({ children, className = '' }) {
  const rootRef = useRef(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;

    // Track the pointer in the hero and lift nearby tiles; a short ripple trails it.
    let pointer = null;
    let frame = 0;
    let isLeaving = false;
    let leaveStarted = 0;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const tiles = [...root.querySelectorAll('.grid-rise-tile')];

    const draw = now => {
      frame = 0;
      const bounds = root.getBoundingClientRect();
      const elapsed = now / 1000;
      let hasLift = false;

      tiles.forEach(tile => {
        const column = Number(tile.dataset.column);
        const row = Number(tile.dataset.row);
        const x = ((column + 0.5) / 14) * bounds.width;
        const y = ((row + 0.5) / 8) * bounds.height;
        const dx = pointer ? (x - pointer.x) / bounds.width : 2;
        const dy = pointer ? (y - pointer.y) / bounds.height : 2;
        const distance = Math.hypot(dx, dy);
        const influence = pointer ? Math.max(0, 1 - distance / 0.42) : 0;
        const fade = isLeaving ? Math.max(0, 1 - (now - leaveStarted) / 260) : 1;
        const lift = influence * fade;
        const ripple = reducedMotion ? 0 : Math.sin(distance * 38 - elapsed * 5) * lift * 2.1;

        tile.style.transform = `translate3d(0, ${-(lift * 19 + ripple)}px, 0) scale(${1 + lift * 0.09})`;
        tile.style.opacity = `${0.26 + lift * 0.56}`;
        tile.style.backgroundColor = lift > 0.03
          ? `rgba(141, 205, 163, ${0.12 + lift * 0.52})`
          : '';
        if (lift > 0.005) hasLift = true;
      });

      if (pointer && hasLift && !isLeaving) frame = requestAnimationFrame(draw);
      if (isLeaving && now - leaveStarted < 270) frame = requestAnimationFrame(draw);
      else if (isLeaving) {
        isLeaving = false;
        pointer = null;
        tiles.forEach(tile => {
          tile.style.transform = '';
          tile.style.opacity = '';
          tile.style.backgroundColor = '';
        });
      }
    };

    const onPointerMove = event => {
      const bounds = root.getBoundingClientRect();
      pointer = { x: event.clientX - bounds.left, y: event.clientY - bounds.top };
      isLeaving = false;
      if (!frame) frame = requestAnimationFrame(draw);
    };
    const onPointerLeave = () => {
      if (!pointer) return;
      isLeaving = true;
      leaveStarted = performance.now();
      if (!frame) frame = requestAnimationFrame(draw);
    };

    root.addEventListener('pointermove', onPointerMove, { passive: true });
    root.addEventListener('pointerleave', onPointerLeave);
    return () => {
      root.removeEventListener('pointermove', onPointerMove);
      root.removeEventListener('pointerleave', onPointerLeave);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div ref={rootRef} className={`grid-rise ${className}`}>
      <div className="grid-rise-field" aria-hidden="true">
        {gridTiles.map(({ row, column }) => (
          <span
            className="grid-rise-tile"
            data-row={row}
            data-column={column}
            key={`${row}-${column}`}
          />
        ))}
      </div>
      <div className="grid-rise-content">{children}</div>
    </div>
  );
}

export function LuminousType({ children, className = '' }) {
  // Let the spotlight drift by itself, then steer it directly when the user points.
  function moveSpotlight(event) {
    const bounds = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty('--spot-x', `${((event.clientX - bounds.left) / bounds.width) * 100}%`);
    event.currentTarget.style.setProperty('--spot-y', `${((event.clientY - bounds.top) / bounds.height) * 100}%`);
    event.currentTarget.classList.add('is-steered');
  }

  return (
    <span className={`luminous-type ${className}`} onPointerMove={moveSpotlight}>
      <span className="luminous-dim" aria-hidden="true">{children}</span>
      <span className="luminous-light" aria-hidden="true">{children}</span>
      <span className="visually-hidden">{children}</span>
    </span>
  );
}

export function MeshLettering({ text, className = '' }) {
  return (
    <svg className={`mesh-lettering ${className}`} viewBox="0 0 600 76" role="img" aria-label={text}>
      <defs>
        <filter id="mesh-lettering-warp" x="-10%" y="-35%" width="120%" height="170%">
          <feTurbulence type="fractalNoise" baseFrequency="0.012 0.035" numOctaves="2" seed="7" result="silk">
            <animate attributeName="baseFrequency" values="0.012 0.035;0.018 0.06;0.012 0.035" dur="8s" repeatCount="indefinite" />
          </feTurbulence>
          <feDisplacementMap in="SourceGraphic" in2="silk" scale="6" xChannelSelector="R" yChannelSelector="G">
            <animate attributeName="scale" values="4;9;4" dur="7s" repeatCount="indefinite" />
          </feDisplacementMap>
        </filter>
      </defs>
      <text x="300" y="56" textAnchor="middle" filter="url(#mesh-lettering-warp)">{text}</text>
    </svg>
  );
}
