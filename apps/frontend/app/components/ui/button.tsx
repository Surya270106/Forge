import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'destructive';
  size?: 'default' | 'sm' | 'lg';
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = '', variant = 'primary', size = 'default', children, ...props }, ref) => {
    // Base classes
    const baseClasses = "inline-flex items-center justify-center gap-2 font-medium transition-all duration-200 ease-forge focus:outline-none focus:ring-2 focus:ring-blue-500/40 disabled:opacity-50 disabled:pointer-events-none";

    // Variants
    let variantClass = '';
    if (variant === 'primary') variantClass = 'bg-blue-600 text-white hover:bg-blue-700 hover:shadow-md';
    else if (variant === 'secondary') variantClass = 'bg-white/80 border border-slate-200 text-slate-700 hover:bg-white hover:border-slate-300 shadow-sm';
    else if (variant === 'destructive') variantClass = 'bg-red-500 text-white hover:bg-red-600 hover:shadow-md';
    else if (variant === 'ghost') variantClass = 'bg-transparent text-slate-500 hover:bg-slate-100 hover:text-slate-900 border-transparent';

    // Sizes
    let sizeClass = '';
    if (size === 'default') sizeClass = 'h-[42px] px-5 rounded-xl text-sm';
    else if (size === 'sm') sizeClass = 'h-9 px-4 rounded-lg text-xs';
    else if (size === 'lg') sizeClass = 'h-12 px-8 rounded-xl text-base';

    return (
      <button
        ref={ref}
        className={`${baseClasses} ${variantClass} ${sizeClass} ${className}`}
        {...props}
      >
        {children}
      </button>
    );
  }
);
Button.displayName = 'Button';
