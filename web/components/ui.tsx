"use client";

// Peças visuais usadas em todas as telas.

import { useEffect } from "react";
import { X } from "lucide-react";

const CORES_DOS_DOMINIOS: Record<string, string> = {
  Fury: "var(--color-fury)",
  Calm: "var(--color-calm)",
  Mind: "var(--color-mind)",
  Body: "var(--color-body)",
  Chaos: "var(--color-chaos)",
  Order: "var(--color-order)",
};

export const NOMES_DOS_DOMINIOS: Record<string, string> = {
  Fury: "Fúria",
  Calm: "Calma",
  Mind: "Mente",
  Body: "Corpo",
  Chaos: "Caos",
  Order: "Ordem",
};

export function corDoDominio(dominio: string | undefined): string {
  return (dominio && CORES_DOS_DOMINIOS[dominio]) || "var(--color-linha)";
}

export function juntar(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

export function Cabecalho({ titulo, subtitulo, acao }: { titulo: string; subtitulo?: React.ReactNode; acao?: React.ReactNode }) {
  return (
    <header className="mb-5 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="font-titulo text-2xl font-bold tracking-wide text-ouro md:text-3xl">{titulo}</h1>
        {subtitulo && <p className="mt-1 text-sm text-apagado">{subtitulo}</p>}
      </div>
      {acao}
    </header>
  );
}

export function PontosDosDominios({ dominios }: { dominios: string[] }) {
  return (
    <span className="inline-flex gap-1">
      {dominios.map((d) => (
        <span key={d} title={NOMES_DOS_DOMINIOS[d] ?? d} className="h-2.5 w-2.5 rounded-full" style={{ background: corDoDominio(d) }} />
      ))}
    </span>
  );
}

export function Progresso({ porcentagem }: { porcentagem: number }) {
  const completo = porcentagem >= 100;
  return (
    <div className="h-2 overflow-hidden rounded-full bg-superficie-2" role="progressbar" aria-valuenow={Math.round(porcentagem)}>
      <div
        className={juntar("h-full rounded-full transition-all", completo ? "bg-ok" : "bg-gradient-to-r from-ouro-escuro to-ouro")}
        style={{ width: `${Math.min(100, porcentagem)}%` }}
      />
    </div>
  );
}

export function Chip({
  ativo,
  onClick,
  className = "",
  children,
}: {
  ativo?: boolean;
  onClick?: () => void;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={juntar(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition",
        ativo ? "border-ouro bg-ouro/15 text-ouro" : "border-linha bg-superficie text-apagado hover:text-texto",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Segmentos<T extends string>({
  opcoes,
  valor,
  onChange,
}: {
  opcoes: { valor: T; rotulo: string; desligado?: boolean }[];
  valor: T;
  onChange: (valor: T) => void;
}) {
  return (
    <div className="flex rounded-xl border border-linha bg-superficie p-1">
      {opcoes.map((o) => (
        <button
          key={o.valor}
          type="button"
          disabled={o.desligado}
          onClick={() => onChange(o.valor)}
          className={juntar(
            "flex-1 rounded-lg px-3 py-1.5 text-sm transition disabled:opacity-40",
            valor === o.valor ? "bg-superficie-2 font-semibold text-texto shadow" : "text-apagado hover:text-texto",
          )}
        >
          {o.rotulo}
        </button>
      ))}
    </div>
  );
}

export function Alternador({ ligado, onChange, children }: { ligado: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3 py-2 text-sm">
      <span>{children}</span>
      <button
        type="button"
        role="switch"
        aria-checked={ligado}
        onClick={() => onChange(!ligado)}
        className={juntar("relative h-6 w-11 shrink-0 rounded-full transition", ligado ? "bg-ouro" : "bg-linha")}
      >
        <span className={juntar("absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all", ligado ? "left-[22px]" : "left-0.5")} />
      </button>
    </label>
  );
}

export function Botao({
  variante = "primario",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variante?: "primario" | "secundario" | "perigo" }) {
  const estilos = {
    primario: "bg-ouro text-fundo hover:bg-[#e2c06f] font-semibold",
    secundario: "border border-linha bg-superficie text-texto hover:bg-superficie-2",
    perigo: "border border-erro/50 text-erro hover:bg-erro/10",
  }[variante];
  return (
    <button
      {...props}
      className={juntar(
        "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-50",
        estilos,
        className,
      )}
    />
  );
}

export function Aviso({ tipo = "info", children }: { tipo?: "info" | "erro" | "ok" | "alerta"; children: React.ReactNode }) {
  const estilos = {
    info: "border-azul/30 bg-azul/10 text-texto",
    erro: "border-erro/40 bg-erro/10 text-texto",
    ok: "border-ok/40 bg-ok/10 text-texto",
    alerta: "border-ouro/40 bg-ouro/10 text-texto",
  }[tipo];
  return <div className={juntar("rounded-xl border px-4 py-3 text-sm leading-relaxed", estilos)}>{children}</div>;
}

export function Carregando({ texto = "Carregando..." }: { texto?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-sm text-apagado">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-ouro border-t-transparent" />
      {texto}
    </div>
  );
}

export function Cartao({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return <div className={juntar("rounded-2xl border border-linha bg-superficie", className)}>{children}</div>;
}

/** Janela que sobe de baixo no celular e fica no meio da tela no computador. */
export function Folha({ aberta, onFechar, titulo, children }: { aberta: boolean; onFechar: () => void; titulo: string; children: React.ReactNode }) {
  useEffect(() => {
    if (!aberta) return;
    const fechar = (e: KeyboardEvent) => e.key === "Escape" && onFechar();
    window.addEventListener("keydown", fechar);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", fechar);
      document.body.style.overflow = "";
    };
  }, [aberta, onFechar]);
  if (!aberta) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center md:items-center" role="dialog" aria-modal aria-label={titulo}>
      <button type="button" aria-label="Fechar" className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onFechar} />
      <div className="relative max-h-[90dvh] w-full overflow-y-auto rounded-t-3xl border border-linha bg-superficie p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] md:max-w-lg md:rounded-3xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-titulo text-lg font-bold text-ouro">{titulo}</h2>
          <button type="button" onClick={onFechar} aria-label="Fechar" className="rounded-full p-1.5 text-apagado hover:bg-superficie-2 hover:text-texto">
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
