import React from 'react';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'success' | 'warning' | 'destructive' | 'outline';
}

export function Badge({ className = '', variant = 'default', ...props }: BadgeProps) {
  let variantClass = '';
  switch (variant) {
    case 'success':
      variantClass = 'bg-green-100 text-green-700 border-green-200';
      break;
    case 'warning':
      variantClass = 'bg-yellow-100 text-yellow-700 border-yellow-200';
      break;
    case 'destructive':
      variantClass = 'bg-red-100 text-red-700 border-red-200';
      break;
    case 'outline':
      variantClass = 'bg-transparent text-slate-600 border-slate-300';
      break;
    default:
      variantClass = 'bg-blue-100 text-blue-700 border-blue-200';
  }

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${variantClass} ${className}`}
      {...props}
    />
  );
}
