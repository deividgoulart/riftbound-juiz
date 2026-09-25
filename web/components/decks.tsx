"use client";

import Link from "next/link";
import { useState } from "react";
import { CheckCircle2, SlidersHorizontal } from "lucide-react";
import { dataCurta, reais, type Ordem, type ResumoDoDeck } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { ImagemDaCarta } from "./carta";
import { Alternador, Folha, PontosDosDominios, Progresso, Segmentos } from "./ui";

export function textoDoCusto(d: ResumoDoDeck): string | null {
  if (d.cartas_faltando === 0) return null;
  if (d.custo === null) return "sem preço";
  return `falta ≈ ${reais(d.custo)}${d.sem_preco ? " + cartas sem preço" : ""}`;
}

export function CartaoDoDeck({ d }: { d: ResumoDoDeck }) {
  const custo = textoDoCusto(d);
  const doMeta = d.origem !== "manual";
  return (
    <Link
      href={`/decks/${d.id}`}
      className="group flex gap-3 rounded-2xl border border-linha bg-superficie p-3 transition hover:border-ouro/50 hover:bg-superficie-2/60"
    >
      <ImagemDaCarta nome={d.lenda?.rotulo ?? d.nome} imagem={d.lenda?.imagem} dominios={d.lenda?.dominios} className="w-16 shrink-0 sm:w-20" ampliavel={false} />
      <div className="flex min-w-0 flex-1 flex-col justify-between gap-2">
        <div>
          <div className="flex items-start justify-between gap-2">
            <h3 className="line-clamp-2 font-semibold leading-snug">{doMeta && d.lenda ? d.lenda.rotulo : d.nome}</h3>
            {d.lenda && <PontosDosDominios dominios={d.lenda.dominios} />}
          </div>
          <p className="mt-0.5 truncate text-xs text-apagado">
            {doMeta
              ? `${d.colocacao}º · ${d.torneio ?? "Torneio"}${d.data ? ` · ${dataCurta(d.data)}` : ""}`
              : d.lenda
                ? d.lenda.rotulo
                : "Sem lenda"}
          </p>
        </div>
        <div className="space-y-1.5">
          <Progresso porcentagem={d.porcentagem} />
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="text-apagado">
              <strong className="text-texto">{Math.round(d.porcentagem)}%</strong> · {d.tenho}/{d.total} cópias
            </span>
            {d.cartas_faltando === 0 ? (
              <span className="flex items-center gap-1 text-ok">
                <CheckCircle2 size={13} /> completo
              </span>
            ) : (
              <span className="text-ouro">{custo}</span>
            )}
          </div>
        </div>
      </div>
    </Link>
  );
}

/** Ordem da lista e a conta da conclusão (runas básicas, sideboard), guardadas no navegador. */
export function AjustesDosDecks({ temPrecos }: { temPrecos: boolean }) {
  const { prefs, setPrefs } = useSessao();
  const [aberto, setAberto] = useState(false);
  return (
    <>
      <div className="mb-4 flex items-center gap-2">
        <div className="flex-1">
          <Segmentos<Ordem>
            valor={temPrecos ? prefs.ordem : "faltando"}
            onChange={(ordem) => setPrefs({ ordem })}
            opcoes={[
              { valor: "barato", rotulo: "Mais barato", desligado: !temPrecos },
              { valor: "faltando", rotulo: "Menos faltando" },
            ]}
          />
        </div>
        <button
          type="button"
          onClick={() => setAberto(true)}
          aria-label="Ajustes da conta"
          className="grid h-10 w-10 place-items-center rounded-xl border border-linha bg-superficie text-apagado hover:text-texto"
        >
          <SlidersHorizontal size={18} />
        </button>
      </div>
      <Folha aberta={aberto} onFechar={() => setAberto(false)} titulo="Conta da conclusão">
        <div className="divide-y divide-linha">
          <Alternador ligado={prefs.runas} onChange={(runas) => setPrefs({ runas })}>
            Conto com as runas básicas
            <span className="block text-xs text-apagado">Quase todo jogador tem as runas de um deck inicial.</span>
          </Alternador>
          <Alternador ligado={prefs.sideboard} onChange={(sideboard) => setPrefs({ sideboard })}>
            Incluir o sideboard
            <span className="block text-xs text-apagado">O sideboard não é necessário pra jogar.</span>
          </Alternador>
        </div>
        <p className="mt-4 text-xs leading-relaxed text-apagado">
          &quot;Mais barato&quot; ordena pelo custo estimado do que falta (TCGplayer convertido pra reais). &quot;Menos faltando&quot;, pelo número de cópias
          que ainda faltam.
        </p>
      </Folha>
    </>
  );
}

export function parametrosDaConta(prefs: { runas: boolean; sideboard: boolean }) {
  return `runas=${prefs.runas}&sideboard=${prefs.sideboard}`;
}
