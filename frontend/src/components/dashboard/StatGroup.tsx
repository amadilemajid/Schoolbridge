import React from 'react';

interface StatGroupProps {
  children: React.ReactNode;
}

export const StatGroup: React.FC<StatGroupProps> = ({ children }) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {children}
    </div>
  );
};
