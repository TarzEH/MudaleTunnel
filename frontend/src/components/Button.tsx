import type { ButtonHTMLAttributes } from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: 'bg-accent text-black hover:opacity-90 border border-transparent font-medium',
  secondary:
    'bg-surface hover:bg-surface-2 text-text-primary border border-border-subtle',
  ghost: 'bg-transparent hover:bg-surface-2 text-text-secondary border border-transparent',
  danger: 'bg-transparent hover:bg-error/10 text-error border border-error/30',
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'h-7 px-2.5 text-xs gap-1.5',
  md: 'h-9 px-3.5 text-sm gap-2',
};

export function Button({
  variant = 'secondary',
  size = 'md',
  className = '',
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
      {...rest}
    />
  );
}

export function IconButton({
  className = '',
  'aria-label': ariaLabel,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { 'aria-label': string }) {
  return (
    <button
      aria-label={ariaLabel}
      className={`inline-flex h-7 w-7 items-center justify-center rounded-md border border-transparent text-text-secondary transition-colors hover:border-border-subtle hover:bg-surface-2 hover:text-text-primary ${className}`}
      {...rest}
    />
  );
}
