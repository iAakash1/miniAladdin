interface SkeletonProps {
  height?: number | string
  width?: number | string
  radius?: number | string
  style?: React.CSSProperties
}

export default function Skeleton({ height = 16, width = '100%', radius, style }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className="skeleton"
      style={{ height, width, borderRadius: radius, ...style }}
    />
  )
}
