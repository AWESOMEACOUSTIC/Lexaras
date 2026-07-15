import React from "react";

export function Header() {
  return (
    <div className="mb-8 select-none animate-fade-in-up">
      <div className="flex items-baseline gap-0">
        <span className="text-2xl font-bold tracking-tight text-white">
          ◈ Lex<span className="text-accent">aras</span>
        </span>
      </div>
      <span className="block mt-1.5 text-[0.625rem] font-semibold uppercase tracking-widest text-text-muted">
        research intelligence
      </span>
    </div>
  );
}
