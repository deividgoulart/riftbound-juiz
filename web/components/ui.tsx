"use client";

// Peças visuais usadas em todas as telas.

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
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

/** Imagem deitada (os battlefields vêm na horizontal)? Decide pela própria imagem, quando ela carrega. */
function useDeitada(): [boolean, (e: React.SyntheticEvent<HTMLImageElement>) => void] {
  const [deitada, setDeitada] = useState(false);
  return [deitada, (e) => setDeitada(e.currentTarget.naturalWidth > e.currentTarget.naturalHeight)];
}

/** A carta em tela cheia: toque ou Esc fecham. Battlefields aparecem deitados, do jeito que são. */
function TelaCheia({ nome, imagem, onFechar }: { nome: string; imagem: string; onFechar: () => void }) {
  useEffect(() => {
    const fechar = (e: KeyboardEvent) => e.key === "Escape" && onFechar();
    window.addEventListener("keydown", fechar);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", fechar);
      document.body.style.overflow = "";
    };
  }, [onFechar]);
  return createPortal(
    <div
      role="dialog"
      aria-modal
      aria-label={nome}
      onClick={onFechar}
      className="fixed inset-0 z-[60] flex cursor-zoom-out flex-col items-center justify-center gap-3 bg-black/85 p-4 backdrop-blur-sm"
    >
      <button type="button" onClick={onFechar} aria-label="Fechar" className="absolute right-4 top-4 rounded-full bg-superficie/80 p-2 text-texto">
        <X size={22} />
      </button>
      {/* eslint-disable-next-line @next/next/no-img-element -- imagens do site da Riot */}
      <img src={imagem} alt={nome} className="max-h-[82dvh] max-w-full rounded-2xl object-contain shadow-2xl shadow-black" />
      <p className="text-sm font-semibold text-texto">{nome}</p>
    </div>,
    document.body,
  );
}

/** Arte da carta (galeria oficial). Sem imagem, um cartão com as cores dos domínios e o nome.
    Battlefields (imagem na horizontal) são girados pra caber no espaço de uma carta em pé. Com
    `ampliavel`, passar o mouse destaca a carta e clicar (ou tocar, no celular) abre em tela cheia. */
export function ImagemDaCarta({
  nome,
  imagem,
  dominios = [],
  className = "",
  ampliavel = true,
}: {
  nome: string;
  imagem: string | null | undefined;
  dominios?: string[];
  className?: string;
  ampliavel?: boolean;
}) {
  const [deitada, aoCarregar] = useDeitada();
  const [aberta, setAberta] = useState(false);
  const [a, b] = [corDoDominio(dominios[0]), corDoDominio(dominios[1] ?? dominios[0])];
  const clicavel = ampliavel && !!imagem;
  return (
    <>
      <div
        role={clicavel ? "button" : undefined}
        tabIndex={clicavel ? 0 : undefined}
        aria-label={clicavel ? `Ver ${nome} em tela cheia` : undefined}
        onClick={clicavel ? () => setAberta(true) : undefined}
        onKeyDown={clicavel ? (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setAberta(true)) : undefined}
        className={juntar(
          "relative aspect-[744/1039] overflow-hidden rounded-lg border border-linha bg-superficie-2",
          clicavel &&
            "cursor-zoom-in transition duration-200 hover:z-10 hover:-translate-y-0.5 hover:scale-[1.04] hover:border-ouro/70 hover:shadow-xl hover:shadow-black/50 focus-visible:outline-2 focus-visible:outline-ouro",
          className,
        )}
        style={
          imagem
            ? undefined
            : {
                background: `linear-gradient(160deg, color-mix(in srgb, ${a} 45%, transparent), var(--color-superficie-2) 55%, color-mix(in srgb, ${b} 35%, transparent))`,
              }
        }
      >
        {imagem ? (
          // eslint-disable-next-line @next/next/no-img-element -- imagens do site da Riot, sem otimização da Vercel
          <img
            src={imagem}
            alt={nome}
            loading="lazy"
            onLoad={aoCarregar}
            className={
              deitada
                ? // girada 90°: a largura dela vira a altura do quadro, e a altura, a largura
                  "absolute left-1/2 top-1/2 h-[71.6%] w-[139.65%] max-w-none -translate-x-1/2 -translate-y-1/2 rotate-90 object-cover"
                : "h-full w-full object-cover"
            }
          />
        ) : (
          <div className="flex h-full items-end p-2">
            <span className="line-clamp-3 text-[11px] font-semibold leading-tight text-texto/90">{nome}</span>
          </div>
        )}
      </div>
      {aberta && imagem && <TelaCheia nome={nome} imagem={imagem} onFechar={() => setAberta(false)} />}
    </>
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

export function Chip({ ativo, onClick, children }: { ativo?: boolean; onClick?: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={juntar(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition",
        ativo ? "border-ouro bg-ouro/15 text-ouro" : "border-linha bg-superficie text-apagado hover:text-texto",
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
