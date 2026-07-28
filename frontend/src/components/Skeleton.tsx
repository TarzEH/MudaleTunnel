interface SkeletonRowsProps {
  rows?: number;
  columns?: number;
}

/** Skeleton loading rows for tables — used instead of spinners per design spec. */
export function SkeletonRows({ rows = 6, columns = 4 }: SkeletonRowsProps) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <tr key={rowIdx} className="border-b border-border-subtle">
          {Array.from({ length: columns }).map((__, colIdx) => (
            <td key={colIdx} className="px-4 py-3">
              <div
                className="h-3.5 animate-pulse rounded-sm bg-surface-2"
                style={{ width: `${55 + ((rowIdx * 13 + colIdx * 27) % 40)}%` }}
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export function SkeletonBlock({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-surface-2 ${className}`} />;
}
