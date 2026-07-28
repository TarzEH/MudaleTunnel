// Small inline SVG icon set. No external icon package per design spec.
import type { ReactNode, SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement>;

function base(children: ReactNode, props: IconProps) {
  return (
    <svg
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export function IconPlay(props: IconProps) {
  return base(<path d="M4 2.5v11l9-5.5-9-5.5z" fill="currentColor" stroke="none" />, props);
}

export function IconStop(props: IconProps) {
  return base(<rect x="3.5" y="3.5" width="9" height="9" rx="1" fill="currentColor" stroke="none" />, props);
}

export function IconTrash(props: IconProps) {
  return base(
    <>
      <path d="M2.5 4.5h11" />
      <path d="M5.5 4.5V3a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v1.5" />
      <path d="M6 7.5v4M10 7.5v4" />
      <path d="M3.5 4.5l.7 8a1 1 0 0 0 1 .9h5.6a1 1 0 0 0 1-.9l.7-8" />
    </>,
    props
  );
}

export function IconPlus(props: IconProps) {
  return base(
    <>
      <path d="M8 3v10M3 8h10" />
    </>,
    props
  );
}

export function IconSearch(props: IconProps) {
  return base(
    <>
      <circle cx="7" cy="7" r="4.5" />
      <path d="M13.5 13.5L10.5 10.5" />
    </>,
    props
  );
}

export function IconX(props: IconProps) {
  return base(
    <>
      <path d="M4 4l8 8M12 4l-8 8" />
    </>,
    props
  );
}

export function IconChevronDown(props: IconProps) {
  return base(<path d="M4 6l4 4 4-4" />, props);
}

export function IconChevronRight(props: IconProps) {
  return base(<path d="M6 4l4 4-4 4" />, props);
}

export function IconLogs(props: IconProps) {
  return base(
    <>
      <path d="M2.5 4h11M2.5 8h11M2.5 12h7" />
    </>,
    props
  );
}

export function IconSun(props: IconProps) {
  return base(
    <>
      <circle cx="8" cy="8" r="3" />
      <path d="M8 1.5v1.5M8 13v1.5M2.6 2.6l1 1M12.4 12.4l1 1M1.5 8h1.5M13 8h1.5M2.6 13.4l1-1M12.4 3.6l1-1" />
    </>,
    props
  );
}

export function IconMoon(props: IconProps) {
  return base(<path d="M13.5 9.5A5.5 5.5 0 1 1 6.5 2.5a4.5 4.5 0 0 0 7 7z" />, props);
}

export function IconArrowRight(props: IconProps) {
  return base(<path d="M3 8h10M9 4l4 4-4 4" />, props);
}

export function IconServer(props: IconProps) {
  return base(
    <>
      <rect x="2.5" y="2.5" width="11" height="4.5" rx="1" />
      <rect x="2.5" y="9" width="11" height="4.5" rx="1" />
      <path d="M5 4.75h.01M5 11.25h.01" />
    </>,
    props
  );
}

export function IconTunnel(props: IconProps) {
  return base(
    <>
      <path d="M2 12V8a6 6 0 0 1 12 0v4" />
      <path d="M2 12h3M11 12h3" />
    </>,
    props
  );
}

export function IconMap(props: IconProps) {
  return base(
    <>
      <path d="M5.5 3L2 4.5v9L5.5 12M5.5 3l5 1.5M5.5 3v9M10.5 4.5L14 3v9l-3.5 1.5M10.5 4.5v9M10.5 13.5L5.5 12" />
    </>,
    props
  );
}

export function IconRadar(props: IconProps) {
  return base(
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 8L12 5" />
      <circle cx="8" cy="8" r="1" fill="currentColor" stroke="none" />
    </>,
    props
  );
}

export function IconShield(props: IconProps) {
  return base(<path d="M8 1.5l5 2v4.2c0 3.4-2.2 5.9-5 6.8-2.8-.9-5-3.4-5-6.8V3.5l5-2z" />, props);
}

export function IconBriefcase(props: IconProps) {
  return base(
    <>
      <rect x="2" y="5" width="12" height="8" rx="1.2" />
      <path d="M6 5V3.8A1.3 1.3 0 0 1 7.3 2.5h1.4A1.3 1.3 0 0 1 10 3.8V5" />
    </>,
    props
  );
}

export function IconSettings(props: IconProps) {
  return base(
    <>
      <circle cx="8" cy="8" r="2.2" />
      <path d="M8 1.8v1.4M8 12.8v1.4M14.2 8h-1.4M3.2 8H1.8M12.2 3.8l-1 1M4.8 11.2l-1 1M12.2 12.2l-1-1M4.8 4.8l-1-1" />
    </>,
    props
  );
}

export function IconEdit(props: IconProps) {
  return base(
    <>
      <path d="M11 2.5l2.5 2.5-8 8-3 .5.5-3 8-8z" />
      <path d="M9.5 4l2.5 2.5" />
    </>,
    props
  );
}

export function IconCommand(props: IconProps) {
  return base(
    <path d="M6 4.5A1.5 1.5 0 1 0 4.5 6H6V4.5zM6 6H4.5A1.5 1.5 0 1 0 6 7.5V6zM10 4.5A1.5 1.5 0 1 1 11.5 6H10V4.5zM10 6h1.5A1.5 1.5 0 1 1 10 7.5V6zM6 10H4.5A1.5 1.5 0 1 0 6 11.5V10zM6 10V8.5H4.5M10 10h1.5A1.5 1.5 0 1 1 10 11.5V10zM10 10V8.5h1.5M6 8.5h4" />,
    props
  );
}
