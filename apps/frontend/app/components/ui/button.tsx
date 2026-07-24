import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'default' | 'sm' | 'lg';
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = '', variant = 'primary', size = 'default', children, ...props }, ref) => {
    
    // Using the globals.css classes for primary/secondary, and fallback to Tailwind for ghost/sm
    let variantClass = '';
    if (variant === 'primary') variantClass = 'button-primary';
    else if (variant === 'secondary') variantClass = 'button-secondary';
    else if (variant === 'ghost') variantClass = 'bg-transparent text-slate-500 hover:bg-slate-100 hover:text-slate-900 border-transparent';

    let sizeClass = '';
    if (size === 'sm') sizeClass = '!min-h-10 !px-4 !text-xs';
    else if (size === 'lg') sizeClass = '!min-h-14 !px-8 !text-base';

    return (
      <button
        ref={ref}
        className={`button ${variantClass} ${sizeClass} ${className}`}
        {...props}
      >
        {children}
      </button>
    );
  }
);
Button.displayName = 'Button';
