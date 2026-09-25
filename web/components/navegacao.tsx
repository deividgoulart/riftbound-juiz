"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Layers, Library, Lock, LockOpen, Scale, Trophy } from "lucide-react";
import { useSessao } from "@/lib/sessao";
import { juntar } from "./ui";

const ABAS = [
  { href: "/", rotulo: "Juiz", icone: Scale },
  { href: "/colecao", rotulo: "Coleção", icone: Library },
  { href: "/decks", rotulo: "Decks", icone: Layers },
  { href: "/meta", rotulo: "Meta", icone: Trophy },
];

function ativa(caminho: string, href: string) {
  return href === "/" ? caminho === "/" : caminho.startsWith(href);
}

function BotaoDaSenha() {
  const { info, sair, setPedirSenha } = useSessao();
  if (!info?.publico) return null; // rodando no computador: não tem senha
  return info.dono ? (
    <button type="button" onClick={sair} title="Sair do modo dono" className="rounded-full p-2 text-ok hover:bg-superficie-2">
      <LockOpen size={18} />
    </button>
  ) : (
    <button type="button" onClick={() => setPedirSenha(true)} title="Entrar com a senha" className="rounded-full p-2 text-apagado hover:bg-superficie-2 hover:text-texto">
      <Lock size={18} />
    </button>
  );
}

export function Topo() {
  const caminho = usePathname();
  return (
    <header className="sticky top-0 z-40 border-b border-linha/70 bg-fundo/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg border border-ouro/50 bg-ouro/10 text-ouro">
            <Scale size={16} />
          </span>
          <span className="font-titulo text-base font-bold tracking-wider text-ouro">Juiz Riftbound</span>
        </Link>
        <nav className="hidden items-center gap-1 md:flex">
          {ABAS.map(({ href, rotulo, icone: Icone }) => (
            <Link
              key={href}
              href={href}
              className={juntar(
                "flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition",
                ativa(caminho, href) ? "bg-superficie-2 text-ouro" : "text-apagado hover:text-texto",
              )}
            >
              <Icone size={16} />
              {rotulo}
            </Link>
          ))}
        </nav>
        <BotaoDaSenha />
      </div>
    </header>
  );
}

/** Barra de navegação de baixo, só no celular. */
export function BarraDeBaixo() {
  const caminho = usePathname();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-linha bg-superficie/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
      <div className="grid grid-cols-4">
        {ABAS.map(({ href, rotulo, icone: Icone }) => {
          const sim = ativa(caminho, href);
          return (
            <Link key={href} href={href} className={juntar("flex flex-col items-center gap-1 py-2.5 text-[11px]", sim ? "text-ouro" : "text-apagado")}>
              <Icone size={21} strokeWidth={sim ? 2.2 : 1.8} />
              {rotulo}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
