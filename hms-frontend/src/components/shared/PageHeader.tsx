import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

interface Props {
  title:       string;
  subtitle?:   string;
  backTo?:     string;
  actions?:    React.ReactNode;
}

export function PageHeader({ title, subtitle, backTo, actions }: Props) {
  const navigate = useNavigate();
  return (
    <div className="flex items-start justify-between">
      <div className="flex items-center gap-3">
        {backTo && (
          <button onClick={() => navigate(backTo)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors flex-shrink-0">
            <ArrowLeft size={18} />
          </button>
        )}
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
          {subtitle && <p className="text-sm text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
