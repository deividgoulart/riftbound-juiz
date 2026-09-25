"use client";

import Link from "next/link";
import { CheckCircle2, Gem, Layers } from "lucide-react";
import { dataCurta, reais, type Ordem, type ResumoDoDeck } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { ImagemDaCarta } from "./carta";
import { Chip, PontosDosDominios, Progresso, Segmentos } from "./ui";

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

/** Ordem da lista e a conta da conclusão (runas básicas, sideboard), à vista e guardadas no navegador. */
export function AjustesDosDecks({ temPrecos }: { temPrecos: boolean }) {
  const { prefs, setPrefs } = useSessao();
  return (
    <div className="mb-4 space-y-2">
      <Segmentos<Ordem>
        valor={temPrecos ? prefs.ordem : "faltando"}
        onChange={(ordem) => setPrefs({ ordem })}
        opcoes={[
          { valor: "barato", rotulo: "Mais barato", desligado: !temPrecos },
          { valor: "faltando", rotulo: "Menos faltando" },
        ]}
      />
      <OpcoesDaConta />
    </div>
  );
}

/** O que entra na conta do "quanto falta": runas básicas e sideboard. À vista na lista e no detalhe do deck. */
export function OpcoesDaConta() {
  const { prefs, setPrefs } = useSessao();
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Chip ativo={prefs.runas} onClick={() => setPrefs({ runas: !prefs.runas })}>
          <Gem size={13} /> {prefs.runas ? "Runas básicas: conto como minhas" : "Runas: só as da coleção"}
        </Chip>
        <Chip ativo={prefs.sideboard} onClick={() => setPrefs({ sideboard: !prefs.sideboard })}>
          <Layers size={13} /> {prefs.sideboard ? "Sideboard: conta no que falta" : "Sideboard: não conta"}
        </Chip>
      </div>
      {prefs.runas && (
        <p className="text-xs text-apagado">As runas básicas estão contando como suas mesmo sem estarem na coleção. Toque acima pra contar só as que você tem.</p>
      )}
    </div>
  );
}

export function parametrosDaConta(prefs: { runas: boolean; sideboard: boolean }) {
  return `runas=${prefs.runas}&sideboard=${prefs.sideboard}`;
}
