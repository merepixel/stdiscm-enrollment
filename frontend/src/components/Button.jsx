import React from 'react';
import { Link } from 'react-router-dom';
import clsx from 'clsx';

const base = 'inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-offset-2';
const variants = {
  primary: 'bg-accent text-white hover:bg-blue-600 focus:ring-accent',
  ghost: 'bg-transparent text-gray-700 hover:bg-gray-100 focus:ring-gray-300',
};

export default function Button({ as, children, variant = 'primary', className = '', ...props }) {
  const Comp = as || 'button';
  return (
    <Comp
      className={clsx(base, variants[variant] || variants.primary, className)}
      {...props}
    >
      {children}
    </Comp>
  );
}
