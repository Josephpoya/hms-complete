import React from 'react';
import { Card, CardContent } from '../ui';
import { SearchInput } from '../ui/SearchInput';

interface FilterBarProps {
  search?:       string;
  onSearch?:     (v: string) => void;
  searchPlaceholder?: string;
  children?:     React.ReactNode;
}

export function FilterBar({ search, onSearch, searchPlaceholder, children }: FilterBarProps) {
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-3 py-3">
        {onSearch !== undefined && (
          <SearchInput
            value={search ?? ''}
            onChange={onSearch}
            placeholder={searchPlaceholder}
            className="flex-1 min-w-48"
          />
        )}
        {children}
      </CardContent>
    </Card>
  );
}
