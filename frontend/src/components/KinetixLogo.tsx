import { useId } from 'react';
import type { SVGProps } from 'react';

type KinetixLogoProps = SVGProps<SVGSVGElement> & { title?: string };

export function KinetixLogo({ title = 'KINETIX AI', ...props }: KinetixLogoProps) {
  const titleId = useId();

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 80 88"
      fill="none"
      role="img"
      aria-labelledby={titleId}
      {...props}
    >
      <title id={titleId}>{title}</title>
      <path d="M40 4 73 23v40L40 84 7 63V23L40 4Z" fill="currentColor" fillOpacity=".06" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" />
      <path d="M16 43h14l6-13 9 27 7-14h12" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <g stroke="currentColor" strokeWidth="3" strokeLinecap="round">
        <path d="M19 65h42M19 59v12M24 57v16M56 57v16M61 59v12" />
      </g>
    </svg>
  );
}
